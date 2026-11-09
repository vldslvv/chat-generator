# API contract

- **Participants:** The [API](../tasks/02_api.md) provides HTTP operations to the [client](../tasks/03_client.md), assembled by [integration](../tasks/04_integration.md).
- **Sources:** [Project requirements](../project.md).
- **Interface:** JSON endpoints under `/api`, using `X-User` to select the current identity.
- **Semantics:** Validate participants, expose conversation data, save messages, and acknowledge client display.
- **Guarantees:** Apply the [database contract](database.md) to persistence, ordering, participant isolation, and delivery transitions.

## Data and identity

Apply to all endpoints.

- Require a known login name in the `X-User` header on every request.
- Trim surrounding whitespace from login and recipient names before matching.
- Match names case-sensitively against the predefined lowercase names.
- Derive the sender from `X-User` rather than accepting a sender field in the send body.
- Return timestamps as UTC ISO 8601 strings with a timezone indicator.
- Return message IDs as positive JSON integers.
- Represent messages as `{id, sender, recipient, text, created_at, delivered_at}`.
- Represent `sender` and `recipient` as login names and an absent delivery timestamp as JSON `null`.
- Represent delivery updates as `{id, delivered_at}` with a non-null timestamp.
- Keep login selection stateless without issuing session cookies or tokens.

## Operations

| Method and path | Input | Success response | Effects |
|---|---|---|---|
| `GET /api/messages/history` | Query parameter `recipient` | `200`, `{messages: Message[]}` | None. |
| `POST /api/messages/poll` | `{recipient, awaiting_delivery_ids: number[]}` | `200`, `{pending_messages: Message[], delivery_updates: DeliveryUpdate[]}` | None. |
| `POST /api/messages` | `{recipient, text}` | `201`, `Message` | Save one message. |
| `POST /api/messages/{id}/ack` | Positive message ID; no body | `200`, `DeliveryUpdate` | Record first delivery. |

### History and polling

Apply to conversation retrieval requests.

- Validate the current user and recipient before returning history or poll results.
- Return the latest 100 messages in both directions through history, in ascending ID order.
- Return all unacknowledged messages from the selected peer to the current user through polling.
- Include pending messages older than the history window.
- Return delivery updates only for supplied outgoing IDs that have been acknowledged.
- Return empty arrays when no matching messages or updates exist.
- Reject invalid delivery lookups according to the [storage operation rules](database.md#storage-operations).
- Keep retrieval operations free of acknowledgment effects.

### Sending and acknowledgment

Apply to message mutations.

- Return a newly saved message only after its database transaction commits.
- Initialize its delivery timestamp to null.
- Record delivery only when the recipient explicitly acknowledges the message.
- Return the original timestamp when an acknowledgment is repeated.
- Permit acknowledgment of incoming messages obtained from either history or polling.
- Treat each send request as a new message without an idempotency key.
- Permit duplicates if a client retries a send after losing the response to a committed request.

## Validation and errors

Apply validation before performing mutations.

- Reject self-chat.
- Require message text to contain at least one non-whitespace character.
- Limit message text to 2,000 Unicode code points.
- Reject text containing NUL (U+0000) with `422`, as approved during implementation.
- Preserve valid text exactly, including surrounding spaces and line breaks.
- Require JSON bodies with the declared field types and reject unexpected body fields.
- Return errors as JSON with a `detail` field describing the failure.
- Allow `detail` to contain FastAPI validation details for malformed requests.
- Leave persisted state unchanged after input or permission rejection.

| Condition | Status |
|---|---|
| Missing or unknown `X-User` | `401` |
| Unknown recipient or message | `404` |
| Delivery lookup containing an absent or out-of-conversation message | `404` |
| Existing message acknowledged by someone other than its recipient | `403` |
| Self-chat, invalid text, malformed fields, or invalid message ID | `422` |
| Database unavailable or a storage operation fails | `503` |

## Client interaction

- **Context:** One selected identity and peer are active in a browser page.
- **Inputs:** Login, recipient, message drafts, history responses, poll responses, and acknowledgment responses.
- **Effects:** Send messages and acknowledge incoming messages after rendering them.
- **Outputs:** Ordered chat messages, connection errors, retained failed drafts, and outgoing Sent/Delivered labels.

Follow this sequence when opening a chat.

1. Load history using the entered login and recipient.
2. Show the chat only after successful validation and history retrieval.
3. Render history and acknowledge its undelivered incoming messages.
4. Poll immediately, then every two seconds without overlapping poll requests.
5. Merge responses by message ID and render messages in ascending ID order.
6. Acknowledge incoming messages after rendering and apply outgoing delivery updates.

Apply these lifecycle rules while the chat is open.

- Include displayed outgoing IDs with null delivery timestamps in subsequent polls.
- Show Sent after a successful send response and Delivered after a non-null delivery timestamp arrives.
- Append new messages without enforcing a fixed display limit.
- Deduplicate repeated history, send, and poll records by message ID.
- Acknowledge repeated pending messages even when their rendered records already exist.
- Preserve known delivery timestamps when merging an older response with a null timestamp.
- Keep the draft until sending succeeds and disable concurrent composer submissions.
- Preserve the draft and show an error after a failed send without automatically resending.
- Keep the current chat visible and retry polling after transient connection failures.
- Retry unconfirmed acknowledgments when messages reappear as pending.
- Schedule the next poll after the preceding poll completes, with a two-second delay.
- Keep identity and recipient in page memory and return to the entry form on reload.
- Display each message's sender, text, and creation time.
- Render text as text rather than executable markup.

## Examples

| Interaction | Observable outcome |
|---|---|
| user1 sends to user2 | user1 sees Sent after persistence; user2 receives the message through history or polling. |
| user2 renders and acknowledges that message | A later user1 poll returns its delivery timestamp and the label becomes Delivered. |
| An acknowledgment response is lost | The first timestamp remains authoritative and retrying acknowledgment is safe. |
| History contains 100 records and pending contains older records | The client displays their ordered union without duplicate records. |
