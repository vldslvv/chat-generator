# Local chat

The FastAPI server provides online and offline messaging at `ws://localhost:8000/ws` with in-memory users and messages.
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
Messages for existing offline users stay pending on the server until acknowledged.
After a successful login, the server delivers pending messages in acceptance order,
even when their senders are offline. Clients retain outgoing messages in memory
until acceptance and resume sending when the same user reconnects.
An offline `/send` reports `✓ Queued locally`. Clients do not reconnect automatically,
and queues do not survive process restarts.

Interactive terminals show a `> ` prompt and preserve unfinished input when a
message arrives. Incoming messages appear as `← alice: Hello`, using the sender's
authenticated name and preserving message spacing. Command results and incoming
events are separated by blank lines. Errors appear once on stderr with an
actionable description and the request correlation ID when available.

## Container

Build and run from `apps/chat/api`:

```sh
docker build -t local-chat .
docker run --rm -p 8000:8000 local-chat
```

Each client directory also contains a Dockerfile.
Build it in that directory and run it with `docker run --rm -it`, passing
`--url` with a server address reachable from the container.

## Offline delivery test and demo

Install both Python environments with `uv sync --frozen` in their respective API
and client directories; install Cargo to build the Rust client.
Run these commands from the repository root:

```sh
make test-offline-delivery
make demo-offline-delivery
```

Both commands build the Rust binary and start a fresh server on an available local
port. The headless pytest run checks Alice in Python and Bob in Rust, then swaps
the languages with a fresh server. Each run keeps all three processes alive while
clients disconnect, queue messages, and reconnect. It checks CLI output and server
acceptance; API and storage tests verify acknowledgment records and pending state.

The visual demo also requires `tmux` and an interactive terminal. It opens a dedicated
session with Server, Alice, and Bob panes. Press Space to run the step shown in the
status line and q to exit. The completed transcript stays visible until you advance
or exit. If already inside tmux, launch the demo from a terminal outside tmux.
Viewer pauses do not count toward event timeouts. The runners stop their own
processes on completion or interruption and leave unrelated tmux sessions alone.
Failures include the current step and captured output; demo failures save a
transcript in the reported temporary directory.
