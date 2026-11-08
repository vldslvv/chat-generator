<!-- agentic-workflow:start -->
# Agentic Workflow

- Before planning, changing or reviewing code, tests or tooling, read
  [Engineering guidelines](agentic-workflow/policies/GUIDELINES.md).
- For specification implementation, read
  [Workflow entry points](agentic-workflow/AGENTS.md) and act as Supervisor.
- For document authoring or workflow maintenance, read those entry points
  and act as Planner.
- Before authoring or editing project documents,
  read [Document style](agentic-workflow/policies/DOCUMENT_STYLE.md), regardless of role.
- Ordinary planning and implementation follows
  [Project memory](agentic-workflow/policies/MEMORY.md); implement ordinary work directly.
- Keep project inputs, application code, memory and execution evidence
  outside `agentic-workflow/`.
<!-- agentic-workflow:end -->

For ordinary work, apply the guidelines, run relevant checks, inspect the diff and
report results. Formal workflow artifacts and roles are optional unless requested.
Plan-only requests stop at the plan; preserve explicit approval requirements.
Workflow helpers may be changed when workflow/tooling implementation is requested.
Advice/tooling work uses requested files and relevant references without task-history
discovery. For the repository's todolist eval, read [the eval guide](evals/README.md).
