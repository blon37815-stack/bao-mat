"""Validate model-generated text files and package them without executing code."""
import io
import json
import re
import subprocess
import sys
import shutil
import time
import unicodedata
import zipfile

MAX_FILES = 30
MAX_FILE_BYTES = 100_000
MAX_TOTAL_BYTES = 1_000_000


def parse_files(text):
    if len(text.encode('utf-8')) > MAX_TOTAL_BYTES * 2:
        raise ValueError('Phản hồi tạo tệp quá lớn')
    text = text.strip()
    if text.startswith('```') and text.endswith('```'):
        text = text.split('\n', 1)[1].rsplit('```', 1)[0].strip()
    try:
        value = json.loads(text)
    except (ValueError, TypeError):
        raise ValueError('Bộ tệp phải là JSON gồm files: [{path, content}]') from None
    files = value.get('files') if isinstance(value, dict) else None
    if not isinstance(files, list) or not 1 <= len(files) <= MAX_FILES:
        raise ValueError('Bộ sản phẩm cần từ 1 đến 30 tệp')
    result, seen, total = [], set(), 0
    for item in files:
        if not isinstance(item, dict) or not isinstance(item.get('path'), str) or not isinstance(item.get('content'), str):
            raise ValueError('Mỗi tệp cần path và content dạng văn bản')
        path = unicodedata.normalize('NFC', item['path'])
        parts = path.split('/')
        if len(path) > 200 or any(not part or part in ('.', '..') or part.endswith((' ', '.')) for part in parts):
            raise ValueError('Đường dẫn tệp không an toàn')
        if any(ord(char) < 32 or ord(char) == 127 or char in '\\:<>"|?*' for char in path):
            raise ValueError('Tên tệp chứa ký tự không hợp lệ')
        for part in parts:
            stem = part.split('.')[0].upper()
            if stem in {'CON','PRN','AUX','NUL','CONIN$','CONOUT$'} or re.fullmatch(r'(COM|LPT)[0-9¹²³]', stem):
                raise ValueError('Tên tệp dành riêng cho Windows')
            if part.casefold() in ('.git', '.venv'):
                raise ValueError('Không tạo thư mục Git hoặc môi trường ảo')
        folded = path.casefold()
        if folded in seen or any(folded.startswith(old+'/') or old.startswith(folded+'/') for old in seen):
            raise ValueError('Tên tệp bị trùng hoặc xung đột thư mục')
        seen.add(folded)
        size = len(item['content'].encode('utf-8'))
        total += size
        if size > MAX_FILE_BYTES or total > MAX_TOTAL_BYTES:
            raise ValueError('Bộ tệp vượt giới hạn dung lượng')
        result.append({'path':path, 'content':item['content']})
    return result


def zip_files(files):
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, 'w', compression=zipfile.ZIP_DEFLATED) as archive:
        for item in files:
            archive.writestr(item['path'], item['content'].encode('utf-8'))
    return buffer.getvalue()


SYNTAX_CHECKER = r'''
import json, sys
files = json.load(sys.stdin)
findings = []
for file in files:
    path, text = file['path'], file['content']
    extension = path.rsplit('.', 1)[-1].lower()
    if extension not in ('py','json'):
        findings.append({'path':path,'status':'skipped','message':'Chưa hỗ trợ kiểm tra cú pháp loại tệp này'})
        continue
    try:
        if extension == 'py':
            # Compile creates a code object; it never executes the supplied code.
            compile(text, path, 'exec', dont_inherit=True)
        else:
            def reject_constant(value):
                raise ValueError('Hằng số không hợp lệ trong JSON: '+value)
            json.loads(text, parse_constant=reject_constant)
        findings.append({'path':path,'status':'passed','message':'Đạt kiểm tra cú pháp Python' if extension == 'py' else 'Đạt kiểm tra cú pháp JSON'})
    except (SyntaxError, ValueError, RecursionError, MemoryError) as error:
        if isinstance(error, SyntaxError):
            message = 'Dòng '+str(error.lineno)+': '+error.msg
        else:
            message = str(error)[:300] or 'Không phân tích được tệp'
        findings.append({'path':path,'status':'failed','message':message})
json.dump(findings, sys.stdout, ensure_ascii=True)
'''


def check_files(files):
    """Check syntax in a short-lived interpreter; never execute generated code."""
    deadline = time.monotonic()+8
    try:
        process = subprocess.run([sys.executable, '-I', '-c', SYNTAX_CHECKER],
            input=json.dumps(files, ensure_ascii=True), capture_output=True,
            text=True, encoding='utf-8', timeout=8)
        findings = json.loads(process.stdout) if process.returncode == 0 else None
        if not isinstance(findings, list) or len(findings) != len(files):
            raise ValueError('Invalid checker output')
    except (subprocess.TimeoutExpired, OSError, ValueError):
        return {'status':'unavailable', 'findings':[], 'checked':0, 'skipped':len(files),
                'message':'Bộ kiểm tra không hoàn tất; chưa thể kết luận cú pháp'}
    node = shutil.which('node')
    for file, finding in zip(files, findings):
        extension = file['path'].rsplit('.', 1)[-1].lower()
        if extension not in ('js','mjs','cjs'):
            continue
        if node is None:
            finding['message'] = 'Chưa kiểm tra JavaScript: máy chưa có Node.js'
            continue
        try:
            remaining = deadline-time.monotonic()
            if remaining <= 0:
                raise subprocess.TimeoutExpired('node', 8)
            mode = 'commonjs' if extension == 'cjs' else 'module'
            process = subprocess.run([node,'--check','--input-type='+mode], input=file['content'],
                capture_output=True, text=True, encoding='utf-8', errors='replace', timeout=min(3,remaining))
            finding.update(status='passed' if process.returncode == 0 else 'failed',
                message='Đạt cú pháp JavaScript ('+mode+')' if process.returncode == 0 else process.stderr.strip()[:800] or 'Lỗi cú pháp JavaScript')
        except (subprocess.TimeoutExpired, OSError):
            finding.update(status='unavailable', message='Không hoàn tất kiểm tra JavaScript')
    checked = sum(item['status'] in ('passed','failed') for item in findings)
    failed = any(item['status'] == 'failed' for item in findings)
    unavailable = any(item['status'] == 'unavailable' for item in findings)
    return {'status':'failed' if failed else 'unavailable' if unavailable else 'passed' if checked else 'not_supported',
            'findings':findings, 'checked':checked, 'skipped':len(files)-checked,
            'message':'Chỉ kiểm tra cú pháp Python/JSON/JavaScript (nếu có Node.js); chưa kiểm thử chức năng, HTML/CSS hay bảo mật'}
