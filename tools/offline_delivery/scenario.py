"""One offline delivery scenario, driven through pipes or visible tmux panes."""

import re
import shlex
import subprocess
import sys
import tempfile
import time
from collections.abc import Callable
from contextlib import ExitStack, contextmanager
from dataclasses import dataclass, field
from pathlib import Path
from uuid import UUID, uuid4

from configuration import load_commands
from terminals import (
    Pane,
    Terminal,
    free_port,
    tmux,
    wait_server,
)


@dataclass
class Scenario:
    terminals: dict
    advance: Callable[[str], None] = lambda step: None
    step: str = "startup"
    consumed: dict = field(default_factory=dict)


def check(scenario):
    for name, terminal in scenario.terminals.items():
        assert terminal.alive(), f"{name} exited unexpectedly"
        lines = terminal.snapshot()
        assert not any(
            "✗ Error:" in line or "Traceback (most recent" in line or "ERROR:" in line
            for line in lines
        ), f"{name} reported an error"


def begin(scenario, description):
    scenario.step = description
    scenario.advance(description)
    check(scenario)
    return {
        name: len(terminal.snapshot()) for name, terminal in scenario.terminals.items()
    }


def expect(scenario, name, expected, marks):
    deadline = time.monotonic() + 10
    while time.monotonic() < deadline:
        check(scenario)
        for index, line in enumerate(scenario.terminals[name].snapshot()):
            if index < marks[name] or index in scenario.consumed.setdefault(
                name, set()
            ):
                continue
            if (
                expected.fullmatch(line)
                if isinstance(expected, re.Pattern)
                else line == expected
            ):
                scenario.consumed.setdefault(name, set()).add(index)
                return line
        time.sleep(0.02)
    raise AssertionError(f"{name}: missing complete output {expected!r}")


def accepted(scenario, name, marks):
    line = expect(scenario, name, re.compile(r"✓ Accepted [0-9a-fA-F-]{36}"), marks)
    UUID(line.removeprefix("✓ Accepted "))


def send(scenario, name, command):
    scenario.terminals[name].send(command)


def disconnected(scenario, name, marks):
    send(scenario, name, "/status")
    expect(scenario, name, "Connection: disconnected", marks)
    expect(scenario, name, "Session: none", marks)


def no_acceptance(scenario, name, since):
    assert not any(
        line.startswith("✓ Accepted ")
        for line in scenario.terminals[name].snapshot()[since:]
    ), f"{name}: accepted while offline"


def run_scenario(scenario):
    marks = begin(scenario, "1. Connect Alice and Bob")
    for name in ("alice", "bob"):
        send(scenario, name, f"/connect {name}")
        expect(scenario, name, f"✓ Logged in as {name}", marks)

    marks = begin(scenario, "2. Alice sends a greeting")
    send(scenario, "alice", "/send bob Hi Bob, I have something important to tell you")
    accepted(scenario, "alice", marks)
    expect(
        scenario,
        "bob",
        "← alice: Hi Bob, I have something important to tell you",
        marks,
    )

    marks = begin(scenario, "3. Bob replies")
    send(scenario, "bob", "/send alice What is it?")
    accepted(scenario, "bob", marks)
    expect(scenario, "alice", "← bob: What is it?", marks)

    marks = begin(scenario, "4. Alice disconnects and queues")
    send(scenario, "alice", "/disconnect")
    disconnected(scenario, "alice", marks)
    alice_offline = len(scenario.terminals["alice"].snapshot())
    send(scenario, "alice", "/send bob The meeting is tomorrow")
    expect(scenario, "alice", "✓ Queued locally", marks)
    no_acceptance(scenario, "alice", alice_offline)

    marks = begin(scenario, "5. Bob disconnects and queues")
    send(scenario, "bob", "/disconnect")
    disconnected(scenario, "bob", marks)
    bob_offline = len(scenario.terminals["bob"].snapshot())
    send(scenario, "bob", "/send alice Thanks for telling me")
    expect(scenario, "bob", "✓ Queued locally", marks)
    no_acceptance(scenario, "bob", bob_offline)

    marks = begin(scenario, "6. Alice sends her queue, then disconnects")
    no_acceptance(scenario, "alice", alice_offline)
    send(scenario, "alice", "/connect")
    expect(scenario, "alice", "✓ Logged in as alice", marks)
    accepted(scenario, "alice", marks)
    send(scenario, "alice", "/disconnect")
    disconnected(scenario, "alice", marks)

    marks = begin(scenario, "7. Bob receives while Alice is offline")
    no_acceptance(scenario, "bob", bob_offline)
    send(scenario, "bob", "/connect")
    expect(scenario, "bob", "✓ Logged in as bob", marks)
    expect(scenario, "bob", "← alice: The meeting is tomorrow", marks)
    accepted(scenario, "bob", marks)
    disconnected(scenario, "alice", marks)
    check(scenario)


def diagnostics(scenario):
    return f"Failed step: {scenario.step}\n" + "\n".join(
        f"--- {name} ---\n" + "\n".join(terminal.snapshot())
        for name, terminal in scenario.terminals.items()
    )


