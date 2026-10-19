"""Ephemeral application instance used by browser integration tests."""
from pathlib import Path
import os
import sys
import tempfile

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import app

with tempfile.TemporaryDirectory(prefix='bao-mat-ui-') as temporary:
    app.DB = Path(temporary)/'tasks.sqlite3'
    app.recover()
    # Old data exists only in this disposable test instance, never in the app.
    old='2020-01-01T00:00:00+00:00'
    with app.connect() as db:
        db.execute('INSERT INTO tasks VALUES (?,?,?,?,?,?,?)',('cleanup-fixture','Nhiệm vụ cũ để kiểm thử dọn','demo','completed','','{"result":"Kết quả cuối cần giữ"}',old))
        db.execute('INSERT INTO task_steps(task_id,role,attempt,started_at,finished_at,status,output) VALUES (?,?,1,?,?,?,?)',('cleanup-fixture','result',old,old,'completed','Nội dung lượt đã cũ'))
    server = app.ThreadingHTTPServer(('127.0.0.1',int(os.environ.get('PORT','8989'))),app.Handler)
    server.serve_forever()
