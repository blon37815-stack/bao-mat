"""Capabilities for trusted workflow calls; content-free bounded audit events.

No endpoint/model tool accepts a callable or shell command. Current revocations
apply to old runs; frozen grants cannot be expanded by later configuration.
"""
import json
import time
from datetime import datetime, timezone

from artifacts import parse_files
from ollama_transport import InferenceCancelled

TOOLS = {
    'generate_text': 'Gọi model theo hạn mức',
    'read_workspace': 'Đọc dữ liệu của công việc',
    'write_workspace': 'Lưu bộ tệp của công việc',
    'check_syntax': 'Kiểm tra cú pháp',
    'run_python_tests': 'Chạy unittest trong Docker',
    'propose_upgrade': 'Soạn đề xuất nâng cấp để duyệt',
}
CEILINGS = {key: ('read_workspace', 'generate_text') for key in ('planner', 'architect', 'python', 'web', 'data')}
CEILINGS.update(plan=('read_workspace', 'generate_text'),
                result=('read_workspace', 'generate_text', 'write_workspace', 'propose_upgrade'),
                review=('read_workspace', 'generate_text', 'check_syntax', 'run_python_tests'))


class ToolDenied(PermissionError):
    pass


class ToolLimit(Exception):
    pass


def initialize(db):
    db.execute('CREATE TABLE IF NOT EXISTS bot_tool_policy (bot_id TEXT PRIMARY KEY, revision INTEGER NOT NULL, spec TEXT NOT NULL)')
    db.execute('CREATE TABLE IF NOT EXISTS task_tool_grants (task_id TEXT PRIMARY KEY, spec TEXT NOT NULL)')
    db.execute('''CREATE TABLE IF NOT EXISTS audit_events (
        id INTEGER PRIMARY KEY, task_id TEXT, bot_id TEXT NOT NULL, tool TEXT NOT NULL,
        decision TEXT NOT NULL, outcome TEXT NOT NULL, reason TEXT NOT NULL,
        details TEXT NOT NULL, created TEXT NOT NULL, duration_ms INTEGER NOT NULL DEFAULT 0)''')
    db.execute('CREATE INDEX IF NOT EXISTS audit_by_task ON audit_events(task_id,id)')


def policy(db, bot_id):
    if bot_id not in CEILINGS:
        raise ValueError('Không có vai trò công cụ này')
    row = db.execute('SELECT revision,spec FROM bot_tool_policy WHERE bot_id=?', (bot_id,)).fetchone()
    return {'revision': row['revision'] if row else 0,
            'tools': json.loads(row['spec']) if row else list(CEILINGS[bot_id])}


def snapshot(db):
    return {key: policy(db, key) for key in CEILINGS}


def grants(db, task_id, runtime):
    if 'tool_policy' in runtime:
        return runtime['tool_policy']
    row = db.execute('SELECT spec FROM task_tool_grants WHERE task_id=?', (task_id,)).fetchone()
    # Legacy/test data created without runtime metadata uses the original v2 role
    # contract; initialize() freezes all pre-existing production tasks on upgrade.
    return json.loads(row['spec']) if row else {key:{'revision':0,'tools':list(value)} for key,value in CEILINGS.items()}


def save_policy(db, bot_id, tools):
    if (bot_id not in CEILINGS or not isinstance(tools, list)
            or any(not isinstance(item, str) for item in tools)
            or len(set(tools)) != len(tools) or set(tools) - set(CEILINGS[bot_id])):
        raise ValueError('Chỉ chọn công cụ thuộc vai trò; không cấp shell hoặc quyền sửa ứng dụng')
    revision = policy(db, bot_id)['revision'] + 1
    db.execute('INSERT INTO bot_tool_policy VALUES (?,?,?) ON CONFLICT(bot_id) DO UPDATE SET revision=excluded.revision,spec=excluded.spec',
               (bot_id, revision, json.dumps(tools)))
    return revision


def describe(db, bot_id):
    value = policy(db, bot_id)
    return dict(value, capabilities=[{'id': key, 'name': TOOLS[key], 'enabled': key in value['tools'],
        'status': 'implemented', 'scope': 'Chỉ công việc đang xử lý; không có shell tùy ý'} for key in CEILINGS[bot_id]],
        workspace='Dữ liệu riêng theo công việc trong SQLite; đề xuất nâng cấp có thư mục bản sao',
        verification='Công cụ đã nối vào luồng; chất lượng model cần đánh giá trên máy thực tế')


def arguments(tool, value):
    """Validate bounded metadata. Never persist prompts, bodies or raw errors."""
    if tool not in TOOLS or not isinstance(value, dict):
        raise ValueError('Công cụ hoặc tham số không hợp lệ')
    if tool == 'generate_text':
        if set(value) != {'input_chars', 'provider'} or value['provider'] not in ('ollama', 'ai'):
            raise ValueError('Tham số gọi model không hợp lệ')
        if type(value['input_chars']) is not int or not 0 <= value['input_chars'] <= 2_000_000:
            raise ValueError('Kích thước ngữ cảnh không hợp lệ')
        return dict(value)
    if set(value) != {'paths'} or not isinstance(value['paths'], list):
        raise ValueError('Công cụ chỉ nhận danh sách đường dẫn tương đối')
    if value['paths']:
        files = parse_files(json.dumps({'files': [{'path': path, 'content': ''} for path in value['paths']]}))
        return {'paths': [item['path'] for item in files]}
    return {'paths': []}


