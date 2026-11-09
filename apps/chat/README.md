# Local chat

The FastAPI server provides online messaging at `ws://localhost:8000/ws` with in-memory users and messages.
Run one server process so all connections share the same state.
The API and both clients log rejected requests and operational failures to stderr,
including the cause and any available correlation ID.

## Run

From `apps/chat/api`, install the locked environment and start Uvicorn:

```sh
uv sync --frozen
uv run chat-server
```

The server sends a standard WebSocket ping every 20 seconds and closes connections after 20 seconds without the matching pong.
Restarting the process discards users and messages.

## Check

The test harness starts real localhost Uvicorn servers and connects with the WebSocket library and raw socket frames.
The raw heartbeat scenario takes about 40 seconds and checks matching and unrelated pong behavior.
The delivery failure scenario uses a real Starlette connection with a failing ASGI transport to exercise failure after storage deterministically.

```sh
uv run ruff check .
uv run ruff format --check .
uv run pytest -q
```

Pytest reports the evidence and closes its connections, threads and listening sockets in fixture cleanup.
No application clients or external services are needed.
The protocol, storage, and CLI contracts are in `../../specs/spec_chat/contracts/`.

After installing both Python environments and building the Rust client, run the
cross-language CLI check from the repository root:

```sh
cargo build --locked --manifest-path apps/chat/rust-client/Cargo.toml
uv run --project apps/chat/api pytest apps/chat/integration -q
```

This check starts a real API process and both terminal clients, exchanges Unicode
messages in both directions, and closes all processes when it finishes.

## Clients

Run the Python client from `apps/chat/python-client`:

```sh
uv sync --frozen
uv run chat-python --url ws://localhost:8000/ws
```

Run the Rust client from `apps/chat/rust-client`:

```sh
cargo run --locked -- --url ws://localhost:8000/ws
```

Use `/connect alice` to log in, `/send bob Hello Bob` to send a message,
and `/status` to inspect the connection and latest heartbeat.
Use `/disconnect` to close gracefully or `/drop-connection` to terminate the socket.
Use `/connect` to reconnect with the last successfully logged-in name.
Use `/help` to list commands and `/quit` to exit.
Both clients keep accepting terminal commands after connection loss.
Messages are delivered only to users currently online; clients do not retry or reconnect automatically.

## Container

Build and run from `apps/chat/api`:

```sh
docker build -t local-chat .
docker run --rm -p 8000:8000 local-chat
```

Each client directory also contains a Dockerfile.
Build it in that directory and run it with `docker run --rm -it`, passing
`--url` with a server address reachable from the container.
