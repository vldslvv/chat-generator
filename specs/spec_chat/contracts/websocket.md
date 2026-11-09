# WebSocket contract

Apply this contract to the API and both Python and Rust clients.
Exchange JSON objects over the WebSocket endpoint `/ws`.

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
- Use the server-generated message ID to associate delivery receipts with stored messages.

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

If Bob is offline, the server correlates the error with that request.

```json
{
  "type": "error",
  "correlation_id": "629a6d45-679d-4e09-8b3a-d6d779ab415c",
  "data": {
    "message": "Recipient is offline"
  }
}
```

### ack

- `message_id: UUID` — message being acknowledged.
- `recipient_received_at: ClientTimestampInput` — optional recipient timestamp.

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

### message_received

Notify the recipient of an incoming message with `data` matching the [messages contract](storage.md#messages).

### delivery_receipt

Notify the original sender of a valid acknowledgment if still connected, using these fields inside `data`.

- `message_id: UUID`.
- `recipient_received_at: UtcTimestamp | 0`.
- `server_ack_received_at: UtcTimestamp`.

A valid `ack` produces a delivery receipt for the original sender without a separate success reply to the acknowledging client.

### error

Reply to the client whose request failed validation or was rejected, including an invalid `ack`, using this field inside `data`.

- `message: string`.
