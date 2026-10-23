"""Read-only runtime checks and consistent SQLite backup exports."""
import io
import json
from pathlib import Path
import sqlite3
import tempfile
import urllib.request
import zipfile


def ollama_health(base_url, model):
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    try:
        with opener.open(base_url.rstrip('/')+'/api/tags', timeout=3) as response:
            payload = json.load(response)
        models = payload.get('models')
        if not isinstance(models, list):
            raise ValueError('Invalid models response')
        names = [item.get('name', item.get('model')) for item in models if isinstance(item, dict)]
        names = [name for name in names if isinstance(name, str)]
        wanted = model if ':' in model else model+':latest'
        ready = model in names or wanted in names
        return {'status':'ready' if ready else 'model_missing', 'model':model, 'models':names[:50]}
    except (OSError, ValueError, AttributeError):
        return {'status':'unavailable', 'model':model, 'models':[]}


def backup_database(source):
    """Use SQLite's backup API so committed WAL content is included."""
    with tempfile.TemporaryDirectory(prefix='bao-mat-backup-') as temporary:
        snapshot = Path(temporary)/'tasks.sqlite3'
        target = sqlite3.connect(snapshot)
        try:
            source.backup(target, pages=256)
        finally:
            target.close()
        output = io.BytesIO()
        with zipfile.ZipFile(output, 'w', compression=zipfile.ZIP_DEFLATED) as archive:
            archive.write(snapshot, 'tasks.sqlite3')
            archive.writestr('KHOI-PHUC.txt', (
                'Bao Mat - ban sao du lieu\n'
                'Chua lich su, ket qua, bo nho va cac phien ban san pham. Khong chia se cong khai.\n'
                'De khoi phuc: dung app hoan toan, giu ban sao toan bo thu muc data hien tai.\n'
                'Chuyen thu muc data cu sang noi an toan, tao data moi, va chep tasks.sqlite3 vao do.\n'
                'Neu dung BOT_DB tuy chinh, khoi phuc vao dung duong dan do.\n'
                'Khong chep de len co so du lieu dang mo; khong ghep voi tep -wal/-shm cu.\n'
                'Ban sao nay khong chua ma nguon, moi truong Python, mo hinh Ollama hay khoa API.\n'
                'Viec dang cho/dang chay se thanh gian doan khi mo app lai.\n'
            ))
        return output.getvalue()
