"""WebSocket I/O and graceful versus abrupt connection shutdown."""

from collections.abc import AsyncIterator, Awaitable, Callable
from datetime import UTC, datetime
from uuid import UUID

import aiohttp

from .diagnostics import ReportedFailure, failure
from .outgoing import outstanding_correlation
from .protocol import Correlations, Request
from .state import ClientState


async def open_socket(
    session: aiohttp.ClientSession, url: str
) -> aiohttp.ClientWebSocketResponse:
    return await session.ws_connect(url, autoping=False)


async def send(socket: aiohttp.ClientWebSocketResponse, request: Request) -> None:
    try:
        await socket.send_str(request.model_dump_json())
    except (aiohttp.ClientError, OSError, TimeoutError) as error:
        await failure(f"{request.type} send failed", error, request.correlation_id)
        raise ReportedFailure from error


async def pong(
    socket: aiohttp.ClientWebSocketResponse,
    data: bytes,
    correlation_id: UUID | None,
) -> None:
    try:
        await socket.pong(data)
    except (aiohttp.ClientError, OSError, TimeoutError) as error:
        await failure("WebSocket pong failed", error, correlation_id)
        raise ReportedFailure from error


async def receive(
    state: ClientState,
    correlations: Correlations,
    respond_to_ping: Callable[[bytes], Awaitable[None]],
) -> AsyncIterator[str]:
    socket = state.connection
    assert socket is not None
    while True:
        try:
            frame = await socket.receive()
        except (aiohttp.ClientError, OSError, TimeoutError) as error:
            await failure(
                "WebSocket receive failed",
                error,
                outstanding_correlation(state) or correlations.login,
            )
            raise ReportedFailure from error
        correlation = outstanding_correlation(state) or correlations.login
        if frame.type == aiohttp.WSMsgType.PING:
            state.last_heartbeat_at = datetime.now(UTC)
            await respond_to_ping(bytes(frame.data))
        elif frame.type == aiohttp.WSMsgType.TEXT:
            yield frame.data
        elif frame.type == aiohttp.WSMsgType.ERROR:
            cause = socket.exception() or frame.data
            await failure("WebSocket receive failed", cause, correlation)
            return
        elif frame.type in {
            aiohttp.WSMsgType.CLOSE,
            aiohttp.WSMsgType.CLOSED,
            aiohttp.WSMsgType.CLOSING,
        }:
            code = socket.close_code
            if state.connection is socket:
                cause = (
                    socket.exception()
                    or frame.extra
                    or (
                        "server closed connection"
                        if code in {1000, 1001}
                        else "no close handshake"
                    )
                )
                await failure(
                    "WebSocket connection lost",
                    f"close code {code}; {cause}",
                    correlation,
                )
            return
        elif frame.type != aiohttp.WSMsgType.PONG:
            await failure(
                "Invalid server event", f"Unexpected WebSocket frame {frame.type}"
            )


async def close(
    socket: aiohttp.ClientWebSocketResponse,
    *,
    abrupt: bool,
    correlation_id: UUID | None = None,
) -> None:
    try:
        if not abrupt:
            closed = await socket.close()
            if closed and socket.exception() is not None:
                await failure(
                    "WebSocket close failed", socket.exception(), correlation_id
                )
            return
        # aiohttp has no public abort method; abort the underlying TCP transport.
        response = socket._response
        connection = response.connection
        if connection is not None and connection.transport is not None:
            connection.transport.abort()
        response.close()
    except (aiohttp.ClientError, OSError, TimeoutError) as error:
        await failure("WebSocket close failed", error, correlation_id)
        socket._response.close()
