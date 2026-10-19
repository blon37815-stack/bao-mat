import json
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import patch
import urllib.request

import app
import runtime_version


class RuntimeVersionTest(unittest.TestCase):
    def test_source_snapshot_does_not_change_when_files_change_after_start(self):
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary)
            for name in ('app.py','index.html','app.js','styles.css','requirements.txt'):
                (root/name).write_text('original',encoding='utf-8')
            with patch.object(runtime_version,'ROOT',root),patch.object(runtime_version.subprocess,'run',side_effect=FileNotFoundError):
                first=runtime_version.startup_info()
                (root/'app.py').write_text('changed',encoding='utf-8')
                second=runtime_version.startup_info()
            self.assertNotEqual(first['source_digest'],second['source_digest'])
            self.assertEqual(first['commit'],'unknown')
            self.assertIsNone(first['dirty_at_start'])

    def test_version_endpoint_returns_startup_snapshot_without_database_access(self):
        server=app.ThreadingHTTPServer(('127.0.0.1',0),app.Handler)
        worker=threading.Thread(target=server.serve_forever,daemon=True);worker.start()
        try:
            with patch.object(app,'connect',side_effect=AssertionError('Version should not need database')):
                with urllib.request.urlopen('http://127.0.0.1:'+str(server.server_port)+'/api/version') as response:
                    info=json.load(response)
            self.assertEqual(info,app.RUNTIME_INFO)
            self.assertEqual(len(info['source_digest']),64)
            self.assertIn('started_at',info)
        finally:
            server.shutdown();server.server_close();worker.join()
