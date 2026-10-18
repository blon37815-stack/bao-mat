"""Local agent team dashboard. Run: python app.py"""
import json
import re
import secrets
import queue
import os
import sqlite3
import threading
import uuid
import urllib.request
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import TypedDict
from artifacts import parse_files, zip_files
from langgraph.graph import StateGraph, START, END

TASK_QUEUE = queue.Queue()
WORKER_LOCK = threading.Lock()
WORKER = None
CSRF_TOKEN = secrets.token_urlsafe(32)
ROOT = Path(__file__).resolve().parent
DB = Path(os.environ.get('BOT_DB', str(ROOT / 'data' / 'tasks.sqlite3')))
ROLES = [('plan', 'Điều phối', 'Chia yêu cầu thành kế hoạch cụ thể, nêu tiêu chí hoàn thành.'),
         ('result', 'Thực hiện', 'Dựa trên kế hoạch, tạo câu trả lời hoặc nội dung được yêu cầu. Không khẳng định đã chạy lệnh hay sửa tệp.'),
         ('review', 'Kiểm tra', 'Đánh giá kết quả theo yêu cầu và kế hoạch. Nêu thiếu sót, điều chưa được xác minh.')]


def connect():
    DB.parent.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(DB, timeout=30)
    db.execute('PRAGMA busy_timeout=30000')
    db.execute('PRAGMA journal_mode=WAL')
    db.row_factory = sqlite3.Row
    db.execute('CREATE TABLE IF NOT EXISTS tasks (id TEXT PRIMARY KEY, prompt TEXT, mode TEXT, status TEXT, stage TEXT, output TEXT, created TEXT)')
    db.execute('CREATE TABLE IF NOT EXISTS project_memory (id INTEGER PRIMARY KEY CHECK(id=1), content TEXT NOT NULL)')
    db.execute('CREATE TABLE IF NOT EXISTS task_memory (task_id TEXT PRIMARY KEY, content TEXT NOT NULL)')
    db.execute('CREATE TABLE IF NOT EXISTS task_products (task_id TEXT PRIMARY KEY, enabled INTEGER NOT NULL)')
    return db


def get_memory():
    with connect() as db:
        row = db.execute('SELECT content FROM project_memory WHERE id=1').fetchone()
    return row['content'] if row else ''


def save_memory(content):
    if not isinstance(content, str) or len(content) > 8000:
        raise ValueError('Bộ nhớ tối đa 8000 ký tự')
    with connect() as db:
        db.execute('INSERT INTO project_memory VALUES (1,?) ON CONFLICT(id) DO UPDATE SET content=excluded.content', (content.strip(),))


def snapshot_memory(db, task_id):
    db.execute("INSERT INTO task_memory SELECT ?, COALESCE((SELECT content FROM project_memory WHERE id=1),'')", (task_id,))


def is_product(task_id):
    with connect() as db:
        row = db.execute('SELECT enabled FROM task_products WHERE task_id=?', (task_id,)).fetchone()
    return bool(row and row['enabled'])


def product_files(task_id):
    with connect() as db:
        row = db.execute('SELECT * FROM tasks WHERE id=?', (task_id,)).fetchone()
    if row is None or not is_product(task_id):
        return 404, {'error':'Không tìm thấy bộ sản phẩm'}
    if row['status'] not in ('completed','needs_review','approved'):
        return 409, {'error':'Chờ nhiệm vụ kết thúc trước khi tải bộ tệp'}
    try:
        files = parse_files(json.loads(row['output']).get('result', ''))
    except ValueError as error:
        return 409, {'error':str(error)}
    return 200, {'files':files, 'mode':row['mode'], 'status':row['status']}


def task_context(task_id):
    with connect() as db:
        row = db.execute('SELECT content FROM task_memory WHERE task_id=?', (task_id,)).fetchone()
    return row['content'] if row else ''


def update(task_id, **fields):
    with connect() as db:
        db.execute('UPDATE tasks SET ' + ','.join(k+'=?' for k in fields) + ' WHERE id=?', [*fields.values(), task_id])


class TaskCancelled(Exception):
    pass


