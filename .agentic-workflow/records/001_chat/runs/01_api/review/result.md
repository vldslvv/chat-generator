# Reviewer — result

- **Scope and candidate:** `specs/spec_chat/project.md`, `tasks/01_api.md`, both shared contracts, `verification.md`, task acceptance and `apps/chat`; repository HEAD `ba787f6ce7419b1fb79f93d2fa4437a7a8efec8b`, with the candidate untracked and paused by Supervisor throughout review.
- **Role and status:** Reviewer; **FAIL** for R1, an applicable check-policy violation; no API behavior defect reproduced.
- **Model routing:** `agentic-workflow/policies/MODELS.md`; Reviewer default `careful`, requested `gpt-6.1-sol` / `high`; inherited host settings retained because this session cannot change them; observed model/reasoning unavailable.
- **Checks:** Selected login, send/ack, malformed input, timestamp fallback, session lifecycle, one-attempt delivery failure, heartbeat and process/storage lifecycle checks from original requirements before reading acceptance or code.
- **Checks:** In `apps/chat`, independently ran `uv run ruff check .` and `uv run ruff format --check .`; both exited 0, with 15 files formatted.
- **Checks:** In `apps/chat`, independently ran `uv run pytest -q` with loopback-network escalation; exit 0, **38 passed in 47.58s**, with 75 dependency deprecation warnings; fixture cleanup passed.
- **Checks:** Inspected every production and test module, dependency configuration, Dockerfile and README against task constraints and engineering guidelines; `git diff --check` exited 0, but untracked candidate files are outside its coverage.
- **Checks:** Read factual implementation `docker-build.txt` and `container.txt` as supplemental evidence of successful image build, login/send/ack, real process restart and container cleanup; did not independently rerun Docker.

## Findings and resolutions

- **R1 — Remove test-only state exposure (medium):** `apps/chat/chat/api.py:16` and `:17` attach storage and sessions to `app.state`, but production behavior only uses the closed-over `store` and `active` variables. Every reader of these attached attributes is in tests, as confirmed by `rg -n '\.state\.(storage|sessions)' apps/chat`. These attributes are production hooks added solely for tests, prohibited by `agentic-workflow/policies/CHECKS.md` and the test-audit skill.
- **R1 — Affected proof:** `tests/test_websocket.py:48`, `:97`, `:111`, `:112`, `:139`, `:161`, `:177`, `:190`, `:194`, `:212`, `:214`, `:215`, and `tests/test_heartbeat.py:115`, `:117` inspect these hooks and couple transport tests to storage/session representation.
- **R1 — Repair direction:** Remove the attached inspection attributes and retain proof through public storage/session operations or observable WebSocket behavior. Verify rejected requests permit a subsequent valid action, repeated acknowledgments preserve receipts, reconnect preserves identity, offline sends fail, and reconnect after heartbeat timeout succeeds. Existing component tests already own storage identity, immutable acknowledgment fields, and session binding/cleanup invariants. Keep distinct transport lifecycle checks while removing redundant dictionary inspection.
- **R1 — Resolution:** Not repaired during review; candidate remained unchanged.

## Coverage and blockers

- Behavior coverage is otherwise adequate for the task and acceptance criteria.
- The deterministic failing ASGI transport in `test_delivery_failure_retains_message_and_never_retries` is justified: it exercises failure after storage through a real Starlette WebSocket without relying on a network race; real sockets cover successful transport and heartbeat separately.
- No mocks supply the asserted storage, session or acknowledgment behavior, and no further concrete coverage gaps were identified.
- Runtime Docker checks were supplemental existing evidence, rather than independently executed review checks.
- The test-audit skill's optional linked boundary guide was absent at `/home/vv/.agents/docs/help/testing/writing-tests.md`; the skill's explicit rules and repository check policy were available and sufficient.
- No plans, project memory, conversations or implementation design claims were read.
- Usage counters and native-session telemetry are unavailable; this does not block app acceptance.
- Supervisor must schedule a fresh independent review after the R1 repair; this report does not accept the candidate.
