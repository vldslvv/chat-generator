# Reviewer

## Review a task

- Context:
  - Read [AGENTS.md](../AGENTS.md), [Checks](../policies/CHECKS.md) and [Records](../policies/RECORDS.md).
- Inputs:
  - Requirements, acceptance, candidate and permitted evidence.
  - Supervisor confirms review boundary paused.
- Effects:
  - Apply Checks' fresh-context, permitted-input and inspection-order rules.
  - Check implementation against acceptance, public API contracts and expected scenarios.
  - Check code and acceptance against every applicable requirement.
  - Find omissions, weakened expectations and unjustified constraints.
  - Check interactions, unintended changes and prior findings.
  - Report missing or conflicting contracts.
  - Inspect public API unit and integration tests.
  - Check scenario coverage and independent expected outcomes.
  - Assess internal tests and mock justifications under Checks.
  - Accept internal tests and mocks when they provide useful evidence.
  - Request stronger tests for concrete coverage gaps.
  - Check that each test layer covers a distinct risk.
  - Assess guideline exceptions.
  - Check for test-only production hooks.
  - Run relevant checks.
  - Reproduce findings where feasible.
  - Keep requirements and code unchanged.
  - Report candidate changes to Implementer and Supervisor.
  - Apply Checks' recheck rules.
  - Save the [result](../templates/result.md).
  - Report blockers promptly.
- Outputs:
  - Result and available usage paths.
  - Include status, source-linked findings, reproductions, verified fixes and coverage limits.
  - Identify public API contract defects and test gaps.
- Next:
  - Return findings and result to Implementer.
  - Supervisor releases paused writers.
