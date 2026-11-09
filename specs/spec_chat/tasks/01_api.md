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
- Follow the shared [connection behavior](../contracts/websocket.md#connection-behavior) for heartbeat, validation failures, and repeated login.
- Validate acknowledgments at the API boundary before passing them to storage.
- Log delivery attempts and their outcomes in the server log.
- On delivery failure, retain the stored message and take no further action, including retries or sender notifications.

## Endpoints

Use the endpoint, envelopes, payload types, and correlation rules in the shared [WebSocket contract](../contracts/websocket.md).

### Login

**Inputs:** [login request](../contracts/websocket.md#login).

Validate login before creating a user or binding the connection.

- Require `name` to match the [user name format](../contracts/storage.md#users).
- Reject a second active login for the same name through the session resolver.

**Effects:** Find or create the user and bind the connection.

**Outputs:** `login_ok` or `error` returned to the requesting client.

### Send

**Inputs:** [send request](../contracts/websocket.md#send).

Validate the send request before storing the message.

- Require an active login and derive `sender_id` from its session.
- Require `recipient` to identify an existing, online user.
- Require `text` to be present.
- Preserve valid `client_sent_at` values and replace missing or malformed values with `0` without rejecting the request.
- Replace any client-provided `server_received_at` with the server's receive time.

**Effects:** Resolve recipient to user ID, store the message, and attempt delivery once.

Populate the notification's `sender_name` from the authenticated sender's user record according to the [message notification contract](../contracts/websocket.md#message_received).

**Outputs:** `message_accepted` to the sender, `message_received` to the recipient if delivery succeeds, or `error` to the sender on request rejection.

### Acknowledge

**Inputs:** [ack request](../contracts/websocket.md#ack).

Validate the acknowledgment before updating the stored message.

- Require an active login.
- Require `message_id` to identify an existing message.
- Require the message's recipient to match the user bound to the session.
- Preserve valid `recipient_received_at` values and replace missing or malformed values with `0` without rejecting the acknowledgment.
- Replace any client-provided `server_ack_received_at` with the server's acknowledgment receive time.
- Accept repeated acknowledgments while preserving the first recorded timestamps.

**Effects:** Record the acknowledgment.

**Outputs:** No success reply or sender notification; return `error` to the acknowledging client on validation failure.

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

## Design guide

Implement each responsibility below as a separate module with a public interface that hides its implementation and allows behavior to be extended independently.

- Encapsulate storage operations for users, messages, and acknowledgments.
- Isolate session management for connection bindings, online-user lookup, disconnect cleanup, and duplicate-login policy.
- Encapsulate delivery attempts and outcome logging.
- Isolate message handling to coordinate sends and acknowledgments through storage, sessions, and delivery.
- Isolate the WebSocket API to decode and validate requests, derive the acting user from the session, and format responses.
- Keep `User` and `Message` as plain data models.

## Constraints

Apply these constraints to implementation.

- Use FastAPI and Uvicorn with one worker process.
- Use Pydantic to validate endpoint inputs, preserving the timestamp fallback rules.
- Optionally use Pydantic to validate endpoint outputs.
- Use uv for dependency management.
- Use Ruff for code checks.
- Create a Dockerfile for the project.
- Use pytest for unit and behavior testing.
