# 01_api — acceptance

- **Request, sources and scope:** Server behavior from `specs/spec_chat/tasks/01_api.md`, `project.md` and shared contracts; apply engineering guidelines.
- **Prerequisites:** None per `specs/spec_chat/task_order.md`.
- **Target and paths:** `apps/chat`; evidence in `.agentic-workflow/records/001_chat/runs/01_api/implementation`.
- **Contracts:** `specs/spec_chat/contracts/websocket.md` defines `/ws`, JSON envelopes, correlation, errors and heartbeat; `storage.md` defines IDs, names, records and timestamps.

| Requirement ID | Source / contract | Check scenario and pass rule |
|---|---|---|
| API-1 | Login and connection behavior | Open real connections; valid login returns UUID user; invalid names, repeated login and duplicate online names return correlated errors; disconnect permits rebinding with original user ID. |
| API-2 | Send and envelope | Login Alice/Bob; send content; acceptance and notification share stored ID and full fields; authenticated sender comes from session; unknown/offline recipient and invalid input return errors without mutation. |
| API-3 | Acknowledge | Acknowledge as recipient; sender receives uncorrelated receipt; missing, invalid, unknown and wrong-recipient IDs fail without mutation; repeated ack preserves first pair; no separate ack success event. |
| API-4 | Timestamp and storage contracts | Exercise valid UTC strings and missing/malformed values; preserve valid strings and normalize others to 0; replace spoofed server times; null ack fields until valid ack; preserve original message fields. |
| API-5 | Validation and correlation | Exercise malformed JSON, envelope, types, binary input and IDs; errors retain valid request correlation and keep connection usable; notifications omit correlation. |
| API-6 | Heartbeat | Use raw WebSocket frames against real server; observe ping at 20 seconds, matching pong keeps alive, withholding pong closes around 40 seconds; cleanup permits login again. |
| API-7 | Delivery failure | Exercise failed transport after storage; retained record, one logged attempt/outcome, failed session cleanup, no retry or extra sender notification. |
| API-8 | Storage lifecycle | Disconnect/reconnect retains users and messages; new server starts empty; store and ack public operations preserve generated IDs and first timestamps. |
| API-9 | Constraints and design | Inspect separate responsibility modules, plain data models, uv lock, Ruff, pytest and Dockerfile; run source checks and complete automated harness. |

- **Shared/regression/final checks:** Run `uv run ruff check .`, `uv run ruff format --check .` and `uv run pytest`; real network harness implements the scenarios in `specs/spec_chat/verification.md` and closes connections and server processes on exit.
- **Limits and decisions:** Docker runtime execution depends on Docker availability; failed-transport doubles may cover deterministic delivery exceptions where a real network race cannot reliably trigger the required point.
