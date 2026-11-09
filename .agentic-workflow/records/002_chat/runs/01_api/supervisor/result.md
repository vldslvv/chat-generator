# API acceptance

- Scope: `specs/spec_chat/tasks/01_api.md` and shared contracts; candidate `apps/chat/api/`.
- Status: PASS, direct mode, task acceptance only; assembled validation remains pending.
- Checks: API implementer reported 51 passing tests in 47.76 seconds, including real heartbeat timing and disconnect cleanup; locked dependency sync, lock check, Ruff lint and format, and package build passed.
- Regression: silent-acknowledgment WebSocket check failed on the obsolete receipt before the fix and passed afterward.
- Supervisor checks: built `chat-generator-api-check` successfully, ran the installed application in Docker, checked `/ws`, single-worker configuration and 20-second ping/timeout settings; `git diff --check` passed.
- Inspection: API handler now records valid acknowledgments without delivering sender notifications; component relocated to the specified directory.
- Final affected rerun: 50 tests passed in 7.60 seconds; detailed result is saved at `../implementer/result.md`; API production code and heartbeat test are unchanged since the full passing run.
- Limits: assembled validation remains pending; client tasks may proceed against the accepted protocol.
