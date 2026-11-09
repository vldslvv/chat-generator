# Chat API

The API serves the shared [WebSocket contract](../../../specs/spec_chat/contracts/websocket.md) at `ws://localhost:8000/ws`.
It keeps users and messages in memory until the server stops.

Run from this directory with Python 3.12 or newer and uv installed.

```sh
uv sync --frozen
uv run chat-server
```

The server runs one worker on `0.0.0.0:8000` and sends standard WebSocket pings every 20 seconds.
A valid acknowledgment updates storage without sending a reply or a notification.
Rejected requests and operational failures are logged to stderr with their cause and available correlation ID.

Run the checks from this directory.

```sh
uv run ruff check .
uv run ruff format --check .
uv run pytest -q
```

The tests use local TCP connections, including a real heartbeat timeout that takes about 40 seconds.

Build and run the container from this directory.

```sh
docker build -t chat-api .
docker run --rm -p 8000:8000 chat-api
```

For an embedded server, import `chat.api.create_app` and pass the resulting app to `chat.server.create_server(app, host, port)`.
This helper applies the required one-worker and heartbeat settings.
