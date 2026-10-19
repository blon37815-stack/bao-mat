"""Cancellable local Ollama requests; no model-generated code is executed."""
import json
from pathlib import Path
import subprocess
import sys
import time
import urllib.request


class InferenceCancelled(Exception):
    pass


def request_completion(messages, model, base_url, cancelled=None):
    """Own the request process so even a stalled stream can be cancelled."""
    if cancelled is not None and cancelled.is_set():
        raise InferenceCancelled()
    process = subprocess.Popen([sys.executable, '-I', str(Path(__file__).resolve())],
        stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        text=True, encoding='utf-8')
    payload = json.dumps({'messages':messages, 'model':model, 'base_url':base_url}, ensure_ascii=True)
    deadline = time.monotonic()+600
    try:
        while True:
            if cancelled is not None and cancelled.is_set():
                raise InferenceCancelled()
            if time.monotonic() >= deadline:
                raise TimeoutError('Ollama request exceeded its deadline')
            try:
                output, _ = process.communicate(input=payload, timeout=.2)
            except subprocess.TimeoutExpired:
                payload = None
                continue
            if cancelled is not None and cancelled.is_set():
                raise InferenceCancelled()
            if process.returncode != 0:
                raise RuntimeError('Ollama stream failed')
            content = json.loads(output)
            if not isinstance(content, str) or not content.strip():
                raise ValueError('Empty Ollama response')
            return content
    finally:
        if process.poll() is None:
            process.kill()
        process.communicate()


def stream_request(settings):
    payload = {'model':settings['model'], 'messages':settings['messages'], 'stream':True, 'think':False}
    request = urllib.request.Request(settings['base_url'].rstrip('/')+'/api/chat',
        data=json.dumps(payload).encode('utf-8'), headers={'Content-Type':'application/json'})
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    chunks, size = [], 0
    with opener.open(request, timeout=600) as response:
        while True:
            raw = response.readline(2_000_001)
            if not raw:
                raise ValueError('Incomplete Ollama stream')
            if len(raw) > 2_000_000:
                raise ValueError('Ollama chunk exceeds limit')
            item = json.loads(raw)
            if item.get('error'):
                raise ValueError('Ollama reported an error')
            content = item.get('message', {}).get('content', '')
            if not isinstance(content, str):
                raise ValueError('Invalid Ollama content')
            size += len(content.encode('utf-8'))
            if size > 2_000_000:
                raise ValueError('Ollama response exceeds limit')
            chunks.append(content)
            if item.get('done') is True:
                return ''.join(chunks)


if __name__ == '__main__':
    try:
        result = stream_request(json.load(sys.stdin))
        json.dump(result, sys.stdout, ensure_ascii=True)
    except Exception:
        # Provider exceptions can contain private request data; do not forward them.
        raise SystemExit(1)
