"""Terminal input, command parsing and append-only output formatting."""

import asyncio
import re
import sys
from collections.abc import AsyncIterator
from dataclasses import dataclass

from .diagnostics import failure
from .state import ClientState

HELP = """/connect [username]
/disconnect
/drop-connection
/send <recipient> <text>
/status
/help
/quit"""


@dataclass(frozen=True)
class Command:
    name: str
    arguments: tuple[str, ...] = ()


def parse_command(line: str) -> Command:
    line = line.rstrip("\r\n").lstrip()
    if not line:
        return Command("")
    name, _, rest = line.partition(" ")
    if name == "/send":
        match = re.fullmatch(r"\s*(\S+)\s(.+)", rest)
        if match is None or not match[2].strip():
            raise ValueError("Usage: /send <recipient> <text>")
        return Command(name, (match[1], match[2]))
    arguments = tuple(rest.split())
    if name == "/connect":
        if len(arguments) > 1:
            raise ValueError("Usage: /connect [username]")
    elif name not in {"/disconnect", "/drop-connection", "/status", "/help", "/quit"}:
        raise ValueError("Unknown command: use /help")
    elif arguments:
        raise ValueError(f"Usage: {name}")
    return Command(name, arguments)


def format_status(state: ClientState) -> str:
    heartbeat = (
        state.last_heartbeat_at.isoformat().replace("+00:00", "Z")
        if state.last_heartbeat_at
        else "never"
    )
    user = state.authenticated_user.name if state.authenticated_user else "-"
    return (
        f"Server: {state.server_url}\n"
        f"Connection: {state.connection_state}\n"
        f"Session: {state.session_state.value.replace('_', ' ')}\n"
        f"User: {user}\n"
        f"Last heartbeat: {heartbeat}"
    )


def output(text: str) -> None:
    try:
        print(text, flush=True)
    except (OSError, UnicodeError) as error:
        failure("Terminal output failed", error)
        raise


async def read_lines() -> AsyncIterator[str]:
    reader = asyncio.StreamReader()
    protocol = asyncio.StreamReaderProtocol(reader)
    transport = None
    try:
        transport, _ = await asyncio.get_running_loop().connect_read_pipe(
            lambda: protocol, sys.stdin
        )
        while line := await reader.readline():
            yield line.decode()
    except (OSError, UnicodeError, ValueError) as error:
        failure("Terminal input failed", error)
        raise
    finally:
        if transport is not None:
            transport.close()
