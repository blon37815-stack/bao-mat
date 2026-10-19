import concurrent.futures
import json
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import Mock, patch
import urllib.error
import urllib.request

import app


class QueueLimitTest(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.db_patch = patch.object(app,'DB',Path(self.temporary.name)/'tasks.db')
        self.queue = app.TaskQueue(maxsize=1)
        self.queue_patch = patch.object(app,'TASK_QUEUE',self.queue)
        self.worker_patch = patch.object(app,'WORKER',Mock(is_alive=Mock(return_value=True)))
        self.db_patch.start(); self.queue_patch.start(); self.worker_patch.start()
        app.save_memory('Giữ bộ nhớ')

    def tearDown(self):
        self.worker_patch.stop(); self.queue_patch.stop(); self.db_patch.stop()
        self.temporary.cleanup()

    def seed(self, status):
        with app.connect() as db:
            db.execute('INSERT INTO tasks VALUES (?,?,?,?,?,?,?)',('original','Yêu cầu','demo',status,'','{"result":"old"}','now'))
            db.execute('INSERT INTO task_memory VALUES (?,?)',('original','Bộ nhớ cũ'))
            db.execute('INSERT INTO task_products VALUES (?,1)',('original',))
            db.execute('INSERT INTO task_sources VALUES (?,?,?,?)',('original','parent','[]','Earlier request'))

    def test_cancelling_waiting_work_frees_capacity_immediately(self):
        self.seed('queued')
        app.enqueue_task('original','Yêu cầu','demo')
        self.assertTrue(self.queue.full())
        self.assertEqual(app.task_action('original','cancel')[0],200)
        self.assertTrue(self.queue.empty())
        self.assertEqual(self.queue.unfinished_tasks,0)
        status, result = app.retry_task('original')
        self.assertEqual(status,202)
        self.assertNotEqual(result['id'],'original')
        self.assertEqual(self.queue.qsize(),1)
        with app.connect() as db:
            self.assertEqual(db.execute('SELECT status FROM tasks WHERE id="original"').fetchone()[0],'cancelled')

    def test_full_queue_preserves_retry_source_and_snapshots(self):
        self.seed('needs_review')
        self.queue.put_nowait(('held','held','demo'))
        self.assertEqual(app.retry_task('original')[0],429)
        with app.connect() as db:
            self.assertEqual(db.execute('SELECT COUNT(*) FROM tasks').fetchone()[0],1)
            self.assertEqual(db.execute('SELECT COUNT(*) FROM task_retries').fetchone()[0],0)
        self.queue.get_nowait(); self.queue.task_done()
        status, result = app.retry_task('original')
        self.assertEqual(status,202)
        with app.connect() as db:
            retry = db.execute(app.TASK_SELECT+' WHERE t.id=?',(result['id'],)).fetchone()
            original = db.execute('SELECT output FROM tasks WHERE id="original"').fetchone()[0]
            source = db.execute('SELECT files FROM task_sources WHERE task_id=?',(result['id'],)).fetchone()[0]
        self.assertEqual(retry['project_memory'],'Bộ nhớ cũ')
        self.assertEqual(retry['parent_id'],'parent')
        self.assertEqual(retry['retry_of'],'original')
        self.assertEqual(source,'[]')
        self.assertEqual(original,'{"result":"old"}')

    def test_concurrent_retries_create_only_one_attempt(self):
        self.seed('failed')
        with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
            results=list(pool.map(lambda _:app.retry_task('original')[0],range(4)))
        self.assertEqual(results.count(202),1)
        self.assertEqual(results.count(409),3)
        self.assertEqual(self.queue.qsize(),1)

    def test_http_capacity_is_atomic_for_concurrent_new_tasks(self):
        server=app.ThreadingHTTPServer(('127.0.0.1',0),app.Handler)
        helper=threading.Thread(target=server.serve_forever,daemon=True)
        helper.start()
        def submit(index):
            request=urllib.request.Request('http://127.0.0.1:'+str(server.server_port)+'/api/tasks',
                data=json.dumps({'prompt':'Job '+str(index),'mode':'demo'}).encode(),
                headers={'Content-Type':'application/json','X-CSRF-Token':app.CSRF_TOKEN})
            try:
                with urllib.request.urlopen(request) as response:
                    return response.status
            except urllib.error.HTTPError as error:
                return error.code
        try:
            with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
                statuses=list(pool.map(submit,range(4)))
            self.assertEqual(statuses.count(201),1)
            self.assertEqual(statuses.count(429),3)
            with app.connect() as db:
                self.assertEqual(db.execute('SELECT COUNT(*) FROM tasks').fetchone()[0],1)
            self.assertEqual(self.queue.qsize(),1)
        finally:
            server.shutdown();server.server_close();helper.join()
