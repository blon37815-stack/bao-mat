"""Ephemeral application instance used by browser integration tests."""
from pathlib import Path
import os
import json
import sys
import tempfile

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import app


def fixture_ollama(messages):
    """Only this marked browser fixture is accepted; no real inference in UI tests."""
    context=json.loads(messages[1]['content'])
    if context.get('prompt')!='Kiểm thử sinh từng tệp trên trình duyệt':
        raise RuntimeError('Unexpected inference in browser test')
    path=context.get('target_path')
    if path:
        notes=[{'id':i,'title':'Ghi chú','content':'Nội dung','created_at':'2026-10-19T00:00:00Z'} for i in range(3)]
        return {'notes.json':json.dumps(notes),'config.json':'{}','README.md':'# Dữ liệu ghi chú'}[path]
    return '{"passed":true,"issues":[]}' if 'result' in context else 'Kế hoạch thử nghiệm'


app.ollama_reply=fixture_ollama

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
