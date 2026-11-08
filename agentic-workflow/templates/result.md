# <Role/run> — result

Omit inapplicable fields. Keep forwarded independent-check inputs within [Checks](../policies/CHECKS.md). Document-only results describe document validation, not app execution.

- **Scope and candidate:** <Sources, applicable acceptance, candidate location/revision and dependencies.>
- **Role and status:** <Assigned mode; PASS, FAIL, BLOCKED or NOT_RUN; rationale and unfinished work.>
- **Model routing:** <Profile, reason, requested model/reasoning, observed settings if available, fallback or known mismatch.>
- **Checks:** <Requirement ID, command/method, working directory, exit/outcome and evidence. For manual checks, authority and inspected artifact. Separate execution from coverage and cleanup errors from primary failures.>
- **Findings and resolutions:** <Requirement, expected/observed behavior, reproduction, repair and remaining findings. Preserve useful failures.>
- **Coverage and blockers:** <Substitutes, skipped checks, gaps and required decisions.>
- **Independent checks:** <Fresh session/result paths and prior fixes. Keep review findings distinct from the Supervisor's acceptance decision.>
- **Assembled app:** <Final execution evidence or why incomplete; omit for task-only/document results.>
- **Usage:** <Derived aggregate reports when available, missing counters and coverage limits, including repairs and blocked work.>
- **Reconstruction:** <Allowed/retained inputs, target changes, actual isolation controls, exclusions/leakage and limits.>