def worker_update(task_id, **fields):
    with connect() as db:
        changed = db.execute('UPDATE tasks SET ' + ','.join(k+'=?' for k in fields)
            + " WHERE id=? AND status!='cancelled'", [*fields.values(), task_id]).rowcount
    if not changed:
        raise TaskCancelled()


def task_action(task_id, action):
    with connect() as db:
        row = db.execute('SELECT * FROM tasks WHERE id=?', (task_id,)).fetchone()
        if row is None:
            return 404, {'error':'Không tìm thấy nhiệm vụ'}
        if action == 'cancel':
            changed = db.execute("UPDATE tasks SET status='cancelled', stage='Đã hủy; phản hồi đang tính sẽ bị bỏ qua' WHERE id=? AND status IN ('queued','running')", (task_id,)).rowcount
        elif action == 'approve':
            if is_product(task_id):
                try:
                    parse_files(json.loads(row['output']).get('result',''))
                except ValueError:
                    return 409, {'error':'Bộ tệp chưa hợp lệ; chưa thể duyệt'}
            if row['mode'] == 'demo' or not json.loads(row['output']).get('result'):
                return 409, {'error':'Không thể duyệt mô phỏng hoặc nhiệm vụ chưa có kết quả'}
            changed = db.execute("UPDATE tasks SET status='approved', stage='Người dùng đã duyệt kết quả' WHERE id=? AND status IN ('completed','needs_review')", (task_id,)).rowcount
        else:
            return 404, {'error':'Không tìm thấy thao tác'}
    return (200, {'id':task_id}) if changed else (409, {'error':'Trạng thái nhiệm vụ không cho phép thao tác này'})


class State(TypedDict, total=False):
    id: str
    prompt: str
    mode: str
    plan: str
    result: str
    review: str
    product: bool
    project_memory: str
    attempts: int
    verdict: str


def final_answer(text):
    """Strip only a leading reasoning block; preserve literal tags in answers."""
    text = text.strip()
    if text.startswith('<think>'):
        end = text.find('</think>')
        return text[end+len('</think>'):].strip() if end != -1 else ''
    # Older Qwen responses omitted the opening tag. Restrict this workaround
    # to recognizable English preambles and a closing tag on its own line.
    if text.startswith(('Okay,', 'Let me think', 'Hmm,', 'Alright,')):
        marker = re.search(r'^</think>[ \t]*(?:\r?\n|$)', text, re.MULTILINE)
        if marker:
            return text[marker.end():].strip()
    return text


def public_task(row):
    task = dict(row)
    task['product'] = is_product(task['id'])
    task['project_memory'] = task_context(task['id'])
    task['output'] = json.dumps({key: final_answer(value) for key, value in
        json.loads(task['output']).items()}, ensure_ascii=False)
    return task


def ollama_reply(messages):
    """Use the local Ollama HTTP API; no API key or cloud fallback."""
    payload = {'model': os.environ.get('OLLAMA_MODEL', 'qwen3:4b'),
               'messages': [dict(message, content=message['content'] + ('\n/no_think' if message['role'] == 'user' else '')) for message in messages], 'stream': False, 'think': False}
    base = os.environ.get('OLLAMA_BASE_URL', 'http://127.0.0.1:11434').rstrip('/')
    request = urllib.request.Request(base+'/api/chat',
        data=json.dumps(payload).encode(), headers={'Content-Type':'application/json'})
    # Local inference may be slow on CPU. Do not send loopback through proxies.
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    with opener.open(request, timeout=600) as response:
        content = json.load(response)['message']['content']
    if not isinstance(content, str):
        raise ValueError('Invalid Ollama response')
    content = final_answer(content)
    if not content:
        raise ValueError('Empty Ollama response')
    return content


def parse_review(text):
    # Accept an optional outer Markdown fence, but no surrounding prose.
    text = text.strip()
    if text.startswith('```') and text.endswith('```'):
        text = text.split('\n', 1)[1].rsplit('```', 1)[0].strip()
    try:
        value = json.loads(text)
    except (ValueError, TypeError):
        return None
    if not isinstance(value, dict) or type(value.get('passed')) is not bool:
        return None
    issues = value.get('issues')
    if not isinstance(issues, list) or not all(isinstance(item, str) for item in issues):
        return None
    if not value['passed'] and not any(item.strip() for item in issues):
        return None
    if value['passed'] and issues:
        return None
    return {'passed': value['passed'], 'issues': issues}


