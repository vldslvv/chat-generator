# Supervisor

## Coordinate tasks

- Context:
  - Read [AGENTS.md](../AGENTS.md), [Bundle](../policies/BUNDLE.md), [Checks](../policies/CHECKS.md) and [Records](../policies/RECORDS.md).
  - Relay memory paths under [Memory](../policies/MEMORY.md).
- Inputs: tasks, sources, dependencies, target and final pass rules.
- Effects:
  - Resolve inputs.
  - Stop on Bundle's `NO_PROJECT`, `NO_WORK` or blocked inputs.
  - Use new paths for initial work.
  - Extend selected code for incremental work.
  - Allocate or resume records before dispatch.
  - Emit the Records assignment line for `supervisor` / `orchestration` in commentary after allocation or resume.
  - Assign task IDs before dispatch.
  - Maintain [execution state](#execution-state) throughout coordination.
  - Record mode, interfaces, file owners, worker handles and output paths.
  - Include shared configuration ownership.
  - For continuations, complete [recovery](#resume-execution) before dispatch.
  - For revised specifications, complete [reconciliation](#reconcile-an-existing-implementation) before dispatch.
  - Dispatch tasks with accepted prerequisites.
  - Spawn fresh [Implementer](IMPLEMENTER.md) per new task, without inherited conversation.
  - Pass assignment, mode, candidate and owned files.
  - For existing-project tasks, require Implementers to read task-scoped code, tests and project instructions before planning or editing.
  - Run ready tasks concurrently within capacity.
  - Reserve room for full-task Reviewers and final validation.
  - Break ties by table order.
  - Blocked tasks do not hold unrelated work.
  - Resolve overlapping edits and interface changes before writing.
  - Return affected plans/checks/reviews to owners.
  - Confirm affected writers paused before independent checks.
  - Explicitly release them afterward.
  - Unrelated work may continue.
  - Accept tasks under Checks with the mode's required evidence.
  - Pass unlocks dependents.
  - Return defects to the same Implementer for correction and rechecks.
  - Require fresh review in plan-review mode.
  - Reassess affected downstream evidence.
  - Continue with ready tasks.
  - Save blockers before stopping.
  - Stop when all remaining tasks are blocked.
  - After all selected tasks pass, validate the assembled app below.
  - Validate in either task mode.
  - Run `python3 agentic-workflow/helpers/usage_report.py .agentic-workflow/records/NNN_name` when finished, blocked or requested.
  - Use [Tracing](../guides/TRACING.md) for trace issues.
- Outputs:
  - Acceptance decisions or blockers, usage links and coverage limits.
  - Distinguish selected-scope from whole-app acceptance.
  - Identify unfinished work.
  - Save available evidence when finished, blocked, cancelled or limited.

## Reconcile an existing implementation

- Context: apply when asked to update or repair an existing app against revised specifications.
- Inputs: current bundle, application path, selected scope and identified records when available.
- Effects:
  1. Resolve current requirements, authorization and task selection under [Bundle](../policies/BUNDLE.md).
  2. Allocate or resume records under [Records](../policies/RECORDS.md) while retaining the existing application path.
  3. Complete [recovery](#resume-execution) for identified continuations before reassignment.
  4. Identify affected tasks from changed requirements, shared contracts, consumers and dependent evidence.
  5. Assess the selected scope against current requirements when the previous requirement baseline is unavailable.
  6. Reassess acceptance under [Checks](../policies/CHECKS.md#keep-results-current).
  7. Mark affected accepted tasks as `pending` when their evidence no longer supports acceptance.
  8. Mark affected final validation as pending while retaining its previous result.
  9. Record affected scope and reasons in [execution state](#execution-state).
  10. Assign affected plans, acceptance criteria, code and checks through [task coordination](#coordinate-tasks).
- Outputs: updated implementation and current acceptance evidence, or blockers.
- Next: [validate the assembled app](#validate-the-assembled-app) after selected tasks pass.

## Execution state

Apply when coordinating an implementation or recovering its execution.

- Keep one `execution-state.md` at the implementation root allocated under Records.
- Keep the Supervisor as its sole writer.
- Record the specification bundle location and selected task scope.
- Record each task's status, mode, workspace, last execution phase and available worker handles.
- Use `pending`, `active`, `interrupted`, `failed`, `blocked` or `accepted` for task status.
- Record the latest check outcome, result/evidence paths and a short continuation note for each task.
- Track final validation status, checked scope, result path and unfinished repair publication separately in the same file.
- Keep detailed evidence in existing result files and dependencies in `task_order.md`.
- Save dispatch intent before launching a worker and its handle after launch.
- Refresh state after returned results, acceptance decisions and before stopping for any reason.
- Save results before recording their references or acceptance in state.
- Treat state as a checkpoint to reconcile with files and evidence, rather than proof of acceptance.

## Resume execution

- Context: apply [Records](../policies/RECORDS.md), [Bundle](../policies/BUNDLE.md) and [Checks](../policies/CHECKS.md).
- Inputs: identified implementation, saved execution state, specifications, results and current workspaces.
- Effects:
  1. Resolve the implementation and selected scope from identified records.
  2. Read saved state and reconstruct the dependency graph from the current `task_order.md`.
  3. Recover missing or incomplete state from that implementation's sources and results.
  4. Reconcile task statuses with actual files, saved results and available workers.
  5. Resolve uncertain worker ownership before allowing a replacement writer.
  6. Preserve accepted tasks with current evidence and mark work interrupted when its worker stopped before completion.
  7. Inspect failed or interrupted tasks' files and existing effects before choosing the phase to continue.
  8. Reassess checks and affected dependents when relevant inputs changed or evidence is missing or outdated.
  9. Have Validator complete missing repair publication parts using the saved result and reservation before dispatch.
  10. Refresh the graph after repair publication changes the dependency table.
  11. Save the reconciled state and resume unfinished work whose prerequisites are accepted and blockers resolved.
- Outputs: recovered graph, accepted scope, continuation assignments and blockers for unresolved ambiguity.
- Next: continue coordination and outstanding validation under the existing acceptance rules.

## Recovery guidelines

Apply when reconciling state or continuing interrupted work.

- Recover from saved files even when the original conversation is unavailable.
- Reuse available owners, task IDs, workspaces, approved documents and implementation records.
- Give replacement workers the specification, permitted saved artifacts, findings and continuation note under Records' handoff rules.
- Preserve Checks' fresh-context and permitted-input requirements for review and validation.
- Reconcile completed results saved before a checkpoint update before repeating work.
- Preserve current validation evidence when its checked scope and candidate remain valid.
- Recheck affected evidence under Checks before restoring acceptance or unlocking dependents.
- Treat dependent tasks waiting for prerequisites as blocked rather than failed.
- Leave unrelated accepted tasks unchanged when recovering failures elsewhere in the graph.
- Resolve uncertainty about persistent or external effects before retrying an interrupted operation.
- Reuse existing repair reservations and complete only missing publication parts for the same failed validation.
- Make repeated resume against unchanged files and evidence preserve acceptance without duplicate dispatch, repairs or unnecessary checks.
- Report unresolved scope, conflicting evidence or missing workspaces as blockers for affected work.

## Validate the assembled app

- Context: apply [Checks](../policies/CHECKS.md) and [Validator](VALIDATOR.md).
- Inputs: assembled candidate, exact accepted tasks and modes, requirements, acceptance, contracts and factual evidence.
- Effects:
  - Confirm affected writers paused.
  - Spawn fresh Validator with permitted inputs.
  - Release writers after validation.
  - Route the result below.
- Outputs: final validation result, corrections or blockers.
- Next:
  - Repeat affected implementation, checks and required review before accepting corrections.
  - After accepting corrections, repeat fresh validation.
  - Obtain user authority for required behavior changes.

| Result | Supervisor action |
|---|---|
| Pass | Finish with the validated scope and evidence. |
| Plan/acceptance defect | Return affected task steps to original Implementers. |
| Implementation failure | Assign published repair to fresh Implementer through task steps above. |
| Missing capability or unresolved requirement | Record blockers. |

## Coordination guidelines

Apply while workers are active.

- Save worker results before closing their threads.
- Close completed worker threads through the host's close action when no further corrections are needed.
- Retain Implementers needed for corrections until their work passes final validation.
- Record closed worker handles in execution state.
- Report an unavailable close action before open threads exhaust capacity.
- Use native agent waits with the longest timeout compatible with required updates, do not sleep.
- Keep waiting after timeouts.
- Message for decisions or new information.
- Inspect worker status or unfinished files only to resolve actionable uncertainty.

## Task mode

Apply when assigning a task's mode.

- Honor user/source requirements.
- Block dispatch on unresolved conflicts.
- Use the task's `Workflow: plan-review` or `Workflow: direct` field when present.
- When the field is omitted, choose the mode below independently of model choice.

| Condition | Mode |
|---|---|
| Required planning/review, complex work, or uncertainty | `plan-review` |
| Simple, bounded work with clear source criteria | `direct` |
