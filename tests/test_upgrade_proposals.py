import io
import hashlib
import json
from pathlib import Path
import shutil
import sqlite3
import subprocess
import tempfile
import threading
import unittest
from unittest.mock import patch
import urllib.error
import urllib.request
import zipfile

import app
import bot_tools
from maintenance import backup_database
import upgrade_proposals


class UpgradeProposalsTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)/'source'; self.root.mkdir()
        (self.root/'main.py').write_bytes(b'print("original")\n')
        (self.root/'README.md').write_text('# Original\n',encoding='utf-8')
        (self.root/'data').mkdir(); (self.root/'data/secret.txt').write_text('PRIVATE DATA')
        (self.root/'.env').write_text('PRIVATE KEY')
        for name, value in (('DB', Path(self.temp.name)/'data/tasks.db'), ('ROOT', self.root), ('TASK_QUEUE', app.TaskQueue(10))):
            change = patch.object(app, name, value); change.start(); self.addCleanup(change.stop)
        self.files = [{'path':'main.py','content':'print("candidate")\n'}, {'path':'tests/test_example.py','content':'import unittest\n'}]
        with app.connect() as db:
            db.execute('INSERT INTO tasks VALUES (?,?,?,?,?,?,?)', ('source','Nâng cấp thử','ollama','completed','Xong',json.dumps({'result':json.dumps({'files':self.files})}),app.utc_now()))
            db.execute('INSERT INTO task_products VALUES (?,1)', ('source',))
            app.platform_config.snapshot(db,'source','ollama',app_version=app.RUNTIME_INFO)
        self.server = app.ThreadingHTTPServer(('127.0.0.1',0),app.Handler)
        self.thread = threading.Thread(target=self.server.serve_forever,daemon=True); self.thread.start()
        self.base = 'http://127.0.0.1:'+str(self.server.server_port)
        self.addCleanup(self.close)

    def close(self):
        self.server.shutdown(); self.server.server_close(); self.thread.join()

    def post(self, path, body, protected=True):
        headers={'Content-Type':'application/json'}
        if protected:headers['X-CSRF-Token']=app.CSRF_TOKEN
        req=urllib.request.Request(self.base+path,json.dumps(body).encode(),headers)
        with urllib.request.urlopen(req) as response:return json.load(response)

    def get(self, path):
        with urllib.request.urlopen(self.base+path) as response:return json.load(response)

    def create(self):
        return self.post('/api/upgrades', {'task_id':'source','title':'Bản ứng viên'})['id']

    def review(self, key, decision='approved'):
        return self.post('/api/upgrades/'+key+'/review', {'decision':decision,'confirmation':key})

    def set_files(self, files):
        with app.connect() as db:
            db.execute('UPDATE tasks SET output=? WHERE id=?',(json.dumps({'result':json.dumps({'files':files})}),'source'))

    def test_copy_diff_review_download_never_touch_running_source_or_execute_code(self):
        original=(self.root/'main.py').read_bytes()
        with patch.object(app.product_runner,'check_product',side_effect=AssertionError('No implicit execution')), patch.object(app,'model_reply',side_effect=AssertionError('No inference')):
            key=self.create()
            detail=self.get('/api/upgrades/'+key)
            self.assertFalse(detail['stale'])
            self.assertEqual(detail['checks']['status'],'passed')
            self.assertEqual(len(detail['changes']),2)
            self.assertIn('-print("original")', detail['changes'][0]['diff'])
            self.assertEqual(self.review(key)['status'],'approved')
        self.assertEqual((self.root/'main.py').read_bytes(),original)
        self.assertFalse((self.root/'tests').exists())
        with urllib.request.urlopen(self.base+'/api/upgrades/'+key+'/artifact.zip') as response:
            self.assertIn('attachment',response.headers['Content-Disposition'])
            raw=response.read()
        with zipfile.ZipFile(io.BytesIO(raw)) as archive:
            self.assertEqual(archive.read('base/main.py'),original)
            self.assertIn(b'candidate',archive.read('candidate/main.py'))
            self.assertEqual(json.loads(archive.read('REVIEW.json'))['status'],'approved')
            for name, sha in json.loads(archive.read('MANIFEST.json'))['files'].items():
                self.assertEqual(hashlib.sha256(archive.read(name)).hexdigest(),sha)
            self.assertFalse(any('secret.txt' in name or '.env' in name for name in archive.namelist()))
        audit=self.get('/api/audit')['events']
        self.assertEqual({row['bot_id'] for row in audit},{'result','user'})

    def test_patch_applies_in_separate_checkout_including_missing_newline_and_empty_file(self):
        self.set_files([{'path':'main.py','content':'print("candidate")'}, {'path':'empty.py','content':''}])
        key=self.create()
        directory=upgrade_proposals.directory_for(app.DB.parent,key)
        trial=Path(self.temp.name)/'trial'; shutil.copytree(directory/'base',trial)
        applied=subprocess.run(['git','apply',str(directory/'proposal.patch')],cwd=trial,capture_output=True,text=True)
        self.assertEqual(applied.returncode,0,applied.stderr)
        self.assertEqual((trial/'main.py').read_bytes(),b'print("candidate")')
        self.assertTrue((trial/'empty.py').exists())
        self.assertEqual((self.root/'main.py').read_bytes(),b'print("original")\n')

    def test_invalid_syntax_and_stale_source_cannot_be_approved(self):
        self.set_files([{'path':'main.py','content':'def broken('}])
        broken=self.create()
        with self.assertRaises(urllib.error.HTTPError):self.review(broken)
        self.assertEqual(self.get('/api/upgrades/'+broken)['status'],'pending')
        self.set_files(self.files)
        stale=self.create()
        (self.root/'main.py').write_text('print("changed after proposal")\n')
        self.assertTrue(self.get('/api/upgrades/'+stale)['stale'])
        with self.assertRaises(urllib.error.HTTPError):self.review(stale)
        self.assertEqual(self.review(stale,'rejected')['status'],'rejected')

    def test_unsafe_targets_and_missing_source_are_rejected_without_creating_copies(self):
        for name in ('../../outside.py','.env','data/private.py','third_party/ecc/agent.md','.github/workflows/run.py'):
            self.set_files([{'path':name,'content':'x=1'}])
            with self.assertRaises(urllib.error.HTTPError):self.create()
        with self.assertRaises(urllib.error.HTTPError):self.post('/api/upgrades',{'task_id':'missing','title':'x'})
        with app.connect() as db:self.assertEqual(db.execute('SELECT COUNT(*) FROM upgrade_proposals').fetchone()[0],0)
        self.assertFalse((Path(self.temp.name)/'outside.py').exists())

    def test_tampered_candidate_is_not_downloaded_or_approved_but_can_be_deleted(self):
        key=self.create()
        directory=upgrade_proposals.directory_for(app.DB.parent,key)
        (directory/'candidate/main.py').write_text('print("tampered")')
        with self.assertRaises(urllib.error.HTTPError) as error:self.get('/api/upgrades/'+key)
        self.assertEqual(error.exception.code,409)
        with self.assertRaises(urllib.error.HTTPError):self.review(key)
        self.post('/api/upgrades/'+key+'/delete',{'confirmation':key})
        self.assertFalse(directory.exists())
        self.assertEqual(self.get('/api/upgrades')['proposals'],[])

    def test_sqlite_backup_restores_proposal_source_and_patch_without_old_cache(self):
        key=self.create()
        with app.connect() as db:backup=backup_database(db)
        restored=Path(self.temp.name)/'restored'; restored.mkdir()
        with zipfile.ZipFile(io.BytesIO(backup)) as archive:(restored/'tasks.db').write_bytes(archive.read('tasks.sqlite3'))
        with patch.object(app,'DB',restored/'tasks.db'):
            self.assertFalse((restored/'proposals').exists())
            detail=self.get('/api/upgrades/'+key)
            self.assertEqual(detail['status'],'pending')
            self.assertIn('candidate', (restored/'proposals'/key/'candidate/main.py').read_text())
        self.assertEqual((self.root/'main.py').read_bytes(),b'print("original")\n')

    def test_csrf_confirmation_and_role_policy_are_enforced(self):
        with self.assertRaises(urllib.error.HTTPError) as error:self.post('/api/upgrades',{'task_id':'source','title':'x'},False)
        self.assertEqual(error.exception.code,403)
        key=self.create()
        for path,body in [(f'/api/upgrades/{key}/review',{'decision':'approved','confirmation':'wrong'}),
                          (f'/api/upgrades/{key}/delete',{'confirmation':'wrong'})]:
            with self.assertRaises(urllib.error.HTTPError):self.post(path,body)
            with self.assertRaises(urllib.error.HTTPError) as error:self.post(path,body,False)
            self.assertEqual(error.exception.code,403)
        with app.connect() as db:bot_tools.save_policy(db,'result',['read_workspace','generate_text','write_workspace'])
        with self.assertRaises(urllib.error.HTTPError) as error:self.create()
        self.assertEqual(error.exception.code,403)
        self.assertEqual(len(self.get('/api/upgrades')['proposals']),1)

    def test_proposals_survive_source_task_deletion_and_have_a_quota(self):
        key=self.create()
        status,preview=app.preview_task_delete('source'); self.assertEqual(status,200)
        status,_=app.delete_task('source',preview['token'],'source');self.assertEqual(status,200)
        self.assertEqual(self.get('/api/upgrades/'+key)['task_id'],'source')
        with app.connect() as db:
            for index in range(9):
                db.execute('INSERT INTO upgrade_proposals SELECT ?,task_id,title,status,spec,created,reviewed,bundle FROM upgrade_proposals WHERE id=?', ('f'+str(index).zfill(31),key))
            with self.assertRaises(ValueError):upgrade_proposals.create(db,self.root,app.DB.parent,'source','Extra',self.files,{})
