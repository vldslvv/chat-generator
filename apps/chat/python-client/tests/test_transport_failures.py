import asyncio
import sys
from uuid import uuid4

import pytest
from aiohttp import web
from test_cli import server

TRANSPORT_PROCESS = """
import asyncio
import sys
from datetime import UTC, datetime
from uuid import UUID, uuid4
import aiohttp
from chat_client import protocol, transport
from chat_client.state import ClientState
from chat_client.diagnostics import ReportedFailure

async def main():
    url, mode, identifier = sys.argv[1:]
    correlation = UUID(identifier)
    async with aiohttp.ClientSession() as http:
        socket = await http.ws_connect(
            url, autoping=False, timeout=aiohttp.ClientWSTimeout(ws_close=0.03)
        )
        try:
            if mode == "send":
                await socket.receive()
                request = protocol.ack_request(uuid4(), datetime.now(UTC))
                request.correlation_id = correlation
                await transport.send(socket, request)
            elif mode == "close":
                await transport.close(socket, abrupt=False, correlation_id=correlation)
            else:
                request = protocol.login_request("alice")
                request.correlation_id = correlation
                await transport.send(socket, request)
                # Allow the peer's ping and TCP abort to reach the local socket
                # before consuming the buffered ping and attempting its pong.
                await asyncio.sleep(0.05)
                state = ClientState(url, connection=socket)
                correlations = protocol.Correlations(login=correlation)
                async for _ in transport.receive(state, correlations):
                    pass
        except (aiohttp.ClientError, OSError, ReportedFailure):
            pass
        finally:
            await socket.close()

asyncio.run(main())
"""


@pytest.mark.parametrize(
    ("mode", "operation", "cause"),
    [
        ("send", "ack send failed", "Cannot write"),
        ("pong", "WebSocket pong failed", "Cannot write"),
        ("close", "WebSocket close failed", "operation timed out"),
    ],
)
async def test_transport_failure_logs_cause_and_actual_request_id(
    mode, operation, cause
):
    release = asyncio.Event()

    async def handler(request):
        ws = web.WebSocketResponse(autoclose=False)
        await ws.prepare(request)
        if mode == "send":
            await ws.close()
        elif mode == "pong":
            await ws.receive_json()
            await ws.ping(b"buffered-ping")
            request.transport.abort()
        else:
            await ws.receive()
            await release.wait()
        return ws

    correlation = str(uuid4())
    async with server(handler) as url:
        process = await asyncio.create_subprocess_exec(
            sys.executable,
            "-c",
            TRANSPORT_PROCESS,
            url,
            mode,
            correlation,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        try:
            async with asyncio.timeout(4):
                stdout, stderr = await process.communicate()
            assert process.returncode == 0, stderr.decode()
            diagnostic = stderr.decode()
            assert operation in diagnostic
            assert cause in diagnostic
            assert correlation in diagnostic
            assert not stdout
        finally:
            release.set()
            if process.returncode is None:
                process.kill()
                await process.wait()
