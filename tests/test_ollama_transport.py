import json
import os
import threading
import time
import unittest
from unittest.mock import patch
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from ollama_transport import request_completion, request_timeout


class TransportTest(unittest.TestCase):
    def test_timeout_configuration_default_custom_and_invalid(self):
        with patch.dict(os.environ,{},clear=True):
            self.assertEqual(request_timeout(),600)
            os.environ['OLLAMA_TIMEOUT_SECONDS']='1200'
            self.assertEqual(request_timeout(),1200)
            for value in ('no','nan','inf','0','7201','-10'):
                os.environ['OLLAMA_TIMEOUT_SECONDS']=value
                with self.subTest(value=value), self.assertRaises(ValueError):
                    request_completion([],'unused','http://127.0.0.1:1')

    def test_configured_deadline_stops_a_stream_that_keeps_sending(self):
        release=threading.Event()
        class Stream(BaseHTTPRequestHandler):
            def do_POST(self):
                self.rfile.read(int(self.headers['Content-Length']))
                self.send_response(200);self.end_headers()
                while not release.wait(.05):
                    try:
                        self.wfile.write(b'{"message":{"content":"x"},"done":false}\n');self.wfile.flush()
                    except OSError:
                        return
        server=ThreadingHTTPServer(('127.0.0.1',0),Stream)
        worker=threading.Thread(target=server.serve_forever,daemon=True);worker.start()
        started=time.monotonic()
        try:
            with patch.dict(os.environ,{'OLLAMA_TIMEOUT_SECONDS':'1'}), self.assertRaises(TimeoutError):
                request_completion([],'qwen3:4b','http://127.0.0.1:'+str(server.server_port))
            self.assertLess(time.monotonic()-started,4)
        finally:
            release.set();server.shutdown();server.server_close();worker.join()

    def test_stream_joins_chunks_and_rejects_incomplete_response(self):
        state={'complete':True}
        class Stream(BaseHTTPRequestHandler):
            def do_POST(self):
                payload=json.loads(self.rfile.read(int(self.headers['Content-Length'])))
                assert payload['stream'] is True
                self.send_response(200)
                self.end_headers()
                chunks=[{'message':{'thinking':'Do not include','content':'Xin '}},
                        {'message':{'content':'chào'},'done':state['complete']}]
                for item in chunks:
                    self.wfile.write((json.dumps(item)+'\n').encode())
                    self.wfile.flush()
        server=ThreadingHTTPServer(('127.0.0.1',0),Stream)
        worker=threading.Thread(target=server.serve_forever,daemon=True)
        worker.start()
        try:
            base='http://127.0.0.1:'+str(server.server_port)
            self.assertEqual(request_completion([], 'qwen3:4b',base),'Xin chào')
            state['complete']=False
            with self.assertRaises(RuntimeError):
                request_completion([], 'qwen3:4b',base)
        finally:
            server.shutdown();server.server_close();worker.join()
