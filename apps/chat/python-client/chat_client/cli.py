"""Compose terminal commands with independent connection processing."""

import argparse
import asyncio
import sys
from contextlib import suppress
from dataclasses import dataclass, field

import aiohttp
from pydantic import ValidationError

from . import protocol, terminal, transport
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
        await transport.send(socket, request)
        async for raw in transport.receive(state, runtime.correlations):
            try:
                await protocol.handle_event(
                    raw,
                    state,
                    runtime.correlations,
                    lambda request: transport.send(socket, request),
                    terminal.output,
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
            runtime.correlations.send or runtime.correlations.login,
        )
    except (aiohttp.ClientError, OSError, ValueError, TimeoutError) as error:
        await failure(
            "Connection failed",
            error,
            runtime.correlations.send or runtime.correlations.login,
        )
    finally:
        try:
            if socket is not None and state.connection is socket:
                await transport.close(
                    socket,
                    abrupt=False,
                    correlation_id=runtime.correlations.send
                    or runtime.correlations.login,
                )
        finally:
            correlation = runtime.correlations.send or runtime.correlations.login
            reset_connection(state)
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
    task = runtime.connection_task
    socket = runtime.state.connection
    reset_connection(runtime.state)
    if socket is not None:
        await transport.close(
            socket,
            abrupt=abrupt,
            correlation_id=runtime.correlations.send or runtime.correlations.login,
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
            if state.session_state != SessionState.LOGGED_IN:
                await failure("", "Login required for /send. Use /connect <username>.")
            elif runtime.correlations.send is not None:
                await failure(
                    "",
                    "/send rejected: Send in progress; try again after its reply",
                    runtime.correlations.send,
                )
            else:
                socket = state.connection
                assert socket is not None
                request = protocol.send_request(*command.arguments)
                runtime.correlations.send = request.correlation_id
                try:
                    await transport.send(socket, request)
                except ReportedFailure:
                    await disconnect(runtime, abrupt=True)
                    await terminal.output("Use /connect to reconnect.")
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
