# Model routing

Read on role entry and before launching workers.

## Routing source

- Context: choose routing on role entry and before launching workers.
- Inputs: assigned workspace and optional `<project-root>/.agentic-workflow/config/MODELS.md`.
- Effects:
  1. Find the project root from the assigned workspace.
  2. Use the project file if present, otherwise this file.
  3. Correct missing or invalid project routes without falling back to this file.
- Outputs: chosen policy path.
- Next:
  - Pass the chosen policy path in handoffs.
  - Reread the chosen policy before launching more workers.

The project file replaces this entire policy, including all tables.
The eval launcher uses the same selection rule for the Supervisor's default route.

To customize routing, copy this file to the project path and edit it there.

## Select settings

- Context: read the latest chosen policy and its tables before launching workers.
- Inputs: role, task conditions, profiles and role routes.
- Effects:
  1. Check that routes are valid and refer to defined profiles.
  2. Correct errors before choosing a route.
  3. Select the first matching route below.
  4. Request its settings through controls the host supports.
- Outputs:
  - Record the profile and reason in the role's result.
  - Record requested and observed settings separately.
  - Leave unknown observations unavailable.

## Routing guidelines

Apply when requesting or changing worker settings.

- Use host defaults for unsupported settings.
- Report fallbacks.
- Change existing worker settings only through supported controls.
- Preserve worker context and fresh-review requirements when changing settings.
- Keep current settings when the session cannot change them.
- Without session controls, use top-level routing only to guide session launches.
- Report known differences between requested and actual settings.
- Keep model names and supported reasoning values in this policy.
- Use exact model identifiers, including provider prefixes.
- Use `default` to keep the host setting.
- Keep authentication and connections in the host configuration.
- Do not add a dispatcher, adapters or a Markdown parser to apply these tables.

## Route selection

| First matching condition | Route |
|---|---|
| Two consecutive implementation repairs reproduce the same failure without new diagnostic evidence | `escalation` |
| Conflicting requirements, complex interactions, or correctness decisions involving security, data loss or compatibility | Role's demanding route |
| Local implementation, explicit behavior, established pattern, no interface or dependency changes | `small-change` |
| Otherwise | Role default |

## Profiles

| Profile | Model | Reasoning |
|---|---|---|
| coordination | `gpt-6.1-sol` | `low` |
| standard | `gpt-6.1-sol` | `medium` |
| careful | `gpt-6.1-sol` | `high` |
| small-change | `gpt-6-luna` | `high` |
| escalation | `gpt-6-astra` | `medium` |

## Role routes

| Role | Default | Demanding work |
|---|---|---|
| Supervisor | coordination | standard |
| Planner | standard | careful |
| Implementer | standard | careful |
| Reviewer | careful | escalation |
| Validator | careful | escalation |
