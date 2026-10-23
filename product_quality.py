"""Evidence layers for a specific product. No generated code is executed here."""
import hashlib
import json

from task_requirements import check_requirements
from product_contracts import missing_paths


def content_digest(files):
    canonical = json.dumps(sorted(files,key=lambda f:f['path']),ensure_ascii=False,sort_keys=True,separators=(',', ':'))
    return hashlib.sha256(canonical.encode('utf-8')).hexdigest()


def report(files, spec, syntax, execution=None, ai_review=None, *, demo=False):
    digest = content_digest(files)
    issues = check_requirements(files, spec)
    required = spec.get('required_files', [])
    missing = missing_paths(files, spec)
    contents = {f['path']:f['content'] for f in files}
    inventory = [{'path':p, 'required':p in required, 'bytes':len(contents.get(p,'').encode('utf-8')),
                  'status':'missing' if p not in contents else 'empty' if not contents[p].strip() else 'present'}
                 for p in dict.fromkeys([*required, *contents])]
    completeness = 'failed' if issues else 'passed' if required else 'unverified'
    execution = dict(execution or {'status':'not_run','tests':0,'output':'Chưa chạy kiểm thử chức năng.'})
    if execution.get('content_sha256') != digest and execution['status'] != 'not_run':
        execution = {'status':'not_run','tests':0,'output':'Báo cáo cũ chưa gắn với đúng bộ tệp này; cần chạy lại kiểm thử.'}
    if execution['status']=='passed' and (type(execution.get('tests')) is not int or execution['tests'] <= 0):
        execution = dict(execution,status='not_supported',output='Không có kiểm thử thực sự được chạy.')
    blocked = bool(issues) or syntax['status']=='failed' or execution['status']=='failed'
    status = ('demo' if demo else 'blocked' if blocked else 'needs_review'
              if ai_review and ai_review.get('passed') is False else 'tested_scope'
              if completeness=='passed' and execution['status']=='passed' else 'static_only'
              if completeness=='passed' and syntax['status']=='passed' else 'needs_review')
    return {'version':1, 'content_sha256':digest, 'kind':spec.get('kind','unknown'),
            'manifest_source':spec.get('manifest_source','legacy'), 'status':status,
            'complete':not demo and completeness=='passed',
            'functional_verified':not demo and not blocked and completeness=='passed' and execution['status']=='passed',
            'files':inventory, 'missing_files':missing, 'required_files':required,
            'completeness':{'status':'demo' if demo else completeness,'issues':issues},
            'syntax':syntax, 'execution':execution,
            'ai_review':ai_review or {'passed':None,'issues':[]},
            'scope':'Đủ tệp và cú pháp không chứng minh chức năng. Kiểm thử Docker chỉ xác minh các ca thực sự chạy; chưa bảo đảm mọi yêu cầu hoặc bảo mật.'}


def inspect_task(app, task_id):
    status, product = app.product_files(task_id)
    if status != 200:
        return status, product
    files = product['files']
    try:
        syntax = app.bot_tools.invoke(app.connect, task_id, 'review', 'check_syntax',
            {'paths':[f['path'] for f in files]}, lambda:app.check_files(files))
    except app.bot_tools.ToolDenied as error:
        return 403, {'error':str(error)}
    with app.connect() as db:
        row = db.execute('SELECT output FROM tasks WHERE id=?',(task_id,)).fetchone()
        latest = db.execute('SELECT spec FROM task_checks WHERE task_id=? ORDER BY attempt DESC LIMIT 1',(task_id,)).fetchone()
    if row is None:
        return 404, {'error':'Công việc đã bị xóa.'}
    execution = json.loads(latest['spec']) if latest else None
    ai = app.parse_review(json.loads(row['output']).get('review','')) if row else None
    return 200, dict(report(files, app.get_requirements(task_id), syntax, execution, ai,
                            demo=product['mode']=='demo'), id=task_id, task_status=product['status'],
                     recorded_at=app.utc_now(), app=app.RUNTIME_INFO)


def approval_issues(app, task_id, files):
    """User approval cannot erase known syntax/test failures on the same content."""
    try:
        checks = app.bot_tools.invoke(app.connect,task_id,'review','check_syntax',
            {'paths':[f['path'] for f in files]},lambda:app.check_files(files))
    except app.bot_tools.ToolDenied as error:
        return [str(error)]
    if checks['status']=='failed':
        return ['Cú pháp chưa đạt: '+f['path']+': '+f['message'] for f in checks['findings'] if f['status']=='failed']
    with app.connect() as db:
        row = db.execute('SELECT spec FROM task_checks WHERE task_id=? ORDER BY attempt DESC LIMIT 1',(task_id,)).fetchone()
    previous = json.loads(row['spec']) if row else {}
    if previous.get('status')=='failed' and previous.get('content_sha256')==content_digest(files):
        return ['Kiểm thử Docker của bộ tệp này chưa đạt; tạo phiên bản sửa và kiểm thử lại trước khi duyệt.']
    return []
