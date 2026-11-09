# Database — persistent message storage

## Context

- **Responsibility:** Persist users and messages and expose the storage operations used by the API.
- **Boundary:** Own the schema, seed data, database-access module, and Postgres service definition.
- **Sources:** [Project requirements](../project.md).

## Contracts

- **Provides:** [Database contract](../contracts/database.md).

## Behavior

- **Inputs:** Storage calls, database connection configuration, and an empty or existing Postgres volume.
- **Effects:** Initialize empty storage and commit message and delivery changes.
- **Outputs:** Records and errors defined by the database contract.
- **State and lifecycle:** Initialize once and preserve stored data across normal restarts.
- **Failures:** Roll back failed transactions and report storage failures through the contract.
- **Invariants:** Preserve participant isolation, referential integrity, and first-delivery timestamps.

## Constraints

Apply when implementing the database component.

- Implement every [storage operation](../contracts/database.md#storage-operations) against real Postgres.
- Keep database side effects inside the database-access module.
- Supply schema initialization and seeded users without manual SQL steps.
- Keep API routing and browser behavior outside this component.

## Acceptance

| Scenario | Observable pass condition |
|---|---|
| Initialize an empty database | The contracted schema and three unique seed users exist. |
| Exercise storage operations | Results, errors, ordering, and effects satisfy the [database contract](../contracts/database.md). |
| Repeat or race acknowledgments | All successful acknowledgments preserve the first timestamp. |
| Restart storage | Satisfy [persistence](../verification.md#persistence). |
| Disconnect storage | Satisfy the storage portion of [failure recovery](../verification.md#failure-recovery). |
