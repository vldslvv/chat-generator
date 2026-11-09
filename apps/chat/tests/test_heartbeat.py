import base64
import hashlib
import json
import os
import socket
import struct
import time
from contextlib import contextmanager
from uuid import uuid4

from helpers import receive, request
from websockets.sync.client import connect


def exact(sock, size):
    result = b""
    while len(result) < size:
        chunk = sock.recv(size - len(result))
        if not chunk:
            raise EOFError("Connection closed")
        result += chunk
    return result


def frame(sock):
    first, second = exact(sock, 2)
    size = second & 127
    if size == 126:
        size = struct.unpack("!H", exact(sock, 2))[0]
    elif size == 127:
        size = struct.unpack("!Q", exact(sock, 8))[0]
    assert second & 128 == 0
    return first & 15, exact(sock, size)


def send_frame(sock, opcode, payload):
    mask = os.urandom(4)
    size = len(payload)
    header = (
        bytes([128 | opcode, 128 | size])
        if size < 126
        else (bytes([128 | opcode, 128 | 126]) + struct.pack("!H", size))
    )
    masked = bytes(byte ^ mask[index % 4] for index, byte in enumerate(payload))
    sock.sendall(header + mask + masked)


@contextmanager
def raw_connection(port):
    with socket.create_connection(("127.0.0.1", port), timeout=25) as sock:
        key = base64.b64encode(os.urandom(16)).decode()
        sock.sendall(
            (
                f"GET /ws HTTP/1.1\r\nHost: 127.0.0.1:{port}\r\n"
                "Upgrade: websocket\r\nConnection: Upgrade\r\n"
                f"Sec-WebSocket-Key: {key}\r\nSec-WebSocket-Version: 13\r\n\r\n"
            ).encode()
        )
        response = b""
        while not response.endswith(b"\r\n\r\n"):
            response += exact(sock, 1)
        assert b"101 Switching Protocols" in response
        accept = base64.b64encode(
            hashlib.sha1(
                (key + "258EAFA5-E914-47DA-95CA-C5AB0DC85B11").encode(), usedforsecurity=False
            ).digest()
        )
        assert accept in response
        yield sock


def test_real_ping_matching_pong_and_timeout_cleanup(server):
    url, port = server
    with raw_connection(port) as responsive, raw_connection(port) as silent:
        correlation = str(uuid4())
        send_frame(
            silent,
            1,
            json.dumps(
                {"type": "login", "correlation_id": correlation, "data": {"name": "silent"}}
            ).encode(),
        )
        opcode, payload = frame(silent)
        assert opcode == 1
        user = json.loads(payload)["data"]
        start = time.monotonic()
        opcode, payload = frame(responsive)
        assert opcode == 9
        assert 18 <= time.monotonic() - start <= 23
        send_frame(responsive, 10, payload)
        opcode, _ = frame(silent)
        assert opcode == 9
        # An unrelated pong must not satisfy the outstanding server ping.
        send_frame(silent, 10, b"not-the-ping-payload")
        opcode, second_ping = frame(responsive)
        assert opcode == 9
        send_frame(responsive, 10, second_ping)
        opcode, close = frame(silent)
        assert opcode == 8
        assert struct.unpack("!H", close[:2])[0] == 1011
        assert 38 <= time.monotonic() - start <= 44
        send_frame(silent, 8, close)
        # Responsive connection remains usable after two matching pongs.
        send_frame(
            responsive,
            1,
            json.dumps(
                {"type": "login", "correlation_id": str(uuid4()), "data": {"name": "responsive"}}
            ).encode(),
        )
        opcode, payload = frame(responsive)
        assert opcode == 1
        assert json.loads(payload)["type"] == "login_ok"
    deadline = time.monotonic() + 3
    with connect(url) as reconnected:
        while True:
            request(reconnected, "login", {"name": "silent"})
            reply = receive(reconnected)
            if reply["type"] == "login_ok":
                assert reply["data"] == user
                break
            assert reply["type"] == "error"
            assert time.monotonic() < deadline, "Heartbeat session was not released"
            time.sleep(0.01)
