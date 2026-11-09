# Integration — containerized chat application

## Context

- **Responsibility:** Assemble the web client, API, and database into a runnable prototype.
- **Boundary:** Own the final Compose wiring, proxy configuration, startup guidance, and assembled-app checks.
- **Sources:** [Project requirements](../project.md).

## Contracts

- **Consumes:** [API contract](../contracts/api.md) and [database contract](../contracts/database.md).

## Behavior

- **Inputs:** Component images, environment configuration, and an empty or existing named database volume.
- **Effects:** Start the three services and route browser API traffic to FastAPI.
- **Outputs:** A reachable web page backed by persistent message operations.
- **State and lifecycle:** Wait for database readiness and preserve the volume during normal shutdown and restart.
- **Failures:** Expose service failures without presenting successful message operations.
- **Invariants:** Keep browser traffic on one origin and storage reachable through the API service.

## Constraints

Apply when assembling the application.

- Supply one documented Docker Compose startup command and the browser URL.
- Document configuration, ordinary shutdown, and the explicitly destructive reset command.
- Start the database and API without requiring manual initialization.
- Keep the database service internal to the Compose network in the default configuration.
- Verify the assembled system against real Postgres and real browser clients.

## Acceptance

| Scenario | Observable pass condition |
|---|---|
| Start from an empty volume | The documented command produces a usable chat page and seeded users. |
| Run all shared scenarios | Every scenario in [verification](../verification.md) passes. |
| Restart the stack | Messages and delivery timestamps remain available. |
| Inspect browser requests | API traffic uses the web origin and the contracted `/api` paths. |
