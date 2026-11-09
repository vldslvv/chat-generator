# WebSocket contract

Apply this contract to the API and both Python and Rust clients.
Exchange JSON objects over the WebSocket endpoint `/ws`.

## Connection behavior

Apply these rules to every connection and action.

- Have the server send a standard WebSocket ping every 20 seconds on the existing connection.
- Have clients respond with pong through their WebSocket library.
- Have the server close the connection if the matching pong does not arrive within 20 seconds of the ping.
- Have the server return `error` to the requesting client for requests that fail validation, keeping the connection open and existing state unchanged.
- Reject another `login` on an already logged-in connection, even for the same name.
- Require disconnecting and opening a new connection to switch users.

## Delivery behavior

Apply these rules to accepted messages and successful logins.

- Have the server accept messages for existing recipients whether online or offline.
- Have the server attempt immediate delivery when the recipient is online.
- Treat messages with `server_ack_received_at: null` as pending delivery.
- Have the server run `flush_messages` for the recipient after every successful login, attempting all their pending messages even when senders are offline.
- Deliver messages in server acceptance order, independently of client timestamps and IDs.
- Keep unacknowledged messages pending for the next login after failed or unacknowledged delivery attempts.
- Remove acknowledged messages from pending delivery while retaining their stored records.

`flush_messages` names an internal operation, not a new endpoint or batch request.
Duplicate handling and retries during an established connection remain outside this scope.

## Envelope

Use these fields for requests, replies, and notifications.

- `type: string` identifies the action or event listed below.
- `correlation_id: UUID` identifies a client request and its direct replies.
- `data: object` contains the payload for that action or event.

Apply these correlation rules to each connection.

- Have the client generate a fresh, opaque UUID as `correlation_id` for each request.
- Echo the correlation ID in direct replies, including errors.
- Omit `correlation_id` from server notifications.
- Omit `correlation_id` from an error when the malformed request has no valid correlation ID.
- Determine processing and delivery order on the server independently of correlation and message IDs.
- Use the server-generated message ID to associate recipient acknowledgments with stored messages.

A correlation ID identifies a request, including one rejected before a message exists.
A message ID identifies a stored message across delivery and acknowledgment.

## Shared types

Use these types in the envelope and inside `data`.

- `UUID`: JSON string containing a UUID.
- `UtcTimestamp`: JSON string containing an ISO 8601 timestamp in UTC.
- `ClientTimestampInput`: Any JSON value; preserve a valid `UtcTimestamp` and convert missing or invalid values to the JSON number `0`.

Use these wire types for record IDs and timestamps, preserving the `0` and `null` alternatives defined in the [data contract](storage.md).

## Client requests

Use the action name as `type` and the following fields inside `data`.

### login

- `name: string`.

Example request:

```json
{
  "type": "login",
  "correlation_id": "53dd2b06-e8b7-4a19-9c61-9f8df9bf8524",
  "data": {
    "name": "alice"
  }
}
```

### send

- `recipient: string` — recipient name.
- `text: string` — message content.
- `client_sent_at: ClientTimestampInput` — optional sender timestamp.

Example request:

```json
{
  "type": "send",
  "correlation_id": "629a6d45-679d-4e09-8b3a-d6d779ab415c",
  "data": {
    "recipient": "bob",
    "text": "Hi Bob",
    "client_sent_at": "2026-11-08T12:00:00Z"
  }
}
```

An existing offline Bob receives the message on a later login; the sender receives `message_accepted` immediately after storage.
An unknown recipient still produces a correlated error.

```json
{
  "type": "error",
  "correlation_id": "629a6d45-679d-4e09-8b3a-d6d779ab415c",
  "data": {
    "message": "Recipient does not exist"
  }
}
```

### ack

- `message_id: UUID` — message being acknowledged.
- `recipient_received_at: ClientTimestampInput` — optional recipient timestamp.

A valid `ack` updates server records without a success reply or a notification to the original sender.

Example request acknowledging a received message:

```json
{
  "type": "ack",
  "correlation_id": "b4a0fa95-9c1c-472e-98ae-42fdc01c8aa7",
  "data": {
    "message_id": "6ab59054-8e3c-4b20-9a11-32922d384f68",
    "recipient_received_at": "2026-11-08T12:01:00Z"
  }
}
```

## Server events

Use these event names and payloads for replies and notifications.

### login_ok

Reply to a successful login with `data` matching the [users contract](storage.md#users).

### message_accepted

Reply to an accepted send with `data` matching the [messages contract](storage.md#messages).
Acceptance confirms server receipt and storage only; the server does not notify the sender of recipient acknowledgment.

### message_received

Notify the recipient of an incoming message with `data` containing all fields from the [messages contract](storage.md#messages) and the following display field.

- `sender_name: string` — sender name resolved from the stored message's `sender_id`, without requiring an active sender session.

Keep `sender_id` and the stored message fields unchanged.
Include `sender_name` only in the notification payload, without adding it to stored messages or requiring a client-side user lookup.

### error

Reply to the client whose request failed validation or was rejected, including an invalid `ack`, using this field inside `data`.

- `message: string`.
