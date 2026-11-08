# Implementation workflow

This document defines the workflow's core behavior; role documents and policies provide the execution details.

## Author documents — when requested

- Context: [PLANNER.md](roles/PLANNER.md), authorized brief and sources.
- Inputs: requested documents, target paths, relevant code and accepted contracts.
- Effects:
  - Planner writes requested documents.
  - Planner defines component boundaries and shared interaction contracts.
  - Planner checks document validity.
  - Acceptance maps required behavior and contracts to concrete checks under [Checks](policies/CHECKS.md).
  - For workflow changes, check behavior, role reading paths and package validity.
  - Preserve approved history.
- Outputs:
  - Document paths, blockers and check gaps.
  - Report document validity and generation readiness separately.
- Next:
  - Stop before execution.
  - App setup and review are not prerequisites.
  - Implementation needs authorization under [BUNDLE.md](policies/BUNDLE.md).

## Start Supervisor

- Context:
  - [SUPERVISOR.md](roles/SUPERVISOR.md), project files, [BUNDLE.md](policies/BUNDLE.md), [RECORDS.md](policies/RECORDS.md).
  - All roles apply [AGENTS.md](AGENTS.md) and [model routing](policies/MODELS.md).
- Inputs: spec directory or identified continuation.
- Effects:
  - Resolve work.
  - Stop on `NO_PROJECT`, `NO_WORK` or blocked inputs.
  - Start initial work at new paths.
  - Extend selected code for incremental work.
  - Reconcile existing implementations against revised specifications before dispatch.
  - Allocate or resume records before dispatch.
  - Capture native turns through explicit host identities and report unavailable telemetry.
  - Supervisor records its own orchestration assignment before dispatch.
  - Assign task IDs before dispatch.
  - Supervisor maintains an execution state.
  - Record modes, interfaces, file owners, worker handles and output paths.
  - Include shared configuration ownership.
  - Choose modes independently of models.
  - Use plan-review for required planning/review, complexity or uncertainty.
  - Use direct for simple, bounded tasks with clear criteria.
  - Honor user/source requirements.
  - Block on conflicts.
  - For existing-project tasks, Supervisor requires Implementers to read task-scoped code, tests and project instructions before planning or editing.
  - Dispatch tasks with accepted prerequisites.
  - Run ready tasks concurrently within capacity.
  - Reserve Reviewer capacity.
  - Break ties by table order.
  - Blocked tasks do not hold unrelated work.
- Outputs: accepted task results or blockers.

## Reconcile an existing implementation

