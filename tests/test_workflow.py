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

    def test_retry_claims_once_and_preserves_original_output(self):
        app.update('test', status='failed', output='{"plan":"old"}')
        with patch.object(app, 'enqueue_task') as worker:
            status, result = app.retry_task('test')
            self.assertEqual(status, 202)
            self.assertNotEqual(result['id'], 'test')
            self.assertEqual(app.retry_task('test')[0], 409)
            worker.assert_called_once()
        self.assertEqual(self.row()['output'], '{"plan":"old"}')
        self.assertEqual(self.row()['status'], 'failed')
        with app.connect() as db:
            clone = db.execute('SELECT * FROM tasks WHERE id=?',(result['id'],)).fetchone()
        self.assertEqual(clone['output'],'{}')
        self.assertEqual(clone['status'],'queued')

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
            memory_request = urllib.request.Request(base+'/api/memory', data=json.dumps({'content':'Dự án tiếng Việt'}).encode(), headers={'Content-Type':'application/json','X-CSRF-Token':app.CSRF_TOKEN})
            with urllib.request.urlopen(memory_request) as response:
                self.assertTrue(json.load(response)['saved'])
            self.assertEqual(get('/api/memory')['content'], 'Dự án tiếng Việt')
            create_request = urllib.request.Request(base+'/api/tasks', data=json.dumps({'prompt':'Thử bộ nhớ','mode':'demo','product':True}).encode(), headers={'Content-Type':'application/json','X-CSRF-Token':app.CSRF_TOKEN})
            with urllib.request.urlopen(create_request) as response:
                new_id = json.load(response)['id']
            for _ in range(100):
                new_task = get('/api/tasks/'+new_id)
                if new_task['status'] == 'completed':
                    break
                time.sleep(.02)
            self.assertEqual(new_task['project_memory'], 'Dự án tiếng Việt')
            self.assertEqual(new_task['status'], 'completed')
            self.assertTrue(new_task['product'])
            self.assertEqual(get('/api/tasks/'+new_id+'/files')['files'][0]['path'], 'README.md')
            self.assertEqual(get('/api/tasks/'+new_id+'/checks')['status'], 'not_supported')
            with urllib.request.urlopen(base+'/api/tasks/'+new_id+'/file/0') as response:
                self.assertIn('attachment', response.headers['Content-Disposition'])
                self.assertIn('mô phỏng', response.read().decode('utf-8'))
            child_request = urllib.request.Request(base+'/api/tasks', data=json.dumps({'prompt':'Thêm hướng dẫn','mode':'demo','parent_id':new_id}).encode(), headers={'Content-Type':'application/json','X-CSRF-Token':app.CSRF_TOKEN})
            with urllib.request.urlopen(child_request) as response:
                child_id = json.load(response)['id']
            for _ in range(100):
                child = get('/api/tasks/'+child_id)
                if child['status']=='completed':
                    break
                time.sleep(.02)
            self.assertEqual(child['parent_id'], new_id)
            self.assertTrue(child['product'])
            self.assertEqual(get('/api/tasks/'+child_id+'/diff')['changes'], [])
            for path in ('/api/tasks/'+new_id+'/file/99','/api/tasks/'+new_id+'/file/../app.py'):
                with self.assertRaises(urllib.error.HTTPError) as error:
                    get(path)
                self.assertEqual(error.exception.code, 404)
            invalid = urllib.request.Request(base+'/api/tasks', data=json.dumps({'prompt':'Edit','mode':'demo','parent_id':'missing'}).encode(), headers={'Content-Type':'application/json','X-CSRF-Token':app.CSRF_TOKEN})
            with self.assertRaises(urllib.error.HTTPError) as error:
                urllib.request.urlopen(invalid)
            self.assertEqual(error.exception.code, 404)

            import io, zipfile
            with urllib.request.urlopen(base+'/api/tasks/'+new_id+'/artifact.zip') as response:
                self.assertEqual(response.headers['Content-Type'], 'application/zip')
                with zipfile.ZipFile(io.BytesIO(response.read())) as archive:
                    self.assertIn('mô phỏng', archive.read('README.md').decode('utf-8'))
            with self.assertRaises(urllib.error.HTTPError) as error:
                get('/api/tasks/missing')
            self.assertEqual(error.exception.code, 404)
            app.update('test', status='interrupted')
            request = urllib.request.Request(base+'/api/tasks/test/retry', method='POST', headers={'Content-Type':'application/json','X-CSRF-Token':app.CSRF_TOKEN})
            with urllib.request.urlopen(request) as response:
                self.assertEqual(response.status, 202)
                retry_id = json.load(response)['id']
            for _ in range(100):
                task = get('/api/tasks/'+retry_id)
                if task['status'] == 'completed':
                    break
                time.sleep(.02)
            self.assertEqual(task['status'], 'completed')
            self.assertEqual(len(json.loads(task['output'])), 3)
            self.assertEqual(get('/api/team')['totals']['completed'], 3)
            with urllib.request.urlopen(base+'/api/tasks/'+retry_id+'/export/all') as response:
                self.assertIn('attachment', response.headers['Content-Disposition'])
                self.assertIn('text/markdown', response.headers['Content-Type'])
                self.assertIn('Kiểm tra', response.read().decode('utf-8'))
        finally:
            server.shutdown()
            server.server_close()
            thread.join()

    def test_ollama_runs_three_stages_without_api_key(self):
        import threading
        requests = []
        class OllamaStub(app.BaseHTTPRequestHandler):
            def do_POST(self):
                requests.append((self.path, json.loads(self.rfile.read(int(self.headers['Content-Length'])))))
                payload = (json.dumps({'message': {'content': (json.dumps({'passed':True,'issues':[]}) if len(requests)==3 else 'Kết quả local ' + str(len(requests)))}, 'done':True})+'\n').encode()
                self.send_response(200)
                self.end_headers()
                self.wfile.write(payload)
        server = app.ThreadingHTTPServer(('127.0.0.1', 0), OllamaStub)
        worker = threading.Thread(target=server.serve_forever, daemon=True)
        worker.start()
        try:
            with patch.dict(app.os.environ, {'OLLAMA_BASE_URL': 'http://127.0.0.1:'+str(server.server_port)}, clear=True):
                app.run('test', 'Lập kế hoạch', 'ollama')
            self.assertEqual(self.row()['status'], 'completed')
            self.assertEqual(len(requests), 3)
            self.assertEqual(requests[0][0], '/api/chat')
            self.assertEqual(requests[0][1]['model'], 'qwen3:4b')
            self.assertFalse(requests[0][1]['think'])
            self.assertTrue(requests[0][1]['stream'])
            self.assertIn('Kết quả local 1', requests[1][1]['messages'][1]['content'])
            self.assertIn('Kết quả local 2', requests[2][1]['messages'][1]['content'])
        finally:
            server.shutdown()
            server.server_close()
            worker.join()

    def test_ollama_failure_does_not_fall_back_to_paid_provider(self):
        with patch.object(app, 'ollama_reply', side_effect=OSError('unreachable')):
            app.run('test', 'Lập kế hoạch', 'ollama')
        self.assertEqual(self.row()['status'], 'failed')
        self.assertIn('Ollama', self.row()['stage'])

    def test_dashboard_has_valid_provider_options(self):
        from html.parser import HTMLParser
        class Options(HTMLParser):
            def __init__(self):
                super().__init__()
                self.in_mode = False
                self.options = []
            def handle_starttag(self, tag, attrs):
                attrs = dict(attrs)
                if tag == 'select':
                    self.in_mode = attrs.get('id') == 'mode'
                if tag == 'option' and self.in_mode:
                    self.options.append(attrs.get('value'))
            def handle_endtag(self, tag):
                if tag == 'select':
                    self.in_mode = False
        parser = Options()
        parser.feed((app.ROOT/'index.html').read_text(encoding='utf-8'))
        self.assertEqual(parser.options, ['demo', 'ollama', 'ai'])

    def test_reasoning_is_removed_from_new_and_saved_results(self):
        self.assertEqual(app.final_answer('Okay, let me think.\n</think>\nKết quả tiếng Việt'), 'Kết quả tiếng Việt')
        self.assertEqual(app.final_answer('<think>English</think> Kết quả'), 'Kết quả')
        self.assertEqual(app.final_answer('<think>unfinished'), '')
        self.assertEqual(app.final_answer('Tiếng Việt bình thường'), 'Tiếng Việt bình thường')
        app.update('test', output=json.dumps({'plan': '<think>English</think> Kế hoạch'}))
        self.assertEqual(json.loads(app.public_task(self.row())['output'])['plan'], 'Kế hoạch')
        self.assertIn('English', self.row()['output'])

    def test_export_preserves_vietnamese_and_removes_reasoning(self):
        app.update('test', status='completed', output=json.dumps({'plan': '<think>thinking</think>Kế hoạch tiếng Việt', 'result': 'Sản phẩm'}))
        status, body = app.export_task('test', 'all')
        self.assertEqual(status, 200)
        text = body.decode('utf-8')
        self.assertIn('Kế hoạch tiếng Việt', text)
        self.assertIn('Sản phẩm', text)
        self.assertIn('MÔ PHỎNG', text)
        self.assertNotIn('thinking', text)
        _, body = app.export_task('test', 'plan')
        self.assertNotIn('Sản phẩm', body.decode('utf-8'))

    def test_export_handles_missing_and_partial_results(self):
        self.assertEqual(app.export_task('missing', 'all')[0], 404)
        self.assertEqual(app.export_task('test', 'unknown')[0], 404)
        self.assertEqual(app.export_task('test', 'all')[0], 409)
        app.update('test', output=json.dumps({'plan': 'Kế hoạch'}))
        status, body = app.export_task('test', 'all')
        self.assertEqual(status, 200)
        self.assertIn('Kết quả một phần', body.decode('utf-8'))
        self.assertEqual(app.export_task('test', 'result')[0], 409)

    def test_memory_snapshots_survive_changes_and_restart(self):
        app.save_memory('Mục tiêu: ứng dụng tiếng Việt')
        with app.connect() as db:
            app.snapshot_memory(db, 'test')
        app.save_memory('Yêu cầu mới')
        self.assertEqual(app.get_memory(), 'Yêu cầu mới')
        app.recover()
        self.assertEqual(app.task_context('test'), 'Mục tiêu: ứng dụng tiếng Việt')
        self.assertEqual(app.public_task(self.row())['project_memory'], 'Mục tiêu: ứng dụng tiếng Việt')
        app.save_memory('')
        self.assertEqual(app.get_memory(), '')
        self.assertNotEqual(app.task_context('test'), '')

    def test_memory_is_sent_to_every_role(self):
        app.save_memory('Dùng SQLite')
        with app.connect() as db:
            app.snapshot_memory(db, 'test')
        with patch.object(app, 'ollama_reply', return_value=json.dumps({'passed':True,'issues':[]})) as model:
            app.run('test', 'Lập kế hoạch', 'ollama')
        self.assertEqual(model.call_count, 3)
        for call in model.call_args_list:
            context = json.loads(call.args[0][1]['content'])
            self.assertEqual(context['project_memory'], 'Dùng SQLite')
        self.assertEqual(self.row()['status'], 'completed')

    def test_memory_rejects_invalid_input(self):
        app.save_memory('Giữ nguyên')
        for value in (None, 12, 'x'*8001):
            with self.assertRaises(ValueError):
                app.save_memory(value)
        self.assertEqual(app.get_memory(), 'Giữ nguyên')

    def test_http_rejects_cross_site_invalid_host_and_missing_token(self):
        import threading
        import urllib.request
        import urllib.error
        server = app.ThreadingHTTPServer(('127.0.0.1', 0), app.Handler)
        worker = threading.Thread(target=server.serve_forever, daemon=True)
        worker.start()
        base = 'http://127.0.0.1:'+str(server.server_port)
        try:
            for path, headers, data, code in [
                ('/api/session', {'Host':'attacker.example'}, None, 403),
                ('/api/session', {'Origin':'https://attacker.example'}, None, 403),
                ('/api/session', {'Origin':'null'}, None, 403),
                ('/api/memory', {'Content-Type':'text/plain'}, b'{}', 415),
                ('/api/memory', {'Content-Type':'application/json'}, b'{}', 403),
                ('/api/memory', {'Content-Type':'application/json','X-CSRF-Token':app.CSRF_TOKEN,'Origin':'https://attacker.example'}, b'{}', 403),
            ]:
                with self.subTest(headers=headers):
                    request = urllib.request.Request(base+path, headers=headers, data=data)
                    with self.assertRaises(urllib.error.HTTPError) as error:
                        urllib.request.urlopen(request)
                    self.assertEqual(error.exception.code, code)
            self.assertEqual(app.get_memory(), '')
            navigation_headers = {'Sec-Fetch-Site':'cross-site','Sec-Fetch-Mode':'navigate','Sec-Fetch-Dest':'document'}
            with urllib.request.urlopen(urllib.request.Request(base+'/', headers=navigation_headers)) as response:
                self.assertEqual(response.status, 200)
                self.assertIn('Đội bot', response.read().decode('utf-8'))
            for path in ('/api/session', '/api/memory'):
                with self.assertRaises(urllib.error.HTTPError) as error:
                    urllib.request.urlopen(urllib.request.Request(base+path, headers=navigation_headers))
                self.assertEqual(error.exception.code, 403)
            request = urllib.request.Request(base+'/api/session', headers={'Origin':base})
            with urllib.request.urlopen(request) as response:
                self.assertEqual(json.load(response)['token'], app.CSRF_TOKEN)
        finally:
            server.shutdown(); server.server_close(); worker.join()

    def test_filter_preserves_literal_tags_and_code(self):
        for text in ('Thẻ <think> là gì?', 'Ví dụ </think> ở giữa câu.',
                     '```xml\n<think>example</think>\n```',
                     'Okay, thẻ </think> là ví dụ.'):
            self.assertEqual(app.final_answer(text), text)
        self.assertEqual(app.final_answer('<think>reason</think>Giải thích <think> và </think>'), 'Giải thích <think> và </think>')

    def test_queue_serializes_jobs_and_preserves_order(self):
        import threading
        app.TASK_QUEUE.join()
        entered, release, finished = threading.Event(), threading.Event(), threading.Event()
        calls = []
        def fake_run(task_id, prompt, mode):
            calls.append(task_id)
            if task_id == 'first':
                entered.set()
                release.wait(5)
            else:
                finished.set()
        with patch.object(app, 'run', side_effect=fake_run):
            try:
                app.enqueue_task('first', 'one', 'demo')
                self.assertTrue(entered.wait(2))
                app.enqueue_task('second', 'two', 'demo')
                self.assertFalse(finished.wait(.1))
                self.assertEqual(calls, ['first'])
            finally:
                release.set()
                app.TASK_QUEUE.join()
            self.assertEqual(calls, ['first', 'second'])

    def test_sqlite_uses_wal_and_busy_timeout(self):
        with app.connect() as db:
            self.assertEqual(db.execute('PRAGMA journal_mode').fetchone()[0], 'wal')
            self.assertEqual(db.execute('PRAGMA busy_timeout').fetchone()[0], 30000)

    def test_review_repairs_once_then_passes(self):
        responses = ['Kế hoạch', 'Thiếu chức năng', '{"passed":false,"issues":["Thiếu xóa"]}', 'Đã thêm xóa', '{"passed":true,"issues":[]}']
        with patch.object(app, 'ollama_reply', side_effect=responses) as model:
            app.run('test', 'Làm ứng dụng', 'ollama')
        self.assertEqual(model.call_count, 5)
        self.assertEqual(self.row()['status'], 'completed')
        self.assertIn('Thiếu xóa', model.call_args_list[3].args[0][1]['content'])
        self.assertEqual(json.loads(self.row()['output'])['result'], 'Đã thêm xóa')

    def test_review_stops_after_two_repairs(self):
        responses = ['Kế hoạch', 'Bản 1', '{"passed":false,"issues":["Thiếu"]}', 'Bản 2', '{"passed":false,"issues":["Thiếu"]}', 'Bản 3', '{"passed":false,"issues":["Thiếu"]}']
        with patch.object(app, 'ollama_reply', side_effect=responses) as model:
            app.run('test', 'Làm ứng dụng', 'ollama')
        self.assertEqual(model.call_count, 7)
        self.assertEqual(self.row()['status'], 'needs_review')
        self.assertEqual(json.loads(self.row()['output'])['result'], 'Bản 3')

    def test_invalid_review_never_claims_success(self):
        with patch.object(app, 'ollama_reply', side_effect=['Kế hoạch','Kết quả','Có vẻ tốt']):
            app.run('test', 'Làm ứng dụng', 'ollama')
        self.assertEqual(self.row()['status'], 'needs_review')
        for value in ('{"passed":"false","issues":[]}', '{"passed":true,"issues":["Lỗi"]}', '{"passed":false,"issues":[]}', '[]'):
            self.assertIsNone(app.parse_review(value))

    def test_cancel_queued_task_never_calls_model(self):
        self.assertEqual(app.task_action('test','cancel')[0], 200)
        with patch.object(app, 'ollama_reply') as model:
            app.run('test','Không chạy','ollama')
        model.assert_not_called()
        self.assertEqual(self.row()['status'], 'cancelled')
        self.assertEqual(app.task_action('test','cancel')[0], 409)

    def test_cancel_inflight_discards_response_and_stops_following_steps(self):
        import threading
        entered, release = threading.Event(), threading.Event()
        def reply(messages):
            entered.set()
            release.wait(5)
            return 'Không được lưu'
        with patch.object(app, 'ollama_reply', side_effect=reply) as model:
            worker = threading.Thread(target=app.run, args=('test','Yêu cầu','ollama'))
            worker.start()
            try:
                self.assertTrue(entered.wait(2))
                self.assertEqual(app.task_action('test','cancel')[0], 200)
            finally:
                release.set()
                worker.join(5)
            self.assertFalse(worker.is_alive())
            self.assertEqual(model.call_count, 1)
        self.assertEqual(self.row()['status'], 'cancelled')
        self.assertEqual(self.row()['output'], '{}')

    def test_approve_is_explicit_and_preserves_result(self):
        self.assertEqual(app.task_action('test','approve')[0], 409)
        app.update('test', mode='ollama', status='needs_review', output=json.dumps({'result':'Nội dung'}))
        self.assertEqual(app.task_action('test','approve')[0], 200)
        self.assertEqual(self.row()['status'], 'approved')
        self.assertEqual(json.loads(self.row()['output'])['result'], 'Nội dung')
        self.assertEqual(app.task_action('test','approve')[0], 409)
        self.assertEqual(app.task_action('test','cancel')[0], 409)
        self.assertEqual(app.task_action('missing','cancel')[0], 404)

    def test_demo_cannot_be_approved(self):
        app.run('test','Mô phỏng','demo')
        self.assertEqual(app.task_action('test','approve')[0], 409)

    def test_product_validation_triggers_repair_and_blocks_bad_approval(self):
        with app.connect() as db:
            db.execute('INSERT INTO task_products VALUES (?,1)', ('test',))
        bad = json.dumps({'files':[{'path':'../../bad','content':'x'}]})
        good = json.dumps({'files':[{'path':'main.py','content':'print("Hi")'}]})
        responses = ['Kế hoạch', bad, '{"passed":true,"issues":[]}', good, '{"passed":true,"issues":[]}']
        with patch.object(app, 'ollama_reply', side_effect=responses):
            app.run('test','Tạo app','ollama')
        self.assertEqual(self.row()['status'], 'completed')
        self.assertEqual(app.product_files('test')[1]['files'][0]['path'], 'main.py')
        app.update('test', mode='ollama', output=json.dumps({'result':bad}))
        self.assertEqual(app.task_action('test','approve')[0], 409)
        self.assertEqual(app.product_files('test')[0], 409)
        self.assertEqual(app.product_files('missing')[0], 404)

    def test_revision_uses_immutable_snapshot_in_each_role(self):
        source = [{'path':'main.py','content':'print("old")'}]
        with app.connect() as db:
            db.execute('INSERT INTO task_products VALUES (?,1)', ('test',))
            db.execute('INSERT INTO task_sources VALUES (?,?,?,?)', ('test','parent',json.dumps(source),'Tạo ứng dụng'))
        product = json.dumps({'files':[{'path':'main.py','content':'print("new")'}]})
        with patch.object(app, 'ollama_reply', side_effect=['Kế hoạch',product,'{"passed":true,"issues":[]}']) as model:
            app.run('test','Sửa lời chào','ollama')
        for call in model.call_args_list:
            context = json.loads(call.args[0][1]['content'])
            self.assertEqual(context['source_files'], source)
            self.assertEqual(context['original_request'], 'Tạo ứng dụng')
        self.assertEqual(self.row()['status'], 'completed')
        self.assertEqual(json.loads(app.task_source('test')['files']), source)
        self.assertEqual(app.public_task(self.row())['parent_id'], 'parent')

    def test_diff_reports_added_modified_deleted_and_unchanged(self):
        before = [{'path':'keep.txt','content':'same'}, {'path':'edit.py','content':'old'}, {'path':'remove.txt','content':'gone'}]
        after = [{'path':'keep.txt','content':'same'}, {'path':'edit.py','content':'new'}, {'path':'add.txt','content':'new file'}]
        with app.connect() as db:
            db.execute('INSERT INTO task_products VALUES (?,1)', ('test',))
            db.execute('INSERT INTO task_sources VALUES (?,?,?,?)', ('test','parent',json.dumps(before),'Original'))
        app.update('test', status='completed', output=json.dumps({'result':json.dumps({'files':after})}))
        status, diff = app.product_diff('test')
        self.assertEqual(status, 200)
        self.assertEqual({change['path']:change['kind'] for change in diff['changes']}, {'add.txt':'added','edit.py':'modified','remove.txt':'deleted'})
        self.assertIn('-old', next(change['diff'] for change in diff['changes'] if change['path']=='edit.py'))
        self.assertEqual(app.product_diff('unknown')[0], 404)

    def test_real_syntax_error_overrides_ai_pass_and_gets_repaired(self):
        with app.connect() as db:
            db.execute('INSERT INTO task_products VALUES (?,1)', ('test',))
        bad = json.dumps({'files':[{'path':'main.py','content':'def broken(:'}]})
        good = json.dumps({'files':[{'path':'main.py','content':'print("Hi")'}]})
        with patch.object(app, 'ollama_reply', side_effect=['Kế hoạch',bad,'{"passed":true,"issues":[]}',good,'{"passed":true,"issues":[]}']) as model:
            app.run('test','Tạo Python','ollama')
        self.assertEqual(self.row()['status'], 'completed')
        self.assertEqual(model.call_count, 5)
        repair_context = json.loads(model.call_args_list[3].args[0][1]['content'])
        review = json.loads(repair_context['review'])
        self.assertFalse(review['passed'])
        self.assertIn('main.py', review['issues'][0])
        self.assertIn('Dòng 1', review['issues'][0])

    def test_unavailable_checker_does_not_claim_success(self):
        with app.connect() as db:
            db.execute('INSERT INTO task_products VALUES (?,1)', ('test',))
        product = json.dumps({'files':[{'path':'main.py','content':'pass'}]})
        with patch.object(app, 'ollama_reply', side_effect=['Kế hoạch',product,'{"passed":true,"issues":[]}']), patch.object(app, 'check_files', return_value={'status':'unavailable'}):
            app.run('test','Tạo Python','ollama')
        self.assertEqual(self.row()['status'], 'needs_review')

    def test_cancel_stalled_stream_releases_queue_for_next_task(self):
        import threading, time
        entered, release = threading.Event(), threading.Event()
        class StalledOllama(app.BaseHTTPRequestHandler):
            def do_POST(self):
                self.rfile.read(int(self.headers['Content-Length']))
                self.send_response(200)
                self.end_headers()
                self.wfile.write(b'{"message":')
                self.wfile.flush()
                entered.set()
                release.wait(8)
        server = app.ThreadingHTTPServer(('127.0.0.1',0), StalledOllama)
        helper = threading.Thread(target=server.serve_forever,daemon=True)
        helper.start()
        with app.connect() as db:
            db.execute('INSERT INTO tasks VALUES (?,?,?,?,?,?,?)', ('next','Next','demo','queued','','{}','now'))
        try:
            with patch.dict(app.os.environ, {'OLLAMA_BASE_URL':'http://127.0.0.1:'+str(server.server_port)}):
                app.enqueue_task('test','Will hang','ollama')
                self.assertTrue(entered.wait(3))
                app.enqueue_task('next','Next','demo')
                start = time.monotonic()
                self.assertEqual(app.task_action('test','cancel')[0], 200)
                while time.monotonic()-start < 3:
                    with app.connect() as db:
                        status = db.execute('SELECT status FROM tasks WHERE id=?',('next',)).fetchone()[0]
                    if status == 'completed':
                        break
                    time.sleep(.02)
                self.assertEqual(status, 'completed')
                self.assertEqual(self.row()['status'], 'cancelled')
                self.assertEqual(self.row()['output'], '{}')
        finally:
            release.set()
            app.TASK_QUEUE.join()
            server.shutdown(); server.server_close(); helper.join()

    def test_unsupported_product_is_not_marked_completed_by_ai_alone(self):
        with app.connect() as db:
            db.execute('INSERT INTO task_products VALUES (?,1)', ('test',))
        product = json.dumps({'files':[{'path':'index.html','content':'<html></html>'}]})
        with patch.object(app, 'ollama_reply', side_effect=['Plan', product, '{"passed":true,"issues":[]}']):
            app.run('test','Build HTML','ollama')
        self.assertEqual(self.row()['status'], 'needs_review')
        self.assertIn('Chỉ có AI', self.row()['stage'])

if __name__ == '__main__':
    unittest.main()
