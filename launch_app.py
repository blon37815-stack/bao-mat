"""Select the dependency environment prepared by the updater without replacing .venv."""
import json
import os
from pathlib import Path
import subprocess
import sys
from release_support import requirements_hash

ROOT = Path(__file__).resolve().parent
POINTER = ROOT/'data'/'runtime-environment.json'


def selected_python():
    if not POINTER.exists():
        return sys.executable
    value = json.loads(POINTER.read_text(encoding='utf-8'))
    if value['requirements_sha256'] != requirements_hash(ROOT/'requirements.txt'):
        raise ValueError('Moi truong va requirements khong khop. Chay cai-dat.bat de cai lai va dat lai moi truong.')
    relative = Path(value['python_relative'])
    if relative.is_absolute() or '..' in relative.parts or not relative.parts or relative.parts[0] != '.runtime-envs':
        raise ValueError('Duong dan moi truong khong hop le')
    python = (ROOT/relative).absolute()
    if not python.is_file():
        raise ValueError('Khong tim thay Python cua ban cap nhat; chay cai-dat.bat')
    return str(python)


def main():
    if len(sys.argv) == 2 and sys.argv[1] == 'reset-environment':
        POINTER.unlink(missing_ok=True)
        return 0
    command = sys.argv[1] if len(sys.argv) > 1 else 'run'
    if command not in ('run', 'update'):
        raise ValueError('Lenh khoi dong khong hop le')
    environment = dict(os.environ)
    if (ROOT/'RECOVERED_VERSION.json').is_file():
        environment['BOT_DB'] = str(ROOT/'data'/'tasks.sqlite3')
    return subprocess.call([selected_python(), str(ROOT/('app.py' if command == 'run' else 'update_app.py'))], cwd=ROOT, env=environment)


if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except (OSError, ValueError, KeyError) as error:
        print(str(error)); raise SystemExit(1)
    except KeyboardInterrupt:
        raise SystemExit(130)
