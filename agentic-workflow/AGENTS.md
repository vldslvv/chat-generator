# Agentic Workflow

Read the context for your action:

| Action | Context |
|---|---|
| Implement specifications, including one task | [SUPERVISOR.md](roles/SUPERVISOR.md), enter as Supervisor |
| Update or repair an existing app against revised specifications | [Supervisor reconciliation](roles/SUPERVISOR.md#reconcile-an-existing-implementation) |
| Coordinate tasks | [SUPERVISOR.md](roles/SUPERVISOR.md) |
| Plan or edit documents/workflow | [PLANNER.md](roles/PLANNER.md) |
| Implement a task | [IMPLEMENTER.md](roles/IMPLEMENTER.md) |
| Review a task | [REVIEWER.md](roles/REVIEWER.md) |
| Validate the app | [VALIDATOR.md](roles/VALIDATOR.md) |
| Resolve project files | [BUNDLE.md](policies/BUNDLE.md) |
| Define or assess checks | [CHECKS.md](policies/CHECKS.md) |
| Hand off, save or resume work | [RECORDS.md](policies/RECORDS.md) |
| Ordinary planning/implementation | [MEMORY.md](policies/MEMORY.md) |
| Rebuild without prior implementation | [RECONSTRUCTION.md](policies/RECONSTRUCTION.md), before any role starts |
| Review workflow documents | [WORKFLOW_REVIEW.md](guides/WORKFLOW_REVIEW.md) |
| Install or check the package/optional skills | [README.md](README.md) |
| Inspect traces or usage | [TRACING.md](guides/TRACING.md) |

Every role reads [GUIDELINES.md](policies/GUIDELINES.md), resolves [MODELS.md](policies/MODELS.md#routing-source),
and applies its context documents. Follow conditional references when applicable.
Before authoring or editing project documents,
read and apply [Document style](policies/DOCUMENT_STYLE.md), regardless of role.
Keep project inputs, code, memory and execution evidence outside this package.

Templates: [project inputs](policies/BUNDLE.md), [plan](templates/plan.md),
[acceptance](templates/acceptance.md), [result](templates/result.md).
