import io
import json
from pathlib import Path
import sqlite3
import tempfile
import threading
import unittest
from unittest.mock import patch
import zipfile

import app
from maintenance import backup_database, ollama_health


class MaintenanceTest(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.patch = patch.object(app, 'DB', Path(self.temporary.name)/'live.sqlite3')
        self.patch.start()

    def tearDown(self):
        self.patch.stop()
        self.temporary.cleanup()

    def test_search_paginates_all_history_and_uses_literal_query(self):
        with app.connect() as db:
            db.executemany('INSERT INTO tasks VALUES (?,?,?,?,?,?,?)',
                [(f'task-{index:03}', 'GHI CHÚ' if index % 2 == 0 else 'Other', 'demo',
                  'completed' if index % 2 == 0 else 'failed', '', '{}', 'now') for index in range(110)])
        first = app.list_tasks()
        self.assertEqual(len(first['tasks']), 50)
        self.assertEqual(first['total'], 110)
        next_page = app.list_tasks(offset=50)
        self.assertFalse({row['id'] for row in first['tasks']} & {row['id'] for row in next_page['tasks']})
        self.assertEqual(len(app.list_tasks(offset=100)['tasks']), 10)
        self.assertEqual(app.list_tasks('ghi chú')['total'], 55)
        self.assertEqual(app.list_tasks('ghi chú', 'failed')['total'], 0)
        self.assertEqual(app.list_tasks('task-109')['total'], 1)
        self.assertEqual(app.list_tasks("%' OR 1=1 --")['total'], 0)
        for args in (('', 'unknown', 0), ('', 'all', -1), ('x'*201, 'all', 0)):
            with self.assertRaises(ValueError):
                app.list_tasks(*args)

    def test_backup_opens_independently_with_memory_products_and_wal(self):
        app.save_memory('Mục tiêu tiếng Việt')
        source = app.connect()
        try:
            source.execute('INSERT INTO tasks VALUES (?,?,?,?,?,?,?)', ('original', 'Build', 'ollama', 'completed', '', '{"result":"code"}', 'now'))
            source.execute('INSERT INTO task_products VALUES (?,?)', ('original', 1))
            app.snapshot_memory(source, 'original')
            source.execute('INSERT INTO task_sources VALUES (?,?,?,?)', ('child','original','[]','request'))
            source.commit()
            self.assertTrue(Path(str(app.DB)+'-wal').exists())
            payload = backup_database(source)
        finally:
            source.close()
        with zipfile.ZipFile(io.BytesIO(payload)) as archive:
            self.assertEqual(set(archive.namelist()), {'tasks.sqlite3','KHOI-PHUC.txt'})
            restored_path = Path(self.temporary.name)/'restored.sqlite3'
            restored_path.write_bytes(archive.read('tasks.sqlite3'))
        restored = sqlite3.connect(restored_path)
        try:
            self.assertEqual(restored.execute('PRAGMA integrity_check').fetchone()[0], 'ok')
            self.assertEqual(restored.execute('SELECT content FROM project_memory').fetchone()[0], 'Mục tiêu tiếng Việt')
            self.assertEqual(restored.execute('SELECT COUNT(*) FROM tasks').fetchone()[0], 1)
            self.assertEqual(restored.execute('SELECT enabled FROM task_products').fetchone()[0], 1)
            self.assertEqual(restored.execute('SELECT content FROM task_memory').fetchone()[0], 'Mục tiêu tiếng Việt')
            self.assertEqual(restored.execute('SELECT parent_id FROM task_sources').fetchone()[0], 'original')
        finally:
            restored.close()

    def test_ollama_health_checks_tags_without_generating(self):
        state = {'names':['qwen3:4b']}
        requests = []
        class Stub(app.BaseHTTPRequestHandler):
            def do_GET(self):
                requests.append(self.path)
                payload = json.dumps({'models':[{'name':name} for name in state['names']]}).encode()
                self.send_response(200)
                self.end_headers()
                self.wfile.write(payload)
        server = app.ThreadingHTTPServer(('127.0.0.1',0), Stub)
        worker = threading.Thread(target=server.serve_forever, daemon=True)
        worker.start()
        try:
            base = 'http://127.0.0.1:'+str(server.server_port)
            self.assertEqual(ollama_health(base, 'qwen3:4b')['status'], 'ready')
            state['names'] = ['other:latest']
            self.assertEqual(ollama_health(base, 'qwen3:4b')['status'], 'model_missing')
            self.assertEqual(requests, ['/api/tags','/api/tags'])
        finally:
            server.shutdown(); server.server_close(); worker.join()
        self.assertEqual(ollama_health(base, 'qwen3:4b')['status'], 'unavailable')

    def test_http_search_health_and_protected_backup(self):
        import urllib.request
        import urllib.error
        app.save_memory('Bản sao kiểm tra HTTP')
        server = app.ThreadingHTTPServer(('127.0.0.1',0), app.Handler)
        worker = threading.Thread(target=server.serve_forever, daemon=True)
        worker.start()
        base = 'http://127.0.0.1:'+str(server.server_port)
        try:
            with urllib.request.urlopen(base+'/api/tasks?q=test&status=all&offset=0') as response:
                self.assertEqual(json.load(response)['total'], 0)
            with self.assertRaises(urllib.error.HTTPError) as error:
                urllib.request.urlopen(base+'/api/tasks?offset=-1')
            self.assertEqual(error.exception.code, 400)
            with patch.object(app, 'ollama_health', return_value={'status':'ready','model':'qwen3:4b','models':['qwen3:4b']}):
                with urllib.request.urlopen(base+'/api/health') as response:
                    self.assertEqual(json.load(response)['ollama']['status'], 'ready')
            request = urllib.request.Request(base+'/api/backup', method='POST', headers={'Content-Type':'application/json','X-CSRF-Token':app.CSRF_TOKEN})
            with urllib.request.urlopen(request) as response:
                self.assertEqual(response.headers['Content-Type'], 'application/zip')
                self.assertIn('attachment', response.headers['Content-Disposition'])
                with zipfile.ZipFile(io.BytesIO(response.read())) as archive:
                    self.assertIn('tasks.sqlite3', archive.namelist())
            bad = urllib.request.Request(base+'/api/backup', method='POST', headers={'Content-Type':'application/json'})
            with self.assertRaises(urllib.error.HTTPError) as error:
                urllib.request.urlopen(bad)
            self.assertEqual(error.exception.code, 403)
        finally:
            server.shutdown(); server.server_close(); worker.join()

    def test_list_uses_one_connection_and_keeps_joined_metadata(self):
        with app.connect() as db:
            db.executemany('INSERT INTO tasks VALUES (?,?,?,?,?,?,?)',[(str(index),'Job','demo','completed','','{}','now') for index in range(50)])
            db.execute('INSERT INTO task_memory VALUES (?,?)',('0','Memory snapshot'))
            db.execute('INSERT INTO task_products VALUES (?,?)',('0',1))
            db.execute('INSERT INTO task_sources VALUES (?,?,?,?)',('0','parent','[]','request'))
            db.execute('INSERT INTO task_retries VALUES (?,?)',('0','1'))
        with patch.object(app,'connect',wraps=app.connect) as connections:
            page=app.list_tasks()
        self.assertEqual(connections.call_count,1)
        task=next(row for row in page['tasks'] if row['id']=='0')
        self.assertTrue(task['product'])
        self.assertEqual(task['project_memory'],'Memory snapshot')
        self.assertEqual(task['parent_id'],'parent')
        self.assertEqual(task['retry_id'],'1')
