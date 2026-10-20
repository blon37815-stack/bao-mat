"""Versioned local profiles and immutable per-run configuration; no provider calls."""
import hashlib
import json
import os
from pathlib import Path
import re

from expert_team import ECC_COMMIT, EXPERTS

API_VERSION = 1
SCHEMA_VERSION = 1
ROOT = Path(__file__).resolve().parent
BOT_IDS = (*EXPERTS, 'plan', 'result', 'review')


class ConfigurationError(ValueError):
    pass


def initialize(db):
    version = db.execute('PRAGMA user_version').fetchone()[0]
    if version > SCHEMA_VERSION:
        raise ValueError('Dữ liệu thuộc phiên bản mới hơn; hãy dùng đúng bản ứng dụng hoặc phục hồi bản sao tương thích')
    db.execute('CREATE TABLE IF NOT EXISTS model_profiles (id TEXT PRIMARY KEY, revision INTEGER NOT NULL, spec TEXT NOT NULL)')
    db.execute('CREATE TABLE IF NOT EXISTS bot_model_bindings (bot_id TEXT NOT NULL, provider TEXT NOT NULL, profile_id TEXT NOT NULL, PRIMARY KEY(bot_id,provider))')
    db.execute('CREATE TABLE IF NOT EXISTS projects (id TEXT PRIMARY KEY, name TEXT NOT NULL, memory TEXT NOT NULL)')
    db.execute("INSERT OR IGNORE INTO projects VALUES ('default','Dự án chung','')")
    db.execute('CREATE TABLE IF NOT EXISTS task_runtime (task_id TEXT PRIMARY KEY, spec TEXT NOT NULL)')
    db.execute('CREATE TABLE IF NOT EXISTS task_checks (task_id TEXT NOT NULL, attempt INTEGER NOT NULL, spec TEXT NOT NULL, PRIMARY KEY(task_id,attempt))')
    db.execute('CREATE TABLE IF NOT EXISTS execution_policy (id INTEGER PRIMARY KEY CHECK(id=1), enabled INTEGER NOT NULL)')
    db.execute('PRAGMA user_version=1')


def identifier(value):
    if not isinstance(value, str) or not re.fullmatch(r'[a-zA-Z0-9_-]{1,64}', value):
        raise ValueError('ID chỉ gồm chữ, số, gạch ngang hoặc gạch dưới, tối đa 64 ký tự')
    return value


def integer(value, low, high, label):
    if type(value) is not int or not low <= value <= high:
        raise ValueError(f'{label}: từ {low} đến {high}')
    return value


def defaults():
    try:
        timeout = float(os.environ.get('OLLAMA_TIMEOUT_SECONDS', '600'))
        if not 1 <= timeout <= 7200:
            raise ValueError()
    except ValueError:
        raise ConfigurationError('OLLAMA_TIMEOUT_SECONDS phải từ 1 đến 7200 giây') from None
    return [dict(id='default-ollama', name='Ollama mặc định', provider='ollama',
                 model=os.environ.get('OLLAMA_MODEL', 'qwen3:4b'), revision=0,
                 timeout_seconds=timeout,
                 context_tokens=0, max_output_tokens=4096, max_input_chars=100000, builtin=True),
            dict(id='default-openai', name='OpenAI mặc định', provider='ai',
                 model=os.environ.get('BOT_MODEL', 'gpt-4.1-mini'), revision=0,
                 timeout_seconds=90, context_tokens=0, max_output_tokens=4096,
                 max_input_chars=100000, builtin=True)]


def models(db):
    return defaults() + [dict(json.loads(row['spec']), id=row['id'], revision=row['revision'], builtin=False)
                         for row in db.execute('SELECT * FROM model_profiles ORDER BY id')]


