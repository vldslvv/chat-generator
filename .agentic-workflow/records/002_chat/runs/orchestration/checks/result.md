# Assembled checks

- Scope: API, Python and Rust clients in `apps/chat/`, against `specs/spec_chat`.
- Status: component and integration checks pass; independent final validation pending.
- API: 51 tests passed, including the real 20-second heartbeat and 20-second timeout; locked dependency checks, Ruff and package build pass, as recorded under `runs/01_api/implementer/result.md`.
- Python: worker reports 24 passing tests, clean Ruff lint/format and current lock; Supervisor ran all 24 tests on Python 3.12.16 in the actual Docker image, passing in 1.27 seconds.
- Rust: worker reports 6 passing tests, clean `cargo fmt --check`, `cargo clippy --all-targets --locked -- -D warnings`, `cargo test --locked`, and `cargo build --locked`.
- Integration: `uv run --project apps/chat/api pytest apps/chat/integration -q` passed 1 test in 0.70 seconds; both shipped CLI subprocesses exchanged Unicode and preserved repeated spaces over the real API.
- Containers: all three Docker images built successfully with their locked dependencies; API application import/configuration smoke passed; fixed Python and Rust images accept `--url`, `/status` and `/quit` through stdin.
- Regression: initial Python 3.12 container startup failed with `NameError: ClientState` from a type-only import; postponed function annotations repaired the runtime defect, and the full Python 3.12 suite plus stdin smoke passed afterward.
- Check boundaries: integration uses real subprocesses, real localhost sockets and actual client entrypoints, with no mocks or production test hooks; cleanup exits or kills child processes and closes streams.
- Limits: component evidence is worker-reported unless identified as Supervisor-run; fresh final validation remains pending.
