# Engineering guidelines

Read before planning, production code, tests, tooling, review or repairs.

- Separate state and logic.
- Use classes that mix state and logic only when required.
- Localize side effects.
- Keep each module's top-level flow clear and functional.
- Prefer small, Unix-like modules.
- Give each module a public API with few responsibilities.
- Prioritize public behaviour tests.
- Internal tests can add useful coverage.
- Prefer real infrastructure.
- Justify mocks under [Checks](CHECKS.md).
- Compose larger structures from small modules.
- Test public behaviour for every eligible module.
- Test public contracts specified in the task.
- Add validations, locks, checksums and manifests only when needed or explicitly requested.
- Do not create backwards-compatible functionality unless explicitly requested.
- Use simple language in comments and documents.
- Avoid dense jargon and stock AI phrasing.
