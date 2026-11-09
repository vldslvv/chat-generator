FROM python:3.12-slim
COPY --from=ghcr.io/astral-sh/uv:0.11.1 /uv /usr/local/bin/uv
WORKDIR /app
COPY pyproject.toml uv.lock ./
COPY chat ./chat
RUN uv sync --frozen --no-dev
EXPOSE 8000
CMD ["/app/.venv/bin/chat-server"]
