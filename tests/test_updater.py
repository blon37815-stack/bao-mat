from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch
import update_app


class UpdaterTest(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.remote, self.seed, self.client = [self.root/name for name in ('remote.git','seed','client')]
        self.git('init','--bare',str(self.remote),cwd=self.root)
        self.git('init','-b','main',str(self.seed),cwd=self.root)
        (self.seed/'requirements.txt').write_text('')
        (self.seed/'README.md').write_text('initial')
        self.commit('initial')
        self.git('remote','add','origin',str(self.remote),cwd=self.seed)
        self.git('push','-u','origin','main',cwd=self.seed)
        self.git('clone','--branch','main',str(self.remote),str(self.client),cwd=self.root)
        self.patch = patch.object(update_app,'ROOT',self.client)
        self.patch.start()

    def tearDown(self):
        self.patch.stop()
        # Git object files can be read-only on Windows.
        import os, stat
        def remove_readonly(function, path, exc):
            os.chmod(path, stat.S_IWRITE)
            function(path)
        import shutil
        shutil.rmtree(self.root, onerror=remove_readonly)
        self.temporary.cleanup()

    def git(self,*args,cwd):
        return subprocess.run(['git','-c','user.name=Test','-c','user.email=test@example.invalid',*args],cwd=cwd,
                              check=True,capture_output=True,text=True).stdout

    def commit(self,message):
        self.git('add','.',cwd=self.seed)
        self.git('commit','-m',message,cwd=self.seed)

    def test_updates_main_and_preserves_local_changes(self):
        (self.seed/'README.md').write_text('new')
        self.commit('update')
        self.git('push',cwd=self.seed)
        self.assertEqual(update_app.main(),0)
        self.assertEqual((self.client/'README.md').read_text(),'new')
        (self.client/'README.md').write_text('my change')
        self.assertEqual(update_app.main(),1)
        self.assertEqual((self.client/'README.md').read_text(),'my change')

    def test_deleted_feature_moves_to_main_only_after_verified_merge(self):
        branch='feat/bot-team-dashboard'
        self.git('switch','-c',branch,cwd=self.seed)
        (self.seed/'README.md').write_text('feature')
        self.commit('feature')
        self.git('push','-u','origin',branch,cwd=self.seed)
        self.git('fetch','origin',cwd=self.client)
        self.git('switch','-c',branch,'--track','origin/'+branch,cwd=self.client)
        self.git('switch','main',cwd=self.seed)
        self.git('merge','--ff-only',branch,cwd=self.seed)
        self.git('push','origin','main',cwd=self.seed)
        self.git('push','origin','--delete',branch,cwd=self.seed)
        self.assertEqual(update_app.main(),0)
        self.assertEqual(self.git('branch','--show-current',cwd=self.client).strip(),'main')
        self.assertEqual((self.client/'README.md').read_text(),'feature')

    def test_deleted_unmerged_feature_is_preserved(self):
        branch='feat/bot-team-dashboard'
        self.git('switch','-c',branch,cwd=self.seed)
        (self.seed/'README.md').write_text('local feature')
        self.commit('feature')
        self.git('push','origin',branch,cwd=self.seed)
        self.git('fetch','origin',cwd=self.client)
        self.git('switch','-c',branch,'--track','origin/'+branch,cwd=self.client)
        self.git('push','origin','--delete',branch,cwd=self.seed)
        self.assertEqual(update_app.main(),1)
        self.assertEqual(self.git('branch','--show-current',cwd=self.client).strip(),branch)
        self.assertEqual((self.client/'README.md').read_text(),'local feature')
