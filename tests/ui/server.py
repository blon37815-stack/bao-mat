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
    custom = context.get('prompt')=='Kiểm thử danh sách tệp tự nhập' or context.get('prompt','').startswith('Bổ sung các tệp bắt buộc còn thiếu hoặc rỗng:')
    if custom:
        files={'main.py':'def add(a,b):\n return a+b\n',
               'tests/test_main.py':'import unittest\nfrom main import add\nclass T(unittest.TestCase):\n def test_add(self): self.assertEqual(add(2,3),5)\n',
               'README.md':'# Công cụ tính tổng'}
        if context.get('target_path'): return files[context['target_path']]
        if context.get('kind'): return json.dumps({'plan':'Sinh chương trình, kiểm thử và hướng dẫn.','required_files':list(files)})
        return '{"passed":true,"issues":[]}' if 'result' in context else 'Kế hoạch'
    if context.get('prompt')!='Kiểm thử sinh từng tệp trên trình duyệt':
        raise RuntimeError('Unexpected inference in browser test')
    if context.get('team_request')=='supervise':
        return 'Chuyên gia ECC giao ba tệp dữ liệu và yêu cầu đối chiếu lược đồ.'
    path=context.get('target_path')
    if path:
        notes=[{'id':i,'title':'Ghi chú','content':'Nội dung','created_at':'2026-10-19T00:00:00Z'} for i in range(3)]
        return {'notes.json':json.dumps(notes),'config.json':'{}','README.md':'# Dữ liệu ghi chú'}[path]
    return '{"passed":true,"issues":[]}' if 'result' in context else 'Kế hoạch thử nghiệm'


app.ollama_reply=fixture_ollama

with tempfile.TemporaryDirectory(prefix='bao-mat-ui-') as temporary:
    app.DB = Path(temporary)/'tasks.sqlite3'
    app.recover()
    app.configure_queue()
    # Old data exists only in this disposable test instance, never in the app.
    old='2020-01-01T00:00:00+00:00'
    with app.connect() as db:
        db.execute('INSERT INTO tasks VALUES (?,?,?,?,?,?,?)',('cleanup-fixture','Nhiệm vụ cũ để kiểm thử dọn','demo','completed','','{"result":"Kết quả cuối cần giữ"}',old))
        db.execute('INSERT INTO task_steps(task_id,role,attempt,started_at,finished_at,status,output) VALUES (?,?,1,?,?,?,?)',('cleanup-fixture','result',old,old,'completed','Nội dung lượt đã cũ'))
        preview_files=[
            {'path':'index.html','content':'<!doctype html><html><head><link rel="stylesheet" href="style.css"><script>window.parent.previewExecuted=true;fetch("https://outside.test/script")</script></head><body><h1 onclick="alert(1)">Trang xem trước tiếng Việt</h1><img src="https://outside.test/pixel"><a href="https://outside.test">Ngoài</a></body></html>'},
            {'path':'style.css','content':'@import url("https://outside.test/style"); body { background: rgb(1, 2, 3); color: white; }'},
            {'path':'app.js','content':'window.parent.previewExecuted=true;'},
            {'path':'README.md','content':'# Sản phẩm giả lập cho kiểm thử khung xem trước'},
        ]
        db.execute('INSERT INTO tasks VALUES (?,?,?,?,?,?,?)',('web-preview-fixture','Trang mẫu để duyệt và chỉnh sửa','ollama','completed','Dữ liệu giả lập kiểm thử',json.dumps({'result':json.dumps({'files':preview_files},ensure_ascii=False)},ensure_ascii=False),app.utc_now()))
        db.execute('INSERT INTO task_products VALUES (?,1)',('web-preview-fixture',))
        db.execute('INSERT INTO tasks VALUES (?,?,?,?,?,?,?)',('incomplete-product-fixture','Sản phẩm còn thiếu mã nguồn','ollama','needs_review','Cần bổ sung tệp',json.dumps({'result':json.dumps({'files':[{'path':'README.md','content':'# Giữ nguyên hướng dẫn gốc'}]})}),app.utc_now()))
        db.execute('INSERT INTO task_products VALUES (?,1)',('incomplete-product-fixture',))
        db.execute('INSERT INTO task_requirements VALUES (?,?)',('incomplete-product-fixture',json.dumps({'contract_version':1,'kind':'application','manifest_source':'user','required_files':['main.py','tests/test_main.py','README.md']})))
    server = app.ThreadingHTTPServer(('127.0.0.1',int(os.environ.get('PORT','8989'))),app.Handler)
    server.serve_forever()