def review_route(state):
    if state.get('verdict') == 'revise' and state.get('attempts', 0) < 3:
        return 'result'
    return END


def build_graph():
    graph = StateGraph(State)
    for key, role, instruction in ROLES:
        def step(state, key=key, role=role, instruction=instruction):
            attempts = state.get('attempts', 0) + (1 if key == 'result' else 0)
            worker_update(state['id'], stage=role + (f' · lượt {attempts}/3' if key in ('result','review') else ''))
            if state['mode'] == 'demo':
                output = {'plan': '1. Làm rõ mục tiêu: '+state['prompt']+'\n2. Soạn kết quả.\n3. Kiểm tra theo yêu cầu.',
                          'result': 'Đây là kết quả mô phỏng cho: '+state['prompt']+'\nChưa gọi mô hình AI và chưa thực hiện thao tác bên ngoài.',
                          'review': 'Luồng ba bước đã chạy. Nội dung là mô phỏng, chưa chứng minh nhiệm vụ thực tế hoàn thành.'}[key]
            else:
                from openai import OpenAI
                context = {k: state[k] for k in ('prompt', 'project_memory', 'plan', 'result', 'review') if k in state}
                role_instruction = instruction
                if key == 'review':
                    role_instruction += ' Chỉ xuất JSON hợp lệ: {"passed":true,"issues":[]} nếu đạt; nếu chưa đạt dùng passed=false và issues là danh sách lỗi cụ thể bằng tiếng Việt. Không tuyên bố đã thực thi hay kiểm thử mã. Không có văn bản ngoài JSON.'
                elif key == 'result' and state.get('review'):
                    role_instruction += ' Sửa kết quả trước theo các lỗi trong review, giữ đầy đủ yêu cầu ban đầu.'
                if key == 'result' and state.get('product'):
                    role_instruction += ' Tạo bộ mã nguồn nhỏ theo yêu cầu, kèm README.md hướng dẫn chạy. Chỉ xuất JSON: {"files":[{"path":"README.md","content":"..."}]}. Tối đa 30 tệp văn bản, dùng đường dẫn tương đối với dấu /, không dùng .., không tạo .git hay .venv. Nội dung giao diện và tài liệu bằng tiếng Việt; mã dùng cú pháp đúng ngôn ngữ. Không có văn bản ngoài JSON.'
                messages = [{'role':'system','content':role_instruction+' Chỉ trả lời kết quả cuối cùng bằng tiếng Việt rõ ràng, ngắn gọn. Không trình bày quá trình suy nghĩ hoặc tự đối thoại. Bạn chỉ tạo văn bản, không có công cụ thực thi.'},
                            {'role':'user','content':json.dumps(context, ensure_ascii=False)}]
                if state['mode'] == 'ollama':
                    output = ollama_reply(messages)
                else:
                    response = OpenAI(timeout=90, max_retries=1).chat.completions.create(
                        model=os.environ.get('BOT_MODEL', 'gpt-4.1-mini'), messages=messages)
                    output = response.choices[0].message.content or ''
            if state.get('product') and state['mode'] == 'demo' and key == 'result':
                output = json.dumps({'files':[{'path':'README.md','content':'# Sản phẩm mô phỏng\nChưa gọi AI hay tạo dự án thực tế.'}]}, ensure_ascii=False)
            if key == 'review' and state.get('product'):
                try:
                    parse_files(state.get('result',''))
                except ValueError as error:
                    output = json.dumps({'passed':False,'issues':[str(error)]}, ensure_ascii=False)
            output = final_answer(output)
            if not output:
                raise ValueError('No final answer')
            partial = {k: state[k] for k, _, _ in ROLES if k in state}
            partial[key] = output
            worker_update(state['id'], output=json.dumps(partial, ensure_ascii=False))
            changes = {key: output, 'attempts': attempts}
            if key == 'review' and state['mode'] != 'demo':
                review = parse_review(output)
                changes['verdict'] = 'unverified' if review is None else ('passed' if review['passed'] else 'revise')
            return changes
        graph.add_node(key, step)
    graph.add_edge(START, 'plan')
    graph.add_edge('plan', 'result')
    graph.add_edge('result', 'review')
    graph.add_conditional_edges('review', review_route, ['result', END])
    return graph.compile()


