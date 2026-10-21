import json
from contextlib import closing
from pathlib import Path
import sqlite3
import tempfile
import threading
import unittest
from unittest.mock import patch
import urllib.error
import urllib.request

import app
import bot_tools
import platform_config
from task_deletion import deletion_plan, apply_deletion


class BotToolsTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        for name, value in (('DB', Path(self.temp.name)/'tasks.db'), ('TASK_QUEUE', app.TaskQueue(10)), ('ACTIVE_CANCEL', {})):
            change = patch.object(app, name, value); change.start(); self.addCleanup(change.stop)
        change = patch.object(app, 'enqueue_task'); change.start(); self.addCleanup(change.stop)
        self.server = app.ThreadingHTTPServer(('127.0.0.1', 0), app.Handler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True); self.thread.start()
        self.base = 'http://127.0.0.1:'+str(self.server.server_port)
        self.addCleanup(self.close)

    def close(self):
        self.server.shutdown(); self.server.server_close(); self.thread.join()

    def get(self, path):
        with urllib.request.urlopen(self.base+path) as response:
            return json.load(response)

    def post(self, path, value, protected=True):
        headers = {'Content-Type':'application/json'}
        if protected: headers['X-CSRF-Token'] = app.CSRF_TOKEN
        request = urllib.request.Request(self.base+path, json.dumps(value).encode(), headers)
        with urllib.request.urlopen(request) as response:
            return json.load(response)

    def task(self, **changes):
        return self.post('/api/tasks', dict(prompt='Yêu cầu thử quyền', mode='ollama', expert='none', **changes))['id']

    def save_tools(self, role, tools):
        return self.post('/api/bots', {'id':role, 'name':'Tên thử', 'instructions':'', 'tools':tools})

    def invoke(self, task, role='result', tool='write_workspace', operation=lambda: 'ok'):
        return bot_tools.invoke(app.connect, task, role, tool, {'paths':['main.py']}, operation)

    def test_caps_cannot_escalate_roles_and_api_writes_are_protected(self):
        bot = next(item for item in self.get('/api/bots')['bots'] if item['id']=='result')
        self.assertIn('write_workspace', bot['tools'])
        self.assertNotIn('run_python_tests', bot['tools'])
        for tools in (['run_python_tests'], ['shell'], ['write_workspace','write_workspace']):
            with self.assertRaises(urllib.error.HTTPError) as error:
                self.save_tools('plan', tools)
            self.assertEqual(error.exception.code, 400)
        self.assertEqual(next(item for item in self.get('/api/bots')['bots'] if item['id']=='plan')['name'], 'Điều phối')
        with self.assertRaises(urllib.error.HTTPError) as error:
            self.post('/api/bots', {'id':'plan','name':'X','instructions':'','tools':[]}, False)
        self.assertEqual(error.exception.code, 403)

    def test_frozen_grants_cannot_expand_and_current_revocation_blocks_old_runs(self):
        self.save_tools('result', ['read_workspace','generate_text'])
        old = self.task()
        self.save_tools('result', list(bot_tools.CEILINGS['result']))
        new = self.task()
        called = []
        with self.assertRaises(bot_tools.ToolDenied): self.invoke(old, operation=lambda:called.append(True))
        self.assertEqual(called, [])
        self.assertEqual(self.invoke(new), 'ok')
        self.save_tools('result', ['read_workspace','generate_text'])
        with self.assertRaises(bot_tools.ToolDenied): self.invoke(new)
        self.assertEqual(self.get('/api/audit?decision=BLOCK')['total'], 2)

    def test_wrong_actor_unsafe_paths_and_unknown_arguments_never_run_operation(self):
        task = self.task()
        called = []
        for role, tool, args in [('plan','write_workspace',{'paths':['main.py']}), ('result','shell',{'command':'secret-value'}),
                                 ('result','write_workspace',{'paths':['../outside.py']}), ('result','generate_text',{'messages':'secret-value'})]:
            with self.assertRaises(bot_tools.ToolDenied):
                bot_tools.invoke(app.connect, task, role, tool, args, lambda:called.append(True))
        self.assertEqual(called, [])
        audit = self.get('/api/audit?task_id='+task)
        self.assertEqual(audit['total'], 4)
        self.assertNotIn('secret-value', json.dumps(audit))
        self.assertNotIn('../outside', json.dumps(audit))

    def test_audit_does_not_capture_contents_provider_secrets_or_raw_exceptions(self):
        task = self.task()
        secret = 'private-api-key-DO-NOT-STORE'
        def fail(): raise RuntimeError(secret)
        with self.assertRaises(RuntimeError): self.invoke(task, operation=fail)
        self.invoke(task, operation=lambda:{'content':secret})
        value = self.get('/api/audit?task_id='+task)
        self.assertNotIn(secret, json.dumps(value))
        self.assertEqual([item['outcome'] for item in value['events']], ['completed','failed'])
        self.assertEqual(value['events'][0]['details']['paths'], ['main.py'])

    def test_disabled_reads_stop_before_model_and_leave_block_evidence(self):
        self.save_tools('plan', ['generate_text'])
        task = self.task()
        with patch.object(app, 'ollama_reply') as provider:
            app.run(task, 'Yêu cầu thử quyền', 'ollama')
        provider.assert_not_called()
        self.assertEqual(self.get('/api/tasks/'+task)['status'], 'needs_review')
        self.assertEqual(self.get('/api/audit?task_id='+task)['events'][0]['decision'], 'BLOCK')

    def test_disabled_product_writes_stop_before_result_generation(self):
        self.save_tools('result', ['read_workspace','generate_text'])
        task = self.task(product=True)
        with patch.object(app, 'ollama_reply', return_value='{"plan":"Kế hoạch","required_files":["main.py","README.md"]}') as provider:
            app.run(task, 'Yêu cầu thử quyền', 'ollama')
        self.assertEqual(provider.call_count, 1)
        row = self.get('/api/tasks/'+task)
        self.assertEqual(row['status'], 'needs_review')
        self.assertNotIn('result', json.loads(row['output']))

    def test_call_budget_denial_is_recorded_and_provider_is_not_called_again(self):
        task = self.task(call_limit=1)
        with patch.object(app, 'ollama_reply', return_value='Kế hoạch') as provider:
            app.run(task, 'Yêu cầu thử quyền', 'ollama')
        self.assertEqual(provider.call_count, 1)
        limited = self.get('/api/audit?task_id='+task+'&decision=BLOCK')['events']
        self.assertEqual(limited[0]['outcome'], 'limited')
        self.assertEqual(self.get('/api/tasks/'+task)['model_calls'], 1)

    def test_warn_events_report_unsupported_checks_without_claiming_success(self):
        task = self.task()
        result = bot_tools.invoke(app.connect, task, 'review', 'run_python_tests', {'paths':[]},
                                  lambda:{'status':'unavailable','output':'Docker missing'})
        self.assertEqual(result['status'], 'unavailable')
        self.assertEqual(self.get('/api/audit?decision=WARN')['events'][0]['outcome'], 'unavailable')

    def test_retention_pagination_recovery_and_task_delete(self):
        task = self.task()
        with app.connect() as db:
            for _ in range(505): bot_tools.record(db, task, 'plan','generate_text','ALLOW','completed','Kết quả')
            bot_tools.record(db, task, 'plan','generate_text','ALLOW','running','Đang chạy')
        self.assertEqual(self.get('/api/audit?task_id='+task)['total'], 500)
        self.assertEqual(len(self.get('/api/audit?task_id='+task+'&offset=490')['events']), 10)
        app.recover()
        self.assertEqual(self.get('/api/audit?task_id='+task)['events'][0]['outcome'], 'interrupted')
        with app.connect() as db:
            plan = deletion_plan(db, task)
            apply_deletion(db, plan, app.utc_now())
            self.assertEqual(db.execute('SELECT COUNT(*) FROM audit_events WHERE task_id=?',(task,)).fetchone()[0], 0)

    def test_v1_database_migrates_without_changing_existing_work(self):
        path = Path(self.temp.name)/'legacy.db'
        with closing(sqlite3.connect(path)) as db, db:
            db.execute('PRAGMA user_version=1')
            db.execute('CREATE TABLE preserved (value TEXT)')
            db.execute("INSERT INTO preserved VALUES ('Nội dung cũ')")
            db.execute('CREATE TABLE tasks (id TEXT PRIMARY KEY, prompt TEXT, mode TEXT, status TEXT, stage TEXT, output TEXT, created TEXT)')
            db.execute("INSERT INTO tasks VALUES ('legacy','Yêu cầu cũ','ollama','completed','','{}','now')")
        with patch.object(app, 'DB', path), app.connect() as db:
            self.assertEqual(db.execute('PRAGMA user_version').fetchone()[0], 2)
            self.assertEqual(db.execute('SELECT * FROM preserved').fetchone()[0], 'Nội dung cũ')
            self.assertEqual(db.execute('SELECT COUNT(*) FROM audit_events').fetchone()[0], 0)
            self.assertEqual(db.execute('SELECT COUNT(*) FROM task_tool_grants').fetchone()[0], 1)
