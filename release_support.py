"""Local release preparation and recovery bundles; never overwrite a recovery target."""
from contextlib import contextmanager, closing
from datetime import datetime, timezone
import hashlib
import io
import json
import os
import re
from pathlib import Path, PurePosixPath
import shutil
import sqlite3
import stat
import subprocess
import sys
import tempfile
import uuid
import zipfile


def requirements_hash(path):
    """Git's LF/CRLF checkout conversion does not change dependencies."""
    return hashlib.sha256(Path(path).read_bytes().replace(b'\r\n', b'\n')).hexdigest()


@contextmanager
def application_lock(database):
    path = Path(database).parent/'.bao-mat.lock'
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('a+b') as handle:
        if path.stat().st_size == 0:
            handle.write(b'0'); handle.flush()
        handle.seek(0)
        try:
            if os.name == 'nt':
                import msvcrt
                msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            raise ValueError('Ung dung hoac bo cap nhat dang mo. Dung cua so do truoc.') from None
        try:
            yield
        finally:
            handle.seek(0)
            if os.name == 'nt':
                msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                fcntl.flock(handle, fcntl.LOCK_UN)


def atomic_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name+'.'+uuid.uuid4().hex+'.tmp')
    try:
        with temporary.open('x', encoding='utf-8') as stream:
            json.dump(value, stream, ensure_ascii=False, indent=2)
            stream.flush(); os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def source_zip(root, ref):
    return subprocess.run(['git', 'archive', '--format=zip', ref], cwd=root,
                          check=True, capture_output=True).stdout


def extract_source(raw, destination):
    with zipfile.ZipFile(io.BytesIO(raw)) as archive:
        if len(archive.infolist()) > 5000 or sum(item.file_size for item in archive.infolist()) > 64_000_000:
            raise ValueError('Goi ma nguon vuot gioi han phuc hoi')
        names = set()
        for item in archive.infolist():
            path = PurePosixPath(item.filename)
            if (not path.parts or path.is_absolute() or '..' in path.parts or '\\' in item.filename
                    or ':' in item.filename or stat.S_ISLNK(item.external_attr >> 16)
                    or any(part.rstrip(' .') != part or part.lower() == '.git' for part in path.parts)
                    or any(re.fullmatch(r'(CON|PRN|AUX|NUL|COM[1-9]|LPT[1-9])(?:\..*)?', part, re.I) for part in path.parts)
                    or item.filename.casefold() in names):
                raise ValueError('Duong dan goi ma nguon khong hop le')
            names.add(item.filename.casefold())
        archive.extractall(destination)


def recovery_bundle(root, database, commit):
    root, database = Path(root), Path(database)
    code = source_zip(root, commit)
    directory = database.parent/'backups'
    directory.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
    target = directory/f'update-{stamp}-{uuid.uuid4().hex[:12]}.zip'
    metadata = {'format_version':1, 'commit':commit, 'created_at':stamp,
                'source_sha256':hashlib.sha256(code).hexdigest(), 'database':database.exists(),
                'python':sys.version.split()[0], 'secrets_included':False}
    temporary = target.with_suffix('.tmp')
    try:
        with tempfile.TemporaryDirectory(prefix='bao-recovery-') as staging:
            snapshot = Path(staging)/'tasks.sqlite3'
            if database.exists():
                with closing(sqlite3.connect(database.as_uri()+'?mode=ro', uri=True, timeout=5)) as source:
                    if source.execute('PRAGMA quick_check').fetchone()[0] != 'ok':
                        raise ValueError('Du lieu chua dat quick_check; chua cap nhat')
                    with closing(sqlite3.connect(snapshot)) as backup:
                        source.backup(backup)
                metadata['database_sha256'] = file_hash(snapshot)
                with closing(sqlite3.connect(snapshot)) as check:
                    metadata['schema_version'] = check.execute('PRAGMA user_version').fetchone()[0]
            with temporary.open('xb') as stream:
                with zipfile.ZipFile(stream, 'w', zipfile.ZIP_DEFLATED) as archive:
                    archive.writestr('source.zip', code)
                    if snapshot.exists():
                        archive.write(snapshot, 'tasks.sqlite3')
                    archive.writestr('RECOVERY.json', json.dumps(metadata, ensure_ascii=False, indent=2))
                    archive.writestr('HUONG-DAN.txt', 'Dung app. Chay phuc-hoi.bat va chon goi nay. Phuc hoi tao thu muc moi, khong chep de du lieu dang dung.\nChay cai-dat.bat roi chay-phuc-hoi.bat trong thu muc moi.\nGoi khong chua .env, khoa API, model Ollama, .venv hay Git history.\n')
                stream.flush(); os.fsync(stream.fileno())
            os.replace(temporary, target)
    finally:
        temporary.unlink(missing_ok=True)
    return target


