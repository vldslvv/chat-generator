# Setup and launch contract

Apply this contract to every implementation and regeneration of the [chat project](../project.md).
The offline delivery test and demo depend on these public commands, independently
of application module names and internal structure.

## Setup

Run these commands from the repository root with Python 3.12 or later, uv and
Cargo installed.

```sh
uv sync --frozen --project apps/chat/api
uv sync --frozen --project apps/chat/python-client
cargo build --locked --manifest-path apps/chat/rust-client/Cargo.toml
```

- Preserve the component directories declared in the project specification.
- Include `pyproject.toml` and a current `uv.lock` in both Python projects.
- Include `Cargo.toml` and a current `Cargo.lock` in the Rust project.
- Make setup succeed from a fresh checkout without existing virtual environments or build output.
- Make repeated setup succeed without changing committed dependency locks.
- Produce the Rust executable at `apps/chat/rust-client/target/debug/chat-rust` with the setup command above.

## Launch

Run these commands from the repository root after setup, using a free port in
place of `8000` when running automated checks.

```sh
uv run --frozen --project apps/chat/api chat-server --host 127.0.0.1 --port 8000
uv run --frozen --project apps/chat/python-client chat-python --url ws://127.0.0.1:8000/ws
apps/chat/rust-client/target/debug/chat-rust --url ws://127.0.0.1:8000/ws
```

- Expose `chat-server` and `chat-python` as installed Python console entry points.
- Preserve these executable names and options across regeneration.
- Accept `--host` and `--port` in `chat-server`, defaulting to `0.0.0.0` and `8000` when omitted.
- Bind the server to the supplied address and port with one worker and the specified WebSocket heartbeat behavior.
- Serve the WebSocket endpoint at `/ws`.
- Accept `--url` in both clients and use the supplied WebSocket URL without replacing its host, port or path.
- Start both clients disconnected and implement the [CLI contract](cli.md) over stdin, stdout and stderr.
- Support both piped input for tests and interactive terminal input for the demo.
- Keep each launched command in the foreground until shutdown.
- Release server resources on SIGINT or SIGTERM and exit clients on `/quit`.
- Report startup failures on stderr and exit nonzero.
- Keep internal Python import paths out of external launch commands.

## Offline runner configuration

Generate `apps/chat/offline-delivery.json` for the durable
[runner](../../../tools/offline_delivery/README.md), using paths relative to that
configuration file.

```json
{
  "prepare": [
    {"command": ["uv", "sync", "--frozen", "--project", "api"]},
    {"command": ["uv", "sync", "--frozen", "--project", "python-client"]},
    {"command": ["cargo", "build", "--locked", "--manifest-path", "rust-client/Cargo.toml"]}
  ],
  "server": {
    "cwd": "api",
    "command": ["uv", "run", "--frozen", "chat-server", "--host", "127.0.0.1", "--port", "{port}"]
  },
  "python": {
    "cwd": "python-client",
    "command": ["uv", "run", "--frozen", "chat-python", "--url", "{url}"]
  },
  "rust": {
    "cwd": "rust-client",
    "command": ["./target/debug/chat-rust", "--url", "{url}"]
  }
}
```

- Assign generation of this configuration to the API task, using the fixed client launch interfaces above.
- Preserve the runner, its dependencies and the Make targets outside `apps/` during regeneration.
- Keep `make test-offline-delivery` and `make demo-offline-delivery` usable without configuration edits after regenerating `apps/chat/`.

## Acceptance

Verify the public commands against real processes.

- Run setup with no preexisting component virtual environments or Rust build output and verify all commands succeed.
- Repeat setup and verify the dependency locks remain unchanged.
- Start the server on an available nondefault localhost port and connect both clients with the exact launch interfaces above.
- Exchange a message in both directions and verify each client uses the supplied server URL.
- Stop the clients with `/quit` and stop the server with SIGTERM, verifying all three processes exit.
- Run both offline delivery Make targets against the regenerated configuration without modifying the durable runner.
- Verify both headless language assignments pass and the demo advances automatically every five seconds, provides a Walkthrough window, and supports exiting and cleanup.
