"""Review-only source copies and downloadable patches. Never apply or execute them."""
from datetime import datetime, timezone
import difflib
import hashlib
import io
import json
from pathlib import Path
import shutil
import tempfile
import uuid
import zipfile

from artifacts import parse_files, check_files
from release_support import atomic_json, extract_source

EXTENSIONS = {'.py', '.js', '.cjs', '.mjs', '.css', '.html', '.md'}


def stamp():
    return datetime.now(timezone.utc).isoformat()


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def source_snapshot(root):
    """Copy a bounded source inventory, never data, environments, credentials or Git."""
    root = Path(root).resolve()
    paths = [p for p in root.iterdir() if p.is_file() and (p.suffix in EXTENSIONS or p.name in ('requirements.txt', 'LICENSE'))]
    for directory in ('tests', 'docs', 'third_party/ecc'):
        target = root/directory
        if target.is_dir():
            paths.extend(p for p in target.rglob('*') if p.is_file() and
                (p.suffix in EXTENSIONS | {'.json'} or p.name == 'LICENSE') and
                not any(part.startswith('.') or part in ('node_modules', '__pycache__', 'test-results', 'playwright-report') for part in p.relative_to(target).parts))
    if not paths or len(paths) > 500:
        raise ValueError('Bản sao mã nguồn trống hoặc vượt 500 tệp')
    files, total = {}, 0
    for path in sorted(paths):
        if path.is_symlink() or not path.resolve().is_relative_to(root) or any(parent.is_symlink() for parent in path.parents if parent != root):
            raise ValueError('Bản sao mã nguồn có liên kết đường dẫn không được hỗ trợ')
        size = path.stat().st_size
        total += size
        if size > 2_000_000 or total > 16_000_000:
            raise ValueError('Bản sao mã nguồn vượt 16 MB hoặc có tệp trên 2 MB')
        raw = path.read_bytes()
        if len(raw) != size:
            raise ValueError('Mã nguồn đang thay đổi; thử tạo bản sao lại')
        files[path.relative_to(root).as_posix()] = raw
    manifest = {key: digest(value) for key, value in files.items()}
    return files, digest(json.dumps(manifest, sort_keys=True).encode())


def proposed_files(files):
    files = parse_files(json.dumps({'files': files}, ensure_ascii=False))
    for file in files:
        path = Path(file['path'])
        if (any(part.startswith('.') for part in path.parts) or path.parts[0] in ('data', 'third_party')
                or not (len(path.parts) == 1 or path.parts[0] in ('tests', 'docs'))
                or not (path.suffix in EXTENSIONS or file['path'] == 'requirements.txt')):
            raise ValueError('Đề xuất chỉ sửa mã nguồn gốc, tests hoặc docs; không sửa dữ liệu, khóa, Git hay thư viện ECC')
    return files


def patch_text(before, files):
    changes, patches = [], []
    for file in files:
        name, text = file['path'], file['content']
        old = before.get(name)
        if old == text.encode('utf-8'):
            continue
        if any(key.casefold() == name.casefold() and key != name for key in before):
            raise ValueError('Tên tệp xung đột chữ hoa/thường trên Windows')
        if any(name.startswith(key+'/') or key.startswith(name+'/') for key in before):
            raise ValueError('Tên tệp xung đột thư mục gốc')
        previous = old.decode('utf-8') if old is not None else ''
        lines = list(difflib.unified_diff(previous.splitlines(keepends=True), text.splitlines(keepends=True),
            fromfile='a/'+name if old is not None else '/dev/null', tofile='b/'+name, lineterm='\n'))
        patch = ''.join(line if line.endswith('\n') else line+'\n\\ No newline at end of file\n' for line in lines)
        # An empty newly created file needs Git's header even without a hunk.
        if old is None:
            patch = 'diff --git a/'+name+' b/'+name+'\nnew file mode 100644\n'+patch
        patches.append(patch)
        changes.append({'path':name, 'kind':'added' if old is None else 'modified', 'diff':patch,
                        'sha256':digest(text.encode('utf-8'))})
    if not changes:
        raise ValueError('Bộ tệp không thay đổi mã nguồn; chưa tạo đề xuất rỗng')
    patch = ''.join(patches)
    if len(patch.encode('utf-8')) > 2_000_000:
        raise ValueError('Patch vượt 2 MB; chia đề xuất thành các thay đổi nhỏ hơn')
    return changes, patch


def public(row):
    return {key: row[key] for key in ('id', 'task_id', 'title', 'status', 'created', 'reviewed')}


