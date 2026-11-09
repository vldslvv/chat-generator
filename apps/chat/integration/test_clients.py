"""Exercise both shipped CLIs against the real API, in both directions."""

import time
from contextlib import ExitStack
from uuid import UUID

from harness import ROOT, Terminal, server


def test_python_and_rust_exchange_messages():
    with server() as url, ExitStack() as cleanup:
        python = Terminal(
            ["uv", "run", "--frozen", "chat-python", "--url", url],
            ROOT / "python-client",
        )
        cleanup.callback(python.close)
        rust = Terminal(
            [str(ROOT / "rust-client/target/debug/chat-rust"), "--url", url],
            ROOT / "rust-client",
        )
        cleanup.callback(rust.close)
        for client, name in [(python, "python_user"), (rust, "rust_user")]:
            client.send(f"/connect {name}")
            # Status is local; poll until the asynchronous login completes.
            deadline = time.monotonic() + 10
            while True:
                client.send("/status")
                line = client.expect("Session:")
                if "logged in" in line:
                    break
                assert time.monotonic() < deadline, client.transcript
                time.sleep(0.05)
        for sender, recipient, sender_name, name, message in [
            (python, rust, "python_user", "rust_user", "  Python 🌎  spaces  "),
            (rust, python, "rust_user", "python_user", "  Rust 🦀  spaces  "),
        ]:
            sender.send(f"/send {name} {message}")
            UUID(sender.expect("✓ Accepted ").split("✓ Accepted ", 1)[1].strip())
            assert recipient.expect(message) == f"← {sender_name}: {message}"
        for client, name in [(python, "python_user"), (rust, "rust_user")]:
            message = "  note to myself  "
            start = len(client.transcript)
            client.send(f"/send {name} {message}")
            # The server may deliver to self before or after accepting the send.
            deadline = time.monotonic() + 10
            while True:
                lines = client.transcript[start:]
                accepted = [line for line in lines if line.startswith("✓ Accepted ")]
                if accepted and f"← {name}: {message}" in lines:
                    UUID(accepted[0].split("✓ Accepted ", 1)[1])
                    break
                assert time.monotonic() < deadline, client.transcript
                time.sleep(0.02)
        for client in (python, rust):
            assert not any("delivery_receipt" in line for line in client.transcript)
            client.send("/status")
            client.expect("Session: logged in")
