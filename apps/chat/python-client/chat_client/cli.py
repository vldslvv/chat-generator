"""Compose terminal commands with independent connection processing."""

import argparse
import asyncio
import sys
from collections import deque
from contextlib import suppress
from dataclasses import dataclass, field
from uuid import UUID

import aiohttp
from pydantic import ValidationError

from . import outgoing, protocol, terminal, transport
from .diagnostics import ReportedFailure, describe, failure
from .state import (
    ClientState,
    ConnectionState,
    SessionState,
    begin_connection,
    reset_connection,
)


@dataclass
class Runtime:
    state: ClientState
    http: aiohttp.ClientSession
    connection_task: asyncio.Task[None] | None = None
    correlations: protocol.Correlations = field(default_factory=protocol.Correlations)
    disconnecting: bool = False
    closing: bool = False
    flush_task: asyncio.Task[None] | None = None
    control_requests: deque[protocol.Request | bytes] = field(default_factory=deque)


def outstanding_correlation(runtime: Runtime) -> UUID | None:
    return outgoing.outstanding_correlation(runtime.state) or runtime.correlations.login


async def flush_messages(runtime: Runtime) -> None:
    state = runtime.state
    socket = state.connection
    if socket is None:
        return

    async def send_controls() -> None:
        while runtime.control_requests and state.connection is socket:
            control = runtime.control_requests.popleft()
            if isinstance(control, protocol.Request):
                await transport.send(socket, control)
            else:
                await transport.pong(socket, control, outstanding_correlation(runtime))

    async def send_message(request: protocol.Request) -> None:
        await transport.send(socket, request)
        await send_controls()

    try:
        while state.connection is socket:
            await send_controls()
            await outgoing.flush_messages(state, send_message)
            if not runtime.control_requests:
                return
    except ReportedFailure:
        pass
    except terminal.OutputFailure as error:
        await failure("Terminal output failed", error, outstanding_correlation(runtime))
    # Abort this socket without awaiting its receiver: receiver teardown cancels
    # and awaits the flush task, so waiting for it here would create a cycle.
    if state.connection is socket:
        correlation = outstanding_correlation(runtime)
        runtime.control_requests.clear()
        reset_connection(state)
        await transport.close(socket, abrupt=True, correlation_id=correlation)


def start_flush(runtime: Runtime) -> None:
    if (
        runtime.disconnecting
        or runtime.closing
        or runtime.state.connection_state != ConnectionState.CONNECTED
    ):
        return
    if runtime.flush_task is None or runtime.flush_task.done():
        runtime.flush_task = asyncio.create_task(flush_messages(runtime))


async def queue_control(
    runtime: Runtime,
    socket: aiohttp.ClientWebSocketResponse,
    request: protocol.Request | bytes,
) -> None:
    if (
        runtime.state.connection is socket
        and not runtime.disconnecting
        and not runtime.closing
    ):
        runtime.control_requests.append(request)
        start_flush(runtime)


async def stop_flush(runtime: Runtime) -> None:
    task = runtime.flush_task
    runtime.flush_task = None
    if task is not None:
        task.cancel()
        with suppress(asyncio.CancelledError):
            await task
    runtime.control_requests.clear()


async def connection_loop(runtime: Runtime) -> None:
    state = runtime.state
    socket = None
    output_failed = False
    try:
        socket = await transport.open_socket(runtime.http, state.server_url)
        state.connection = socket
        state.connection_state = ConnectionState.CONNECTED
        state.session_state = SessionState.LOGIN_PENDING
        request = protocol.login_request(state.login_username)
        runtime.correlations.login = request.correlation_id
        await queue_control(runtime, socket, request)
        async for raw in transport.receive(
            state,
            runtime.correlations,
            lambda data: queue_control(runtime, socket, data),
        ):
            try:
                await protocol.handle_event(
                    raw,
                    state,
                    runtime.correlations,
                    lambda request: queue_control(runtime, socket, request),
                    terminal.output,
                    lambda: start_flush(runtime),
                )
            except (ValidationError, ValueError) as error:
                cause = (
                    "; ".join(
                        f"{detail['loc']}: {detail['msg']}"
                        for detail in error.errors(include_input=False)
                    )
                    if isinstance(error, ValidationError)
                    else str(error)
                )
                await failure(
                    "Invalid server event", cause, protocol.event_correlation(raw)
                )
    except ReportedFailure:
        pass
    except terminal.OutputFailure as error:
        output_failed = True
        await failure(
            "Terminal output failed",
            error,
            outstanding_correlation(runtime),
        )
    except (aiohttp.ClientError, OSError, ValueError, TimeoutError) as error:
        await failure(
            "Connection failed",
            error,
            outstanding_correlation(runtime),
        )
    finally:
        if runtime.connection_task is asyncio.current_task():
            await finish_connection(runtime, socket, output_failed=output_failed)
        elif socket is not None:
            await transport.close(socket, abrupt=True)


