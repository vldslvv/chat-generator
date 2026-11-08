---
name: agentic-workflow-supervisor
description: Orchestrate single-task implementation or whole-app generation.
disable-model-invocation: true
---

# Supervisor

- Context: when explicitly invoked, read [workflow entry points](../../../agentic-workflow/AGENTS.md) and follow [Supervisor](../../../agentic-workflow/roles/SUPERVISOR.md).
- Inputs: specification selection or identified continuation; load only the role's allowed task inputs and triggered branches.
- Effects: execute the role's local procedure; for saved work, apply [Records](../../../agentic-workflow/policies/RECORDS.md).
- Outputs: implementation acceptance results or blockers.
