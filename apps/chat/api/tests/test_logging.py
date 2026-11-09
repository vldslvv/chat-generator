import asyncio
import json
import socket
import subprocess
import sys
import time
from contextlib import contextmanager
from uuid import uuid4

import pytest
from helpers import login, receive, request
from websockets.sync.client import connect

from chat.api import create_app


@contextmanager
def server_process():
    # Exercise the imported app factory without chat-server's logging setup.
    code = """
import socket
from chat.api import create_app
from chat.server import create_server
listener = socket.socket()
listener.bind(("127.0.0.1", 0))
listener.listen(128)
port = listener.getsockname()[1]
print(port, flush=True)
create_server(create_app(), host="127.0.0.1", port=port).run(sockets=[listener])
"""
    process = subprocess.Popen(
        [sys.executable, "-c", code], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True
    )
    output = {}
    try:
        port = int(process.stdout.readline())
        url = f"ws://127.0.0.1:{port}/ws"
        deadline = time.monotonic() + 5
        while True:
            try:
                with connect(url, open_timeout=0.2):
                    break
            except OSError:
                assert process.poll() is None, "API process exited before startup"
                assert time.monotonic() < deadline, "API did not start"
                time.sleep(0.01)
        yield url, output
    finally:
        process.terminate()
        output["stdout"], output["stderr"] = process.communicate(timeout=8)


def test_imported_api_logs_rejections_and_abnormal_disconnect_to_stderr():
    rejected = []
    with server_process() as (url, output), connect(url) as client:
        client.send("{")
        assert receive(client)["type"] == "error"
        for kind, data, cause in [
            ("send", {"recipient": "bob", "text": "private-message"}, "Login required"),
            ("send", {"recipient": "bob"}, "Field required"),
            ("login", {"name": "INVALID"}, "String should match pattern"),
            ("unknown", {"text": "private-message"}, "Input tag 'unknown'"),
        ]:
            correlation = request(client, kind, data)
            assert receive(client)["type"] == "error"
            rejected.append((correlation, cause))
        login(client, "alice")
        correlation = request(client, "login", {"name": "alice"})
        assert receive(client)["type"] == "error"
        rejected.append((correlation, "Connection is already logged in"))

        # Abort a separate real TCP transport, then observe cleanup by logging in again.
        abrupt = connect(url)
        original = login(abrupt, "abrupt")
        abrupt.socket.shutdown(socket.SHUT_RDWR)
        abrupt.socket.close()
        abrupt.close()
        with connect(url) as replacement:
            deadline = time.monotonic() + 3
            while True:
                request(replacement, "login", {"name": "abrupt"})
                reply = receive(replacement)
                if reply["type"] == "login_ok":
                    assert reply["data"] == original
                    break
                assert time.monotonic() < deadline, "Aborted session was not cleaned up"
                time.sleep(0.01)
    stderr = output["stderr"]
    for correlation, cause in rejected:
        assert any(correlation in line and cause in line for line in stderr.splitlines())
    assert "Request rejected correlation_id=None cause=" in stderr
    assert "Abnormal WebSocket disconnect" in stderr
    assert "close code 1006" in stderr
    assert "private-message" not in stderr
    assert "Request rejected" not in output["stdout"]


@pytest.mark.parametrize("failure_at", ["accept", "receive", "reply"])
def test_asgi_operation_failure_logs_cause_and_available_correlation(caplog, failure_at):
    correlation = str(uuid4())
    frames = iter(
        [
            {"type": "websocket.connect"},
            {
                "type": "websocket.receive",
                "text": json.dumps(
                    {"type": "login", "correlation_id": correlation, "data": {"name": "alice"}}
                ),
            },
        ]
    )

    async def receive_frame():
        if failure_at == "receive":
            raise RuntimeError("receive transport lost")
        return next(frames)

    async def send_frame(frame):
        if failure_at == "accept" or frame["type"] == "websocket.send":
            raise OSError(f"{failure_at} transport lost")

    scope = {"type": "websocket", "path": "/ws", "headers": [], "query_string": b""}
    asyncio.run(create_app()(scope, receive_frame, send_frame))
    assert f"{failure_at} transport lost" in caplog.text
    assert "WebSocket operation failed" in caplog.text
    expected_correlation = correlation if failure_at == "reply" else "None"
    assert f"correlation_id={expected_correlation}" in caplog.text