def run(task_id, prompt, mode):
    try:
        worker_update(task_id, status='running')
        result = build_graph().invoke({'id':task_id, 'prompt':prompt, 'mode':mode, 'project_memory':task_context(task_id), 'product':is_product(task_id)})
        if mode == 'demo':
            worker_update(task_id, status='completed', stage='Hoàn thành mô phỏng')
        elif result.get('verdict') == 'passed':
            worker_update(task_id, status='completed', stage=f"AI đánh giá đạt · {result['attempts']} lượt · chưa xác minh bên ngoài")
        else:
            stage = 'Kiểm tra sai định dạng; cần người xem' if result.get('verdict') == 'unverified' else 'Chưa đạt sau 2 lần sửa; cần người xem'
            worker_update(task_id, status='needs_review', stage=stage)
    except TaskCancelled:
        return
    except Exception:
        # Do not persist provider errors that might contain credentials or request data.
        try:
            worker_update(task_id, status='failed', stage=('Không gọi được Ollama; kiểm tra ứng dụng Ollama đang chạy và đã tải mô hình' if mode == 'ollama' else 'Lỗi xử lý; kiểm tra cấu hình mô hình và kết nối'))
        except TaskCancelled:
            pass


def work_loop():
    while True:
        args = TASK_QUEUE.get()
        try:
            run(*args)
        finally:
            TASK_QUEUE.task_done()


def enqueue_task(task_id, prompt, mode):
    global WORKER
    with WORKER_LOCK:
        if WORKER is None or not WORKER.is_alive():
            WORKER = threading.Thread(target=work_loop, daemon=True, name='bot-worker')
            WORKER.start()
        TASK_QUEUE.put((task_id, prompt, mode))


def recover():
    with connect() as db:
        db.execute("UPDATE tasks SET status='interrupted', stage='Tiến trình bị dừng; có thể chạy lại nhiệm vụ' WHERE status IN ('queued','running')")


def retry_task(task_id):
    """Atomically claim failed work so double clicks cannot start two runs."""
    with connect() as db:
        task = db.execute('SELECT * FROM tasks WHERE id=?', (task_id,)).fetchone()
        if task is None:
            return 404, {'error': 'Không tìm thấy nhiệm vụ'}
        if task['mode'] == 'ai' and not os.environ.get('OPENAI_API_KEY'):
            return 400, {'error': 'Chưa cấu hình OPENAI_API_KEY'}
        changed = db.execute("UPDATE tasks SET status='queued', stage='Chờ chạy lại', output='{}' WHERE id=? AND status IN ('failed','interrupted')", (task_id,)).rowcount
        if not changed:
            return 409, {'error': 'Chỉ chạy lại nhiệm vụ thất bại hoặc bị gián đoạn'}
    enqueue_task(task_id, task['prompt'], task['mode'])
    return 202, {'id': task_id}


def team_status():
    with connect() as db:
        rows = db.execute("SELECT stage, COUNT(*) AS count FROM tasks WHERE status='running' GROUP BY stage").fetchall()
        counts = {}
        for row in rows:
            role = row['stage'].split(' · ')[0]
            counts[role] = counts.get(role, 0) + row['count']
        totals = dict(db.execute('SELECT status, COUNT(*) FROM tasks GROUP BY status').fetchall())
    return {'bots': [{'name': role, 'active': counts.get(role, 0)} for _, role, _ in ROLES], 'totals': totals}


