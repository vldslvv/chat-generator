FROM python:3.12-slim
COPY --from=ghcr.io/astral-sh/uv:0.13.6 /uv /uvx /bin/
WORKDIR /app
COPY pyproject.toml uv.lock ./
COPY chat_client ./chat_client
RUN uv sync --frozen --no-dev
ENTRYPOINT ["/app/.venv/bin/chat-python"]
