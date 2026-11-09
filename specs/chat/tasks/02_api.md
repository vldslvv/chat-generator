# API — message operations

## Context

- **Responsibility:** Expose the chat HTTP operations and translate storage outcomes into API responses.
- **Boundary:** Own FastAPI routing, request validation, serialization, storage wiring, and the API container.
- **Sources:** [Project requirements](../project.md).

## Contracts

- **Provides:** [API contract](../contracts/api.md).
- **Consumes:** [Database contract](../contracts/database.md).

## Behavior

- **Inputs:** HTTP requests, identity headers, JSON bodies, query parameters, and database configuration.
- **Effects:** Call storage mutations only for valid send and acknowledgment requests.
- **Outputs:** JSON responses and HTTP statuses defined by the API contract.
- **State and lifecycle:** Keep identity selection stateless and release database resources after requests.
- **Failures:** Translate validation, permission, missing-record, and storage failures into contracted responses.
- **Invariants:** Use the selected identity for sender and recipient permissions on every operation.

## Constraints

Apply when implementing the API component.

- Use FastAPI served by Uvicorn.
- Consume the database-access module instead of duplicating SQL or storage rules in routes.
- Provide an API image that starts with supplied database configuration.

## Acceptance

| Scenario | Observable pass condition |
|---|---|
| Call every endpoint with real Postgres | Inputs, responses, and persisted effects satisfy both contracts. |
| Submit invalid or unauthorized requests | Satisfy [validation and isolation](../verification.md#validation-and-isolation). |
| Retrieve history and pending data | Satisfy [history and backlog](../verification.md#history-and-backlog). |
| Send and acknowledge a message | Satisfy the API portion of [message delivery](../verification.md#message-delivery). |
| Interrupt the database | Satisfy the API portion of [failure recovery](../verification.md#failure-recovery). |
