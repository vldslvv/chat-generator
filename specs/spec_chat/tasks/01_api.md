# API — data handling draft

## Context

Handle API input validation and storage for the `users` and `messages` collections.

## Contracts

- **Consumes:** [Data contract](../contracts/storage.md).

## Behavior

### Storage operations

Apply these operations when the server requests access to stored records.

| Operation | Inputs | Effects | Outputs |
|---|---|---|---|
| Find or create a user | User name. | Find the existing user or create one with a generated ID. | User record. |
| Find a user | User name. | Look up the user without creating one. | User record or absent result. |
| Store a message | Sender and recipient IDs, text, `client_sent_at`, and `server_received_at`. | Create a message with a generated ID and both acknowledgment-related timestamps set to `null`. | Stored message record. |
| Record acknowledgment | Message ID, `recipient_received_at`, and `server_ack_received_at`. | Record the first acknowledgment's timestamps together. | Updated message record. |

### Timestamps and acknowledgment

Apply these rules when the API receives message events and writes to storage.

- Validate client timestamps as UTC timestamps and use `0` for missing or invalid values.
- Capture server timestamps when handling incoming events, independently of storage writes.
- Overwrite client-provided server timestamps with the server-captured values.
- Reject message storage only when the message text or recipient is missing.
- Preserve the captured and validated event times when writing to storage.
- Treat client-reported times as non-authoritative.
- Validate acknowledgments at the API boundary before passing them to storage.
- Keep `recipient_received_at` and `server_ack_received_at` null until the server supplies an acknowledgment.
- Update both acknowledgment-related timestamps atomically.
- Preserve their first values on repeated acknowledgments.
- Keep all other message fields unchanged during acknowledgment.

### Delivery attempts

Apply this rule when the server attempts delivery.

- Log delivery attempts in the server log.

### Storage lifecycle

Apply these rules to the initial in-memory implementation.

- Start with empty `users` and `messages` collections.
- Retain users and messages while the server process is running.
- Preserve records when clients disconnect.
- Discard both collections when the server process stops.

