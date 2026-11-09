# Offline delivery test and demo

These runners exercise the [offline delivery scenario](../../specs/spec_chat/verification.md#offline-delivery)
through the [CLI contract](../../specs/spec_chat/contracts/cli.md).
The scenario, process adapters and locked test environment live here so deleting
`apps/` preserves them. Real server and client executables are still required;
this directory does not contain a replacement chat implementation.

## Inputs

Use Python 3.12 or later and `uv` for the headless test, plus `tmux` and an
interactive terminal for the visual demo. Install Cargo when using the current
Rust client. Both Make targets run the configuration’s optional `prepare` commands
before starting the scenario, stopping if any command fails.

Set `OFFLINE_CONFIG` to a JSON file containing launch commands for `server`,
`python` and `rust`. For example, with installed executables that accept these flags:

```json
{
  "server": {"command": ["chat-server", "--port", "{port}"]},
  "python": {"command": ["chat-python", "--url", "{url}"]},
  "rust": {"command": ["chat-rust", "--url", "{url}"]}
}
```

Each entry may supply a `cwd`, resolved relative to the configuration file;
the default is that file's directory. Commands are argument arrays executed
without a shell. `{port}` is a fresh localhost port and `{url}` is
`ws://127.0.0.1:{port}/ws`. Use a wrapper executable if an implementation needs
different startup options or a different WebSocket path. The server must listen
on the supplied port, and clients must implement the linked CLI contract.

The Make targets default to `apps/chat/offline-delivery.json` for the current
implementation. Its preparation runs `uv sync --frozen` for both Python projects
and `cargo build --locked` for the Rust client automatically. When replacing or
deleting `apps/`, supply a configuration
for the replacement executables, stored outside `apps/`:

```sh
make test-offline-delivery OFFLINE_CONFIG=/path/to/commands.json
make demo-offline-delivery OFFLINE_CONFIG=/path/to/commands.json
```

An optional top-level `prepare` array contains command entries with the same
`command` and `cwd` fields. Commands run sequentially once per Make invocation,
without port or URL substitution. Omit it for already prepared executables.

## Effects

The headless test runs Alice in Python and Bob in Rust, then swaps their languages
with a fresh server. The demo uses Python Alice and Rust Bob in labeled panes.
Both modes connect, exchange messages, disconnect, queue locally and reconnect,
checking complete CLI output and server acceptance with bounded event waits.
They do not import application modules or inspect storage.

Launch the demo outside an existing tmux session. Steps run automatically with
a five-second delay before each action. Server, Alice, Bob and Walkthrough
appear together in four labeled panes in one window. The Walkthrough explains
each step as the clients act. Press q to exit.
Pacing delays do not count toward event timeouts. The completed transcript
remains visible until you exit.

## Outputs

Pytest reports both language assignments and returns nonzero on failure.
Failures include process transcripts; scenario failures also save them in a
reported temporary directory. Runners stop their processes on completion or
interruption, and the demo removes only its own session and key bindings.
