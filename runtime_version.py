"""Capture startup provenance once so an old process cannot claim freshly pulled code."""
from datetime import datetime, timezone
import hashlib
from pathlib import Path
import subprocess

APP_VERSION = '0.1.0-dev'
ROOT = Path(__file__).resolve().parent


def startup_info():
    digest = hashlib.sha256()
    paths = [*ROOT.glob('*.py'),*(ROOT/name for name in ('index.html','app.js','resource_ui.js','workspace_ui.js','styles.css','requirements.txt'))]
    for path in sorted(paths):
        digest.update(path.name.encode('utf-8')+b'\0'+path.read_bytes()+b'\0')
    commit,dirty = 'unknown',None
    try:
        commit = subprocess.run(['git','-C',str(ROOT),'rev-parse','HEAD'],check=True,
                                capture_output=True,text=True,timeout=2).stdout.strip()
        dirty = bool(subprocess.run(['git','-C',str(ROOT),'status','--porcelain','--untracked-files=normal'],
                                   check=True,capture_output=True,text=True,timeout=2).stdout.strip())
    except (OSError,subprocess.SubprocessError):
        pass
    return {'version':APP_VERSION,'commit':commit,'dirty_at_start':dirty,'source_digest':digest.hexdigest(),
            'started_at':datetime.now(timezone.utc).isoformat()}


RUNTIME_INFO = startup_info()
