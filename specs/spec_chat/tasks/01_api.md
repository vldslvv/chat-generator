# API — draft

## Context

Handle login, live messaging, acknowledgments, and storage using the [data contract](../contracts/storage.md).
Support online-only delivery without offline queues or replay.

## Behavior

Apply these rules to client connections and requests.

- Exchange JSON messages and replies over one WebSocket connection per client.
- Bind successful login to the connection and mark the user online.
- Require login for sends and acknowledgments, deriving the acting user from the session.
- Remove sessions on connection closure or detected failure, allowing delayed detection of network loss.
- Reject malformed requests before storage mutations, except for the timestamp fallback below.
- Validate acknowledgments at the API boundary before passing them to storage.
- Log delivery attempts in the server log.
- Retain accepted messages if recipients disconnect during delivery.

## Endpoints

These actions use the shared WebSocket connection.

### Payload types

Use these types for endpoint inputs and outputs, independently of the event envelope.

- `UUID`: JSON string containing a UUID.
- `UtcTimestamp`: JSON string containing an ISO 8601 timestamp in UTC.
- `ClientTimestampInput`: Any JSON value; preserve a valid `UtcTimestamp` and convert missing or invalid values to the JSON number `0`.
- `User`: JSON object with the fields and types from the [users contract](../contracts/storage.md#users), using `UUID` for its ID.
- `Message`: JSON object with the fields and types from the [messages contract](../contracts/storage.md#messages), using `UUID` and `UtcTimestamp` for IDs and timestamps.
- `DeliveryReceipt`: JSON object containing `message_id: UUID`, `recipient_received_at: UtcTimestamp | 0`, and `server_ack_received_at: UtcTimestamp`.
- `Error`: JSON object containing `message: string`.

### Login

**Inputs:** JSON object with `name: string`.

Validate login before creating a user or binding the connection.

- Require `name` to match the [user name format](../contracts/storage.md#users).
- Reject a second active login for the same name through the session resolver.

**Effects:** Find or create the user and bind the connection.

**Outputs:** `User` on successful login, or `Error`, returned to the requesting client.

### Send

**Inputs:** JSON object with these fields.

- `recipient: string` — recipient name.
- `text: string` — message content.
- `client_sent_at: ClientTimestampInput` — optional sender timestamp.

Validate the send request before storing the message.

- Require an active login and derive `sender_id` from its session.
- Require `recipient` to identify an existing, online user.
- Require `text` to be present.
- Preserve valid `client_sent_at` values and replace missing or malformed values with `0` without rejecting the request.
- Replace any client-provided `server_received_at` with the server's receive time.

**Effects:** Resolve recipient to user ID, store the message, and attempt delivery once.

**Outputs:** `Message` to the sender on acceptance and to the recipient on delivery, or `Error` to the sender on rejection.

### Acknowledge

**Inputs:** JSON object with these fields.

- `message_id: UUID` — message being acknowledged.
- `recipient_received_at: ClientTimestampInput` — optional recipient timestamp.

Validate the acknowledgment before updating the stored message.

- Require an active login.
- Require `message_id` to identify an existing message.
- Require the message's recipient to match the user bound to the session.
- Preserve valid `recipient_received_at` values and replace missing or malformed values with `0` without rejecting the acknowledgment.
- Replace any client-provided `server_ack_received_at` with the server's acknowledgment receive time.
- Accept repeated acknowledgments while preserving the first recorded timestamps.

**Effects:** Record the acknowledgment.

**Outputs:** `DeliveryReceipt` to the sender if connected, or `Error` to the acknowledging client on validation failure.

## Tables

- [users](../contracts/storage.md#users)
- [messages](../contracts/storage.md#messages)

## Storage

Apply these operations to in-memory records.

- Start with empty `users` and `messages` collections.
- Retain records across client disconnections until the server process stops, then discard them.

### Find or create user

- **Inputs:** Name.
- **Effects:** Create with a generated ID only if absent.
- **Outputs:** User record.

### Find user

- **Inputs:** Name.
- **Effects:** Look up without creating.
- **Outputs:** User record or absent result.

### Store message

- **Inputs:** Sender and recipient IDs, text, `client_sent_at`, `server_received_at`.
- **Effects:** Generate ID and initialize both acknowledgment timestamps to `null`.
- **Outputs:** Stored message record.

### Record acknowledgment

- **Inputs:** Message ID, `recipient_received_at`, `server_ack_received_at`.
- **Effects:** Record the first acknowledgment's timestamps.
- **Outputs:** Updated message record.

## Timestamps

Apply these rules when receiving events and storing acknowledgments.

- Validate client timestamps as UTC timestamps and use `0` for missing or invalid values.
- Treat client-reported times as non-authoritative.
- Capture server times on event receipt, replacing any client-provided server timestamps.
- Preserve event times when writing to storage instead of using storage-write times.
- Keep both acknowledgment timestamps null until a validated acknowledgment arrives.
- Record both acknowledgment timestamps atomically without changing other message fields.
- Preserve the first acknowledgment timestamps on repeated acknowledgments.

## Constraints

Apply these constraints to implementation.

- Use FastAPI and Uvicorn with one worker process.
- Use Pydantic to validate endpoint inputs, preserving the timestamp fallback rules.
- Optionally use Pydantic to validate endpoint outputs.
- Use uv for dependency management.
- Use Ruff for code checks.
- Create a Dockerfile for the project.
- Use pytest for unit and behavior testing.

## Pending design details

The WebSocket endpoint path, JSON event envelopes, and heartbeat timing remain to be agreed.
