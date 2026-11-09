# Python client

## Context

Implement the [shared client specification](shared/client.md) in Python, including its behavior, state, module boundaries, and acceptance criteria.

## Constraints

Apply these technology-specific requirements.

- Use `asyncio` and [aiohttp](https://docs.aiohttp.org/en/stable/client_reference.html#clientwebsocketresponse) for asynchronous WebSocket communication.
- Use Pydantic models for protocol payloads, preserving the shared wire types.
- Use uv with `pyproject.toml` and `uv.lock` for dependency management.
- Implement the Python setup and launch interface in the [launch contract](../contracts/launch.md), including its applicable acceptance checks.
- Use Ruff for linting and formatting.
- Use pytest for unit and behavior tests covering the shared acceptance criteria.
- Create a separate Python client Dockerfile with an entry point that accepts `--url` and supports interactive terminal input.
