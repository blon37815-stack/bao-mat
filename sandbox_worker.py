"""Trusted Docker entrypoint. Product code is executed only inside the container."""
import json
import os
from pathlib import Path
import re
import resource
import shutil
import subprocess
import sys


def limits():
    resource.setrlimit(resource.RLIMIT_FSIZE, (65536, 65536))
    resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
    resource.setrlimit(resource.RLIMIT_NOFILE, (128, 128))


def main():
    project = Path('/work/project')
    shutil.copytree('/source', project)
    os.chdir(project)
    if Path('tests').is_dir():
        start = 'tests'
    else:
        start = '.'
    command = [sys.executable, '-m', 'unittest', 'discover', '-s', start, '-p', 'test*.py', '-v']
    with open('/work/test-output.txt', 'wb') as output:
        try:
            result = subprocess.run(command, stdout=output, stderr=subprocess.STDOUT, timeout=25,
                                    preexec_fn=limits, env=dict(os.environ, PYTHONPATH=str(project)))
            code = result.returncode
        except subprocess.TimeoutExpired:
            code = 124
    text = Path('/work/test-output.txt').read_bytes()[:32768].decode('utf-8', errors='replace')
    counts = re.findall(r'Ran (\d+) tests?', text)
    count = int(counts[-1]) if counts else 0
    status = 'passed' if code == 0 and count > 0 else 'not_supported' if count == 0 and code in (0, 5) else 'failed'
    json.dump({'status':status, 'exit_code':code, 'tests':count, 'output':text,
               'command':command[1:], 'scope':'Kiểm thử unittest do sản phẩm cung cấp; chưa xác minh mọi yêu cầu chức năng'}, sys.stdout, ensure_ascii=True)


if __name__ == '__main__':
    main()
