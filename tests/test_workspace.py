import json
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import patch
import urllib.error
import urllib.request

import app
from artifacts import parse_files
import workspace_data
from web_preview import preview_html


class WorkspaceTest(unittest.TestCase):
    def setUp(self):
        self.temporary=tempfile.TemporaryDirectory();self.addCleanup(self.temporary.cleanup)
        for name,value in (('DB',Path(self.temporary.name)/'tasks.db'),('TASK_QUEUE',app.TaskQueue(maxsize=10)),('ACTIVE_CANCEL',{})):
            patcher=patch.object(app,name,value);patcher.start();self.addCleanup(patcher.stop)
        self.server=app.ThreadingHTTPServer(('127.0.0.1',0),app.Handler)
        self.worker=threading.Thread(target=self.server.serve_forever,daemon=True);self.worker.start()
        self.base='http://127.0.0.1:'+str(self.server.server_port)
        self.addCleanup(self.close_server)
        self.enqueue=patch.object(app,'enqueue_task');self.enqueue.start();self.addCleanup(self.enqueue.stop)

    def close_server(self):
        self.server.shutdown();self.server.server_close();self.worker.join()

    def post(self,path,data,token=True):
        headers={'Content-Type':'application/json'}
        if token:headers['X-CSRF-Token']=app.CSRF_TOKEN
        request=urllib.request.Request(self.base+path,data=json.dumps(data).encode(),headers=headers)
        with urllib.request.urlopen(request) as response:return response.status,json.load(response)

    def get(self,path):
        with urllib.request.urlopen(self.base+path) as response:return json.load(response)

    def test_documents_and_bot_preferences_are_frozen_for_new_tasks_and_retries(self):
        _,document=self.post('/api/documents',{'title':'Tiêu chí','content':'Dùng tiếng Việt có dấu'})
        self.post('/api/bots',{'id':'planner','name':'Trưởng nhóm','instructions':'Trả ngắn gọn'})
        _,task=self.post('/api/tasks',{'prompt':'Lên kế hoạch','mode':'ollama','document_ids':[document['id']]})
        self.post('/api/documents',{'id':document['id'],'title':'Đã đổi','content':'Nội dung mới'})
        self.post('/api/bots',{'id':'planner','name':'Tên mới','instructions':'Hướng dẫn mới'})
        self.post('/api/documents/'+document['id']+'/delete',{'confirmation':document['id']})
        contexts=[]
        def provider(messages):
            context=json.loads(messages[1]['content']);contexts.append(context)
            self.assertEqual(context['documents'][0]['content'],'Dùng tiếng Việt có dấu')
            return '{"passed":true,"issues":[]}' if 'result' in context else 'Kế hoạch đầy đủ'
        with patch.object(app,'ollama_reply',side_effect=provider):app.run(task['id'],'Lên kế hoạch','ollama')
        self.assertEqual(contexts[0]['bot_preferences']['name'],'Trưởng nhóm')
        self.assertEqual(contexts[0]['bot_preferences']['instructions'],'Trả ngắn gọn')
        self.assertEqual(len(contexts),4)
        row=self.get('/api/tasks/'+task['id'])
        self.assertEqual(row['status'],'completed')
        self.assertEqual(row['documents'][0]['title'],'Tiêu chí')
        self.assertEqual(self.get('/api/documents')['documents'],[])
        with app.connect() as db:db.execute("UPDATE tasks SET status='needs_review' WHERE id=?",(task['id'],))
        _,retry=self.post('/api/tasks/'+task['id']+'/retry',{})
        context=app.workspace_context(retry['id'])
        self.assertEqual(context['bot_preferences']['planner']['name'],'Trưởng nhóm')
        self.assertEqual(context['documents'][0]['content'],'Dùng tiếng Việt có dấu')
        _,report=app.export_task(task['id'],'all')
        self.assertIn('Tài liệu đính kèm: Tiêu chí',report.decode())

    def test_new_document_endpoints_validate_limits_and_require_protected_writes(self):
        self.assertEqual(len(self.get('/api/bots')['bots']),9)
        for path,data in [('/api/documents',{'title':'Tài liệu','content':'abc'}),('/api/bots',{'id':'plan','name':'Bot','instructions':''}),('/api/preview',{'files':[],'entry':'index.html'})]:
            with self.assertRaises(urllib.error.HTTPError) as error:self.post(path,data,False)
            self.assertEqual(error.exception.code,403)
        with self.assertRaises(urllib.error.HTTPError) as error:self.post('/api/bots',{'id':'manager','name':'Đổi giới hạn','instructions':'Vô hạn'})
        self.assertEqual(error.exception.code,400)
        _,document=self.post('/api/documents',{'title':'Tiêu chí','content':'x'*17000})
        for ids in ([document['id']],['missing'],[document['id']]*2):
            with self.assertRaises(urllib.error.HTTPError) as error:self.post('/api/tasks',{'prompt':'Việc thử','mode':'demo','document_ids':ids})
            self.assertEqual(error.exception.code,400)
        with app.connect() as db:
            self.assertEqual(db.execute('SELECT COUNT(*) FROM tasks').fetchone()[0],0)
            self.assertEqual(db.execute('SELECT COUNT(*) FROM task_documents').fetchone()[0],0)
        with self.assertRaises(urllib.error.HTTPError) as error:self.post('/api/documents/'+document['id']+'/delete',{'confirmation':'wrong'})
        self.assertEqual(error.exception.code,400)
        self.assertEqual(self.get('/api/documents/'+document['id'])['content'],'x'*17000)

    def test_document_quota_is_enforced_without_dropping_existing_data(self):
        with app.connect() as db:
            for number in range(25):workspace_data.save_document(db,None,str(number),'x'*20000,app.utc_now())
            with self.assertRaises(ValueError):workspace_data.save_document(db,None,'Tệp dư','x',app.utc_now())
            first=workspace_data.list_documents(db)[0]
            workspace_data.save_document(db,first['id'],'Tệp ngắn','ok',app.utc_now())
            workspace_data.save_document(db,None,'Có chỗ trống','x'*10000,app.utc_now())
            self.assertEqual(len(workspace_data.list_documents(db)),26)

    def test_manual_editor_creates_unapproved_revision_and_preserves_original(self):
        original=json.dumps({'files':[{'path':'data.json','content':'{"name":"gốc"}'}]},ensure_ascii=False)
        with app.connect() as db:
            db.execute('INSERT INTO tasks VALUES (?,?,?,?,?,?,?)',('original','Dữ liệu','ollama','completed','Xong',json.dumps({'result':original}),app.utc_now()))
            db.execute('INSERT INTO task_products VALUES (?,1)',('original',))
        with patch.object(app,'model_reply',side_effect=AssertionError('Manual edit must not call a model')):
            status,revision=self.post('/api/tasks/original/edit',{'files':[{'path':'data.json','content':'{"name":"bản sửa"}'}]})
        self.assertEqual(status,201)
        self.assertEqual(parse_files(json.loads(self.get('/api/tasks/original')['output'])['result'])[0]['content'],'{"name":"gốc"}')
        row=self.get('/api/tasks/'+revision['id'])
        self.assertEqual((row['status'],row['generation_method'],row['model_calls']),('needs_review','manual',0))
        self.assertEqual(self.get('/api/tasks/'+revision['id']+'/diff')['changes'][0]['kind'],'modified')
        with self.assertRaises(urllib.error.HTTPError) as error:self.post('/api/tasks/original/edit',{'files':[{'path':'../../outside.py','content':'x'}]})
        self.assertEqual(error.exception.code,400)
        with app.connect() as db:self.assertEqual(db.execute('SELECT COUNT(*) FROM tasks').fetchone()[0],2)

    def test_static_preview_embeds_local_css_and_strips_active_content_and_urls(self):
        files=[{'path':'pages/index.html','content':'<html><head><link rel="stylesheet" href="../style.css"><script>window.evil=1</script><meta http-equiv="refresh" content="0;url=https://outside.test"></head><body><h1 onclick="evil()">Xin chào</h1><iframe src="https://outside.test"></iframe><img src="https://outside.test/pixel"><a href="https://outside.test">Link</a><style>p { color:red }</style></body></html>'},
               {'path':'style.css','content':'body { background: rgb(1, 2, 3) }'}]
        html=preview_html(files,'pages/index.html')
        self.assertIn('Content-Security-Policy',html)
        self.assertIn('background: rgb(1, 2, 3)',html)
        self.assertIn('Xin chào',html)
        for unsafe in ('<script','<iframe','onclick','https://outside.test','window.evil','http-equiv="refresh"'):
            self.assertNotIn(unsafe,html)
        with self.assertRaises(ValueError):preview_html(files,'../../outside.html')
        _,result=self.post('/api/preview',{'files':files,'entry':'pages/index.html'})
        self.assertEqual(result['html'],html)