def save_model(db, value):
    if not isinstance(value, dict):
        raise ValueError('Hồ sơ model không hợp lệ')
    key = identifier(value.get('id'))
    if key.startswith('default-'):
        raise ValueError('Giữ hồ sơ mặc định; tạo ID riêng để thay đổi')
    name, model, provider = value.get('name'), value.get('model'), value.get('provider')
    if not isinstance(name, str) or not name.strip() or len(name) > 80:
        raise ValueError('Tên hồ sơ từ 1 đến 80 ký tự')
    if not isinstance(model, str) or not re.fullmatch(r'[a-zA-Z0-9][a-zA-Z0-9_.:/@-]{0,199}', model):
        raise ValueError('Tên model không hợp lệ')
    if provider not in ('ollama', 'ai'):
        raise ValueError('Nhà cung cấp chưa hỗ trợ')
    if db.execute('SELECT 1 FROM bot_model_bindings WHERE profile_id=? AND provider!=?', (key, provider)).fetchone():
        raise ValueError('Hồ sơ đang được bot dùng ở nhà cung cấp khác; tạo ID mới hoặc gỡ phân công trước')
    spec = dict(name=name.strip(), provider=provider, model=model,
                timeout_seconds=integer(value.get('timeout_seconds', 600), 1, 7200, 'Thời hạn giây'),
                context_tokens=integer(value.get('context_tokens', 0), 0, 32768, 'Context'),
                max_output_tokens=integer(value.get('max_output_tokens', 4096), 128, 16384, 'Đầu ra token'),
                max_input_chars=integer(value.get('max_input_chars', 100000), 1000, 200000, 'Đầu vào ký tự'))
    row = db.execute('SELECT revision FROM model_profiles WHERE id=?', (key,)).fetchone()
    if row is None and db.execute('SELECT COUNT(*) FROM model_profiles').fetchone()[0] >= 30:
        raise ValueError('Tối đa 30 hồ sơ model')
    revision = row['revision'] + 1 if row else 1
    db.execute('INSERT INTO model_profiles VALUES (?,?,?) ON CONFLICT(id) DO UPDATE SET revision=excluded.revision,spec=excluded.spec',
               (key, revision, json.dumps(spec, ensure_ascii=False)))
    return dict(spec, id=key, revision=revision)


def bindings(db, bot_id):
    return {row['provider']: row['profile_id'] for row in db.execute('SELECT provider,profile_id FROM bot_model_bindings WHERE bot_id=?', (bot_id,))}


def save_bindings(db, bot_id, value):
    if bot_id not in BOT_IDS or not isinstance(value, dict) or set(value) - {'ollama', 'ai'}:
        raise ValueError('Phân công model không hợp lệ')
    available = {item['id']: item for item in models(db)}
    for provider, key in value.items():
        if not isinstance(key, str) or (key and (key not in available or available[key]['provider'] != provider)):
            raise ValueError('Hồ sơ model không thuộc chế độ được chọn')
    for provider, key in value.items():
        db.execute('DELETE FROM bot_model_bindings WHERE bot_id=? AND provider=?', (bot_id, provider))
        if key:
            db.execute('INSERT INTO bot_model_bindings VALUES (?,?,?)', (bot_id, provider, key))


def source_profile(expert):
    """Read only pinned, hash-verified reference data; never execute upstream hooks."""
    metadata = json.loads((ROOT/'third_party/ecc/PROVENANCE.json').read_text(encoding='utf-8'))
    texts, sources = [], []
    for name in EXPERTS[expert]['sources']:
        raw = (ROOT/'third_party/ecc'/name).read_bytes()
        digest = hashlib.sha256(raw).hexdigest()
        if digest != metadata['files'][name] or metadata['commit'] != ECC_COMMIT:
            raise ValueError('Nguồn ECC đã thay đổi; cần rà soát và cập nhật phiên bản trước khi dùng')
        texts.append(raw.decode('utf-8'))
        sources.append({'path':name, 'sha256':digest})
    return {'version':1, 'commit':ECC_COMMIT, 'sources':sources, 'reference':'\n\n'.join(texts)}


