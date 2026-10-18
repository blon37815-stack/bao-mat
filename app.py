"""Local agent team dashboard. Run: python app.py"""
import json
import os
import sqlite3
import threading
import uuid
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import TypedDict
from langgraph.graph import StateGraph, START, END

ROOT = Path(__file__).resolve().parent
DB = Path(os.environ.get('BOT_DB', str(ROOT / 'data' / 'tasks.sqlite3')))
ROLES = [('plan', 'Điều phối', 'Chia yêu cầu thành kế hoạch cụ thể, nêu tiêu chí hoàn thành.'),
         ('result', 'Thực hiện', 'Dựa trên kế hoạch, tạo câu trả lời hoặc nội dung được yêu cầu. Không khẳng định đã chạy lệnh hay sửa tệp.'),
         ('review', 'Kiểm tra', 'Đánh giá kết quả theo yêu cầu và kế hoạch. Nêu thiếu sót, điều chưa được xác minh.')]


def connect():
    DB.parent.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(DB)
    db.row_factory = sqlite3.Row
    db.execute('CREATE TABLE IF NOT EXISTS tasks (id TEXT PRIMARY KEY, prompt TEXT, mode TEXT, status TEXT, stage TEXT, output TEXT, created TEXT)')
    return db


def update(task_id, **fields):
    with connect() as db:
        db.execute('UPDATE tasks SET ' + ','.join(k+'=?' for k in fields) + ' WHERE id=?', [*fields.values(), task_id])


class State(TypedDict, total=False):
    id: str
    prompt: str
    mode: str
    plan: str
    result: str
    review: str


def build_graph():
    graph = StateGraph(State)
    for key, role, instruction in ROLES:
        def step(state, key=key, role=role, instruction=instruction):
            update(state['id'], stage=role)
            if state['mode'] == 'demo':
                output = {'plan': '1. Làm rõ mục tiêu: '+state['prompt']+'\n2. Soạn kết quả.\n3. Kiểm tra theo yêu cầu.',
                          'result': 'Đây là kết quả mô phỏng cho: '+state['prompt']+'\nChưa gọi mô hình AI và chưa thực hiện thao tác bên ngoài.',
                          'review': 'Luồng ba bước đã chạy. Nội dung là mô phỏng, chưa chứng minh nhiệm vụ thực tế hoàn thành.'}[key]
            else:
                from openai import OpenAI
                context = {k: state[k] for k in ('prompt', 'plan', 'result') if k in state}
                response = OpenAI(timeout=90, max_retries=1).chat.completions.create(
                    model=os.environ.get('BOT_MODEL', 'gpt-4.1-mini'),
                    messages=[{'role':'system','content':instruction+' Trả lời bằng tiếng Việt. Bạn chỉ tạo văn bản, không có công cụ thực thi.'},
                              {'role':'user','content':json.dumps(context, ensure_ascii=False)}])
                output = response.choices[0].message.content or ''
            partial = {k: state[k] for k, _, _ in ROLES if k in state}
            partial[key] = output
            update(state['id'], output=json.dumps(partial, ensure_ascii=False))
            return {key: output}
        graph.add_node(key, step)
    graph.add_edge(START, 'plan')
    graph.add_edge('plan', 'result')
    graph.add_edge('result', 'review')
    graph.add_edge('review', END)
    return graph.compile()


def run(task_id, prompt, mode):
    try:
        update(task_id, status='running')
        build_graph().invoke({'id':task_id, 'prompt':prompt, 'mode':mode})
        update(task_id, status='completed', stage='Hoàn thành luồng')
    except Exception:
        # Do not persist provider errors that might contain credentials or request data.
        update(task_id, status='failed', stage='Lỗi xử lý; kiểm tra cấu hình mô hình và kết nối')


def recover():
    with connect() as db:
        db.execute("UPDATE tasks SET status='interrupted', stage='Tiến trình bị dừng; hãy tạo lại nhiệm vụ' WHERE status IN ('queued','running')")


class Handler(BaseHTTPRequestHandler):
    def respond(self, status, body, content_type='application/json; charset=utf-8'):
        data = body if isinstance(body, bytes) else json.dumps(body, ensure_ascii=False).encode()
        self.send_response(status)
        self.send_header('Content-Type', content_type)
        self.send_header('Content-Length', str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        if self.path == '/':
            return self.respond(200, (ROOT/'index.html').read_bytes(), 'text/html; charset=utf-8')
        if self.path == '/api/tasks':
            with connect() as db:
                tasks = [dict(row) for row in db.execute('SELECT * FROM tasks ORDER BY created DESC LIMIT 100')]
            return self.respond(200, {'tasks':tasks, 'ai_available':bool(os.environ.get('OPENAI_API_KEY'))})
        self.respond(404, {'error':'Không tìm thấy'})

    def do_POST(self):
        if self.path != '/api/tasks':
            return self.respond(404, {'error':'Không tìm thấy'})
        try:
            length = int(self.headers.get('Content-Length', '0'))
            if not 0 < length <= 20000:
                raise ValueError()
            data = json.loads(self.rfile.read(length))
            prompt, mode = data.get('prompt'), data.get('mode', 'demo')
            if not isinstance(prompt, str) or not prompt.strip() or len(prompt) > 4000 or mode not in ('demo','ai'):
                raise ValueError()
        except (ValueError, TypeError, AttributeError):
            return self.respond(400, {'error':'Nhập nhiệm vụ từ 1–4000 ký tự và chế độ hợp lệ'})
        if mode == 'ai' and not os.environ.get('OPENAI_API_KEY'):
            return self.respond(400, {'error':'Chưa cấu hình OPENAI_API_KEY trong môi trường máy chủ'})
        task_id = uuid.uuid4().hex
        with connect() as db:
            db.execute('INSERT INTO tasks VALUES (?,?,?,?,?,?,?)', (task_id, prompt.strip(), mode, 'queued', 'Chờ', '{}', datetime.now(timezone.utc).isoformat()))
        threading.Thread(target=run, args=(task_id,prompt.strip(),mode), daemon=True).start()
        self.respond(201, {'id':task_id})


if __name__ == '__main__':
    recover()
    server = ThreadingHTTPServer(('127.0.0.1', int(os.environ.get('PORT','8000'))), Handler)
    print('Bot team listening on loopback port', server.server_port, flush=True)
    server.serve_forever()
