# Client — shared

## Context

Define the common implementation requirements for the Python and Rust client tasks to reference.
Own terminal interaction, connection state, and client-side message handling using the [CLI contract](../../contracts/cli.md) and [WebSocket contract](../../contracts/websocket.md).

## Behavior

Apply these rules to each client implementation.

- Handle commands, connection lifecycle, remembered usernames, and status output according to the [CLI contract](../../contracts/cli.md#commands).
- Process incoming server events and heartbeats while accepting terminal input.
- Encode requests and match responses according to the [WebSocket envelope](../../contracts/websocket.md#envelope).
- Capture `client_sent_at` in UTC immediately before sending a message.
- Capture `recipient_received_at` in UTC when decoding an incoming message, display the message, then acknowledge it.
- Use the server-provided `sender_name` from [incoming message events](../../contracts/websocket.md#message_received) to identify the sender in terminal output.
- Display server acceptance and errors according to the [CLI behavior](../../contracts/cli.md#behavior).
- Follow the [terminal presentation rules](../../contracts/cli.md#terminal-presentation) for prompts, blank-line separation, incoming messages, and readable errors.
- Record the local UTC time of each received server ping for [status output](../../contracts/cli.md#status).

## State

Use the fields, generic types, and lifecycle rules in the shared [client state contract](../../contracts/cli.md#client-state).

## Design guide

Implement each responsibility as a separate module with a public interface that encapsulates its implementation.

- Isolate terminal command parsing and output formatting.
- Isolate WebSocket transport, heartbeat handling, graceful closure, and abrupt termination.
- Isolate connection and login state management.
- Isolate protocol encoding, event handling, request correlation, and acknowledgment handling.
- Keep state separate from the logic that operates on it.

## Acceptance

Apply the same observable checks to each implementation.

- Verify commands and status fields match the CLI contract, including idempotent connection commands and remembered usernames.
- Verify sends, incoming messages, acknowledgments, and status indicators match the shared contracts.
- Verify incoming messages display the sender's name, including messages sent to oneself.
- Verify command results and unsolicited events follow the terminal presentation rules without delaying incoming events.
- Verify each failure appears once on stderr with an actionable cause and available correlation ID.
- Verify disconnection leaves the CLI usable and preserves only the specified state without queues, retries, or automatic reconnection.
