# Local chat server

The FastAPI server provides online messaging at `ws://localhost:8000/ws` with in-memory users and messages.
Run one server process so all connections share the same state.

## Run

From `apps/chat`, install the locked environment and start Uvicorn:

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
The protocol and storage contracts are in `../../specs/spec_chat/contracts/`.

## Container

Build and run from `apps/chat`:

```sh
docker build -t local-chat .
docker run --rm -p 8000:8000 local-chat
```
