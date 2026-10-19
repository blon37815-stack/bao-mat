import io
import json
from pathlib import Path
import sqlite3
import tempfile
import threading
import unittest
from unittest.mock import patch
import urllib.error
import urllib.request
import zipfile

import app
from task_deletion import TASK_TABLES


class TaskDeletionTest(unittest.TestCase):
    def setUp(self):
        self.temporary=tempfile.TemporaryDirectory();self.addCleanup(self.temporary.cleanup)
        for name,value in (('DB',Path(self.temporary.name)/'tasks.sqlite3'),('TASK_QUEUE',app.TaskQueue(maxsize=10)),('ACTIVE_CANCEL',{}),('TASK_DELETE_PREVIEWS',{})):
            patcher=patch.object(app,name,value);patcher.start();self.addCleanup(patcher.stop)

    def seed(self,task_id='finished',status='completed'):
        result=json.dumps({'files':[{'path':'notes.json','content':'{"title":"tiếng Việt"}'}]},ensure_ascii=False)
        with app.connect() as db:
            db.execute('INSERT INTO tasks VALUES (?,?,?,?,?,?,?)',(task_id,'Công việc '+task_id,'demo',status,'Đã kết thúc',json.dumps({'result':result},ensure_ascii=False),app.utc_now()))
            db.execute('INSERT INTO task_products VALUES (?,1)',(task_id,))
            db.execute('INSERT INTO task_memory VALUES (?,?)',(task_id,'Bộ nhớ riêng'))
            db.execute('INSERT INTO task_assignment VALUES (?,?,?,?)',(task_id,'data',20,'source'))
            db.execute('INSERT INTO task_generation VALUES (?,?,?)',(task_id,'per_file',5))
            db.execute('INSERT INTO task_requirements VALUES (?,?)',(task_id,'{}'))
            db.execute('INSERT INTO task_timing VALUES (?,?,?)',(task_id,'now','now'))
            step_id=db.execute('INSERT INTO task_steps(task_id,role,attempt,started_at,finished_at,status,output) VALUES (?,?,1,?,?,?,?)',(task_id,'result','now','now','completed',result)).lastrowid
            db.execute('INSERT INTO task_step_cleanup VALUES (?,?)',(step_id,'now'))
            db.execute('INSERT OR IGNORE INTO documents VALUES (?,?,?,?)',('library','Tài liệu chung','Giữ thư viện','now'))
            db.execute('INSERT OR IGNORE INTO bot_preferences VALUES (?,?,?)',('plan','Tên chung','Giữ thiết lập'))
            db.execute('INSERT INTO task_documents VALUES (?,?,?,?)',(task_id,'library','Tài liệu chung','Bản chụp riêng'))
            db.execute('INSERT INTO task_bot_preferences VALUES (?,?)',(task_id,'{}'))
        return result

    def test_one_finished_task_is_deleted_after_a_restorable_backup_without_other_data_loss(self):
        self.seed();self.seed('keep')
        app.save_memory('Bộ nhớ chung')
        status,preview=app.preview_task_delete('finished');self.assertEqual(status,200)
        status,result=app.delete_task('finished',preview['token'],'finished')
        self.assertEqual(status,200)
        with app.connect() as db:
            self.assertIsNone(db.execute('SELECT 1 FROM tasks WHERE id="finished"').fetchone())
            for table in TASK_TABLES:self.assertEqual(db.execute('SELECT COUNT(*) FROM '+table+' WHERE task_id="finished"').fetchone()[0],0)
            self.assertEqual(db.execute('SELECT COUNT(*) FROM task_step_cleanup').fetchone()[0],1)
            self.assertEqual(db.execute('SELECT COUNT(*) FROM tasks').fetchone()[0],1)
            self.assertEqual(db.execute('SELECT COUNT(*) FROM documents').fetchone()[0],1)
            self.assertEqual(db.execute('SELECT COUNT(*) FROM bot_preferences').fetchone()[0],1)
        self.assertEqual(app.get_memory(),'Bộ nhớ chung')
        with zipfile.ZipFile(app.DB.parent/'backups'/result['backup_file']) as archive:
            restored=Path(self.temporary.name)/'restored.sqlite3';restored.write_bytes(archive.read('tasks.sqlite3'))
        with sqlite3.connect(restored) as db:
            self.assertEqual(db.execute('PRAGMA integrity_check').fetchone()[0],'ok')
            self.assertEqual(db.execute('SELECT COUNT(*) FROM tasks').fetchone()[0],2)
            self.assertEqual(db.execute('SELECT COUNT(*) FROM task_documents WHERE task_id="finished"').fetchone()[0],1)

    def test_running_queued_and_cancelled_but_still_active_tasks_cannot_be_deleted(self):
        for state in ('queued','running'):
            self.seed(state,state)
            self.assertEqual(app.preview_task_delete(state)[0],409)
        self.seed('cancelled','cancelled');app.ACTIVE_CANCEL['cancelled']=threading.Event()
        self.assertEqual(app.preview_task_delete('cancelled')[0],409)
        app.ACTIVE_CANCEL.clear()
        _,preview=app.preview_task_delete('cancelled');app.ACTIVE_CANCEL['cancelled']=threading.Event()
        self.assertEqual(app.delete_task('cancelled',preview['token'],'cancelled')[0],409)

    def test_backup_failure_expiry_confirmation_and_changed_preview_keep_the_task(self):
        self.seed()
        _,preview=app.preview_task_delete('finished')
        self.assertEqual(app.delete_task('finished',preview['token'],'wrong')[0],400)
        with patch.object(app,'backup_database',side_effect=OSError('Disk unavailable')):
            self.assertEqual(app.delete_task('finished',preview['token'],'finished')[0],500)
        with app.connect() as db:db.execute('UPDATE task_steps SET output=? WHERE task_id=?',('Changed','finished'))
        self.assertEqual(app.delete_task('finished',preview['token'],'finished')[0],409)
        _,preview=app.preview_task_delete('finished');app.TASK_DELETE_PREVIEWS[preview['token']]['created']-=301
        self.assertEqual(app.delete_task('finished',preview['token'],'finished')[0],409)
        with app.connect() as db:self.assertIsNotNone(db.execute('SELECT 1 FROM tasks WHERE id="finished"').fetchone())

    def test_change_during_backup_is_rechecked_and_fsync_failure_never_deletes(self):
        self.seed();_,preview=app.preview_task_delete('finished')
        original_backup=app.backup_database
        def changed(source):
            payload=original_backup(source)
            with app.connect() as db:db.execute('UPDATE tasks SET stage="Changed" WHERE id="finished"')
            return payload
        with patch.object(app,'backup_database',side_effect=changed):
            status,result=app.delete_task('finished',preview['token'],'finished')
        self.assertEqual(status,409);self.assertTrue(result['backup_file'])
        _,preview=app.preview_task_delete('finished')
        with patch.object(app.os,'fsync',side_effect=OSError('Disk unavailable')):
            status,result=app.delete_task('finished',preview['token'],'finished')
        self.assertEqual(status,500);self.assertIsNone(result['backup_file'])
        with app.connect() as db:self.assertEqual(db.execute('SELECT COUNT(*) FROM tasks').fetchone()[0],1)

    def test_linked_versions_keep_source_diff_and_a_deleted_retry_can_be_replaced(self):
        original=self.seed('parent','needs_review')
        status,child=app.save_product_revision('parent',[{'path':'notes.json','content':'{"title":"sửa"}'}])
        self.assertEqual(status,201)
        _,preview=app.preview_task_delete('parent')
        self.assertEqual(preview['related'],1)
        self.assertEqual(app.delete_task('parent',preview['token'],'parent')[0],200)
        child_task=next(task for task in app.list_tasks()['tasks'] if task['id']==child['id'])
        self.assertEqual(child_task['parent_deleted'],1)
        self.assertEqual(app.product_diff(child['id'])[1]['changes'][0]['kind'],'modified')
        self.assertEqual(app.task_source(child['id'])['files'],json.dumps(json.loads(original)['files'],ensure_ascii=False))
        self.seed('retry-parent','needs_review')
        with patch.object(app,'enqueue_task'):
            _,retry=app.retry_task('retry-parent')
            with app.connect() as db:db.execute('UPDATE tasks SET status="interrupted" WHERE id=?',(retry['id'],))
            _,preview=app.preview_task_delete(retry['id'])
            self.assertEqual(app.delete_task(retry['id'],preview['token'],retry['id'])[0],200)
            self.assertEqual(app.preview_task_delete('retry-parent')[1]['related'],0)
            status,replacement=app.retry_task('retry-parent')
        self.assertEqual(status,202);self.assertNotEqual(retry['id'],replacement['id'])

    def test_compact_list_is_paginated_and_excludes_large_outputs_and_private_context(self):
        for number in range(23):self.seed(str(number))
        with app.connect() as db:db.execute('UPDATE tasks SET output=?', (json.dumps({'result':'private '*10000}),))
        page=app.list_tasks(compact=True)
        self.assertEqual((page['total'],page['limit'],len(page['tasks'])),(23,20,20))
        self.assertEqual(len(app.list_tasks(offset=20,compact=True)['tasks']),3)
        for task in page['tasks']:
            for key in ('output','project_memory','bot_preferences'):self.assertNotIn(key,task)
            self.assertEqual(task['has_result'],1)
        self.assertLess(len(json.dumps(page)),30000)

    def test_http_delete_requires_token_preview_and_serves_only_named_backups(self):
        self.seed()
        server=app.ThreadingHTTPServer(('127.0.0.1',0),app.Handler)
        worker=threading.Thread(target=server.serve_forever,daemon=True);worker.start()
        base='http://127.0.0.1:'+str(server.server_port)
        def post(path,data,token=True):
            headers={'Content-Type':'application/json'}
            if token:headers['X-CSRF-Token']=app.CSRF_TOKEN
            with urllib.request.urlopen(urllib.request.Request(base+path,data=json.dumps(data).encode(),headers=headers)) as response:return json.load(response)
        try:
            for endpoint in ('delete-preview','delete'):
                with self.assertRaises(urllib.error.HTTPError) as error:post('/api/tasks/finished/'+endpoint,{},False)
                self.assertEqual(error.exception.code,403)
            preview=post('/api/tasks/finished/delete-preview',{})
            result=post('/api/tasks/finished/delete',{'token':preview['token'],'confirmation':'finished'})
            with urllib.request.urlopen(base+'/api/backups/'+result['backup_file']) as response:
                self.assertTrue(zipfile.is_zipfile(io.BytesIO(response.read())))
            with urllib.request.urlopen(base+'/api/tasks?compact=1') as response:self.assertEqual(json.load(response)['total'],0)
            with self.assertRaises(urllib.error.HTTPError) as error:urllib.request.urlopen(base+'/api/tasks/finished')
            self.assertEqual(error.exception.code,404)
        finally:server.shutdown();server.server_close();worker.join()
