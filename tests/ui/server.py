"""Ephemeral application instance used by browser integration tests."""
from pathlib import Path
import os
import sys
import tempfile

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import app

with tempfile.TemporaryDirectory(prefix='bao-mat-ui-') as temporary:
    app.DB = Path(temporary)/'tasks.sqlite3'
    app.recover()
    server = app.ThreadingHTTPServer(('127.0.0.1',int(os.environ.get('PORT','8989'))),app.Handler)
    server.serve_forever()
