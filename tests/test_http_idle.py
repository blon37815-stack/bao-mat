"""Real sockets distinguish idle browser connections from stalled requests."""
import http.client
import os
import socket
import struct
import threading
import unittest
from unittest.mock import patch

import app


class HTTPIdleTest(unittest.TestCase):
    def setUp(self):
        class ShortTimeoutHandler(app.Handler):
            timeout = .25

            def handle(self):
                self.server.waiting.set()
                super().handle()

        class ObservedServer(app.ThreadingHTTPServer):
            def process_request_thread(self, request, client_address):
                try:
                    super().process_request_thread(request, client_address)
                finally:
                    self.finished.set()
        self.handler = ShortTimeoutHandler
        patcher = patch.object(self.handler, 'log_error')
        self.errors = patcher.start()
        self.addCleanup(patcher.stop)
        self.server = ObservedServer(('127.0.0.1', 0), self.handler)
        self.server.waiting = threading.Event()
        self.server.finished = threading.Event()
        self.worker = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.worker.start()
        self.addCleanup(self.close)

    def close(self):
        self.server.shutdown()
        self.server.server_close()
        self.worker.join()

    def connect(self):
        client = socket.create_connection(('127.0.0.1', self.server.server_port), timeout=3)
        self.addCleanup(client.close)
        return client

    def test_idle_preconnection_closes_without_request_timeout_error(self):
        client = self.connect()
        self.assertEqual(client.recv(1), b'')
        self.errors.assert_not_called()

    def test_browser_reset_of_idle_connection_does_not_escape_request_handler(self):
        # SO_LINGER with zero timeout sends a reset instead of an orderly EOF,
        # as can happen when Chromium discards a connection during navigation.
        with patch.object(self.server, 'handle_error') as uncaught:
            client = self.connect()
            self.assertTrue(self.server.waiting.wait(3))
            linger = struct.pack('hh' if os.name == 'nt' else 'ii', 1, 0)
            client.setsockopt(socket.SOL_SOCKET, socket.SO_LINGER, linger)
            client.close()
            self.assertTrue(self.server.finished.wait(3))
            # finished is signaled after the server's exception handler returns.
            uncaught.assert_not_called()
            self.errors.assert_not_called()

    def test_successful_keepalive_response_then_idle_closes_quietly_and_new_request_works(self):
        client = http.client.HTTPConnection('127.0.0.1', self.server.server_port, timeout=3)
        self.addCleanup(client.close)
        client.request('GET', '/api/session')
        response = client.getresponse()
        response.read()
        self.assertEqual(response.status, 200)
        self.assertFalse(response.will_close)
        self.assertEqual(client.sock.recv(1), b'')
        self.errors.assert_not_called()
        client.close()
        client.request('GET', '/api/session')
        response = client.getresponse()
        response.read()
        self.assertEqual(response.status, 200)

    def test_partial_request_headers_still_log_timeout(self):
        client = self.connect()
        client.sendall(b'GET /api/session HTTP/1.1\r\nHost: ')
        self.assertEqual(client.recv(1), b'')
        self.errors.assert_called_once()
        self.assertIn('Request timed out', self.errors.call_args.args[0])

    def test_partial_request_body_still_logs_timeout(self):
        client = self.connect()
        request = (f'POST /api/queue HTTP/1.1\r\nHost: 127.0.0.1:{self.server.server_port}\r\n'
                   f'Content-Type: application/json\r\nX-CSRF-Token: {app.CSRF_TOKEN}\r\n'
                   'Content-Length: 100\r\n\r\n{"paused":')
        client.sendall(request.encode('ascii'))
        self.assertEqual(client.recv(1), b'')
        self.errors.assert_called_once()
        self.assertIn('Request timed out', self.errors.call_args.args[0])