def snapshot(db, task_id, mode, project_id='default', origin=None, expert='none', app_version=None):
    identifier(project_id)
    if origin:
        row = db.execute('SELECT spec FROM task_runtime WHERE task_id=?', (origin,)).fetchone()
        if row:
            value = json.loads(row['spec'])
            value['copied_from'] = origin
            value.pop('executed_by', None)
            db.execute('INSERT INTO task_runtime VALUES (?,?)', (task_id, json.dumps(value, ensure_ascii=False)))
            return value
    if not db.execute('SELECT 1 FROM projects WHERE id=?', (project_id,)).fetchone():
        raise ValueError('Không tìm thấy dự án')
    selected = {}
    if mode != 'demo':
        available = {item['id']:item for item in models(db)}
        fallback = 'default-ollama' if mode == 'ollama' else 'default-openai'
        for bot_id in BOT_IDS:
            key = bindings(db, bot_id).get(mode, fallback)
            selected[bot_id] = dict(available[key])
    row = db.execute('SELECT enabled FROM execution_policy WHERE id=1').fetchone()
    value = {'schema_version':SCHEMA_VERSION, 'api_version':API_VERSION, 'project_id':project_id,
             'models':selected, 'app':app_version or {}, 'sandbox_enabled':bool(row and row['enabled']),
             'expert_source':source_profile(expert) if expert != 'none' and mode != 'demo' else None}
    if origin:
        value['legacy_origin'] = origin
    db.execute('INSERT INTO task_runtime VALUES (?,?)', (task_id, json.dumps(value, ensure_ascii=False)))
    return value


def task_runtime(db, task_id):
    row = db.execute('SELECT spec FROM task_runtime WHERE task_id=?', (task_id,)).fetchone()
    return json.loads(row['spec']) if row else None


def public_runtime(value):
    if value is None:
        return {'legacy':True, 'message':'Nhiệm vụ cũ chưa lưu cấu hình model; không suy đoán phiên bản đã dùng'}
    result = dict(value)
    if result.get('expert_source'):
        result['expert_source'] = {key:item for key,item in result['expert_source'].items() if key != 'reference'}
    return result


def save_project(db, key, name, memory):
    identifier(key)
    if not isinstance(name, str) or not name.strip() or len(name) > 80 or not isinstance(memory, str) or len(memory) > 8000:
        raise ValueError('Tên dự án tối đa 80 và bộ nhớ tối đa 8000 ký tự')
    if not db.execute('SELECT 1 FROM projects WHERE id=?', (key,)).fetchone() and db.execute('SELECT COUNT(*) FROM projects').fetchone()[0] >= 30:
        raise ValueError('Tối đa 30 dự án')
    db.execute('INSERT INTO projects VALUES (?,?,?) ON CONFLICT(id) DO UPDATE SET name=excluded.name,memory=excluded.memory', (key, name.strip(), memory.strip()))


def workspace(db, task_id):
    row = db.execute('SELECT id,output,status FROM tasks WHERE id=?', (task_id,)).fetchone()
    if not row:
        raise LookupError('Không tìm thấy nhiệm vụ')
    runtime = task_runtime(db, task_id)
    assignment = db.execute('SELECT expert FROM task_assignment WHERE task_id=?', (task_id,)).fetchone()
    expert = assignment['expert'] if assignment else 'none'
    roles = []
    for key in BOT_IDS:
        role = 'supervise' if key == expert else key
        steps = [dict(item) for item in db.execute('SELECT attempt,status,started_at,finished_at FROM task_steps WHERE task_id=? AND role=? ORDER BY id', (task_id, role))]
        roles.append({'id':key, 'workspace':task_id+'/'+key, 'tools':['generate_text'], 'steps':steps,
                      'assigned':key in ('plan','result','review') or key == expert})
    return {'id':task_id, 'storage':'sqlite', 'runtime':public_runtime(runtime), 'roles':roles,
            'checks':[json.loads(item['spec']) for item in db.execute('SELECT spec FROM task_checks WHERE task_id=? ORDER BY attempt', (task_id,))]}