@contextmanager
def processes(alice_language, factory):
    with ExitStack() as cleanup:
        port = free_port()
        commands = load_commands(port)
        server = factory(*commands["server"], "server")
        cleanup.callback(server.close)
        terminals = {"server": server}
        try:
            wait_server(port, server)
            bob_language = "rust" if alice_language == "python" else "python"
            for name, language in (("alice", alice_language), ("bob", bob_language)):
                terminal = factory(*commands[language], name)
                terminals[name] = terminal
                cleanup.callback(terminal.close)
            yield terminals
        except BaseException as error:
            diagnostic = (
                Path(tempfile.mkdtemp(prefix="chat-offline-failure-"))
                / "transcript.txt"
            )
            transcript = (
                str(error)
                + "\n"
                + "\n".join(
                    f"--- {name} ---\n" + "\n".join(terminal.snapshot())
                    for name, terminal in terminals.items()
                )
            )
            diagnostic.write_text(transcript)
            print(f"{transcript}\nDiagnostics saved to {diagnostic}", flush=True)
            raise


def pipe_factory(command, cwd, label):
    return Terminal(command, cwd, server=label == "server")


def run_headless(alice_language):
    with processes(alice_language, pipe_factory) as terminals:
        scenario = Scenario(terminals)
        try:
            run_scenario(scenario)
        except BaseException as error:
            raise AssertionError(diagnostics(scenario)) from error


def demo():
    session = "chat-offline-" + uuid4().hex[:8]
    attachment = None
    with tempfile.TemporaryDirectory(prefix="chat-offline-") as directory:
        exit_file = Path(directory) / "exit"
        walkthrough = Path(directory) / "walkthrough.txt"
        walkthrough.write_text(
            "OFFLINE DELIVERY WALKTHROUGH\n\n"
            "Actions run automatically with five seconds between steps.\n"
            "Watch the chat panes alongside this explanation; q exits.\n"
            "Alice uses Python; Bob uses Rust. Both clients stay running.\n"
        )
        explanations = {
            "1": "Log both users in so they can send and receive messages.",
            "2": "Alice sends a greeting. Watch her acceptance and Bob's incoming message.",
            "3": "Bob replies while both users are online. Alice receives the reply.",
            "4": "Alice disconnects from the server, then queues a message locally.\n"
            "Her client stays open; the server has not accepted this message yet.",
            "5": "Bob also disconnects and queues a reply locally.\n"
            "Both users are now offline, with one outgoing message each.",
            "6": "Alice reconnects and sends her queued message to the server.\n"
            "Bob is still offline. After acceptance, Alice disconnects again.",
            "7": "Bob reconnects: he receives Alice's stored message and sends his queue.\n"
            "Alice stays offline while Bob receives her message.",
        }
        tmux("new-session", "-d", "-s", session, "-n", "Chats", "-x", "160", "-y", "48")
        try:
            tmux("set-option", "-t", session, "history-limit", "50000")
            tmux("set-option", "-t", session, "pane-border-status", "top")
            tmux("set-option", "-t", session, "pane-border-format", " #{@chat_label} ")
            tmux("set-option", "-t", session, "key-table", session)
            tmux(
                "bind-key",
                "-T",
                session,
                "q",
                "run-shell",
                "touch " + shlex.quote(str(exit_file)),
            )

            def factory(command, cwd, label):
                return Pane(
                    session, label.title(), command, cwd, first=label == "server"
                )

            def advance(step, *, complete=False):
                with walkthrough.open("a") as output:
                    output.write(f"\n{step}\n")
                    if complete:
                        output.write(
                            "All checks passed. Alice is offline; Bob is online.\n"
                            "Both queued sends were accepted. Press q to exit.\n"
                        )
                    else:
                        output.write(explanations[step.partition(".")[0]] + "\n")
                        output.write("Running this step in 5 seconds...\n")
                tmux("set-option", "-t", session, "status-left", "")
                tmux("set-option", "-t", session, "status-right-length", "180")
                tmux(
                    "set-option",
                    "-t",
                    session,
                    "status-right",
                    step
                    + (" | Complete" if complete else " | Auto: 5s")
                    + " | q: exit",
                )
                deadline = time.monotonic() + 5
                while complete or time.monotonic() < deadline:
                    if exit_file.exists() or attachment.poll() is not None:
                        raise KeyboardInterrupt
                    check(scenario)
                    time.sleep(0.1)

            with processes("python", factory) as terminals:
                Pane(
                    session,
                    "Walkthrough",
                    ["tail", "-n", "+1", "-f", str(walkthrough)],
                    Path(directory),
                )
                attachment = subprocess.Popen(["tmux", "attach-session", "-t", session])
                scenario = Scenario(terminals, advance)
                try:
                    run_scenario(scenario)
                    advance("Complete: queues accepted; Alice offline", complete=True)
                except KeyboardInterrupt:
                    pass
                except BaseException as error:
                    raise AssertionError(diagnostics(scenario)) from error

        finally:
            cleanup_errors = []
            for command in (
                ("unbind-key", "-a", "-T", session),
                ("kill-session", "-t", session),
            ):
                try:
                    tmux(*command)
                except (OSError, subprocess.SubprocessError) as error:
                    cleanup_errors.append(str(error))
            if attachment is not None:
                try:
                    attachment.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    attachment.kill()
                    attachment.wait(timeout=5)
            if cleanup_errors:
                print(
                    "Demo cleanup failed: " + "; ".join(cleanup_errors), file=sys.stderr
                )
                if sys.exc_info()[0] is None:
                    raise RuntimeError("Demo cleanup failed")


if __name__ == "__main__":
    demo()
