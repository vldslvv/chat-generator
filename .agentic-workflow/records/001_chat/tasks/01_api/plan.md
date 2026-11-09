# 01_api — plan

- **Request and scope:** Implement the server in plan-review mode; Python and Rust clients are excluded.
- **Acceptance:** [acceptance.md](acceptance.md).
- **Sources and dependencies:** `specs/spec_chat/project.md`, `tasks/01_api.md`, both contracts and `verification.md`; engineering guidelines, checks, records and document style apply; no prerequisites.
- **Approach:** Own `apps/chat` and task evidence; use plain records, in-memory storage, session state, delivery, handling, validation and API modules; serialize connection requests and timestamp receipt before validation; run Uvicorn with one worker and standard protocol heartbeat.
- **Target and paths:** FastAPI/Uvicorn application in `apps/chat`; evidence under `runs/01_api/implementation`.
- **Checks:** Run Ruff and pytest with real Uvicorn/WebSocket integration, raw frame heartbeat checks, storage lifecycle checks and focused failed-transport behavior; inspect diff; document narrow transport doubles.
- **Memory:** No project memory is used for this specification task.
