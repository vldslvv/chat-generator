import asyncio
import json
import sys
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest
from aiohttp import WSMsgType, web
from test_protocol import message_data


@asynccontextmanager
async def server(handler):
    app = web.Application()
    app.router.add_get("/ws", handler)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "127.0.0.1", 0)
    await site.start()
    port = runner.addresses[0][1]
    try:
        yield f"ws://127.0.0.1:{port}/ws"
    finally:
        await runner.cleanup()


class Terminal:
    def __init__(self, process):
        self.process = process
        self.diagnostics = []
        self.errors = asyncio.Queue()

    async def capture_errors(self):
        async for line in self.process.stderr:
            text = line.decode().rstrip("\n")
            self.diagnostics.append(text)
            await self.errors.put(text)

    async def error_until(self, expected):
        async with asyncio.timeout(4):
            while True:
                line = await self.errors.get()
                if expected in line:
                    return line

    async def command(self, text):
        self.process.stdin.write((text + "\n").encode())
        await self.process.stdin.drain()

    async def until(self, expected):
        lines = []
        async with asyncio.timeout(4):
            while True:
                raw = await self.process.stdout.readline()
                assert raw, f"Client exited before {expected!r}; output={lines}"
                line = raw.decode().rstrip("\n")
                lines.append(line)
                if expected in line:
                    return "\n".join(lines)

    async def status(self):
        await self.command("/status")
        return await self.until("Last heartbeat:")