def list_proposals(db):
    return {'proposals': [public(row) for row in db.execute('SELECT id,task_id,title,status,created,reviewed FROM upgrade_proposals ORDER BY created DESC,id DESC')],
            'limit':10, 'message':'Bản đề xuất chỉ dùng để duyệt và tải patch; không tự ghi vào ứng dụng đang chạy'}


def directory_for(storage, proposal_id):
    if not isinstance(proposal_id, str) or len(proposal_id) != 32 or any(c not in '0123456789abcdef' for c in proposal_id):
        raise LookupError('Không tìm thấy đề xuất')
    parent = Path(storage)/'proposals'
    if parent.is_symlink() or Path(storage).is_symlink():
        raise ValueError('Thư mục đề xuất có liên kết không được hỗ trợ')
    path = parent/proposal_id
    if path.is_symlink():
        raise ValueError('Thư mục đề xuất có liên kết không được hỗ trợ')
    return path


def verify(db, storage, proposal_id):
    row = db.execute('SELECT * FROM upgrade_proposals WHERE id=?', (proposal_id,)).fetchone()
    if not row:
        raise LookupError('Không tìm thấy đề xuất')
    spec = json.loads(row['spec'])
    directory = directory_for(storage, proposal_id)
    if digest(row['bundle']) != spec['bundle_sha256']:
        raise ValueError('Bản sao trong cơ sở dữ liệu không khớp hash')
    if not directory.exists():
        # SQLite backups include the authoritative bundle; rebuild only its cache.
        directory.parent.mkdir(parents=True, exist_ok=True)
        temporary = Path(tempfile.mkdtemp(prefix='.restoring-', dir=directory.parent))
        try:
            extract_source(row['bundle'], temporary)
            temporary.rename(directory)
        finally:
            if temporary.exists():
                shutil.rmtree(temporary)
    for filename, expected in spec['stored_files'].items():
        path = directory/filename
        if path.is_symlink() or any(parent.is_symlink() for parent in path.parents if parent != directory):
            raise ValueError('Bản đề xuất chứa liên kết không được hỗ trợ')
        if not path.is_file() or path.stat().st_size > 16_000_000 or digest(path.read_bytes()) != expected:
            raise ValueError('Bản đề xuất đã thay đổi hoặc mất tệp; tạo đề xuất mới')
    return row, spec, directory


def create(db, root, storage, task_id, title, files, runtime):
    if not isinstance(title, str) or not title.strip() or len(title) > 120:
        raise ValueError('Tên đề xuất từ 1 đến 120 ký tự')
    if db.execute('SELECT COUNT(*) FROM upgrade_proposals').fetchone()[0] >= 10:
        raise ValueError('Tối đa 10 đề xuất; tải và xóa bản không dùng trước khi tạo tiếp')
    files = proposed_files(files)
    baseline, base_digest = source_snapshot(root)
    changes, patch = patch_text(baseline, files)
    checks = check_files(files)
    proposal_id = uuid.uuid4().hex
    destination = directory_for(storage, proposal_id)
    destination.parent.mkdir(parents=True, exist_ok=True)
    spec = {'version':1, 'base_digest':base_digest, 'app':runtime, 'checks':checks,
            'changes':changes, 'patch_sha256':digest(patch.encode('utf-8')),
            'source_task_files_sha256':digest(json.dumps(files, sort_keys=True, ensure_ascii=False).encode()),
            'limitations':'Kiểm tra cú pháp các tệp được đề xuất; chưa chạy toàn bộ kiểm thử ứng dụng mới, chưa áp dụng hoặc triển khai',
            'source_task_checks':[json.loads(row['spec']) for row in db.execute('SELECT spec FROM task_checks WHERE task_id=? ORDER BY attempt', (task_id,))],
            'stored_files':{}}
    temporary = Path(tempfile.mkdtemp(prefix='.preparing-', dir=destination.parent))
    try:
        source_zip = io.BytesIO()
        with zipfile.ZipFile(source_zip, 'w', zipfile.ZIP_DEFLATED) as archive:
            for name, raw in baseline.items():
                archive.writestr(name, raw)
        extract_source(source_zip.getvalue(), temporary/'base')
        extract_source(source_zip.getvalue(), temporary/'candidate')
        (temporary/'proposal.patch').write_bytes(patch.encode('utf-8'))
        for file in files:
            path = temporary/'candidate'/file['path']
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(file['content'].encode('utf-8'))
        for path in temporary.rglob('*'):
            if path.is_file():
                spec['stored_files'][path.relative_to(temporary).as_posix()] = digest(path.read_bytes())
        atomic_json(temporary/'PROPOSAL.json', {key:value for key,value in spec.items() if key != 'stored_files'})
        spec['stored_files']['PROPOSAL.json'] = digest((temporary/'PROPOSAL.json').read_bytes())
        bundle = io.BytesIO()
        with zipfile.ZipFile(bundle, 'w', zipfile.ZIP_DEFLATED) as archive:
            for name in spec['stored_files']:
                archive.write(temporary/name, name)
        spec['bundle_sha256'] = digest(bundle.getvalue())
        temporary.rename(destination)
        try:
            db.execute('INSERT INTO upgrade_proposals VALUES (?,?,?,?,?,?,NULL,?)',
                (proposal_id, task_id, title.strip(), 'pending', json.dumps(spec, ensure_ascii=False), stamp(), bundle.getvalue()))
        except Exception:
            shutil.rmtree(destination)
            raise
    finally:
        if temporary.exists():
            shutil.rmtree(temporary)
    return {'id':proposal_id, 'status':'pending', 'checks':checks, 'message':'Đã lưu bản sao và patch; chưa thay đổi ứng dụng đang chạy'}


