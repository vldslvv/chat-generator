# Offline delivery test and demo plan

## Context

Plan a headless integration test and a visual demo of the [offline delivery scenario](verification.md#offline-delivery).
Run the real API, Python client, and Rust client locally, keeping all three processes alive throughout each scenario.
This plan depends on implementing the [client](contracts/cli.md#outgoing-queue) and [server](contracts/websocket.md#delivery-behavior) `flush_messages` contracts.

## Preparation

Apply these prerequisites before implementing the runners.

- Implement the active [server delivery](contracts/websocket.md#delivery-behavior) and [client queue](contracts/cli.md#outgoing-queue) contracts.
- Use the [CLI contract's queue feedback](contracts/cli.md#behavior), including `✓ Queued locally` for offline sends.
- Use the setup and launch commands from the [launch contract](contracts/launch.md), with `tmux` required only for the visual demo.

## Entry points

Add these commands to the repository's [Makefile](../../Makefile).

- `make test-offline-delivery` — run headlessly with Alice in Python and Bob in Rust, then repeat with languages swapped and a fresh server.
- `make demo-offline-delivery` — show one run with Alice in Python and Bob in Rust in three labeled terminal panes.

## Shared runner

Keep the scenario driver in Python under `tools/offline_delivery/`, outside disposable implementations.

- Configure executable argument arrays and working directories through `OFFLINE_CONFIG`, as described in the [runner guide](../../tools/offline_delivery/README.md).
- Regenerate the default launch configuration from the [launch contract](contracts/launch.md#offline-runner-configuration) without changing the durable runner.
- Keep runner dependencies independent of application environments and observe only the [CLI contract](contracts/cli.md).
- Keep one scenario definition with separate adapters for subprocess pipes and visible terminal panes.
- Start a fresh server on an available localhost port and wait for readiness before connecting clients.
- Drive clients through their normal CLI commands and observe their output while they communicate through WebSockets.
- Match complete expected output from the current step, retaining other events that arrive in either order.
- Use bounded waits for output and fail immediately on unexpected process exit or errors.
- Capture server and client output for failure diagnostics without introducing inspection endpoints or test-only application hooks.

## Scenario and checks

Use these steps in both modes, matching output produced after each command.

1. Connect Alice and Bob with `/connect alice` and `/connect bob`, waiting for each successful login.
2. Have Alice send `Hi Bob, I have something important to tell you`, checking her acceptance and Bob's displayed message.
3. Have Bob reply `What is it?`, checking his acceptance and Alice's displayed reply.
4. Disconnect Alice, confirm `/status` reports `Connection: disconnected` and `Session: none`, then send `The meeting is tomorrow` to Bob and check `✓ Queued locally`.
5. Disconnect Bob, confirm the same status, then send `Thanks for telling me` to Alice and check `✓ Queued locally`.
6. Reconnect Alice using `/connect`, wait for login and acceptance of her queued message, then disconnect her and confirm disconnected status again.
7. Reconnect Bob using `/connect`, checking login, receipt of Alice's queued message, and acceptance of his queued message in either event order.

Check that neither offline send reports acceptance before its sender reconnects.
At the end, Bob has displayed Alice's queued message while Alice remains disconnected, and both queued sends have received server acceptance.
These observations verify client actions, acceptance, and visible delivery; server acknowledgment recording and pending storage state remain outside this initial check.

## Headless execution

Apply these rules to the automated test.

- Run the scenario through pytest using stdin/stdout pipes without opening terminal windows or requiring `tmux`.
- Report each language assignment and return a nonzero exit status on failure.
- Include the failed step and captured process output in the failure report.

## Visual execution

Apply these rules to the interactive demo.

- Open a dedicated `tmux` session with labeled Server, Alice, and Bob panes running the actual processes.
- Enter CLI commands visibly in the appropriate pane and observe output using the same scenario checks.
- Show the current step in the `tmux` status line and run it automatically after a five-second delay.
- Explain each step in a separate Walkthrough window and bind `w` to switch between that window and the chat panes.
- Bind `q` to exit during playback or after completion.
- Keep event timeouts separate from the five-second pacing delays.
- Leave the completed transcript visible until the viewer exits the demo.

## Cleanup

Apply when either mode finishes, fails, or is interrupted.

- Stop the clients and server started by the runner, using bounded shutdown waits.
- Close only the demo's own `tmux` session and preserve captured diagnostics on failure.

## Implementation order

1. Implement the offline behavior and queued-message feedback in both clients and the API.
2. Extend the integration harness and add the headless Make target.
3. Add the visible terminal adapter and demo Make target using the same scenario.
4. Keep prerequisites and commands in the [runner guide](../../tools/offline_delivery/README.md).
