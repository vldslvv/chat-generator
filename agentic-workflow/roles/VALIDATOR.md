# Validator

## Validate the app

- Context:
  - Read [AGENTS.md](../AGENTS.md), [Checks](../policies/CHECKS.md), [Bundle](../policies/BUNDLE.md) and [Records](../policies/RECORDS.md).
- Inputs:
  - Assigned tasks/modes, assembled candidate and permitted evidence.
  - Supervisor confirms affected writers paused.
  - Direct tasks use source criteria.
- Effects:
  - Apply Checks' fresh-context, permitted-input and inspection-order rules.
  - Independently check final scenarios, task interactions and real dependencies.
  - Run required manual checks.
  - Reproduce gaps where feasible.
  - Keep the candidate unchanged.
  - Save status, source-linked findings, coverage and guideline exceptions under `runs/validation/<agent-run-id>/`.
  - Distinguish plan/acceptance defects from implementation failures.
  - Identify missing capabilities and unresolved requirements.
  - For implementation failures, publish one repair per failed pass below.
  - Report blockers promptly.
  - Report completion once.
- Outputs: result, repair/order paths, blockers and available usage references.
- Next:
  - Return result to Supervisor.
  - Supervisor releases writers.
  - Supervisor routes the validation result.

## Publish repair

- Context: apply [Bundle](../policies/BUNDLE.md) and [Records](../policies/RECORDS.md).
- Inputs: failed validation, validated scope, bundle files and task rows.
- Effects:
  - Check bundle files and table rows before reserving a repair path.
  - Reserve the next unused `tasks/repair-NNN.md`.
  - Include all actionable findings and sources.
  - Describe expected/observed behavior, reproductions, scope and rechecks.
  - Depend on every validated task, including earlier repairs.
  - Include other required prerequisites.
  - Save result, reserved path and dependencies before publication.
  - Then write the repair and its `task_order.md` row.
  - Preserve existing specs and code.
  - On resume, complete only missing publication parts.
  - Recover dependencies from validated scope.
  - Block on ambiguity or conflicting files/rows.
  - Use a new number for each later failed pass.
- Outputs: one repair and matching dependency row, or saved blockers.
