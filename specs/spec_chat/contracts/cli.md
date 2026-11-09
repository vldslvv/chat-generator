# CLI contract — draft

Apply this contract to both Python and Rust clients using the shared [WebSocket contract](websocket.md).

## Commands

Accept these commands in the running CLI.

- `/connect <username>` — connect and log in with the supplied name.
- `/connect` — connect and log in with the remembered name, or display `Username required: /connect <username>` if none exists.
- `/disconnect` — close the connection gracefully and keep the CLI running.
- `/drop-connection` — terminate the connection without a WebSocket close handshake and keep the CLI running.
- `/send <recipient> <text>` — send a message using the logged-in session as the sender, preserving spaces in the text.
- `/status` — display local connection and session information without contacting the server.
- `/help` — list commands and their syntax.
- `/quit` — close any connection and exit.

Apply these rules when handling commands.

- Start disconnected and accept the server WebSocket URL through `--url`.
- Make either form of `/connect` a no-op when connected or already connecting.
- Make `/disconnect` and `/drop-connection` no-ops when disconnected.
- Remember the username after successful login and retain it across disconnections until the CLI exits.
- Clear the authenticated user ID and session on disconnection while retaining the server URL and last heartbeat time.
- Require a successful login before `/send`, rejecting missing recipients or empty text locally.
- Treat text after the recipient as the message without requiring quotes.
- Reject unknown commands locally.
- Keep the CLI running after detected connection loss and require `/connect` to reconnect.
- Do not queue messages, retry sends, or reconnect automatically.

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

Apply these indicators to outgoing messages.

- Display `… Pending` after sending a request while awaiting the server's response.
- Display `✓ Accepted <message_id>` only after receiving `message_accepted`, indicating storage with recipient acknowledgment pending.
- Display `✓✓ Acknowledged <message_id>` after receiving `delivery_receipt`.
- Display `✗ Rejected: <description>` when the server explicitly rejects the send request.
- Display `? Outcome unknown` if the connection drops before the server's response arrives.
- Preserve accepted status when the connection drops before acknowledgment.
- Match send replies through `correlation_id` and delivery receipts through `message_id`.
- Append status updates as new lines instead of modifying earlier output.