- Context: requested updates or repairs against revised specifications under [SUPERVISOR.md](roles/SUPERVISOR.md#reconcile-an-existing-implementation).
- Inputs: current specifications, existing implementation and available evidence.
- Effects:
  - Supervisor reopens affected tasks and coordinates implementation and checks.
  - Preserve unaffected work and applicable acceptance evidence.
  - Preserve previous results under [Records](policies/RECORDS.md).
- Outputs: updated implementation and current acceptance evidence, or blockers.
- Next: validate the assembled app and repair remaining failures through the existing validation loop.

## Spawn Implementer — per task

- Context: [IMPLEMENTER.md](roles/IMPLEMENTER.md), task sources, accepted contracts.
- Inputs: assignment, mode, candidate, owned files.
- Effects:
  - Supervisor spawns Implementer in a fresh session.
  - Use handoff rules in [RECORDS.md](policies/RECORDS.md).
  - Implementer reads inputs.
  - Implementer agrees on scope and file ownership with Supervisor before concurrent edits.
  - Supervisor resolves overlaps and interface changes before edits.
  - Return affected plans/checks/reviews to owners.
  - Plan-review: write plan and source-linked acceptance before code.
  - Plan-review: include public API contracts and test scenarios under [Checks](policies/CHECKS.md).
  - Direct: use source criteria.
  - Direct: skip plan, separate acceptance and review.
  - Keep the assigned mode.
  - Implement the task.
  - Check requirements and regressions.
  - Inspect the diff.
  - Record mock justifications for Reviewer under Checks.
  - Fix defects.
  - Rerun affected checks.
  - Preserve approved originals.
- Outputs:
  - Candidate, evidence, task result.
  - Plan-review mode adds plan and acceptance.
- Next:
  - Plan-review → review.
  - Direct → accept.

## Spawn Reviewer — plan-review mode

- Context:
  - [REVIEWER.md](roles/REVIEWER.md), requirements, acceptance, candidate, factual evidence.
  - Apply independent-check rules in [CHECKS.md](policies/CHECKS.md).
- Inputs:
  - Checked candidate and agreed review boundary.
  - Supervisor confirms affected writers paused.
- Effects:
  - Implementer launches fresh Reviewer.
  - Pass mock justifications with check evidence.
  - Reviewer checks code against acceptance criteria.
  - Reviewer checks code and acceptance against requirements.
  - Focus on public API contracts and their unit/integration tests.
  - Assess internal tests and mocks by their value under Checks.
  - Check expected scenario coverage, test quality and prior fixes.
  - Run relevant checks.
  - Reproduce findings where feasible.
  - Keep requirements and code unchanged.
  - Report candidate changes to Implementer and Supervisor.
  - Apply Checks' recheck rules.
- Outputs: result, source-linked findings, reproductions, verified fixes and coverage gaps.
- Next:
  - Implementer reports review completion.
  - Wait for Supervisor's explicit release before writing.
  - Return findings to the same Implementer.
  - Implementer fixes findings.
  - Implementer reruns affected checks.
  - Implementer repeats fresh review.
  - Pass → task result and acceptance.

## Accept task — Supervisor

- Context: [CHECKS.md](policies/CHECKS.md).
- Inputs: task result, mode, required evidence.
- Effects:
  - Pass unlocks dependents.
  - Return defects to the same Implementer for correction.
- Outputs:
  - Acceptance or findings.
  - Reassess affected downstream evidence.
- Next:
  - Ready tasks → implement.
  - All accepted → validate.
  - All remaining blocked → stop.

## Spawn Validator — Supervisor

- Context:
  - [VALIDATOR.md](roles/VALIDATOR.md), requirements, acceptance, contracts, factual evidence.
  - Apply independent-check rules in [CHECKS.md](policies/CHECKS.md).
- Inputs:
  - Assembled candidate, exact task set and modes.
  - Affected writers paused.
- Effects:
  - After all selected tasks pass, Supervisor launches fresh Validator in either mode.
  - Check final scenarios, interactions and real dependencies.
  - Run required manual checks.
  - Reproduce gaps where feasible.
  - Keep the candidate unchanged.
  - Use source criteria for direct tasks.
- Outputs:
  - Final result.
  - Repair task for implementation failures.
- Next:
  - Supervisor releases writers.
  - Supervisor routes the result below.
  - Repeat fresh validation after accepted corrections.
  - Obtain user authority for required behavior changes.

| Result | Next |
|---|---|
| Pass | Finish |
| Plan/acceptance defect | Original Implementers repeat affected task steps. |
| Implementation failure | Follow repair publication below. |
| Missing capability or unresolved requirement | Record blockers. |

## Publish repair — Validator

- Context: [VALIDATOR.md](roles/VALIDATOR.md), [BUNDLE.md](policies/BUNDLE.md), [RECORDS.md](policies/RECORDS.md).
- Inputs: failed validation, validated scope, bundle files and task rows.
- Effects:
  - Publish one repair per failed pass.
  - Include actionable findings and recheck details from the Validator procedure.
  - Reserve the next unused `tasks/repair-NNN.md` across files and rows.
  - Depend on all validated tasks, earlier repairs and other prerequisites.
  - Save result, path and dependencies before publishing the repair and `task_order.md` row.
  - Preserve existing specs and code.
- Outputs: repair and dependency row, or blockers.
- Next:
  - Supervisor assigns repair to fresh Implementer through the task steps.
  - On resume, Validator completes missing publication parts before dispatch.
  - Recover dependencies from validated scope.
  - Block on ambiguity or conflicts.
  - Use a new number for each later failed pass.

## Finish, stop or resume

- Context: [RECORDS.md](policies/RECORDS.md).
- Inputs: results, findings, current artifacts.
- Effects:
  - Save results and evidence when finished, blocked, cancelled or limited.
  - Apply each role's memory and usage rules.
  - Report blockers promptly.
  - Implementer and Validator report completion once.
  - Supervisor builds usage reports when finished, blocked or requested.
- Outputs:
  - Final/partial result, accepted scope and unfinished work.
  - Distinguish selected-scope from whole-app acceptance.
- Resume:
  - Supervisor recovers failed or interrupted runs idempotently using execution state.
  - Reuse records and available owners.
  - Reassess evidence.
  - Finish repair publication before dispatch.

## Coordination guidelines

Apply while workers are active.

- Supervisor manages worker thread cleanup and reserves capacity for independent checks.
- Use native agent waits with the longest timeout compatible with required updates.
- Keep waiting after timeouts.
- Message for decisions or new information.
- Inspect worker status or unfinished files only to resolve actionable uncertainty.
- Supervisor pauses affected writers before review and validation.
- Supervisor releases writers after review and validation.
- Unrelated work may continue.