def record(db, task_id, bot_id, tool, decision, outcome, reason, details=None):
    row = db.execute('INSERT INTO audit_events(task_id,bot_id,tool,decision,outcome,reason,details,created) VALUES (?,?,?,?,?,?,?,?)',
        (task_id, bot_id, tool, decision, outcome, reason, json.dumps(details or {}, ensure_ascii=False), datetime.now(timezone.utc).isoformat()))
    if task_id:
        db.execute('DELETE FROM audit_events WHERE task_id=? AND id NOT IN (SELECT id FROM audit_events WHERE task_id=? ORDER BY id DESC LIMIT 500)', (task_id, task_id))
    db.execute('DELETE FROM audit_events WHERE id NOT IN (SELECT id FROM audit_events ORDER BY id DESC LIMIT 5000)')
    return row.lastrowid


def authorize(db, task_id, bot_id, tool):
    if not db.execute('SELECT 1 FROM tasks WHERE id=?', (task_id,)).fetchone():
        raise LookupError('Không tìm thấy công việc')
    if bot_id not in CEILINGS or tool not in CEILINGS[bot_id]:
        raise ToolDenied('Vai trò không được dùng công cụ này')
    current = policy(db, bot_id)
    row = db.execute('SELECT spec FROM task_runtime WHERE task_id=?', (task_id,)).fetchone()
    runtime = json.loads(row['spec']) if row else {}
    frozen = grants(db, task_id, runtime).get(bot_id, {'tools':[], 'revision':0})
    if tool not in current['tools'] or tool not in frozen['tools']:
        raise ToolDenied('Công cụ đã bị tắt hoặc không được cấp trong bản chụp công việc')
    return {'policy_revision': current['revision'], 'frozen_revision': frozen['revision']}


def invoke(connect, task_id, bot_id, tool, value, operation):
    """operation is supplied by trusted Python callers, never client/model data."""
    try:
        metadata = arguments(tool, value)
        with connect() as db:
            metadata.update(authorize(db, task_id, bot_id, tool))
    except (ToolDenied, ValueError) as error:
        with connect() as db:
            record(db, task_id, bot_id if bot_id in CEILINGS else 'unknown', tool if tool in TOOLS else 'unknown',
                   'BLOCK', 'denied', 'Quyền công cụ hoặc tham số bị từ chối')
        raise ToolDenied(str(error)) from None
    with connect() as db:
        event_id = record(db, task_id, bot_id, tool, 'ALLOW', 'running', 'Đã kiểm tra quyền và phạm vi', metadata)
    start = time.monotonic()
    outcome, decision, reason = 'failed', 'ALLOW', 'Công cụ không hoàn tất; không lưu chi tiết lỗi riêng tư'
    try:
        result = operation()
        status = result.get('status') if isinstance(result, dict) else None
        outcome = status if status in ('passed', 'failed', 'unavailable', 'not_supported') else 'completed'
        if outcome in ('unavailable', 'not_supported'):
            decision = 'WARN'
        reason = 'Công cụ đã trả kết quả' if outcome != 'failed' else 'Công cụ báo kiểm tra chưa đạt'
        return result
    except ToolLimit:
        decision, outcome, reason = 'BLOCK', 'limited', 'Đã dùng hết hạn mức gọi model của công việc'
        raise
    except InferenceCancelled:
        decision, outcome, reason = 'WARN', 'cancelled', 'Công việc đã được hủy'
        raise
    finally:
        with connect() as db:
            db.execute('UPDATE audit_events SET decision=?,outcome=?,reason=?,duration_ms=? WHERE id=?',
                (decision, outcome, reason, max(0, round((time.monotonic()-start)*1000)), event_id))


def require(connect, task_id, bot_id, tool):
    """Preflight expensive work; log denials, leave successful use to invoke()."""
    failure = None
    with connect() as db:
        try:
            authorize(db, task_id, bot_id, tool)
        except ToolDenied as error:
            record(db, task_id, bot_id, tool, 'BLOCK', 'denied', 'Công cụ bị tắt; dừng trước khi gọi model')
            failure = error
    if failure:
        raise failure


def events(db, task_id=None, offset=0, decision=None):
    if type(offset) is not int or not 0 <= offset <= 5000 or decision not in (None, 'ALLOW', 'BLOCK', 'WARN'):
        raise ValueError('Bộ lọc nhật ký không hợp lệ')
    where, values = [], []
    if task_id:
        where.append('task_id=?'); values.append(task_id)
    if decision:
        where.append('decision=?'); values.append(decision)
    clause = (' WHERE ' + ' AND '.join(where)) if where else ''
    total = db.execute('SELECT COUNT(*) FROM audit_events'+clause, values).fetchone()[0]
    rows = db.execute('SELECT * FROM audit_events'+clause+' ORDER BY id DESC LIMIT 50 OFFSET ?', [*values, offset])
    return {'events': [dict(row, details=json.loads(row['details'])) for row in rows], 'total': total,
            'offset': offset, 'limit': 50, 'retention': 'Tối đa 500 sự kiện/công việc và 5000 sự kiện toàn ứng dụng; không lưu nội dung tệp, prompt hay khóa'}
