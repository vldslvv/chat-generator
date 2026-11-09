# Chat

Build a local messaging app with a FastAPI/Uvicorn server and independent Python and Rust clients.

- Implement the [API](tasks/01_api.md), [Python client](tasks/02_python_client.md), and [Rust client](tasks/03_rust_client.md).
- Follow the [engineering guidelines](../../agentic-workflow/policies/GUIDELINES.md).
- Use the shared [WebSocket](contracts/websocket.md) and [storage](contracts/storage.md) contracts.
- Support online-only messaging with in-memory server storage and no external services.

## Implementation directories

Place each component in its own directory, relative to the repository root.

- `apps/chat/api/` — API source, dependencies, tests, and Dockerfile.
- `apps/chat/rust-client/` — Rust client source, dependencies, tests, and Dockerfile.
- `apps/chat/python-client/` — Python client source, dependencies, tests, and Dockerfile.
