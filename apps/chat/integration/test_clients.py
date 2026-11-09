"""Exercise both shipped CLIs against the real API, in both directions."""

import os
import queue
import socket
import subprocess
import threading
import time
from contextlib import ExitStack, contextmanager
from pathlib import Path
from uuid import UUID

ROOT = Path(__file__).resolve().parents[1]


class Terminal:
    def __init__(self, command, cwd):
        self.lines = queue.Queue()
        self.transcript = []
        self.process = subprocess.Popen(
            command,
            cwd=cwd,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            env={**os.environ, "PYTHONUNBUFFERED": "1"},
        )
        self.reader = threading.Thread(target=self._read, daemon=True)
        self.reader.start()

    def _read(self):
        for line in self.process.stdout:
            self.transcript.append(line.rstrip("\r\n"))
            self.lines.put(line.rstrip("\r\n"))

    def send(self, command):
        self.process.stdin.write(command + "\n")
        self.process.stdin.flush()

    def expect(self, fragment, timeout=10):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            try:
                line = self.lines.get(timeout=max(0.01, deadline - time.monotonic()))
            except queue.Empty:
                break
            if fragment in line:
                return line
        raise AssertionError(f"Missing {fragment!r}; transcript: {self.transcript}")

    def close(self):
        try:
            if self.process.poll() is None:
                self.send("/quit")
                self.process.wait(timeout=5)
        finally:
            if self.process.poll() is None:
                self.process.kill()
                self.process.wait(timeout=5)
            self.reader.join(timeout=2)
            self.process.stdin.close()
            self.process.stdout.close()


@contextmanager
def server():
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        port = listener.getsockname()[1]
    command = [
        "uv",
        "run",
        "--frozen",
        "python",
        "-c",
        (
            "from chat.api import create_app; from chat.server import create_server; "
            f"create_server(create_app(), host='127.0.0.1', port={port}).run()"
        ),
    ]
    process = subprocess.Popen(
        command, cwd=ROOT / "api", stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
    )
    try:
        deadline = time.monotonic() + 10
        while True:
            try:
                with socket.create_connection(("127.0.0.1", port), timeout=0.1):
                    break
            except OSError:
                assert process.poll() is None, "API process exited during startup"
                assert time.monotonic() < deadline, "API startup timed out"
                time.sleep(0.02)
        yield f"ws://127.0.0.1:{port}/ws"
    finally:
        process.terminate()
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=5)


def test_python_and_rust_exchange_messages():
    with server() as url, ExitStack() as cleanup:
        python = Terminal(
            ["uv", "run", "--frozen", "chat-python", "--url", url],
            ROOT / "python-client",
        )
        cleanup.callback(python.close)
        rust = Terminal(
            [str(ROOT / "rust-client/target/debug/chat-rust"), "--url", url],
            ROOT / "rust-client",
        )
        cleanup.callback(rust.close)
        for client, name in [(python, "python_user"), (rust, "rust_user")]:
            client.send(f"/connect {name}")
            # Status is local; poll until the asynchronous login completes.
            deadline = time.monotonic() + 10
            while True:
                client.send("/status")
                line = client.expect("Session:")
                if "logged in" in line:
                    break
                assert time.monotonic() < deadline, client.transcript
                time.sleep(0.05)
        for sender, recipient, sender_name, name, message in [
            (python, rust, "python_user", "rust_user", "  Python 🌎  spaces  "),
            (rust, python, "rust_user", "python_user", "  Rust 🦀  spaces  "),
        ]:
            sender.send(f"/send {name} {message}")
            UUID(sender.expect("✓ Accepted ").split("✓ Accepted ", 1)[1].strip())
            assert recipient.expect(message) == f"← {sender_name}: {message}"
        for client, name in [(python, "python_user"), (rust, "rust_user")]:
            message = "  note to myself  "
            start = len(client.transcript)
            client.send(f"/send {name} {message}")
            # The server may deliver to self before or after accepting the send.
            deadline = time.monotonic() + 10
            while True:
                lines = client.transcript[start:]
                accepted = [line for line in lines if line.startswith("✓ Accepted ")]
                if accepted and f"← {name}: {message}" in lines:
                    UUID(accepted[0].split("✓ Accepted ", 1)[1])
                    break
                assert time.monotonic() < deadline, client.transcript
                time.sleep(0.02)
        for client in (python, rust):
            assert not any("delivery_receipt" in line for line in client.transcript)
            client.send("/status")
            client.expect("Session: logged in")
