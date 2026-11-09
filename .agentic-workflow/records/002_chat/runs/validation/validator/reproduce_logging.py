import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import time
from uuid import uuid4
from websockets.sync.client import connect

root = Path('/home/vv/assignment/chat-generator')
report = []
with socket.socket() as s:
    s.bind(('127.0.0.1', 0))
    port = s.getsockname()[1]
url = f'ws://127.0.0.1:{port}/ws'
env = {**os.environ, 'PYTHONPATH': str(root / 'apps/chat/api')}
server = subprocess.Popen([sys.executable, '-c', 'from chat.server import create_server; from chat.api import create_app; create_server(create_app(), host="127.0.0.1", port='+str(port)+').run()'], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, env=env)
try:
    for _ in range(100):
        try:
            client = connect(url, open_timeout=0.2)
            break
        except OSError:
            time.sleep(0.02)
    correlation = str(uuid4())
    with client:
        client.send(json.dumps({'type': 'send', 'correlation_id': correlation, 'data': {'recipient': 'bob', 'text': 'not logged in'}}))
        reply = json.loads(client.recv(timeout=2))
        report.append({'component': 'api', 'rejected_request': 'send without login', 'correlation_id': correlation, 'reply': reply})
finally:
    server.terminate()
    out, err = server.communicate(timeout=5)
report[-1].update(stderr=err, stderr_contains_correlation=correlation in err, stderr_contains_cause='Login required' in err)
for name, command, cwd in [
    ('python', [str(root/'apps/chat/python-client/.venv/bin/chat-python'), '--url', url], root/'apps/chat/python-client'),
    ('rust', [str(root/'apps/chat/rust-client/target/debug/chat-rust'), '--url', url], root/'apps/chat/rust-client')]:
    cli = subprocess.run(command, input='/send bob rejected\n/unknown\n/quit\n', capture_output=True, text=True, cwd=cwd, timeout=5)
    report.append({'component': name, 'exit_code': cli.returncode, 'stdout': cli.stdout, 'stderr': cli.stderr})
print(json.dumps(report, indent=2, ensure_ascii=False))