async def finish_connection(
    runtime: Runtime,
    socket: aiohttp.ClientWebSocketResponse | None,
    *,
    output_failed: bool,
) -> None:
    state = runtime.state
    runtime.closing = True
    try:
        await stop_flush(runtime)
        if socket is not None and state.connection is socket:
            await transport.close(
                socket,
                abrupt=False,
                correlation_id=outstanding_correlation(runtime),
            )
    finally:
        correlation = outstanding_correlation(runtime)
        reset_connection(state)
        runtime.closing = False
        runtime.correlations = protocol.Correlations()
        if not output_failed:
            try:
                await terminal.output(
                    "Disconnected"
                    if runtime.disconnecting
                    else "Disconnected. Use /connect to reconnect."
                )
            except terminal.OutputFailure as error:
                await failure("Terminal output failed", error, correlation)


async def disconnect(runtime: Runtime, *, abrupt: bool = False) -> None:
    runtime.disconnecting = True
    await stop_flush(runtime)
    task = runtime.connection_task
    socket = runtime.state.connection
    correlation = outstanding_correlation(runtime)
    reset_connection(runtime.state)
    if socket is not None:
        await transport.close(
            socket,
            abrupt=abrupt,
            correlation_id=correlation,
        )
    if task is not None:
        if socket is None or abrupt:
            task.cancel()
        with suppress(asyncio.CancelledError):
            await task
        runtime.connection_task = None
    reset_connection(runtime.state)
    runtime.correlations = protocol.Correlations()


async def execute(runtime: Runtime, command: terminal.Command) -> bool:
    state = runtime.state
    match command.name:
        case "/connect":
            if state.connection_state != ConnectionState.DISCONNECTED:
                return True
            username = (
                command.arguments[0] if command.arguments else state.remembered_username
            )
            if username is None:
                await failure("", "Username required: /connect <username>")
            else:
                begin_connection(state, username)
                runtime.disconnecting = False
                runtime.connection_task = asyncio.create_task(connection_loop(runtime))
        case "/disconnect" | "/drop-connection":
            await disconnect(runtime, abrupt=command.name == "/drop-connection")
        case "/send":
            logged_in = state.session_state == SessionState.LOGGED_IN
            offline = (
                state.connection_state == ConnectionState.DISCONNECTED
                and state.remembered_username is not None
            )
            if not (logged_in or offline):
                await failure("", "Login required for /send. Use /connect <username>.")
            else:
                outgoing.enqueue(state, *command.arguments)
                if offline:
                    await terminal.output("✓ Queued locally")
                    return True
                start_flush(runtime)
        case "/status":
            await terminal.output(terminal.format_status(state))
        case "/help":
            await terminal.output(terminal.HELP)
        case "/quit":
            await disconnect(runtime)
            return False
    return True


async def run(url: str) -> None:
    timeout = aiohttp.ClientTimeout(total=10)
    async with aiohttp.ClientSession(timeout=timeout) as http:
        runtime = Runtime(ClientState(url), http)
        await terminal.output("Chat client ready. Use /help for commands.")
        try:
            async for line in terminal.read_lines():
                try:
                    command = terminal.parse_command(line)
                except ValueError as error:
                    await failure("", error)
                    continue
                if not await execute(runtime, command):
                    break
        finally:
            await disconnect(runtime)


def main() -> None:
    parser = argparse.ArgumentParser(description="Interactive WebSocket chat client")
    parser.add_argument(
        "--url", required=True, help="Server URL, e.g. ws://localhost:8000/ws"
    )
    arguments = parser.parse_args()
    try:
        asyncio.run(run(arguments.url))
    except KeyboardInterrupt:
        pass
    except (OSError, UnicodeError, ValueError, terminal.OutputFailure) as error:
        print(
            f"✗ Error: Terminal operation failed: {describe(error)}\n", file=sys.stderr
        )
        raise SystemExit(1) from None
