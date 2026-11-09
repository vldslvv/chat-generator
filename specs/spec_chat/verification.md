# Verification

Verification is not run yet; execution is deferred until an automated WebSocket test harness exists.
The Python and Rust application clients are not required.

## Check boundaries

Apply when preparing API verification.

- Follow the shared [check policy](../../agentic-workflow/policies/CHECKS.md#prepare-checks).
- Verify WebSocket behavior through replies, notifications, and connection lifecycle.
- Verify storage invariants through the storage module's public operations.
- Verify session cleanup by successfully logging in again after disconnection.
- Verify acknowledgment timestamps through the storage module's public operations.

## Scenarios

Use these scenarios as a checklist for the [API behavior](tasks/01_api.md) and [WebSocket contract](contracts/websocket.md).

- Log in as Alice and Bob, send a message, and acknowledge it as Bob; verify acceptance and received content refer to the same stored message, with acknowledgment recorded only on the server.
- Submit invalid requests and repeat login; verify errors leave the connection open and existing state unchanged.
- Submit missing or malformed client timestamps; verify the stored values become `0`.
- Repeat an acknowledgment; verify the first acknowledgment timestamps remain unchanged.
- Withhold pong responses; verify the server closes the connection according to the heartbeat timing.
- Cause delivery to fail after storage; verify one logged attempt, a retained message, and no retry or failure notification to the sender.
- Restart the server; verify both collections are empty.

Define evidence collection and cleanup instructions when the test harness exists.
