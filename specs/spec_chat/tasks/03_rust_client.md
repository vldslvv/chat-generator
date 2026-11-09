# Rust client

## Context

Implement the [shared client specification](shared/client.md) in Rust, including its behavior, state, module boundaries, and acceptance criteria.

## Constraints

Apply these technology-specific requirements.

- Use Tokio and [tokio-tungstenite](https://docs.rs/tokio-tungstenite/latest/tokio_tungstenite/) for asynchronous WebSocket communication.
- Use Serde and [serde_json](https://docs.rs/serde_json/latest/serde_json/) for protocol payloads, preserving the shared wire types.
- Use Cargo with `Cargo.toml` and `Cargo.lock` for dependency management.
- Use `cargo fmt` and `cargo clippy` for formatting and code checks.
- Use `cargo test` for unit and behavior tests covering the shared acceptance criteria.
- Create a separate Rust client Dockerfile that builds the binary and runs it with `--url` support and interactive terminal input.
