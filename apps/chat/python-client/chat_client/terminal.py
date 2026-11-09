"""Terminal input, command parsing and append-only output formatting."""

from __future__ import annotations

import asyncio
import os
import re
import sys
from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import TYPE_CHECKING

from prompt_toolkit import PromptSession
from prompt_toolkit.application import run_in_terminal

if TYPE_CHECKING:
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


class OutputFailure(Exception):
    """The terminal could not display a completed output block."""


def parse_command(line: str) -> Command:
    line = line.rstrip("\r\n").lstrip()
    if not line:
        return Command("")
    name, _, rest = line.partition(" ")
    if name == "/send":
        match = re.fullmatch(r"\s*(\S+)\s(.+)", rest)
        if match is None or not match[2].strip():
            raise ValueError("Invalid /send. Usage: /send <recipient> <text>")
        return Command(name, (match[1], match[2]))
    arguments = tuple(rest.split())
    if name == "/connect":
        if len(arguments) > 1:
            raise ValueError("Usage: /connect [username]")
    elif name not in {"/disconnect", "/drop-connection", "/status", "/help", "/quit"}:
        hint = "Use /connect <username>." if name == "/login" else "Use /help."
        raise ValueError(f"Unknown command '{name}'. {hint}")
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


def _redirect_broken_output() -> None:
    # Avoid another failed flush and interpreter diagnostic during exit.
    with open(os.devnull, "w") as sink:
        os.dup2(sink.fileno(), sys.stdout.fileno())


def _interactive() -> bool:
    return (
        not sys.stdin.closed
        and not sys.stdout.closed
        and sys.stdin.isatty()
        and sys.stdout.isatty()
    )


async def output(text: str, *, error: bool = False) -> None:
    def write() -> None:
        print(text + "\n", file=sys.stderr if error else sys.stdout, flush=True)

    try:
        if _interactive():
            await run_in_terminal(write)
        else:
            write()
    except (OSError, UnicodeError) as cause:
        if not error and isinstance(cause, BrokenPipeError):
            _redirect_broken_output()
        raise OutputFailure(str(cause)) from cause


async def read_lines() -> AsyncIterator[str]:
    if _interactive():
        session = PromptSession()
        while True:
            try:
                yield await session.prompt_async("> ")
            except EOFError:
                return
    reader = asyncio.StreamReader()
    protocol = asyncio.StreamReaderProtocol(reader)
    transport = None
    try:
        transport, _ = await asyncio.get_running_loop().connect_read_pipe(
            lambda: protocol, sys.stdin
        )
        while line := await reader.readline():
            yield line.decode()
    finally:
        if transport is not None:
            transport.close()
