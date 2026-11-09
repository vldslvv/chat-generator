import json
import subprocess
import time
from uuid import uuid4
from websockets.sync.client import connect
from websockets.exceptions import WebSocketException

container = subprocess.check_output([
    'docker', 'run', '-d', '--rm', '-p', '127.0.0.1::8000', 'local-chat:verification'
], text=True).strip()
try:
    port = subprocess.check_output(['docker', 'port', container, '8000'], text=True).strip().rsplit(':',1)[1]
    url = 'ws://127.0.0.1:' + port + '/ws'
    def client():
        deadline = time.monotonic() + 15
        while True:
            try:
                return connect(url)
            except (OSError, EOFError, WebSocketException):
                if time.monotonic() > deadline:
                    raise
                time.sleep(.1)
    def send(ws, kind, data):
        ws.send(json.dumps({'type':kind, 'correlation_id':str(uuid4()), 'data':data}))
    def receive(ws):
        return json.loads(ws.recv(timeout=3))
    with client() as alice, client() as bob:
        send(alice, 'login', {'name':'alice'})
        old_alice = receive(alice)['data']
        send(bob, 'login', {'name':'bob'})
        old_bob = receive(bob)['data']
        send(alice, 'send', {'recipient':'bob', 'text':'container'})
        accepted, incoming = receive(alice), receive(bob)
        assert accepted['data'] == incoming['data']
        message_id = accepted['data']['id']
        send(bob, 'ack', {'message_id':message_id})
        assert receive(alice)['type'] == 'delivery_receipt'
    subprocess.run(['docker','restart',container], check=True, capture_output=True)
    port = subprocess.check_output(['docker', 'port', container, '8000'], text=True).strip().rsplit(':',1)[1]
    url = 'ws://127.0.0.1:' + port + '/ws'
    with client() as alice, client() as bob:
        send(alice, 'login', {'name':'alice'})
        new_alice = receive(alice)['data']
        send(bob, 'login', {'name':'bob'})
        new_bob = receive(bob)['data']
        assert new_alice['id'] != old_alice['id']
        assert new_bob['id'] != old_bob['id']
        send(bob, 'ack', {'message_id':message_id})
        assert receive(bob)['type'] == 'error'
    print('PASS: container entry point, login/send/ack, process restart resets user IDs and rejects old message acknowledgment')
finally:
    logs = subprocess.check_output(['docker', 'logs', container], stderr=subprocess.STDOUT, text=True)
    assert 'Delivery attempt' in logs and 'Delivery succeeded' in logs
    print(logs)
    subprocess.run(['docker','stop',container], check=True, capture_output=True)
    print('PASS: container stopped and removed')
