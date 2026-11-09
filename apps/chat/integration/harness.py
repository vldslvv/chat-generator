"""Process and terminal adapters shared by CLI integration scenarios."""

import os
import queue
import shlex
import socket
import subprocess
import threading
import time
from contextlib import contextmanager
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class Terminal:
    def __init__(self, command, cwd, *, server=False):
        self.server = server
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

    def snapshot(self):
        return self.transcript.copy()

    def alive(self):
        return self.process.poll() is None

    def send(self, command):
        self.process.stdin.write(command + "\n")
        self.process.stdin.flush()

    def expect(self, fragment, timeout=10):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            try:
                line = self.lines.get(
                    timeout=max(0.001, min(0.1, deadline - time.monotonic()))
                )
            except queue.Empty:
                assert self.alive(), f"Process exited: {self.transcript}"
                continue
            if fragment in line:
                return line
        raise AssertionError(f"Missing {fragment!r}; transcript: {self.transcript}")

    def close(self):
        try:
            if self.alive():
                if self.server:
                    self.process.terminate()
                else:
                    self.send("/quit")
                self.process.wait(timeout=5)
        except (BrokenPipeError, subprocess.TimeoutExpired):
            pass
        finally:
            if self.alive():
                self.process.kill()
                self.process.wait(timeout=5)
            self.reader.join(timeout=2)
            self.process.stdin.close()
            self.process.stdout.close()


def tmux(*arguments):
    return subprocess.check_output(["tmux", *arguments], text=True, timeout=5).strip()


class Pane:
    """Observe completed terminal output while keeping commands visible."""

    def __init__(self, session, label, command, cwd, first=False):
        self.server = first
        if first:
            self.pane = tmux("display-message", "-p", "-t", session, "#{pane_id}")
        else:
            self.pane = tmux(
                "split-window", "-t", session, "-P", "-F", "#{pane_id}", "-c", str(cwd)
            )
        tmux("set-option", "-p", "-t", self.pane, "remain-on-exit", "on")
        tmux("set-option", "-p", "-t", self.pane, "@chat_label", label)
        tmux("select-layout", "-t", self.pane, "tiled")
        tmux(
            "respawn-pane",
            "-k",
            "-t",
            self.pane,
            "-c",
            str(cwd),
            "exec " + shlex.join(command),
        )

    def snapshot(self):
        output = tmux("capture-pane", "-p", "-J", "-S", "-", "-t", self.pane)
        # Prompts and echoed commands aren't output events. Completed output is
        # append-only, even when the interactive library restores its prompt.
        return [
            line
            for line in output.splitlines()
            if line and line != ">" and not line.startswith("> ")
        ]

    def alive(self):
        return tmux("display-message", "-p", "-t", self.pane, "#{pane_dead}") == "0"

    def send(self, command):
        tmux("send-keys", "-t", self.pane, "-l", "--", command)
        tmux("send-keys", "-t", self.pane, "Enter")

    def close(self):
        if self.alive():
            if self.server:
                tmux("send-keys", "-t", self.pane, "C-c")
            else:
                self.send("/quit")
            deadline = time.monotonic() + 5
            while self.alive() and time.monotonic() < deadline:
                time.sleep(0.05)
        if self.alive():
            tmux("kill-pane", "-t", self.pane)


def server_command(port):
    return [
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


def client_command(language, url):
    if language == "python":
        return ["uv", "run", "--frozen", "chat-python", "--url", url]
    return [str(ROOT / "rust-client/target/debug/chat-rust"), "--url", url]


def free_port():
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        return listener.getsockname()[1]


def wait_server(port, terminal):
    deadline = time.monotonic() + 10
    while True:
        assert terminal.alive(), f"API exited: {terminal.snapshot()}"
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=0.1):
                return
        except OSError:
            assert time.monotonic() < deadline, (
                f"API startup timed out: {terminal.snapshot()}"
            )
            time.sleep(0.02)


@contextmanager
def server():
    port = free_port()
    terminal = Terminal(server_command(port), ROOT / "api", server=True)
    try:
        wait_server(port, terminal)
        yield f"ws://127.0.0.1:{port}/ws"
    finally:
        terminal.process.terminate()
        terminal.close()
