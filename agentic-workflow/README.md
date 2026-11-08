# Agentic Workflow

Copy-in instructions, templates and local helpers for specification-driven
implementation. Start at [AGENTS.md](AGENTS.md) for roles and acceptance rules.

## Install

Copy the complete `agentic-workflow/` directory into an existing project root.
Merge this block into the root `AGENTS.md`, preserving existing instructions and
both markers; integration checks inspect only the marked block.

```markdown
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
```

Optionally copy these source-repository directories to the same project paths
and invoke the wrappers explicitly:

| Directory | Invocation |
|---|---|
| `.agents/skills/agentic-workflow-planner/` | `$agentic-workflow-planner` |
| `.agents/skills/agentic-workflow-supervisor/` | `$agentic-workflow-supervisor` |
| `.agents/skills/agentic-workflow-acceptance/` | `$agentic-workflow-acceptance` |

Direct role-file routing works without wrappers. Report unsupported host worker
isolation or settings under [model routing](policies/MODELS.md) and
[Checks](policies/CHECKS.md). Run the [portable checks](#requirements-and-portable-commands)
after installation.

OpenCode 2.2.6 uses [native session capture](guides/TRACING.md#enable-opencode-capture)
without a plugin; follow the update note there to remove the old V1 wrapper.

## Update the package

Replace `agentic-workflow/` in full, refresh installed wrappers, check the root
block and rerun portable checks. Preserve project-owned files and execution
history; provide no old-name aliases, record conversion or legacy assignment-tag
readers.

## Ownership

Keep customizations outside the package:

| Location | Purpose |
|---|---|
| Root `AGENTS.md` | Project instructions and entry-point block |
| `specs/` | Project specification bundles |
| Application directories | Project code and dependencies |
| `.agentic-workflow/memory/` | Project lessons under [Memory](policies/MEMORY.md) |
| `.agentic-workflow/config/MODELS.md` | Complete project routing override |
| `.agentic-workflow/records/NNN_name/` | Tasks, runs, native traces and reports |

For routing overrides, copy [MODELS.md](policies/MODELS.md) to the path above and
edit the complete policy under its [routing-source rules](policies/MODELS.md#routing-source).

Retain the package layout: root `AGENTS.md`, `WORKFLOW.md` and `README.md`, plus
`roles/`, `policies/`, `guides/`, `templates/`, `helpers/` and `tests/`.
Source-repository evals, example specs, generated apps, research, Makefile and
integration tests stay outside the copy boundary.

## Requirements and portable commands

Helpers use the Python 3.10+ standard library and require a local POSIX filesystem
with `fcntl`/`flock`. The trace viewer uses a browser; only its optional Perfetto
UI needs internet. The package includes no app stack, automated runner, Windows
support, package-manager installer or plugin publication.

### Check and operate

Run from the consuming project root. Consult command `--help`, including
`records.py allocate --help` and `records.py resolve --help`, for usage and
lifecycle instructions. Follow [Records](policies/RECORDS.md) for task conventions
and [Tracing](guides/TRACING.md) for capture, imports and reports.

```sh
python3 agentic-workflow/helpers/check_package.py
python3 agentic-workflow/helpers/check_package.py --integration-root .
python3 -m unittest discover -s agentic-workflow/tests -v
python3 agentic-workflow/helpers/records.py allocate example
python3 agentic-workflow/helpers/usage_report.py .agentic-workflow/records/001_example
python3 agentic-workflow/helpers/trace_view.py .agentic-workflow/records/001_example --interval 5
```

Use the actual path printed by allocation; each call advances the numeric prefix.
Quote paths containing spaces. Stop the viewer with `Ctrl+C`. Missing telemetry
limits reports but does not block allocation or app acceptance.

The checker validates the package and local links; `--integration-root` adds the
marked root block and installed workflow wrappers, ignoring other host
instructions and skills. Tests need no source Makefile; optional browser and
Perfetto checks skip when their tools are unavailable.

### Source-repository checks

```sh
python3 -m unittest discover -s tests -v
python3 -m unittest discover -s evals/tests -v
make trace IMPL=PATH
```

These run copy-in integration checks, eval fixtures and a viewer for an explicit
implementation, respectively.

## Example use

Ask the agent to author a specification bundle using the
[project template](templates/project.md), then request `Implement specs/example`
for execution through [Supervisor](roles/SUPERVISOR.md). Ordinary changes follow
[Guidelines](policies/GUIDELINES.md) and [Memory](policies/MEMORY.md) directly.
Preserve explicit plan-only and approval requirements.

## Distribution license

Include an owner-selected distribution license before a public release.
