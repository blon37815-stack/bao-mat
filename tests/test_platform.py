import json
import os
from pathlib import Path
import sqlite3
import tempfile
import threading
import unittest
from unittest.mock import patch
import urllib.error
import urllib.request

import app
import platform_config
from task_commands import parse


class PlatformTest(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        for name, value in (('DB', Path(self.temporary.name)/'tasks.db'), ('TASK_QUEUE', app.TaskQueue(10)), ('ACTIVE_CANCEL', {})):
            change = patch.object(app, name, value); change.start(); self.addCleanup(change.stop)
        self.enqueue = patch.object(app, 'enqueue_task'); self.enqueue.start(); self.addCleanup(self.enqueue.stop)
        self.server = app.ThreadingHTTPServer(('127.0.0.1', 0), app.Handler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True); self.thread.start()
        self.base = 'http://127.0.0.1:'+str(self.server.server_port)
        self.addCleanup(self.close)

    def close(self):
        self.server.shutdown(); self.server.server_close(); self.thread.join()

    def post(self, path, value, protected=True):
        headers = {'Content-Type':'application/json'}
        if protected:
            headers['X-CSRF-Token'] = app.CSRF_TOKEN
        request = urllib.request.Request(self.base+path, json.dumps(value).encode(), headers)
        with urllib.request.urlopen(request) as response:
            return json.load(response)

    def get(self, path):
        with urllib.request.urlopen(self.base+path) as response:
            return json.load(response)

    def model(self, **changes):
        return dict({'id':'python-local', 'name':'Python local', 'provider':'ollama', 'model':'first-model'}, **changes)

    def task(self, **changes):
        return self.post('/api/tasks', dict({'prompt':'Yêu cầu mẫu', 'mode':'ollama', 'expert':'none'}, **changes))['id']

    def test_profile_changes_and_environment_do_not_change_queued_model(self):
        self.post('/api/models', self.model())
        self.post('/api/bots', {'id':'plan', 'name':'Điều phối', 'instructions':'', 'model_bindings':{'ollama':'python-local'}})
        with patch.dict(os.environ, {'OLLAMA_MODEL':'original-default'}):
            task = self.task()
        self.post('/api/models', self.model(model='second-model'))
        self.post('/api/bots', {'id':'plan', 'name':'Điều phối mới', 'instructions':'mới', 'model_bindings':{'ollama':''}})
        calls = []
        def reply(messages):
            calls.append(dict(app.CALL_STATE.model_profile))
            return '{"passed":true,"issues":[]}' if 'result' in json.loads(messages[1]['content']) else 'Nội dung'
        with patch.dict(os.environ, {'OLLAMA_MODEL':'changed-default'}), patch.object(app, 'ollama_reply', side_effect=reply):
            app.run(task, 'Yêu cầu mẫu', 'ollama')
        self.assertEqual([item['model'] for item in calls], ['first-model','original-default','original-default'])
        self.assertEqual(calls[0]['revision'], 1)
        runtime = self.get('/api/tasks/'+task)['runtime']
        self.assertEqual(runtime['models']['plan']['model'], 'first-model')
        self.assertIn('executed_by', runtime)
        self.assertEqual(self.get('/api/platform')['models'][-1]['revision'], 2)

    def test_providers_cannot_cross_and_writes_require_token(self):
        self.post('/api/models', self.model(id='paid', provider='ai'))
        for path, value in [('/api/models', self.model()), ('/api/projects', {'id':'p','name':'P'}), ('/api/sandbox-policy', {'enabled':True})]:
            with self.assertRaises(urllib.error.HTTPError) as error:
                self.post(path, value, False)
            self.assertEqual(error.exception.code, 403)
        with self.assertRaises(urllib.error.HTTPError) as error:
            self.post('/api/bots', {'id':'plan','name':'Should rollback','instructions':'','model_bindings':{'ollama':'paid'}})
        self.assertEqual(error.exception.code, 400)
        self.assertEqual(next(item for item in self.get('/api/bots')['bots'] if item['id']=='plan')['name'], 'Điều phối')

    def test_projects_freeze_memory_and_filter_runs(self):
        app.save_memory('Chung')
        self.post('/api/projects', {'id':'project-a','name':'A','memory':'Bộ nhớ A'})
        self.post('/api/projects', {'id':'project-b','name':'B','memory':'Bộ nhớ B'})
        first = self.task(project_id='project-a')
        second = self.task(project_id='project-b')
        common = self.task()
        self.post('/api/projects', {'id':'project-a','name':'A','memory':'Đã thay'})
        self.assertEqual(app.task_context(first), 'Bộ nhớ A')
        self.assertEqual(app.task_context(second), 'Bộ nhớ B')
        self.assertEqual(app.task_context(common), 'Chung')
        values = self.get('/api/tasks?compact=1&project_id=project-a')['tasks']
        self.assertEqual([item['id'] for item in values], [first])
        self.assertEqual(values[0]['project_id'], 'project-a')
        with self.assertRaises(urllib.error.HTTPError):
            self.task(project_id='missing')
        with app.connect() as db:
            self.assertEqual(db.execute('SELECT COUNT(*) FROM task_runtime').fetchone()[0], 3)

    def test_ecc_reference_is_frozen_and_integrity_checked(self):
        task = self.task(expert='python')
        with app.connect() as db:
            runtime = platform_config.task_runtime(db, task)
        self.assertIn('Python', runtime['expert_source']['reference'])
        self.assertEqual(len(runtime['expert_source']['sources']), 2)
        public = self.get('/api/tasks/'+task)['runtime']['expert_source']
        self.assertNotIn('reference', public)
        with patch.object(platform_config, 'source_profile', side_effect=ValueError('hash mismatch')):
            with self.assertRaises(urllib.error.HTTPError):
                self.task(expert='python')
        with app.connect() as db:
            self.assertEqual(db.execute('SELECT COUNT(*) FROM task_runtime').fetchone()[0], 1)

    def test_retry_retains_old_profiles_and_legacy_is_explicit(self):
        task = self.task()
        with app.connect() as db:
            original = platform_config.task_runtime(db, task)
            db.execute("UPDATE tasks SET status='needs_review' WHERE id=?", (task,))
        retry = self.post('/api/tasks/'+task+'/retry', {})['id']
        with app.connect() as db:
            repeated = platform_config.task_runtime(db, retry)
            self.assertEqual(repeated['models'], original['models'])
            db.execute("INSERT INTO tasks VALUES ('legacy','old','demo','completed','','{}','2020-01-01')")
        self.assertTrue(self.get('/api/tasks/legacy/workspace')['runtime']['legacy'])
        self.assertEqual(self.get('/api/tasks/'+retry+'/workspace')['id'], retry)

    def test_input_limit_stops_before_provider_and_preserves_result_state(self):
        self.post('/api/models', self.model(max_input_chars=1000))
        self.post('/api/bots', {'id':'plan','name':'Điều phối','instructions':'','model_bindings':{'ollama':'python-local'}})
        task = self.task(prompt='x'*2000)
        with patch.object(app, 'ollama_reply', side_effect=AssertionError('must not call provider')):
            app.run(task, 'x'*2000, 'ollama')
        row = self.get('/api/tasks/'+task)
        self.assertEqual(row['status'], 'needs_review')
        self.assertEqual(row['model_calls'], 0)
        self.assertIn('Ngữ cảnh', row['stage'])

    def test_sandbox_failure_drives_repair_and_saved_evidence(self):
        self.post('/api/sandbox-policy', {'enabled':True})
        task = self.task(template='python', product=True)
        provider = {'main.py':'def add(a,b):\n    return a+b\n', 'tests/test_main.py':'import unittest\nfrom main import add\nclass T(unittest.TestCase):\n def test_ok(self): self.assertEqual(add(1,2),3)\n', 'README.md':'# Python'}
        def reply(messages):
            value = json.loads(messages[1]['content'])
            if value.get('target_path'):
                return provider[value['target_path']]
            return '{"passed":true,"issues":[]}' if 'result' in value else 'Kế hoạch'
        reports = [{'status':'failed','tests':1,'output':'AssertionError: incorrect result'}, {'status':'passed','tests':1,'output':'OK'}]
        with patch.object(app, 'ollama_reply', side_effect=reply), patch.object(app.product_runner, 'check_product', side_effect=reports) as runner:
            app.run(task, 'Yêu cầu mẫu', 'ollama')
        self.assertEqual(runner.call_count, 2)
        row = self.get('/api/tasks/'+task)
        self.assertEqual(row['status'], 'completed')
        self.assertIn('đạt unittest trong Docker', row['stage'])
        self.assertEqual([item['status'] for item in self.get('/api/tasks/'+task+'/workspace')['checks']], ['failed','passed'])

    def test_newer_database_is_rejected_without_migration(self):
        with sqlite3.connect(app.DB) as db:
            db.execute('PRAGMA user_version=999')
        with self.assertRaises(ValueError):
            app.connect()
        with sqlite3.connect(app.DB) as db:
            self.assertEqual(db.execute('PRAGMA user_version').fetchone()[0], 999)
            self.assertFalse(db.execute("SELECT name FROM sqlite_master WHERE name='tasks'").fetchall())

    def test_commands_are_explicit_and_do_not_claim_full_ecc(self):
        self.assertEqual(parse('/python Tạo CLI'), ('python','Tạo CLI'))
        self.assertEqual(parse('/verify abc'), ('verify','abc'))
        for value in ('/tdd anything', '/verify ../../x', '/plan'):
            with self.assertRaises(ValueError): parse(value)
        task = self.task(prompt='/data Dữ liệu thử', mode='demo')
        self.assertEqual(self.get('/api/tasks/'+task)['requirements']['template'], 'data')
        self.assertEqual(len(self.get('/api/commands')['commands']), 6)

    def test_bound_provider_change_and_invalid_global_config_are_rejected(self):
        self.post('/api/models', self.model())
        self.post('/api/bots', {'id':'plan','name':'Điều phối','instructions':'','model_bindings':{'ollama':'python-local'}})
        with self.assertRaises(urllib.error.HTTPError) as error:
            self.post('/api/models', self.model(provider='ai'))
        self.assertEqual(error.exception.code, 400)
        with patch.dict(os.environ, {'OLLAMA_TIMEOUT_SECONDS':'invalid'}):
            with self.assertRaises(urllib.error.HTTPError) as error:
                self.get('/api/platform')
            self.assertEqual(error.exception.code, 400)
            self.assertIn('OLLAMA_TIMEOUT_SECONDS', json.load(error.exception)['error'])

    def test_manual_failed_tests_remove_a_previous_pass_status(self):
        files = [{'path':'main.py','content':'x=1'}, {'path':'tests/test_main.py','content':'x=1'}]
        with app.connect() as db:
            db.execute('INSERT INTO tasks VALUES (?,?,?,?,?,?,?)', ('original','Python','ollama','approved','Đã duyệt',json.dumps({'result':json.dumps({'files':files})}),app.utc_now()))
            db.execute('INSERT INTO task_products VALUES (?,1)', ('original',))
        with patch.object(app.product_runner, 'check_product', return_value={'status':'failed','output':'NameError','tests':1}):
            self.post('/api/tasks/original/run-tests', {})
        self.assertEqual(self.get('/api/tasks/original')['status'], 'needs_review')
        with self.assertRaises(urllib.error.HTTPError) as error:
            self.post('/api/tasks/original/run-tests', {}, False)
        self.assertEqual(error.exception.code, 403)

    def test_shutdown_signals_active_work_and_preserves_queued_tasks_for_retry(self):
        task = self.task(mode='demo')
        event = threading.Event()
        with app.ACTIVE_LOCK:
            app.ACTIVE_CANCEL[task] = event
        def release():
            event.wait(2)
            with app.ACTIVE_LOCK:
                app.ACTIVE_CANCEL.pop(task, None)
        worker = threading.Thread(target=release); worker.start()
        try:
            app.stop_workers()
        finally:
            worker.join(timeout=3)
        self.assertTrue(event.is_set())
        self.assertTrue(app.TASK_QUEUE.paused)
        self.assertEqual(self.get('/api/tasks/'+task)['status'], 'interrupted')
