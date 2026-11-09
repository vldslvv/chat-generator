# CLI contract — draft

Apply this contract to both Python and Rust clients using the shared [WebSocket contract](websocket.md).

## Commands

Accept these commands in the running CLI.

- `/connect <username>` — connect and log in with the supplied name.
- `/connect` — connect and log in with the remembered name, or display `✗ Error: Username required: /connect <username>` on stderr if none exists.
- `/disconnect` — close the connection gracefully and keep the CLI running.
- `/drop-connection` — terminate the connection without a WebSocket close handshake and keep the CLI running.
- `/send <recipient> <text>` — send while logged in or queue offline for the remembered user, preserving spaces in the text.
- `/status` — display local connection and session information without contacting the server.
- `/help` — list commands and their syntax.
- `/quit` — close any connection and exit.

Apply these rules when handling commands.

- Start disconnected and accept the server WebSocket URL through `--url`.
- Make either form of `/connect` a no-op when connected or already connecting.
- Make `/disconnect` and `/drop-connection` no-ops when disconnected.
- Remember the username after successful login and retain it across disconnections until the CLI exits.
- Clear the authenticated user ID and session on disconnection while retaining the server URL and last heartbeat time.
- Require an active login or a disconnected client with a remembered username for `/send`.
- Reject missing recipients or empty text locally.
- Treat text after the recipient as the message without requiring quotes.
- Reject unknown commands locally.
- Keep the CLI running after detected connection loss and require explicit `/connect` to reconnect and resume queued sends.

## Outgoing queue

Apply these rules to messages awaiting server acceptance.

- Keep one FIFO queue for all recipients, associating each entry with its sending username.
- Append valid `/send` messages to the queue and attempt to send them in queue order when logged in.
- Call client `flush_messages` after successful login to send that user's queued messages in insertion order using individual `send` requests.
- Assign each send attempt a fresh `correlation_id` and retain it with its queue entry to match replies.
- Remove an entry only when its matching `message_accepted` arrives.
- Retain entries after disconnection or a server error without retrying them during the same connection.
- Send queued entries only when logged in as their associated username.

`flush_messages` is an internal operation, not a CLI command or WebSocket endpoint.

## Client state

Keep these fields in memory using language-neutral types.
`Optional<T>` means a value or `null`, and `Enum<...>` lists allowed values.
`Queue<T>` means an ordered FIFO collection, and `QueuedMessage` is defined below.
Use the [shared UUID and UTC timestamp types](websocket.md#shared-types) and the [user record](storage.md#users).

- `server_url: String` — configured WebSocket URL.
- `connection: Optional<ConnectionHandle>` — opaque handle to the active WebSocket, initially `null`.
- `connection_state: Enum<disconnected, connecting, connected>` — initially `disconnected`.
- `session_state: Enum<none, login_pending, logged_in>` — initially `none`.
- `login_username: Optional<String>` — requested name during connection or login, initially `null`.
- `authenticated_user: Optional<User>` — ID and name returned by `login_ok`, initially `null`.
- `remembered_username: Optional<String>` — last successfully logged-in name, initially `null`.
- `last_heartbeat_at: Optional<UtcTimestamp>` — latest received ping's local time, initially `null`.
- `outgoing_queue: Queue<QueuedMessage>` — messages awaiting acceptance, initially empty.

Keep these fields in each `QueuedMessage`.

- `sender_name: String` — logged-in or remembered username when queued.
- `recipient: String` — recipient name.
- `text: String` — original message text.
- `correlation_id: Optional<UUID>` — current send attempt's correlation ID, initially `null`.

Apply these state lifecycle rules.

- Clear `login_username` when login completes or the connection attempt fails.
- Reset the connection handle, connection state, session state, login username, and authenticated user on disconnection.
- Retain the server URL, remembered username, last heartbeat, and outgoing queue across disconnections.
- Reset queued entries' correlation IDs to `null` on disconnection.
- Keep acceptance matching within queue entries without a separate pending-request or message-status map.
- Discard all state when the CLI exits.

## Status

Display these fields for `/status` in every connection state.

- `Server`: Configured WebSocket URL.
- `Connection`: `disconnected`, `connecting`, or `connected`.
- `Session`: `none`, `login pending`, or `logged in`.
- `User`: Authenticated name, or `-` when not logged in.
- `Last heartbeat`: Local UTC time of the latest received server ping, or `never` if none has been received.

Status reflects the client's current knowledge, so network failure detection can be delayed.
The remembered username is retained separately from the authenticated user shown here.

## Behavior

Apply these rules when displaying queue actions and server events.

- Display `✓ Queued locally` when an offline `/send` enters the outgoing queue.
- Display `✓ Accepted <message_id>` only after receiving `message_accepted`, confirming server receipt and storage.
- Display `✗ Error: <description>` when the server returns `error`.
- Display incoming messages using the terminal presentation rules and acknowledge them so the server can record receipt timestamps.
- Do not display recipient acknowledgment status to the sender.
- Append completed output blocks as new lines instead of modifying them.

## Terminal presentation

Apply these rules to interactive input, command results, and unsolicited events.

- Use `> ` as the interactive command prompt.
- Separate output blocks with one blank line.
- Group related lines of a command result into one block, including all `/status` fields.
- Present unsolicited incoming messages in separate blocks without waiting for a command to complete.
- When an event arrives during input, move the active prompt and unfinished input below the event block without changing completed output.
- Preserve unfinished input and its cursor position when restoring the `> ` prompt.
- Display incoming messages as `← <sender_name>: <text>`, preserving the original message text.
- Take `sender_name` from the [message notification](websocket.md#message_received).
- Confirm successful login with `✓ Logged in as <username>`.
- Display each local rejection, server error, or operational failure once on stderr as `✗ Error: <description>`.
- Include the cause and available correlation ID in that same error output to satisfy the [project logging rule](../project.md).
- Omit exception class names from normal terminal feedback.
- Include the rejected command and a correction or `/help` hint in local command errors.
- Display server errors using their message and available correlation ID without reconstructing the originating command.
- Suggest `/connect <username>` when the user enters `/login`.
- Explain that `/connect` is needed after detected connection loss.
- Keep routine heartbeat traffic silent and expose the latest received ping through `/status`.
- Allow incoming messages and acceptance replies to appear in either server-determined order, including messages sent to oneself.

Example interaction:

```text
> /login bob
✗ Error: Unknown command '/login'. Use /connect <username>.

> /connect bob
✓ Logged in as bob

> /send alice hi
✓ Accepted 85b6bac2-eccd-4068-870b-924a3c1f3b4a

← alice: Hello Bob
```
