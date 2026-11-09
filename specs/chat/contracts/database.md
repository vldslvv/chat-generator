# Database contract

- **Participants:** The [database component](../tasks/01_database.md) provides storage to the [API](../tasks/02_api.md), assembled by [integration](../tasks/04_integration.md).
- **Sources:** [Project requirements](../project.md) and the storage effects required by the [API contract](api.md).
- **Interface:** User lookup, history retrieval, pending retrieval, delivery lookup, message creation, and acknowledgment.
- **Semantics:** Return persisted records and explicit failures through the storage operations below.
- **Guarantees:** Preserve participant isolation, committed writes, message ordering, and the first delivery timestamp.

## Records

Use the following persisted fields.

| Table | Field | Contract |
|---|---|---|
| `users` | `id` | Generated positive integer primary key. |
| `users` | `login` | Unique, non-null login name. |
| `messages` | `id` | Generated positive integer primary key used for display order. |
| `messages` | `sender_id` | Non-null foreign key to `users.id`. |
| `messages` | `recipient_id` | Non-null foreign key to `users.id`, different from `sender_id`. |
| `messages` | `text` | Non-null text satisfying [message validation](api.md#validation-and-errors). |
| `messages` | `created_at` | Non-null server-generated timestamp with time zone. |
| `messages` | `delivered_at` | Nullable timestamp with time zone. |

- Store only `users` and `messages` as application tables.
- Seed `user1`, `user2`, and `user3` once when initializing an empty database.
- Preserve existing users and messages when restarting services.
- Return timestamps as timezone-aware UTC values.
- Keep message IDs unique without requiring gap-free numbering.
- Derive conversations from the sender and recipient pair without a conversation table.
- Return user records with `id` and `login` and message records with all fields defined above.

## Storage operations

Expose these operation semantics through the database-access module.

| Operation | Inputs | Outputs | Effects |
|---|---|---|---|
| `get_user` | Login name | User record or absent result | None. |
| `get_history` | Current user ID, peer ID | Latest 100 messages in either direction, ascending by ID | None. |
| `get_pending` | Current user ID, peer ID | All messages from peer to current user with null delivery timestamp, ascending by ID | None. |
| `get_delivery_updates` | Current user ID, peer ID, outgoing message IDs | Delivered records as ID/timestamp pairs, ascending by ID | None. |
| `create_message` | Sender ID, recipient ID, text | Complete saved message record | Insert one message with a null delivery timestamp. |
| `acknowledge_message` | Current user ID, message ID | Message ID and first delivery timestamp | Set the timestamp only if currently null. |

- Select the latest 100 history records before sorting the returned subset in ascending order.
- Include pending messages older than the history window without a separate limit.
- Restrict delivery lookup to messages sent by the current user to the selected peer.
- Return no update for an allowed message that remains undelivered.
- Treat an empty delivery-ID list as an empty successful lookup.
- Treat repeated delivery IDs as one lookup per distinct ID.
- Reject the entire delivery lookup if any supplied ID is absent or outside the selected outgoing conversation.
- Return `NotFound` for an unknown message or invalid delivery lookup.
- Return `Forbidden` when an existing message is acknowledged by someone other than its recipient.
- Preserve message text, participants, creation time, and ID during acknowledgment.

## Transactions and failures

Apply to every storage mutation.

- Commit a mutation before returning success.
- Roll back an unsuccessful transaction before releasing its connection.
- Record the first acknowledgment atomically so concurrent acknowledgments return the same timestamp.
- Preserve successful earlier transactions when a later operation fails.
- Return `StorageUnavailable` for database connection or execution failures instead of fabricating results.
- Permit an uncertain outcome when the connection fails during commit, as covered by [send retry semantics](api.md#sending-and-acknowledgment).
- Leave state unchanged when rejecting invalid input, missing records, or forbidden acknowledgment.

## Examples

| Interaction | Observable outcome |
|---|---|
| Retrieve user1/user2 history after user3 sends to user1 | The user3 message is excluded. |
| Retrieve history containing 120 messages | The newest 100 are returned in ascending ID order. |
| Retrieve 150 undelivered messages from user2 to user1 | All 150 are returned as pending. |
| Acknowledge one message twice or concurrently | Both successful responses contain the same delivery timestamp. |
| Restart Postgres without deleting its volume | Existing messages and delivery timestamps remain available. |
