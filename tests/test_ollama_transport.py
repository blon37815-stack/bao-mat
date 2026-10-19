import json
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from ollama_transport import request_completion


class TransportTest(unittest.TestCase):
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