def export_task(task_id, section):
    titles = {'plan': 'Kế hoạch', 'result': 'Kết quả', 'review': 'Kiểm tra'}
    if section not in (*titles, 'all'):
        return 404, None
    with connect() as db:
        row = db.execute('SELECT * FROM tasks WHERE id=?', (task_id,)).fetchone()
    if row is None:
        return 404, None
    task = public_task(row)
    outputs = json.loads(task['output'])
    selected = {key: outputs[key] for key in titles if outputs.get(key) and (section == 'all' or section == key)}
    if not selected:
        return 409, None
    lines = ['# Nhiệm vụ đội bot', '', task['prompt'], '',
             'Mã nhiệm vụ: ' + task['id'], 'Chế độ: ' + task['mode'],
             'Trạng thái: ' + task['status'], 'Tạo lúc (UTC): ' + task['created'], '']
    if task['project_memory']:
        lines += ['## Bộ nhớ dự án khi giao việc', '', task['project_memory'], '']
    if task['mode'] == 'demo':
        lines += ['> MÔ PHỎNG: nội dung không phải kết quả AI thực hiện nhiệm vụ.', '']
    if task['status'] not in ('completed','approved'):
        lines += ['> Kết quả một phần; luồng chưa hoàn thành.', '']
    for key, value in selected.items():
        lines += ['## ' + titles[key], '', value, '']
    return 200, '\n'.join(lines).encode('utf-8')


