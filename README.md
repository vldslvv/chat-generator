# Chat

A local chat server with interoperable Python and Rust terminal clients, built
from a shared spec using a reusable agentic harness.

## Deliverables

| Item | Where to find it |
|---|---|
| Agentic harness | [agentic-workflow/](agentic-workflow/README.md): reusable roles, task coordination, independent review, validation and execution records; core behavior in [WORKFLOW.md](agentic-workflow/WORKFLOW.md). |
| Agent setup | [AGENTS.md](AGENTS.md). |
| Authoritative spec | [specs/spec_chat/](specs/spec_chat/project.md): [task order](specs/spec_chat/task_order.md), shared [WebSocket](specs/spec_chat/contracts/websocket.md), [CLI](specs/spec_chat/contracts/cli.md) and [launch](specs/spec_chat/contracts/launch.md) contracts. Resolve behavior questions here. |
| Generator | The harness executed by a coding agent; see regeneration below. |
| Generated clients | [Python](apps/chat/python-client/) and [Rust](apps/chat/rust-client/), committed with source, tests, dependencies and Dockerfiles. |
| Server | [apps/chat/api/](apps/chat/api/README.md), regenerated along with the clients. |
| Design and next steps | [DESIGN.md](DESIGN.md) and [FUTURE.md](FUTURE.md). |

The harness is separate from application requirements: extend the spec's contracts,
tasks and verification scenarios to add features, then use the same Supervisor
workflow to reconcile the implementation.

## Regenerate the application

The regeneration boundary is **all of `apps/`**, including the server, both
clients, application tests and launch configuration. Keep the rest of the
repository as generation inputs and supporting tools.

1. Use a working copy of the repository and delete `apps/`.
2. Open a fresh Codex session at the repository root with shell access and worker
   support, then submit this prompt:

   ```text
   Implement specs/spec_chat
   ```

3. Follow the run from another terminal using the implementation record path
   reported by the agent:

   ```sh
   make trace IMPL=.agentic-workflow/records/<NNN_name>
   ```

4. Follow the [application setup guide](apps/chat/README.md) to run the server
   and clients, then run the checks below.

Generation uses the agent's implementation and review loop, rather than a template
compiler; regenerated source may differ while satisfying the same contracts.

## Run and verify

Install Python 3.12+, `uv`, Cargo and `make`. From the repository root:

```sh
make test-offline-delivery
```

This installs dependencies, builds the Rust client and checks offline queueing and
reconnection through a real server with both client language assignments.
The [verification spec](specs/spec_chat/verification.md) defines broader protocol,
storage, failure and responsiveness checks; the [application README](apps/chat/README.md)
provides setup and test commands.

For the visual Alice/Bob walkthrough, also install `tmux` and run from a terminal
outside tmux:

```sh
make demo-offline-delivery
```

The demo opens Server, Alice, Bob and Walkthrough panes, advances every five
seconds and exits with **q**. The [external runner guide](tools/offline_delivery/README.md)
describes checks and launch configuration for regenerated implementations.

## Authorship and history

- **Agent-written:** application code, tests, configuration and documentation;
  `Makefile`, `AGENTS.md`, this README and other files except those below.
- **Agent-written with minimal human edits:** `specs/spec_chat/` and
  `agentic-workflow/`, except `policies/GUIDELINES.md`.
- **Human-written:** `DESIGN.md`, `FUTURE.md` and most of
  `agentic-workflow/policies/GUIDELINES.md`.

For archive delivery, include the repository's `.git/` directory so reviewers can
inspect the incremental work with `git log --oneline --all`; a source-only archive
omits that history.