@asynccontextmanager
async def client(url):
    process = await asyncio.create_subprocess_exec(
        sys.executable,
        "-m",
        "chat_client",
        "--url",
        url,
        stdin=asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    cli = Terminal(process)
    error_task = asyncio.create_task(cli.capture_errors())
    try:
        await cli.until("Chat client ready")
        yield cli
        await cli.command("/quit")
        async with asyncio.timeout(4):
            assert await process.wait() == 0
        await error_task
        assert "Traceback" not in "\n".join(cli.diagnostics)
    finally:
        if process.returncode is None:
            process.kill()
            await process.wait()
        await error_task


async def next_item(queue):
    async with asyncio.timeout(4):
        return await queue.get()


def reply(kind, request, data):
    return {"type": kind, "correlation_id": request["correlation_id"], "data": data}


async def test_cli_protocol_heartbeat_and_reconnection():
    sockets = asyncio.Queue()
    requests = asyncio.Queue()
    pongs = asyncio.Queue()
    logins = []

    async def handler(request):
        ws = web.WebSocketResponse(autoping=False)
        await ws.prepare(request)
        await sockets.put(ws)
        async for frame in ws:
            if frame.type == WSMsgType.PONG:
                await pongs.put(frame.data)
            elif frame.type == WSMsgType.TEXT:
                data = json.loads(frame.data)
                if data["type"] == "login":
                    logins.append(data)
                    await ws.send_json(
                        reply("login_ok", data, {"id": str(uuid4()), "name": "alice"})
                    )
                else:
                    await requests.put(data)
        return ws

    async with server(handler) as url, client(url) as cli:
        status = await cli.status()
        assert f"Server: {url}" in status
        assert "Connection: disconnected\nSession: none\nUser: -" in status
        assert "Last heartbeat: never" in status
        await cli.command("/connect")
        await cli.until("Username required: /connect <username>")
        await cli.error_until("Username required: /connect <username>")
        await cli.command("/send bob hello")
        await cli.until("Login required")
        await cli.error_until("Login required")
        await cli.command("/bogus")
        await cli.until("Unknown command")
        await cli.error_until("Unknown command")
        await cli.command("/send bob")
        await cli.until("Usage: /send <recipient> <text>")
        await cli.error_until("Usage: /send <recipient> <text>")
        await cli.command("/help")
        help_text = await cli.until("/quit")
        assert (
            "/drop-connection" in help_text and "/send <recipient> <text>" in help_text
        )

        await cli.command("/connect alice")
        ws = await next_item(sockets)
        await cli.until("Logged in as alice")
        await cli.command("/connect bob")
        await ws.ping(b"heartbeat-token")
        assert await next_item(pongs) == b"heartbeat-token"
        status = await cli.status()
        assert "Connection: connected\nSession: logged in\nUser: alice" in status
        heartbeat = status.split("Last heartbeat: ")[1]
        assert datetime.fromisoformat(heartbeat).utcoffset().total_seconds() == 0

        await cli.command("/send bob hello  there  ")
        send = await next_item(requests)
        assert send["type"] == "send"
        assert send["data"]["recipient"] == "bob"
        assert send["data"]["text"] == "hello  there  "
        assert datetime.fromisoformat(send["data"]["client_sent_at"]).tzinfo is not None
        await cli.command("/send bob overlapping")
        await cli.until("Send in progress")
        assert send["correlation_id"] in await cli.error_until("Send in progress")
        assert "✓ Accepted" not in await cli.status()
        message = message_data()
        wrong = {"correlation_id": str(uuid4())}
        await ws.send_json(reply("message_accepted", wrong, message))
        await cli.until("Unexpected send reply")
        assert wrong["correlation_id"] in await cli.error_until("Unexpected send reply")
        await ws.send_json(reply("message_accepted", send, message))
        await cli.until(f"✓ Accepted {message['id']}")

        await cli.command("/send offline no retry")
        failed = await next_item(requests)
        await ws.send_json(reply("error", failed, {"message": "Recipient is offline"}))
        await cli.until("✗ Error: Recipient is offline")
        assert failed["correlation_id"] in await cli.error_until("Recipient is offline")

        before_receive = datetime.now(UTC)
        await ws.send_json({"type": "message_received", "data": message})
        await cli.until("Hi Bob")
        ack = await next_item(requests)
        assert ack["type"] == "ack"
        assert ack["data"]["message_id"] == message["id"]
        received_at = datetime.fromisoformat(ack["data"]["recipient_received_at"])
        assert before_receive <= received_at <= datetime.now(UTC)
        ids = [item["correlation_id"] for item in [logins[0], send, failed, ack]]
        assert len(set(ids)) == 4
        assert all(UUID(value) for value in ids)

        await cli.command("/send bob interrupted")
        assert (await next_item(requests))["data"]["text"] == "interrupted"
        await ws.close()
        await cli.until("Disconnected")
        status = await cli.status()
        assert "Connection: disconnected\nSession: none\nUser: -" in status
        assert f"Last heartbeat: {heartbeat}" in status
        assert requests.empty()
        assert sockets.empty()
        await cli.command("/connect")
        ws = await next_item(sockets)
        await cli.until("Logged in as alice")
        assert logins[-1]["data"]["name"] == "alice"
        assert len(logins) == 2
        await cli.command("/send bob fresh after reconnect")
        fresh = await next_item(requests)
        assert fresh["data"]["text"] == "fresh after reconnect"
        await ws.send_json(reply("error", fresh, {"message": "Recipient is offline"}))
        await cli.until("✗ Error: Recipient is offline")
        assert fresh["correlation_id"] in await cli.error_until("Recipient is offline")
        await cli.command("/disconnect")
        await cli.until("Disconnected")
        await cli.command("/disconnect")
        assert "Connection: disconnected" in await cli.status()


async def test_connection_attempt_is_idempotent_and_status_stays_responsive():
    arrived = asyncio.Event()
    finish = asyncio.Event()
    connections = 0

    async def handler(request):
        nonlocal connections
        connections += 1
        arrived.set()
        await finish.wait()
        return web.Response(status=503)

    async with server(handler) as url:
        try:
            async with client(url) as cli:
                await cli.command("/connect alice")
                async with asyncio.timeout(4):
                    await arrived.wait()
                await cli.command("/connect bob")
                assert (
                    "Connection: connecting\nSession: none\nUser: -"
                    in await cli.status()
                )
                await cli.command("/drop-connection")
                await cli.until("Disconnected")
                assert "Connection: disconnected" in await cli.status()
                assert connections == 1
        finally:
            finish.set()


async def test_abrupt_drop_skips_websocket_close_handshake_and_retains_name():
    sockets = asyncio.Queue()
    closures = asyncio.Queue()

    async def handler(request):
        ws = web.WebSocketResponse()
        await ws.prepare(request)
        login = await ws.receive_json()
        await ws.send_json(
            reply("login_ok", login, {"id": str(uuid4()), "name": "alice"})
        )
        await sockets.put(ws)
        async for _ in ws:
            pass
        await closures.put(ws.close_code)
        return ws

    async with server(handler) as url, client(url) as cli:
        await cli.command("/connect alice")
        await next_item(sockets)
        await cli.until("Logged in as alice")
        await cli.command("/drop-connection")
        await cli.until("Disconnected")
        assert await next_item(closures) == 1006
        await cli.command("/drop-connection")
        assert "Connection: disconnected" in await cli.status()
        await cli.command("/connect")
        await next_item(sockets)
        await cli.until("Logged in as alice")
        await cli.command("/disconnect")
        await cli.until("Disconnected")
        assert await next_item(closures) == 1000


async def test_login_error_and_connection_failure_leave_terminal_usable():
    login_ids = []

    async def handler(request):
        ws = web.WebSocketResponse()
        await ws.prepare(request)
        login = await ws.receive_json()
        login_ids.append(login["correlation_id"])
        await ws.send_json(reply("error", login, {"message": "Name already online"}))
        async for _ in ws:
            pass
        return ws

    async with server(handler) as url, client(url) as cli:
        await cli.command("/connect alice")
        await cli.until("✗ Error: Name already online")
        assert login_ids[-1] in await cli.error_until("Name already online")
        status = await cli.status()
        assert "Connection: connected\nSession: none\nUser: -" in status
        await cli.command("/disconnect")
        await cli.until("Disconnected")
        await cli.command("/connect")
        await cli.until("Username required")

    async with client("http://127.0.0.1:1/ws") as cli:
        await cli.command("/connect alice")
        await cli.until("Connection failed")
        assert "Cannot connect" in await cli.error_until("Connection failed")
        await cli.until("Disconnected")
        assert "Connection: disconnected\nSession: none\nUser: -" in await cli.status()
        await cli.command("/connect")
        await cli.until("Username required")


async def test_login_pending_status_and_quit_close_active_connection():
    logins = asyncio.Queue()
    closures = asyncio.Queue()

    async def handler(request):
        ws = web.WebSocketResponse()
        await ws.prepare(request)
        await logins.put(await ws.receive_json())
        async for _ in ws:
            pass
        await closures.put(ws.close_code)
        return ws

    async with server(handler) as url:
        async with client(url) as cli:
            await cli.command("/connect alice")
            assert (await next_item(logins))["data"]["name"] == "alice"
            status = await cli.status()
            assert "Connection: connected\nSession: login pending\nUser: -" in status
            await cli.command("/connect bob")
            await cli.command("/send bob before login")
            await cli.until("Login required")
            assert logins.empty()
        assert await next_item(closures) == 1000


async def test_malformed_events_log_recoverable_correlation_without_payload():
    sockets = asyncio.Queue()
    logins = asyncio.Queue()

    async def handler(request):
        ws = web.WebSocketResponse()
        await ws.prepare(request)
        await sockets.put(ws)
        await logins.put(await ws.receive_json())
        async for _ in ws:
            pass
        return ws

    async with server(handler) as url, client(url) as cli:
        await cli.command("/connect alice")
        ws = await next_item(sockets)
        login = await next_item(logins)
        await ws.send_str("{invalid json")
        await cli.until("Invalid server event")
        assert "Invalid JSON" in await cli.error_until("Invalid server event")
        await ws.send_json(
            reply("login_ok", login, {"id": "private-invalid-payload", "name": "alice"})
        )
        await cli.until("Invalid server event")
        diagnostic = await cli.error_until("Invalid server event")
        assert login["correlation_id"] in diagnostic
        assert "UUID" in diagnostic
        assert "private-invalid-payload" not in diagnostic
        await ws.send_json(
            reply("login_ok", login, {"id": str(uuid4()), "name": "alice"})
        )
        await cli.until("Logged in as alice")
        assert "Session: logged in" in await cli.status()


@pytest.mark.parametrize(
    ("mode", "cause"),
    [
        ("abort", "close code 1006"),
        ("invalid_utf8", "Invalid UTF-8"),
        ("policy_close", "policy rejected"),
    ],
)
async def test_network_failures_log_cause_and_outstanding_correlation(mode, cause):
    sends = asyncio.Queue()

    async def handler(request):
        ws = web.WebSocketResponse()
        await ws.prepare(request)
        login = await ws.receive_json()
        await ws.send_json(
            reply("login_ok", login, {"id": str(uuid4()), "name": "alice"})
        )
        await sends.put(await ws.receive_json())
        if mode == "abort":
            request.transport.abort()
        elif mode == "invalid_utf8":
            request.transport.write(b"\x81\x01\xff")
        else:
            await ws.close(code=1008, message=b"policy rejected")
        return ws

    async with server(handler) as url, client(url) as cli:
        await cli.command("/connect alice")
        await cli.until("Logged in as alice")
        await cli.command("/send bob interrupted")
        send = await next_item(sends)
        await cli.until("Disconnected")
        diagnostic = await cli.error_until(cause)
        assert send["correlation_id"] in diagnostic
        assert "Connection: disconnected\nSession: none\nUser: -" in await cli.status()
        assert sends.empty()


@pytest.mark.parametrize("broken_stream", ["stdin", "stdout"])
async def test_terminal_operational_failure_is_reported_on_stderr(broken_stream):
    process = await asyncio.create_subprocess_exec(
        sys.executable,
        "-m",
        "chat_client",
        "--url",
        "ws://127.0.0.1:1/ws",
        stdin=asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    if broken_stream == "stdin":
        process.stdin.write(b"\xff\n")
    else:
        # Close the parent's read end so the child's next write hits EPIPE.
        process.stdout._transport.close()
        process.stdin.write(b"/status\n")
    await process.stdin.drain()
    process.stdin.close()
    async with asyncio.timeout(4):
        stdout, stderr = await process.communicate()
    assert process.returncode != 0
    assert f"Terminal {('input' if broken_stream == 'stdin' else 'output')} failed" in (
        stderr.decode()
    )
    assert (
        "UnicodeDecodeError" if broken_stream == "stdin" else "BrokenPipeError"
    ) in (stderr.decode())