def detail(db, root, storage, proposal_id):
    row, spec, _ = verify(db, storage, proposal_id)
    _, current_digest = source_snapshot(root)
    return dict(public(row), **{key:value for key,value in spec.items() if key != 'stored_files'},
                stale=current_digest != spec['base_digest'])


def review(db, root, storage, proposal_id, decision, confirmation):
    if decision not in ('approved', 'rejected') or confirmation != proposal_id:
        raise ValueError('Cần xác nhận đúng đề xuất và quyết định duyệt hoặc từ chối')
    row, spec, _ = verify(db, storage, proposal_id)
    if row['status'] != 'pending':
        raise ValueError('Đề xuất đã được xem xét; hãy tạo bản mới nếu cần đổi')
    if decision == 'approved':
        _, current_digest = source_snapshot(root)
        if current_digest != spec['base_digest']:
            raise ValueError('Mã nguồn gốc đã thay đổi; tạo đề xuất mới để đối chiếu đúng phiên bản')
        if spec['checks']['status'] in ('failed', 'unavailable'):
            raise ValueError('Kiểm tra cú pháp chưa đạt; chưa duyệt đề xuất')
    if not db.execute("UPDATE upgrade_proposals SET status=?,reviewed=? WHERE id=? AND status='pending'", (decision, stamp(), proposal_id)).rowcount:
        raise ValueError('Đề xuất vừa được xem xét ở cửa sổ khác')
    return {'id':proposal_id, 'status':decision, 'message':'Đã lưu quyết định; chưa áp dụng patch, cài phụ thuộc hoặc chạy ứng dụng mới'}


def download(db, storage, proposal_id):
    row, spec, directory = verify(db, storage, proposal_id)
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, 'w', zipfile.ZIP_DEFLATED) as archive:
        for name in spec['stored_files']:
            archive.write(directory/name, name)
        archive.writestr('REVIEW.json', json.dumps(public(row), ensure_ascii=False, indent=2))
        archive.writestr('MANIFEST.json', json.dumps({'files':spec['stored_files'], 'base_digest':spec['base_digest'],
            'bundle_sha256':spec['bundle_sha256']}, ensure_ascii=False, indent=2))
        archive.writestr('HUONG-DAN.md', '# Bản đề xuất nâng cấp\n\nbase/ là mã nguồn gốc; candidate/ là bản sao đã ghép đề xuất.\nproposal.patch dùng để rà soát và áp dụng trong checkout riêng.\nDuyệt chỉ ghi quyết định, không tự chạy hoặc áp dụng vào ứng dụng.\nKiểm thử candidate trong môi trường cô lập trước; sao lưu dữ liệu trước khi triển khai.\n')
    return buffer.getvalue()


def delete(db, storage, proposal_id, confirmation):
    if confirmation != proposal_id:
        raise ValueError('Xác nhận xóa đề xuất không khớp')
    row = db.execute('SELECT id FROM upgrade_proposals WHERE id=?', (proposal_id,)).fetchone()
    if not row:
        raise LookupError('Không tìm thấy đề xuất')
    directory = directory_for(storage, proposal_id)
    if directory.exists():
        shutil.rmtree(directory)
    db.execute('DELETE FROM upgrade_proposals WHERE id=?', (proposal_id,))
    return {'deleted':proposal_id, 'message':'Đã xóa bản sao đề xuất; giữ nguyên công việc và mã ứng dụng'}
