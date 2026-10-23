"""Real sockets distinguish idle browser connections from stalled requests."""
import http.client
import socket
import threading
import unittest
from unittest.mock import patch

import app


class HTTPIdleTest(unittest.TestCase):
    def setUp(self):
        class ShortTimeoutHandler(app.Handler):
            timeout = .25
        self.handler = ShortTimeoutHandler
        patcher = patch.object(self.handler, 'log_error')
        self.errors = patcher.start()
        self.addCleanup(patcher.stop)
        self.server = app.ThreadingHTTPServer(('127.0.0.1', 0), self.handler)
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
