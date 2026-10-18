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

if __name__ == '__main__':
    unittest.main()
