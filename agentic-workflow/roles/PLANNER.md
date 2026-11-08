# Planner

## Author documents

- Context:
  - Read [AGENTS.md](../AGENTS.md), [Checks](../policies/CHECKS.md), [Records](../policies/RECORDS.md) and [Memory](../policies/MEMORY.md).
- Inputs: brief, scope, sources, target paths, relevant code and accepted contracts.
- Effects:
  - Resolve inputs.
  - Write authorized documents using applicable [bundle](../policies/BUNDLE.md), [plan](../templates/plan.md) or [acceptance](../templates/acceptance.md) templates.
  - Include component contracts in acceptance under Checks.
  - Include expected test scenarios in acceptance under Checks.
  - Check source coverage, consistency, component boundaries, contract alignment, links and dependencies.
  - Check that pass rules are observable.
  - Report unresolved requirements and unavailable checks.
  - Save results, usage references and useful memory.
  - Preserve approved history during corrections.
- Outputs:
  - Document paths, document validity and generation readiness.
  - Report validity and readiness separately.
- Next:
  - Stop before execution.
  - App setup and review are not prerequisites.

## Workflow maintenance

Apply when changing workflow instructions or tooling.

- Index persistent Markdown with read conditions and relative links.
- Exclude transient execution artifacts.
- Indexes do not expand role permissions.
- Check preserved behavior and complete role reading paths.
- Run `python3 agentic-workflow/helpers/check_package.py` and relevant tests.
- Add `--integration-root .` for root/skill changes.
- See [portable checks](../README.md#requirements-and-portable-commands).
- Use [Workflow review](../guides/WORKFLOW_REVIEW.md) for requested document conformance reviews.
- Report documentation checks separately from live app experiments.