class Handler(BaseHTTPRequestHandler):
    def allowed_request(self, writing=False):
        hosts = {f'127.0.0.1:{self.server.server_port}', f'localhost:{self.server.server_port}'}
        host = self.headers.get('Host')
        if len(self.headers.get_all('Host', [])) != 1 or host not in hosts:
            self.respond(403, {'error':'Host không hợp lệ'})
            return False
        origin = self.headers.get('Origin')
        document_navigation = (self.command == 'GET' and self.path == '/'
                               and self.headers.get('Sec-Fetch-Mode') == 'navigate'
                               and self.headers.get('Sec-Fetch-Dest') == 'document')
        if ((origin is not None and origin != 'http://' + host)
                or (self.headers.get('Sec-Fetch-Site') == 'cross-site' and not document_navigation)):
            self.respond(403, {'error':'Chỉ nhận yêu cầu từ trang ứng dụng trên máy này'})
            return False
        if writing:
            if self.headers.get_content_type() != 'application/json':
                self.respond(415, {'error':'Yêu cầu phải dùng application/json'})
                return False
            if not secrets.compare_digest(self.headers.get('X-CSRF-Token', '').encode('utf-8'), CSRF_TOKEN.encode('ascii')):
                self.respond(403, {'error':'Phiên không hợp lệ; hãy tải lại trang'})
                return False
        return True

    def end_headers(self):
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.send_header('Cache-Control', 'no-store')
        super().end_headers()

    def respond(self, status, body, content_type='application/json; charset=utf-8'):
        data = body if isinstance(body, bytes) else json.dumps(body, ensure_ascii=False).encode()
        self.send_response(status)
        self.send_header('Content-Type', content_type)
        self.send_header('Content-Length', str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        if not self.allowed_request():
            return
        if self.path == '/api/session':
            return self.respond(200, {'token':CSRF_TOKEN})
        if self.path == '/':
            return self.respond(200, (ROOT/'index.html').read_bytes(), 'text/html; charset=utf-8')
        if self.path == '/api/memory':
            return self.respond(200, {'content':get_memory()})
        if self.path == '/api/team':
            return self.respond(200, team_status())
        if self.path.startswith('/api/tasks/') and self.path.rsplit('/',1)[-1] in ('files','artifact.zip'):
            parts = self.path.split('/')
            if len(parts) != 5 or not re.fullmatch(r'[a-zA-Z0-9_-]+', parts[3]):
                return self.respond(404, {'error':'Không tìm thấy'})
            status, product = product_files(parts[3])
            if status != 200 or parts[4] == 'files':
                return self.respond(status, product)
            payload = zip_files(product['files'])
            self.send_response(200)
            self.send_header('Content-Type','application/zip')
            self.send_header('Content-Disposition','attachment; filename="product-'+parts[3]+'.zip"')
            self.send_header('Content-Length',str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)
            return
        if self.path.startswith('/api/tasks/') and '/export/' in self.path:
            parts = self.path.split('/')
            if len(parts) != 6 or not re.fullmatch(r'[a-zA-Z0-9_-]+', parts[3]):
                return self.respond(404, {'error':'Không tìm thấy'})
            status, payload = export_task(parts[3], parts[5])
            if status != 200:
                return self.respond(status, {'error':'Không tìm thấy hoặc chưa có kết quả để tải'})
            self.send_response(200)
            self.send_header('Content-Type', 'text/markdown; charset=utf-8')
            self.send_header('Content-Disposition', 'attachment; filename="task-'+parts[3]+'-'+parts[5]+'.md"')
            self.send_header('Content-Length', str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)
            return
        if self.path.startswith('/api/tasks/'):
            task_id = self.path.removeprefix('/api/tasks/')
            with connect() as db:
                row = db.execute('SELECT * FROM tasks WHERE id=?', (task_id,)).fetchone()
            return self.respond(200, public_task(row)) if row else self.respond(404, {'error':'Không tìm thấy nhiệm vụ'})
        if self.path == '/api/tasks':
            with connect() as db:
                tasks = [public_task(row) for row in db.execute('SELECT * FROM tasks ORDER BY created DESC LIMIT 100')]
            return self.respond(200, {'tasks':tasks, 'ai_available':bool(os.environ.get('OPENAI_API_KEY')), 'ollama_model':os.environ.get('OLLAMA_MODEL', 'qwen3:4b')})
        self.respond(404, {'error':'Không tìm thấy'})

    def do_POST(self):
        if not self.allowed_request(writing=True):
            return
        if self.path == '/api/memory':
            try:
                length = int(self.headers.get('Content-Length', '0'))
                if not 0 < length <= 50000:
                    raise ValueError()
                data = json.loads(self.rfile.read(length))
                save_memory(data.get('content'))
            except (ValueError, TypeError, AttributeError):
                return self.respond(400, {'error':'Bộ nhớ phải là văn bản tối đa 8000 ký tự'})
            return self.respond(200, {'saved':True})
        if self.path.startswith('/api/tasks/') and self.path.rsplit('/', 1)[-1] in ('cancel','approve'):
            parts = self.path.split('/')
            if len(parts) != 5:
                return self.respond(404, {'error':'Không tìm thấy'})
            status, result = task_action(parts[3], parts[4])
            return self.respond(status, result)
        if self.path.startswith('/api/tasks/') and self.path.endswith('/retry'):
            task_id = self.path[len('/api/tasks/'):-len('/retry')]
            status, result = retry_task(task_id)
            return self.respond(status, result)
        if self.path != '/api/tasks':
            return self.respond(404, {'error':'Không tìm thấy'})
        try:
            length = int(self.headers.get('Content-Length', '0'))
            if not 0 < length <= 20000:
                raise ValueError()
            data = json.loads(self.rfile.read(length))
            prompt, mode = data.get('prompt'), data.get('mode', 'demo')
            product = data.get('product', False)
            if type(product) is not bool:
                raise ValueError()
            if not isinstance(prompt, str) or not prompt.strip() or len(prompt) > 4000 or mode not in ('demo','ai','ollama'):
                raise ValueError()
        except (ValueError, TypeError, AttributeError):
            return self.respond(400, {'error':'Nhập nhiệm vụ từ 1–4000 ký tự và chế độ hợp lệ'})
        if mode == 'ai' and not os.environ.get('OPENAI_API_KEY'):
            return self.respond(400, {'error':'Chưa cấu hình OPENAI_API_KEY trong môi trường máy chủ'})
        task_id = uuid.uuid4().hex
        with connect() as db:
            db.execute('INSERT INTO tasks VALUES (?,?,?,?,?,?,?)', (task_id, prompt.strip(), mode, 'queued', 'Chờ', '{}', datetime.now(timezone.utc).isoformat()))
            snapshot_memory(db, task_id)
            db.execute('INSERT INTO task_products VALUES (?,?)', (task_id, int(product)))
        enqueue_task(task_id, prompt.strip(), mode)
        self.respond(201, {'id':task_id})


if __name__ == '__main__':
    recover()
    server = ThreadingHTTPServer(('127.0.0.1', int(os.environ.get('PORT','8000'))), Handler)
    print('Bot team listening on loopback port', server.server_port, flush=True)
    server.serve_forever()
