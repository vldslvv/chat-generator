---
name: agentic-workflow-planner
description: Author project specifications or planning documents without executing tasks.
disable-model-invocation: true
---

# Planner

- Context: when explicitly invoked, read [workflow entry points](../../../agentic-workflow/AGENTS.md) and follow [Planner](../../../agentic-workflow/roles/PLANNER.md).
- Inputs: brief, authorized scope and source paths; load only the role's allowed task inputs and triggered branches.
- Effects: execute the role's local procedure; for saved work, apply [Records](../../../agentic-workflow/policies/RECORDS.md).
- Outputs: requested documents and document-validation results.
