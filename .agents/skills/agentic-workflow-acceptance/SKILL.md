---
name: agentic-workflow-acceptance
description: Turn an interactive planning discussion into an acceptance specification for approval before implementation.
disable-model-invocation: true
---

# Acceptance specification

- Context: when explicitly invoked, read [workflow entry points](../../../agentic-workflow/AGENTS.md) and follow [Planner](../../../agentic-workflow/roles/PLANNER.md) for document authoring.
- Inputs: interactive planning discussion, agreed requirements, constraints, boundaries, failure behavior and non-goals.
- Effects:
  - Extract source-linked criteria with stable IDs, observable outcomes and concrete checks under [Checks](../../../agentic-workflow/policies/CHECKS.md).
  - Keep design choices open unless explicitly required.
  - Surface material conflicts.
  - Apply [source authority](../../../agentic-workflow/policies/BUNDLE.md) to approvals and implementation authorization.
  - Present complete plan/acceptance drafts when approval is needed.
  - Preserve explicitly approved text.
  - Use the [plan](../../../agentic-workflow/templates/plan.md) and [acceptance](../../../agentic-workflow/templates/acceptance.md) templates.
  - Save and recover originals under [Records](../../../agentic-workflow/policies/RECORDS.md), including its Plan-mode rules.
- Outputs: complete plan/acceptance drafts or saved approved documents, as authorized.
- Next: route authorized app execution to [Supervisor](../../../agentic-workflow/roles/SUPERVISOR.md).

## Guidelines

Apply when choosing this skill for acceptance authoring.

- Treat this skill as optional for the [lightweight execution workflow](../../../agentic-workflow/roles/IMPLEMENTER.md).
