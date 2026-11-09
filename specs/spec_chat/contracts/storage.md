# Data contract

## Users

| Field | Type | Meaning |
|---|---|---|
| `id` | UUID | Server-generated, unique user ID. |
| `name` | String | Unique name matching `[a-z0-9_]{1,32}`. |

## Messages

| Field | Type | Meaning |
|---|---|---|
| `id` | UUID | Server-generated, unique message ID. |
| `sender_id` | UUID | Reference to the sending user. |
| `recipient_id` | UUID | Reference to the receiving user. |
| `text` | String | Original message text. |
| `client_sent_at` | UTC timestamp or `0` | Sender's local time immediately before sending; `0` means missing or invalid. |
| `server_received_at` | UTC timestamp | Server's time when it receives the send request. |
| `recipient_received_at` | UTC timestamp, `0`, or `null` | Recipient's local time when it decodes the incoming message, before displaying it; `0` means missing or invalid, and `null` means no acknowledgment recorded. |
| `server_ack_received_at` | UTC timestamp or `null` | Server's time when it receives the recipient's acknowledgment. |

The [incoming message notification](websocket.md#message_received) adds `sender_name` for display; it is not a stored message field.
