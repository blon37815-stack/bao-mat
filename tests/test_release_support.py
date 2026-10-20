import io
from contextlib import closing
import json
import hashlib
import os
from pathlib import Path
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
import zipfile

import launch_app
import release_support as releases
import update_app


class ReleaseTest(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.seed, self.remote, self.client = [self.root/name for name in ('seed','remote.git','client')]
        self.git('init', '--bare', str(self.remote), cwd=self.root)
        self.git('init', '-b', 'main', str(self.seed), cwd=self.root)
        (self.seed/'requirements.txt').write_text('')
        (self.seed/'.gitignore').write_text('data/\n.runtime-envs/\n')
        (self.seed/'README.md').write_text('Phiên bản cũ', encoding='utf-8')
        (self.seed/'app.py').write_text('import sqlite3, os\ndef connect(): return sqlite3.connect(os.environ["BOT_DB"])\ndef build_graph(): return None\n')
        self.commit('initial')
        self.git('remote','add','origin',str(self.remote),cwd=self.seed)
        self.git('push','-u','origin','main',cwd=self.seed)
        self.git('clone','--branch','main',str(self.remote),str(self.client),cwd=self.root)
        self.database = self.client/'data'/'tasks.sqlite3'
        self.database.parent.mkdir()
        with closing(sqlite3.connect(self.database)) as db, db:
            db.execute('CREATE TABLE memories (content TEXT)')
            db.execute("INSERT INTO memories VALUES ('Bộ nhớ cần giữ')")
        self.addCleanup(self.remove)

    def remove(self):
        import stat
        def writable(function, path, _):
            os.chmod(path, stat.S_IWRITE); function(path)
        shutil.rmtree(self.root, onerror=writable)
        self.temporary.cleanup()

    def git(self, *args, cwd):
        return subprocess.run(['git','-c','user.name=Test','-c','user.email=test@example.invalid',*args], cwd=cwd,
                              check=True, capture_output=True, text=True).stdout

    def commit(self, message):
        self.git('add','.',cwd=self.seed); self.git('commit','-m',message,cwd=self.seed)

    def test_bundle_restores_source_and_data_into_new_directory_only(self):
        before = self.git('rev-parse','HEAD',cwd=self.client).strip()
        bundle = releases.recovery_bundle(self.client, self.database, before)
        (self.client/'README.md').write_text('Current work')
        destination = self.root/'restored'
        releases.restore_bundle(bundle, destination)
        self.assertEqual((destination/'README.md').read_text(encoding='utf-8'), 'Phiên bản cũ')
        self.assertEqual((self.client/'README.md').read_text(), 'Current work')
        with closing(sqlite3.connect(destination/'data'/'tasks.sqlite3')) as db, db:
            self.assertEqual(db.execute('SELECT content FROM memories').fetchone()[0], 'Bộ nhớ cần giữ')
        with self.assertRaises(ValueError): releases.restore_bundle(bundle, destination)
        self.assertFalse((destination/'.git').exists())

    def test_invalid_target_code_stops_before_merge_and_preserves_database(self):
        (self.seed/'app.py').write_text('raise RuntimeError("broken candidate")\n')
        self.commit('broken'); self.git('push',cwd=self.seed)
        before = self.git('rev-parse','HEAD',cwd=self.client)
        with patch.object(update_app,'ROOT',self.client), patch.dict(os.environ, {'BOT_DB':str(self.database)}):
            self.assertEqual(update_app.main(), 1)
        self.assertEqual(self.git('rev-parse','HEAD',cwd=self.client), before)
        with closing(sqlite3.connect(self.database)) as db, db:
            self.assertEqual(db.execute('SELECT content FROM memories').fetchone()[0], 'Bộ nhớ cần giữ')
        self.assertEqual(len(list((self.database.parent/'backups').glob('update-*.zip'))), 1)

    def test_successful_update_records_recovery_and_does_not_mutate_original_db(self):
        (self.seed/'app.py').write_text('import sqlite3, os\ndef connect():\n db=sqlite3.connect(os.environ["BOT_DB"])\n db.execute("PRAGMA user_version=7")\n db.execute("UPDATE memories SET content=\'Trial only\'")\n db.commit()\n return db\ndef build_graph(): return None\n')
        self.commit('migration'); self.git('push',cwd=self.seed)
        with patch.object(update_app,'ROOT',self.client), patch.dict(os.environ, {'BOT_DB':str(self.database)}):
            self.assertEqual(update_app.main(), 0)
        with closing(sqlite3.connect(self.database)) as db, db:
            self.assertEqual(db.execute('PRAGMA user_version').fetchone()[0], 0)
            self.assertEqual(db.execute('SELECT content FROM memories').fetchone()[0], 'Bộ nhớ cần giữ')
        journal = json.loads((self.database.parent/'updates'/'last-update.json').read_text())
        self.assertEqual(journal['preflight'], 'passed')
        self.assertTrue(Path(journal['backup']).is_file())
        self.assertFalse((self.client/'.runtime-envs').exists())

    def test_lock_blocks_update_and_second_process(self):
        with releases.application_lock(self.database):
            with patch.object(update_app,'ROOT',self.client), patch.dict(os.environ, {'BOT_DB':str(self.database)}):
                self.assertEqual(update_app.main(), 1)
            code = 'from pathlib import Path; from release_support import application_lock; import sys\nwith application_lock(Path(sys.argv[1])): pass'
            result = subprocess.run([sys.executable,'-c',code,str(self.database)], capture_output=True)
            self.assertNotEqual(result.returncode, 0)
        with releases.application_lock(self.database): pass

    def test_changed_requirements_prepare_a_separate_environment_before_switch(self):
        (self.seed/'requirements.txt').write_text('# Empty dependency set for an offline environment test\n')
        self.commit('requirements'); self.git('push',cwd=self.seed)
        with patch.object(update_app,'ROOT',self.client), patch.dict(os.environ, {'BOT_DB':str(self.database)}):
            self.assertEqual(update_app.main(), 0)
        pointer = json.loads((self.client/'data'/'runtime-environment.json').read_text())
        executable = self.client/pointer['python_relative']
        self.assertTrue(executable.is_file())
        self.assertTrue(pointer['python_relative'].startswith('.runtime-envs'))
        self.assertEqual(pointer['requirements_sha256'], hashlib.sha256((self.client/'requirements.txt').read_bytes()).hexdigest())
        with closing(sqlite3.connect(self.database)) as db, db:
            self.assertEqual(db.execute('SELECT content FROM memories').fetchone()[0], 'Bộ nhớ cần giữ')

    def test_zip_traversal_and_corrupt_hash_are_rejected(self):
        raw = io.BytesIO()
        with zipfile.ZipFile(raw, 'w') as archive: archive.writestr('../escape.py', 'bad')
        with self.assertRaises(ValueError): releases.extract_source(raw.getvalue(), self.root/'unsafe')
        bundle = self.root/'corrupt.zip'
        with zipfile.ZipFile(bundle, 'w') as archive:
            archive.writestr('RECOVERY.json', json.dumps({'format_version':1,'source_sha256':'bad','database':False}))
            archive.writestr('source.zip', raw.getvalue())
        with self.assertRaises(ValueError): releases.restore_bundle(bundle, self.root/'target')
        self.assertFalse((self.root/'target').exists())

    def test_launcher_rejects_wrong_dependencies_and_path_escape(self):
        pointer = self.client/'data'/'runtime-environment.json'
        target = self.client/'.runtime-envs'/'test'/('Scripts/python.exe' if os.name=='nt' else 'bin/python')
        target.parent.mkdir(parents=True); target.write_text('fixture')
        sha = hashlib.sha256(b'').hexdigest()
        releases.atomic_json(pointer, {'requirements_sha256':sha, 'python_relative':str(target.relative_to(self.client))})
        with patch.object(launch_app,'ROOT',self.client), patch.object(launch_app,'POINTER',pointer):
            self.assertEqual(launch_app.selected_python(), str(target))
            releases.atomic_json(pointer, {'requirements_sha256':sha,'python_relative':'../escape'})
            with self.assertRaises(ValueError): launch_app.selected_python()
            releases.atomic_json(pointer, {'requirements_sha256':'bad','python_relative':str(target.relative_to(self.client))})
            with self.assertRaises(ValueError): launch_app.selected_python()
