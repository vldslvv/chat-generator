# Design of agentic approach

The core idea is to transform the traditional agent instructions into program-like instructions in plain English, organizing the similarly to programming module rather than a set of guides.

This means that every block of ideas should be expressed once, referenced where they are needed. The agent will pick up the reference in the document while scanning for its root instructions.

The models are getting smarter and I expect them to require less and less steering, this means that in the future we may remove more instructions than we add, focusing on specifications and verifications instead.

The core workflow is expressed in [WORKFLOW.md](agentic-workflow/WORKFLOW.md).

Rest of the documents are derived from it, enriching the context and instructions.

The [workflow review guide](agentic-workflow/guides/WORKFLOW_REVIEW.md) describes how to assess alignment between WORKFLOW.md and the rest of the documents. The [Makefile](Makefile) defines `make eval-workflow` for an LLM-based review, but its `evals/workflow.py` runner is absent from this checkout.

## Specifications

Specifications are implemented as a set of tasks and DAG-like execution section.

See the [chat specification](specs/spec_chat/project.md), its [task dependency order](specs/spec_chat/task_order.md), and [verification scenarios](specs/spec_chat/verification.md).

Each task is a self-contained unit of work.

## Implementation flows

The main agent is [Supervisor](agentic-workflow/roles/SUPERVISOR.md) -- it reads the task order and spawns agents that implement individual tasks.

There are two possible flows: direct flow and plan-review flow. Direct flow uses the single agent session to implement and plan-review has two agents, one [implements](agentic-workflow/roles/IMPLEMENTER.md), another [reviews](agentic-workflow/roles/REVIEWER.md) using fresh context, iterating until acceptance is reached.

The supervisor support implementation from scratch, reconciliation against changed requirements, and new task flow against existing project.

# Chat design

The application is designed around contracts and behaviours.

There are few contracts:

- [WebSocket protocol](specs/spec_chat/contracts/websocket.md).
- [Storage behavior](specs/spec_chat/contracts/storage.md).
- [Client CLI](specs/spec_chat/contracts/cli.md).
- [Setup and launch](specs/spec_chat/contracts/launch.md).

There are two conceptual entities: api and chat

The API behavior is defined in the [API task](specs/spec_chat/tasks/01_api.md).

The clients follow [shared behavior](specs/spec_chat/tasks/shared/client.md), with language-specific requirements in the [Python](specs/spec_chat/tasks/02_python_client.md) and [Rust](specs/spec_chat/tasks/03_rust_client.md) tasks.
