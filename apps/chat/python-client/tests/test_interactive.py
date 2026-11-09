"""Exercise the installed CLI through a real terminal and WebSocket peer."""

import asyncio
import codecs
import fcntl
import json
import os
import struct
import sys
import termios
from contextlib import asynccontextmanager
from uuid import uuid4

import pyte
from aiohttp import web
from test_cli import next_item, reply, server
from test_protocol import message_data


class InteractiveTerminal:
    def __init__(self, master, process):
        self.master = master
        self.process = process
        self.screen = pyte.Screen(120, 60)
        self.stream = pyte.Stream(self.screen)
        self.decoder = codecs.getincrementaldecoder("utf-8")()
        self.changed = asyncio.Event()

    def read(self):
        try:
            raw = os.read(self.master, 65536)
        except OSError:
            asyncio.get_running_loop().remove_reader(self.master)
            return
        if raw:
            self.stream.feed(self.decoder.decode(raw))
            self.changed.set()

    def type(self, text):
        os.write(self.master, text.encode())

    async def until(self, predicate):
        async with asyncio.timeout(4):
            while True:
                self.changed.clear()
                if predicate():
                    return self.screen.display
                await self.changed.wait()

    async def prompt(self, text="", cursor=None):
        cursor = len(text) if cursor is None else cursor
        return await self.until(
            lambda: (
                self.screen.display[self.screen.cursor.y].rstrip()
                == ("> " + text).rstrip()
                and self.screen.cursor.x == 2 + cursor
            )
        )

    async def command(self, text):
        self.type(text + "\r")


@asynccontextmanager
async def interactive_client(url):
    master, slave = os.openpty()
    fcntl.ioctl(slave, termios.TIOCSWINSZ, struct.pack("HHHH", 60, 120, 0, 0))
    process = await asyncio.create_subprocess_exec(
        sys.executable,
        "-m",
        "chat_client",
        "--url",
        url,
        stdin=slave,
        stdout=slave,
        stderr=asyncio.subprocess.PIPE,
        env={**os.environ, "TERM": "xterm-256color", "PROMPT_TOOLKIT_NO_CPR": "1"},
    )
    os.close(slave)
    terminal = InteractiveTerminal(master, process)
    asyncio.get_running_loop().add_reader(master, terminal.read)
    try:
        await terminal.prompt()
        yield terminal
        await terminal.command("/quit")
        async with asyncio.timeout(4):
            assert await process.wait() == 0
        assert not await process.stderr.read()
    finally:
        if process.returncode is None:
            process.kill()
            await process.wait()
        asyncio.get_running_loop().remove_reader(master)
        os.close(master)


async def test_event_restores_partial_input_cursor_and_completed_blocks():
    sockets = asyncio.Queue()
    requests = asyncio.Queue()

    async def handler(request):
        ws = web.WebSocketResponse()
        await ws.prepare(request)
        login = await ws.receive_json()
        await ws.send_json(
            reply("login_ok", login, {"id": str(uuid4()), "name": "alice"})
        )
        await sockets.put(ws)
        async for frame in ws:
            await requests.put(json.loads(frame.data))
        return ws

    async with server(handler) as url, interactive_client(url) as terminal:
        await terminal.command("/status")
        await terminal.until(
            lambda: any("Last heartbeat:" in x for x in terminal.screen.display)
        )
        await terminal.prompt()
        display = terminal.screen.display
        server_row = next(
            i for i, line in enumerate(display) if line.startswith("Server:")
        )
        assert [line.rstrip() for line in display[server_row : server_row + 5]] == [
            f"Server: {url}",
            "Connection: disconnected",
            "Session: none",
            "User: -",
            "Last heartbeat: never",
        ]
        assert not display[server_row + 5].strip()
        await terminal.command("/connect alice")
        ws = await next_item(sockets)
        await terminal.until(
            lambda: any("✓ Logged in as alice" in x for x in terminal.screen.display)
        )
        await terminal.prompt()
        completed = terminal.screen.display[: terminal.screen.cursor.y]

        # Move into the middle of the command before delivering the event.
        partial = "/send bob hello world"
        terminal.type(partial + "\x1b[D" * 5)
        await terminal.prompt(partial, len(partial) - 5)
        message = {**message_data(), "sender_name": "bob", "text": " hi  alice  "}
        await ws.send_json({"type": "message_received", "data": message})
        ack = await next_item(requests)
        assert ack["type"] == "ack"
        assert ack["data"]["message_id"] == message["id"]
        display = await terminal.prompt(partial, len(partial) - 5)
        assert display[: len(completed)] == completed
        event_row = next(i for i, line in enumerate(display) if "← bob:" in line)
        assert display[event_row].startswith("← bob:  hi  alice  ")
        assert not display[event_row + 1].strip()
        assert terminal.screen.cursor.y == event_row + 2

        # Keep stderr separate from the PTY so a stream-routing regression is visible.
        correlation = str(uuid4())
        await ws.send_json(
            {
                "type": "error",
                "correlation_id": correlation,
                "data": {"message": "Request rejected by peer"},
            }
        )
        async with asyncio.timeout(4):
            diagnostic = (await terminal.process.stderr.readline()).decode()
            assert diagnostic == (
                "✗ Error: Request rejected by peer correlation_id=" + correlation + "\n"
            )
            assert await terminal.process.stderr.readline() == b"\n"
        await terminal.prompt(partial, len(partial) - 5)
        assert not any("Request rejected" in line for line in terminal.screen.display)

        # The peer observes insertion at the restored cursor, not at line end.
        terminal.type("dear \r")
        send = await next_item(requests)
        assert send["type"] == "send"
        assert send["data"]["text"] == "hello dear world"
        await ws.send_json(reply("message_accepted", send, message_data()))
        await terminal.until(
            lambda: any("✓ Accepted" in x for x in terminal.screen.display)
        )
        await terminal.prompt()
