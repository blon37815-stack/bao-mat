"""Bounded documents and bot preferences; no filesystem or provider access."""
import json
import uuid
import hashlib

from expert_team import EXPERTS

WORKERS = {
    'plan': ('Điều phối', 'Biến yêu cầu và chỉ đạo của chuyên gia thành kế hoạch, thứ tự làm và tiêu chí hoàn thành.'),
    'result': ('Thực hiện', 'Tạo nội dung hoặc từng tệp sản phẩm theo kế hoạch; sửa phần được yêu cầu.'),
    'review': ('Kiểm tra', 'Đối chiếu yêu cầu, đọc kết quả kiểm tra tĩnh và chỉ ra phần còn thiếu.'),
}
EXPERT_DESCRIPTIONS = {
    'planner':'Đọc yêu cầu, chia việc thành các bước và xác định kết quả cần bàn giao.',
    'architect':'Sắp xếp các phần của ứng dụng và cách chúng trao đổi dữ liệu, giữ thiết kế dễ sửa.',
    'python':'Hướng dẫn đội xây ứng dụng Python, xử lý dữ liệu và chuẩn bị kiểm thử.',
    'web':'Hướng dẫn đội tạo trang web, nối HTML/CSS/JavaScript và bố cục cho điện thoại.',
    'data':'Hướng dẫn đội tạo dữ liệu JSON đủ tệp, đúng trường, đúng kiểu và đủ bản ghi.',
}


def initialize(db):
    db.execute('CREATE TABLE IF NOT EXISTS bot_preferences (id TEXT PRIMARY KEY, name TEXT NOT NULL, instructions TEXT NOT NULL)')
    db.execute('CREATE TABLE IF NOT EXISTS task_bot_preferences (task_id TEXT PRIMARY KEY, spec TEXT NOT NULL)')
    db.execute('CREATE TABLE IF NOT EXISTS documents (id TEXT PRIMARY KEY, title TEXT NOT NULL, content TEXT NOT NULL, updated TEXT NOT NULL)')
    db.execute('CREATE TABLE IF NOT EXISTS task_documents (task_id TEXT NOT NULL, document_id TEXT NOT NULL, title TEXT NOT NULL, content TEXT NOT NULL, PRIMARY KEY(task_id,document_id))')


def bot_catalog(db):
    custom = {row['id']:dict(row) for row in db.execute('SELECT * FROM bot_preferences')}
    bots = [{'id':'manager','name':'Quản lý tài nguyên','kind':'manager',
             'description':'Giữ hàng đợi, phân công chuyên gia và chặn lượt gọi vượt hạn mức. Chạy bằng mã, không tốn lượt AI.',
             'instructions':'','configurable':False}]
    bots += [{'id':key,'name':profile['name'],'kind':'expert','description':EXPERT_DESCRIPTIONS[key],
              'instructions':'','configurable':True} for key,profile in EXPERTS.items()]
    bots += [{'id':key,'name':name,'kind':'worker','description':description,
              'instructions':'','configurable':True} for key,(name,description) in WORKERS.items()]
    for bot in bots:
        bot['default_name']=bot['name']
        if bot['id'] in custom and bot['configurable']:
            bot.update(name=custom[bot['id']]['name'],instructions=custom[bot['id']]['instructions'])
        bot['profile_version'] = hashlib.sha256(json.dumps({'id':bot['id'], 'name':bot['name'], 'instructions':bot['instructions'],
            'role':bot['description'], 'source':EXPERTS.get(bot['id'], {})}, sort_keys=True, ensure_ascii=True).encode()).hexdigest()[:12]
    return bots


def save_bot(db, bot_id, name, instructions):
    if bot_id not in {*EXPERTS,*WORKERS}:
        raise ValueError('Chỉ thiết lập chuyên gia hoặc bot thực thi có trong đội')
    if not isinstance(name,str) or not name.strip() or len(name)>60:
        raise ValueError('Tên bot từ 1 đến 60 ký tự')
    if not isinstance(instructions,str) or len(instructions)>1500:
        raise ValueError('Hướng dẫn riêng tối đa 1500 ký tự')
    db.execute('INSERT INTO bot_preferences VALUES (?,?,?) ON CONFLICT(id) DO UPDATE SET name=excluded.name,instructions=excluded.instructions',
               (bot_id,name.strip(),instructions.strip()))


def snapshot_bots(db, task_id):
    settings={bot['id']:{'name':bot['name'],'instructions':bot['instructions'],'profile_version':bot['profile_version']} for bot in bot_catalog(db) if bot['configurable']}
    db.execute('INSERT INTO task_bot_preferences VALUES (?,?)',(task_id,json.dumps(settings,ensure_ascii=False)))


def task_bots(db, task_id):
    row=db.execute('SELECT spec FROM task_bot_preferences WHERE task_id=?',(task_id,)).fetchone()
    return json.loads(row['spec']) if row else {}


def list_documents(db):
    return [dict(row) for row in db.execute('SELECT id,title,length(content) AS characters,updated FROM documents ORDER BY updated DESC,id')]


def save_document(db, document_id, title, content, timestamp):
    if not isinstance(title,str) or not title.strip() or len(title)>100:
        raise ValueError('Tên tài liệu từ 1 đến 100 ký tự')
    if not isinstance(content,str) or not content.strip() or len(content)>20000:
        raise ValueError('Nội dung tài liệu từ 1 đến 20000 ký tự')
    if document_id is not None:
        if not isinstance(document_id,str) or not db.execute('SELECT 1 FROM documents WHERE id=?',(document_id,)).fetchone():
            raise LookupError('Không tìm thấy tài liệu')
    elif db.execute('SELECT COUNT(*) FROM documents').fetchone()[0]>=30:
        raise ValueError('Thư viện tối đa 30 tài liệu; hãy xóa tài liệu không dùng')
    used=db.execute('SELECT COALESCE(SUM(length(CAST(content AS BLOB))),0) FROM documents WHERE id!=?',(document_id or '',)).fetchone()[0]
    if used+len(content.encode('utf-8'))>500000:
        raise ValueError('Thư viện vượt 500 KB; hãy xóa bớt nội dung')
    document_id=document_id or uuid.uuid4().hex
    db.execute('INSERT INTO documents VALUES (?,?,?,?) ON CONFLICT(id) DO UPDATE SET title=excluded.title,content=excluded.content,updated=excluded.updated',
               (document_id,title.strip(),content,timestamp))
    return document_id


def snapshot_documents(db, task_id, ids):
    if not isinstance(ids,list) or len(ids)>5 or any(not isinstance(item,str) for item in ids) or len(set(ids))!=len(ids):
        raise ValueError('Chọn tối đa 5 tài liệu khác nhau')
    selected=[]
    for document_id in ids:
        row=db.execute('SELECT id,title,content FROM documents WHERE id=?',(document_id,)).fetchone()
        if not row:
            raise ValueError('Tài liệu đã bị xóa; hãy chọn lại')
        selected.append(dict(row))
    if sum(len(item['content']) for item in selected)>16000:
        raise ValueError('Tổng tài liệu đính kèm tối đa 16000 ký tự')
    db.executemany('INSERT INTO task_documents VALUES (?,?,?,?)',[(task_id,item['id'],item['title'],item['content']) for item in selected])


def task_documents(db, task_id):
    return [dict(row) for row in db.execute('SELECT document_id AS id,title,content FROM task_documents WHERE task_id=? ORDER BY document_id',(task_id,))]
