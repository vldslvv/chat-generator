# Client — browser chat

## Context

- **Responsibility:** Let a user select a peer, exchange text messages, and observe delivery.
- **Boundary:** Own the Svelte client, styles, frontend build, and Nginx image.
- **Sources:** [Project requirements](../project.md).

## Contracts

- **Consumes:** [API contract](../contracts/api.md).

## Behavior

- **Inputs:** Entry-form values, drafts, user submissions, and API responses.
- **Effects:** Load history, poll updates, send drafts, and acknowledge rendered incoming messages.
- **Outputs:** Entry errors, ordered chat messages, outgoing delivery labels, and connection feedback.
- **State and lifecycle:** Apply the [client interaction rules](../contracts/api.md#client-interaction) and keep state in page memory.
- **Failures:** Preserve visible history and failed drafts while following contracted retry behavior.
- **Invariants:** Render each message ID once and acknowledge only incoming messages already displayed.

## Constraints

Apply when implementing the web client.

- Use Svelte, TypeScript, Vite, and plain CSS.
- Use relative `/api` URLs through the web origin.
- Serve compiled assets through Nginx without a runtime Node server.
- Keep database access outside the browser.

## Acceptance

| Scenario | Observable pass condition |
|---|---|
| Open a valid or invalid conversation | Show the chat only after successful validation and history retrieval. |
| Exchange messages in two browsers | Satisfy [message delivery](../verification.md#message-delivery). |
| Merge history with repeated pending records | Satisfy the browser portion of [history and backlog](../verification.md#history-and-backlog). |
| Lose connectivity during sends or polling | Satisfy the browser portion of [failure recovery](../verification.md#failure-recovery). |
| Reload the page | Return to the entry form and restore persisted history after re-entering names. |
