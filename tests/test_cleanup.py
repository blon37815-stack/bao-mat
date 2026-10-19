import io
import json
from contextlib import closing
from pathlib import Path
import sqlite3
import tempfile
import threading
import time
import unittest
from unittest.mock import patch
import urllib.error
import urllib.request
import zipfile

import app


class CleanupTest(unittest.TestCase):
    def setUp(self):
        self.temporary=tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        for name,value in (('DB',Path(self.temporary.name)/'tasks.db'),('TASK_QUEUE',app.TaskQueue(maxsize=10)),('ACTIVE_CANCEL',{}),('CLEANUP_PREVIEWS',{})):
            patcher=patch.object(app,name,value);patcher.start();self.addCleanup(patcher.stop)
        app.save_memory('Bộ nhớ chung phải giữ')

    def seed(self,identifier='old',status='completed',created='2020-01-01T00:00:00+00:00'):
        with app.connect() as db:
            db.execute('INSERT INTO tasks VALUES (?,?,?,?,?,?,?)',(identifier,'Yêu cầu '+identifier,'demo',status,'','{"result":"final"}',created))
            db.execute('INSERT INTO task_memory VALUES (?,?)',(identifier,'Bộ nhớ lúc tạo'))
            db.execute('INSERT INTO task_products VALUES (?,1)',(identifier,))
            db.execute('INSERT INTO task_requirements VALUES (?,?)',(identifier,'{}'))
            db.execute('INSERT INTO task_generation VALUES (?,?,?)',(identifier,'per_file',5))
            db.execute('INSERT INTO task_assignment VALUES (?,?,?,?)',(identifier,'data',20,'source'))
            db.execute('INSERT INTO task_timing VALUES (?,?,?)',(identifier,created,created))
            db.execute('INSERT INTO task_steps(task_id,role,attempt,started_at,finished_at,status,output) VALUES (?,?,1,?,?,?,?)',
                       (identifier,'result',created,created,'completed','Nội dung lượt cũ'))

    def preview(self,scope='history'):
        status,data=app.preview_cleanup(scope,30)
        self.assertEqual(status,200)
        self.assertNotIn('ids',data);self.assertNotIn('fingerprint',data)
        return data

    def assert_task_exists(self,identifier='old'):
        with app.connect() as db:
            self.assertIsNotNone(db.execute('SELECT id FROM tasks WHERE id=?',(identifier,)).fetchone())

    def test_history_cleanup_keeps_final_outputs_and_metadata_and_backup(self):
        self.seed()
        preview=self.preview()
        self.assertEqual(preview['items'],1)
        self.assert_task_exists()
        status,result=app.perform_cleanup(preview['token'],'DỌN')
        self.assertEqual(status,200)
        _,history=app.task_history('old')
        self.assertEqual(history['steps'][0]['output'],'')
        self.assertTrue(history['steps'][0]['cleared_at'])
        self.assertEqual(history['steps'][0]['status'],'completed')
        with app.connect() as db:
            self.assertEqual(json.loads(db.execute('SELECT output FROM tasks').fetchone()[0])['result'],'final')
            self.assertEqual(db.execute('SELECT content FROM task_memory').fetchone()[0],'Bộ nhớ lúc tạo')
        self.assertEqual(app.get_memory(),'Bộ nhớ chung phải giữ')
        self.assertEqual(self.preview()['items'],0)
        with zipfile.ZipFile(app.DB.parent/'backups'/result['backup_file']) as archive:
            restored=Path(self.temporary.name)/'restored.db'
            restored.write_bytes(archive.read('tasks.sqlite3'))
        with closing(sqlite3.connect(restored)) as db:
            self.assertEqual(db.execute('PRAGMA integrity_check').fetchone()[0],'ok')
            self.assertEqual(db.execute('SELECT output FROM task_steps').fetchone()[0],'Nội dung lượt cũ')

    def test_task_cleanup_preserves_recent_work_and_all_relationship_participants(self):
        for identifier in ('old','parent','version','retry-parent','retry-child'):
            self.seed(identifier)
        self.seed('recent',created=app.utc_now())
        self.seed('recently-finished')
        with app.connect() as db:
            db.execute('UPDATE task_timing SET finished_at=? WHERE task_id=?',(app.utc_now(),'recently-finished'))
            db.execute('INSERT INTO task_sources VALUES (?,?,?,?)',('version','parent','[]','Request'))
            db.execute('INSERT INTO task_retries VALUES (?,?)',('retry-parent','retry-child'))
        preview=self.preview('tasks')
        self.assertEqual((preview['items'],preview['protected']),(1,4))
        self.assertEqual(app.perform_cleanup(preview['token'],'DỌN')[0],200)
        for identifier in ('parent','version','retry-parent','retry-child','recent','recently-finished'):
            self.assert_task_exists(identifier)
        with app.connect() as db:
            self.assertIsNone(db.execute('SELECT id FROM tasks WHERE id="old"').fetchone())
            for table in ('task_memory','task_products','task_timing','task_steps','task_requirements','task_generation','task_assignment'):
                self.assertEqual(db.execute('SELECT COUNT(*) FROM '+table+' WHERE task_id="old"').fetchone()[0],0)
            self.assertEqual(db.execute('SELECT COUNT(*) FROM task_sources').fetchone()[0],1)
            self.assertEqual(db.execute('SELECT COUNT(*) FROM task_retries').fetchone()[0],1)
        self.assertEqual(app.get_memory(),'Bộ nhớ chung phải giữ')

    def test_confirmation_expiry_and_changed_data_require_new_preview(self):
        self.seed()
        preview=self.preview('tasks')
        self.assertEqual(app.perform_cleanup(preview['token'],'DON')[0],400)
        self.assertEqual(app.perform_cleanup('missing','DỌN')[0],409)
        app.CLEANUP_PREVIEWS[preview['token']]['created']=time.monotonic()-301
        self.assertEqual(app.perform_cleanup(preview['token'],'DỌN')[0],409)
        preview=self.preview('tasks')
        app.update('old',output='{"result":"changed"}')
        self.assertEqual(app.perform_cleanup(preview['token'],'DỌN')[0],409)
        self.assert_task_exists()
        self.assertFalse((app.DB.parent/'backups').exists())

    def test_active_queued_and_cancelled_but_still_running_requests_block_cleanup(self):
        self.seed()
        preview=self.preview('tasks')
        self.seed('queued',status='queued')
        self.assertEqual(app.perform_cleanup(preview['token'],'DỌN')[0],409)
        app.update('queued',status='cancelled')
        app.ACTIVE_CANCEL['queued']=threading.Event()
        self.assertEqual(app.perform_cleanup(preview['token'],'DỌN')[0],409)
        app.ACTIVE_CANCEL.clear()
        app.TASK_QUEUE.put_nowait(('held','unused','demo'))
        self.assertEqual(app.perform_cleanup(preview['token'],'DỌN')[0],409)
        self.assert_task_exists()
        self.assertFalse((app.DB.parent/'backups').exists())

    def test_backup_failure_leaves_data_untouched(self):
        self.seed()
        preview=self.preview('tasks')
        with patch.object(app,'backup_database',side_effect=OSError('Disk full')):
            with self.assertRaises(OSError):
                app.perform_cleanup(preview['token'],'DỌN')
        self.assert_task_exists()
        # A writable database but an unwritable backup path must also prevent deletion.
        (app.DB.parent/'backups').write_text('Existing file blocking directory')
        with self.assertRaises(OSError):
            app.perform_cleanup(preview['token'],'DỌN')
        self.assert_task_exists()

    def test_invalid_retention_and_scope_are_rejected(self):
        for days in (True,0,-1,3651,'30',None,1.5):
            self.assertEqual(app.preview_cleanup('history',days)[0],400)
        self.assertEqual(app.preview_cleanup('unknown',30)[0],400)

    def test_data_changed_during_backup_is_checked_again_before_delete(self):
        self.seed()
        preview=self.preview('tasks')
        real_backup=app.backup_database
        def backup_then_change(db):
            payload=real_backup(db)
            app.update('old',output='{"result":"newer"}')
            return payload
        with patch.object(app,'backup_database',side_effect=backup_then_change):
            status,result=app.perform_cleanup(preview['token'],'DỌN')
        self.assertEqual(status,409)
        self.assertTrue((app.DB.parent/'backups'/result['backup_file']).is_file())
        self.assert_task_exists()
        with app.connect() as db:
            self.assertEqual(db.execute('SELECT COUNT(*) FROM task_steps').fetchone()[0],1)

    def test_http_cleanup_requires_token_and_backup_download_is_bounded(self):
        self.seed()
        server=app.ThreadingHTTPServer(('127.0.0.1',0),app.Handler)
        worker=threading.Thread(target=server.serve_forever,daemon=True);worker.start()
        base='http://127.0.0.1:'+str(server.server_port)
        def post(path,data,token=True):
            headers={'Content-Type':'application/json'}
            if token:headers['X-CSRF-Token']=app.CSRF_TOKEN
            request=urllib.request.Request(base+path,data=json.dumps(data).encode(),headers=headers)
            return urllib.request.urlopen(request)
        try:
            with self.assertRaises(urllib.error.HTTPError) as error:
                post('/api/cleanup/preview',{'scope':'tasks','days':30},False)
            self.assertEqual(error.exception.code,403)
            with post('/api/cleanup/preview',{'scope':'tasks','days':30}) as response:
                preview=json.load(response)
            with post('/api/cleanup/apply',{'token':preview['token'],'confirmation':'DỌN'}) as response:
                result=json.load(response)
            with urllib.request.urlopen(base+'/api/backups/'+result['backup_file']) as response:
                self.assertEqual(response.headers['Content-Type'],'application/zip')
                with zipfile.ZipFile(io.BytesIO(response.read())) as archive:
                    self.assertIn('tasks.sqlite3',archive.namelist())
            for name in ('tasks.db','%2e%2e%2ftasks.db','cleanup-invalid.zip'):
                with self.assertRaises(urllib.error.HTTPError) as error:
                    urllib.request.urlopen(base+'/api/backups/'+name)
                self.assertEqual(error.exception.code,404)
        finally:
            server.shutdown();server.server_close();worker.join()
