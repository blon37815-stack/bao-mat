"""Bounded Docker-only product checks. Never fall back to host execution."""
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import threading
import time
import uuid
from contextlib import ExitStack

from artifacts import parse_files
from ollama_transport import InferenceCancelled

DEFAULT_IMAGE = 'python:3.12-slim@sha256:a6e34c598f2467ed0e9a8d349809fcd8b5c603269512df273a0bb1784edc11b1'
RUNNER_LOCK = threading.Lock()


def stop_container(process, name, readers):
    try:
        subprocess.run(['docker', 'rm', '-f', name], capture_output=True, timeout=5)
    except (OSError, subprocess.SubprocessError):
        pass
    if process.poll() is None:
        process.kill()
    process.wait()
    for reader in readers:
        reader.join(timeout=2)
    for stream in (process.stdout, process.stderr):
        stream.close()


def collect_output(stream, buffer, limit, overflow):
    while True:
        block = stream.read(4096)
        if not block:
            return
        remaining = limit-len(buffer)
        buffer.extend(block[:max(0, remaining)])
        if len(block) > remaining:
            overflow.set()


def image_name():
    value = os.environ.get('BOT_SANDBOX_IMAGE', DEFAULT_IMAGE)
    if not re.fullmatch(r'[a-zA-Z0-9][a-zA-Z0-9_./:@-]{0,249}', value):
        raise ValueError('Tên image Docker không hợp lệ')
    return value


def health():
    image = image_name()
    if not shutil.which('docker'):
        return {'status':'unavailable', 'image':image, 'message':'Chưa cài Docker; không chạy mã trên máy thật'}
    try:
        engine = subprocess.run(['docker', 'info', '--format', '{{.OSType}}'], check=True, capture_output=True, timeout=5)
        if engine.stdout.strip() != b'linux':
            return {'status':'unavailable', 'image':image, 'message':'Cần Docker ở chế độ Linux containers'}
        subprocess.run(['docker', 'image', 'inspect', image], check=True, capture_output=True, timeout=5)
    except (OSError, subprocess.SubprocessError):
        return {'status':'unavailable', 'image':image, 'message':'Docker chưa sẵn sàng hoặc thiếu image; không tự tải image'}
    return {'status':'ready', 'image':image, 'message':'Docker và image đã có; chỉ hỗ trợ unittest Python, mạng bị tắt'}


def check_product(files, cancelled=None):
    files = parse_files(json.dumps({'files':files}, ensure_ascii=False))
    if not any(re.search(r'(^|/)test[^/]*\.py$', item['path']) for item in files):
        return {'status':'not_supported', 'tests':0, 'output':'Chưa có tệp unittest Python; không suy đoán đã kiểm thử chức năng'}
    if cancelled is not None and cancelled.is_set():
        raise InferenceCancelled()
    if not RUNNER_LOCK.acquire(blocking=False):
        return {'status':'unavailable', 'output':'Đang có một lượt kiểm thử Docker; thử lại sau'}
    name = 'bao-mat-check-' + uuid.uuid4().hex
    process = None
    try:
        ready = health()
        if ready['status'] != 'ready':
            return dict(ready, output=ready['message'])
        with ExitStack() as stack:
            temporary = stack.enter_context(tempfile.TemporaryDirectory(prefix='bao-mat-check-'))
            source = Path(temporary)/'source'
            runner = Path(temporary)/'runner'
            source.mkdir(); runner.mkdir()
            for item in files:
                path = source/item['path']
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(item['content'], encoding='utf-8')
                path.chmod(0o644)
            for directory in (Path(temporary), source, runner, *[p for p in source.rglob('*') if p.is_dir()]):
                directory.chmod(0o755)
            worker = runner/'check.py'
            worker.write_bytes((Path(__file__).with_name('sandbox_worker.py')).read_bytes())
            worker.chmod(0o644)
            mounts = ['--mount', f'type=bind,source={source},target=/source,readonly',
                      '--mount', f'type=bind,source={runner},target=/runner,readonly']
            # Docker --mount treats commas as separators; do not accept an ambiguous host path.
            if ',' in str(source) or ',' in str(runner):
                return {'status':'unavailable', 'output':'Đường dẫn tạm có dấu phẩy; chọn thư mục TEMP khác'}
            command = ['docker', 'run', '--name', name, '--rm', '--pull=never', '--network', 'none',
                       '--read-only', '--user', '65534:65534', '--cap-drop', 'ALL',
                       '--security-opt', 'no-new-privileges', '--memory', '256m', '--memory-swap', '256m',
                       '--cpus', '1', '--pids-limit', '64', '--log-driver', 'none',
                       '--tmpfs', '/work:rw,nosuid,nodev,size=64m,mode=1777',
                       '--tmpfs', '/tmp:rw,nosuid,nodev,size=32m,mode=1777',
                       '-e', 'PYTHONDONTWRITEBYTECODE=1', '-e', 'PYTHONUTF8=1',
                       *mounts, ready['image'], 'python', '-I', '/runner/check.py']
            process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            readers, output, errors = [], bytearray(), bytearray()
            overflow = threading.Event()
            stack.callback(stop_container, process, name, readers)
            for stream, buffer, limit in ((process.stdout, output, 262144), (process.stderr, errors, 8192)):
                reader = threading.Thread(target=collect_output, args=(stream, buffer, limit, overflow), daemon=True)
                reader.start(); readers.append(reader)
            deadline = time.monotonic() + 40
            while True:
                if cancelled is not None and cancelled.is_set():
                    raise InferenceCancelled()
                if time.monotonic() > deadline:
                    return {'status':'failed', 'exit_code':124, 'output':'Kiểm thử quá thời hạn; đã yêu cầu dừng container'}
                if overflow.is_set():
                    return {'status':'failed', 'output':'Đầu ra kiểm thử vượt giới hạn; đã yêu cầu dừng container'}
                try:
                    process.wait(timeout=.2)
                    break
                except subprocess.TimeoutExpired:
                    continue
            for reader in readers:
                reader.join(timeout=2)
            if overflow.is_set() or any(reader.is_alive() for reader in readers):
                return {'status':'failed', 'output':'Đầu ra kiểm thử vượt giới hạn hoặc chưa đóng'}
            if process.returncode != 0:
                return {'status':'unavailable', 'output':'Không chạy được container; kiểm tra Docker, image và quyền chia sẻ thư mục'}
            try:
                report = json.loads(bytes(output))
                if report['status'] not in ('passed','failed','not_supported'):
                    raise ValueError()
            except (ValueError, KeyError, TypeError):
                return {'status':'unavailable', 'output':'Runner không trả báo cáo hợp lệ'}
            return dict(report, image=ready['image'], isolation={'network':'none', 'user':'65534:65534',
                        'read_only':True, 'memory_mb':256, 'cpus':1, 'pids_limit':64}, runner_version=1)
    finally:
        RUNNER_LOCK.release()