def file_hash(path):
    digest = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for chunk in iter(lambda: stream.read(1_048_576), b''):
            digest.update(chunk)
    return digest.hexdigest()


def restore_bundle(bundle, destination):
    destination = Path(destination).absolute()
    if destination.exists():
        raise ValueError('Thu muc dich da ton tai; chon thu muc moi de giu du lieu cu')
    with zipfile.ZipFile(bundle) as archive:
        names = archive.namelist()
        if len(names) != len(set(names)) or set(names)-{'source.zip','tasks.sqlite3','RECOVERY.json','HUONG-DAN.txt'}:
            raise ValueError('Goi phuc hoi co tep khong hop le')
        if archive.getinfo('RECOVERY.json').file_size > 16000 or archive.getinfo('source.zip').file_size > 64_000_000:
            raise ValueError('Goi phuc hoi qua lon')
        metadata = json.loads(archive.read('RECOVERY.json'))
        if not isinstance(metadata, dict) or metadata.get('format_version') != 1:
            raise ValueError('Phien ban goi phuc hoi chua ho tro')
        source = archive.read('source.zip')
        if hashlib.sha256(source).hexdigest() != metadata.get('source_sha256'):
            raise ValueError('Ma nguon khong khop hash')
        destination.mkdir(parents=True)
        try:
            extract_source(source, destination)
            if metadata.get('database'):
                entry = archive.getinfo('tasks.sqlite3')
                if entry.file_size > 1_000_000_000:
                    raise ValueError('Du lieu phuc hoi vuot 1 GB')
                database = destination/'data'/'tasks.sqlite3'
                database.parent.mkdir(parents=True, exist_ok=True)
                with archive.open(entry) as incoming, database.open('xb') as output:
                    shutil.copyfileobj(incoming, output, length=1_048_576)
                if file_hash(database) != metadata.get('database_sha256'):
                    raise ValueError('Du lieu khong khop hash')
                with closing(sqlite3.connect(database)) as db:
                    if db.execute('PRAGMA quick_check').fetchone()[0] != 'ok':
                        raise ValueError('Du lieu phuc hoi khong hop le')
            atomic_json(destination/'RECOVERED_VERSION.json', metadata)
            (destination/'chay-phuc-hoi.bat').write_text(
                '@echo off\nsetlocal\ncd /d "%~dp0"\nset "BOT_DB=%~dp0data\\tasks.sqlite3"\ncall "%~dp0chay.bat"\n', encoding='ascii')
        except Exception:
            shutil.rmtree(destination)
            raise
    return destination


def prepare_release(root, ref, database):
    """Test imports and DB migration against a copy, installing changed deps separately."""
    root, database = Path(root), Path(database)
    raw = source_zip(root, ref)
    with tempfile.TemporaryDirectory(prefix='bao-release-') as staging:
        source = Path(staging)/'source'
        source.mkdir()
        extract_source(raw, source)
        current = requirements_hash(root/'requirements.txt')
        wanted = requirements_hash(source/'requirements.txt')
        python = Path(sys.executable)
        environment = None
        try:
            if wanted != current:
                if shutil.disk_usage(root).free < 500_000_000:
                    raise ValueError('Can toi thieu 500 MB trong de chuan bi moi truong moi; chua doi ma')
                environment = root/'.runtime-envs'/(wanted[:16]+'-'+uuid.uuid4().hex[:8])
                subprocess.run([sys.executable, '-m', 'venv', str(environment)], check=True, timeout=90)
                python = environment/('Scripts/python.exe' if os.name == 'nt' else 'bin/python')
                install_environment = dict(os.environ, PIP_DISABLE_PIP_VERSION_CHECK='1')
                subprocess.run([str(python), '-m', 'pip', 'install', '-r', str(source/'requirements.txt')], check=True, timeout=600, env=install_environment)
                subprocess.run([str(python), '-m', 'pip', 'check'], check=True, timeout=30)
            trial = Path(staging)/'trial.sqlite3'
            if database.exists():
                with closing(sqlite3.connect(database.as_uri()+'?mode=ro', uri=True)) as original, closing(sqlite3.connect(trial)) as target:
                    original.backup(target)
            probe = ('import sys; from pathlib import Path; sys.path.insert(0,str(Path.cwd())); '
                     'import app; db=app.connect(); assert db.execute("PRAGMA quick_check").fetchone()[0]=="ok"; '
                     'db.close(); app.build_graph()')
            settings = dict(os.environ, BOT_DB=str(trial))
            subprocess.run([str(python), '-I', '-c', probe], cwd=source, env=settings,
                           check=True, capture_output=True, timeout=90)
            return {'python':str(python), 'requirements_sha256':wanted,
                    'isolated_environment':str(environment) if environment else None}
        except BaseException:
            if environment is not None:
                shutil.rmtree(environment, ignore_errors=True)
            raise
