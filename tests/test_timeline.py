import json
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch
import app


class TimelineTest(unittest.TestCase):
    def setUp(self):
        self.temporary=tempfile.TemporaryDirectory()
        self.patch=patch.object(app,'DB',Path(self.temporary.name)/'tasks.sqlite3')
        self.patch.start()
        with app.connect() as db:
            db.execute('INSERT INTO tasks VALUES (?,?,?,?,?,?,?)',('task','Yêu cầu','demo','queued','','{}',app.utc_now()))

    def tearDown(self):
        self.patch.stop();self.temporary.cleanup()

    def test_history_keeps_each_revision_and_matches_latest_result(self):
        responses=['Kế hoạch','Bản cũ','{"passed":false,"issues":["Thiếu yêu cầu"]}','Bản mới','{"passed":true,"issues":[]}']
        with patch.object(app,'ollama_reply',side_effect=responses):
            app.run('task','Yêu cầu','ollama')
        status,history=app.task_history('task')
        self.assertEqual(status,200)
        self.assertEqual([item['role'] for item in history['steps']],['plan','result','review','result','review'])
        self.assertEqual([item['attempt'] for item in history['steps']],[1,1,1,2,2])
        self.assertEqual(history['steps'][1]['output'],'Bản cũ')
        self.assertEqual(history['steps'][3]['output'],'Bản mới')
        self.assertTrue(all(item['status']=='completed' and item['finished_at'] for item in history['steps']))
        self.assertTrue(history['timing']['started_at'])
        self.assertTrue(history['timing']['finished_at'])
        task=app.list_tasks()['tasks'][0]
        self.assertEqual(task['completed_steps'],5)
        self.assertEqual(json.loads(task['output'])['result'],'Bản mới')

    def test_failed_step_and_run_have_end_timestamps_without_private_error(self):
        with patch.object(app,'ollama_reply',side_effect=['Plan',RuntimeError('secret-provider-detail')]):
            app.run('task','Yêu cầu','ollama')
        _,history=app.task_history('task')
        self.assertEqual([item['status'] for item in history['steps']],['completed','failed'])
        self.assertEqual(history['steps'][1]['output'],'')
        self.assertTrue(history['timing']['finished_at'])
        self.assertNotIn('secret-provider-detail',json.dumps(history))

    def test_recovery_closes_interrupted_timeline(self):
        with app.connect() as db:
            db.execute('INSERT INTO task_timing VALUES (?,?,NULL)',('task','2026-10-01T00:00:00+00:00'))
            db.execute('INSERT INTO task_steps(task_id,role,attempt,started_at,status) VALUES (?,?,?,?,?)',('task','plan',1,'2026-10-01T00:00:00+00:00','running'))
        app.recover()
        _,history=app.task_history('task')
        self.assertEqual(history['steps'][0]['status'],'interrupted')
        self.assertTrue(history['steps'][0]['finished_at'])
        self.assertTrue(history['timing']['finished_at'])
        self.assertEqual(app.task_history('missing')[0],404)

    def test_connections_are_closed_on_context_exit(self):
        with app.connect() as db:
            db.execute('SELECT 1')
        with self.assertRaises(sqlite3.ProgrammingError):
            db.execute('SELECT 1')
