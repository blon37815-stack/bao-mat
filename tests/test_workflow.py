import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
import app

class WorkflowTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.patch = patch.object(app, 'DB', Path(self.tmp.name)/'tasks.db')
        self.patch.start()
        with app.connect() as db:
            db.execute('INSERT INTO tasks VALUES (?,?,?,?,?,?,?)', ('test','Viết kế hoạch','demo','queued','Chờ','{}','now'))
    def tearDown(self):
        self.patch.stop()
        self.tmp.cleanup()
    def row(self):
        with app.connect() as db:
            return dict(db.execute('SELECT * FROM tasks').fetchone())
    def test_demo_persists_all_three_stages(self):
        app.run('test','Viết kế hoạch','demo')
        row = self.row()
        self.assertEqual(row['status'],'completed')
        self.assertEqual(set(json.loads(row['output'])), {'plan','result','review'})
        self.assertIn('mô phỏng',json.loads(row['output'])['result'])
    def test_provider_failure_is_not_reported_as_success(self):
        with patch.object(app, 'build_graph', side_effect=RuntimeError('private provider detail')):
            app.run('test','Viết kế hoạch','ai')
        self.assertEqual(self.row()['status'],'failed')
        self.assertNotIn('private',self.row()['stage'])
    def test_restart_marks_unfinished_work(self):
        app.recover()
        self.assertEqual(self.row()['status'],'interrupted')

    def test_retry_claims_once_and_clears_partial_output(self):
        app.update('test', status='failed', output='{"plan":"old"}')
        with patch.object(app.threading, 'Thread') as worker:
            self.assertEqual(app.retry_task('test')[0], 202)
            self.assertEqual(app.retry_task('test')[0], 409)
            worker.return_value.start.assert_called_once()
        self.assertEqual(self.row()['output'], '{}')
        self.assertEqual(self.row()['status'], 'queued')

    def test_retry_preserves_work_when_ai_key_is_missing(self):
        app.update('test', mode='ai', status='failed', output='{"plan":"saved"}')
        with patch.dict(app.os.environ, {}, clear=True):
            self.assertEqual(app.retry_task('test')[0], 400)
        self.assertEqual(self.row()['output'], '{"plan":"saved"}')
        self.assertEqual(self.row()['status'], 'failed')

    def test_retry_missing_task(self):
        self.assertEqual(app.retry_task('missing')[0], 404)

    def test_team_reports_actual_active_stage(self):
        app.update('test', status='running', stage='Thực hiện')
        status = app.team_status()
        self.assertEqual(status['totals'], {'running': 1})
        self.assertEqual([bot['active'] for bot in status['bots']], [0, 1, 0])

    def test_http_detail_retry_and_status(self):
        import threading
        import urllib.request
        import urllib.error
        import time
        server = app.ThreadingHTTPServer(('127.0.0.1', 0), app.Handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        base = 'http://127.0.0.1:' + str(server.server_port)
        def get(path):
            with urllib.request.urlopen(base+path) as response:
                return json.load(response)
        try:
            self.assertEqual(get('/api/tasks/test')['id'], 'test')
            with self.assertRaises(urllib.error.HTTPError) as error:
                get('/api/tasks/missing')
            self.assertEqual(error.exception.code, 404)
            app.update('test', status='interrupted')
            request = urllib.request.Request(base+'/api/tasks/test/retry', method='POST')
            with urllib.request.urlopen(request) as response:
                self.assertEqual(response.status, 202)
            for _ in range(100):
                task = get('/api/tasks/test')
                if task['status'] == 'completed':
                    break
                time.sleep(.02)
            self.assertEqual(task['status'], 'completed')
            self.assertEqual(len(json.loads(task['output'])), 3)
            self.assertEqual(get('/api/team')['totals']['completed'], 1)
        finally:
            server.shutdown()
            server.server_close()
            thread.join()

if __name__ == '__main__':
    unittest.main()
