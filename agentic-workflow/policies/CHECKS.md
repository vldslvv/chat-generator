# Checks and acceptance

Read when preparing checks, reviewing work or deciding whether it passes.

- Resolve requirements through [Bundle](BUNDLE.md).
- Apply engineering rules from [Guidelines](GUIDELINES.md).

## Prepare acceptance

Apply before coding in plan-review mode and when authoring or updating requested acceptance documents.

- Derive acceptance criteria from original requirements, excluding advisory implementation suggestions.
- Cover normal use, boundaries, failures, interactions and specified state or lifecycle guarantees.
- State component contracts in acceptance or link their authoritative definitions.
- Include inputs, outputs, errors and observable side effects in each contract.
- Link contracts to source requirements.
- Map task acceptance outcomes and contract guarantees to concrete check scenarios.
- Link shared scenarios and add only missing task-specific checks.
- State setup, action and expected outcome for each scenario.
- Choose unit or integration tests for each scenario.
- Use both test layers where they cover distinct risks.
- Keep internal design choices in the plan unless the requirements specify them.
- Correct incomplete acceptance criteria against the original requirements.
- Preserve approved history during acceptance corrections.
- Rerun checks affected by acceptance corrections.
- Repeat required independent review after acceptance corrections.

## Prepare checks

Apply before coding and when updating checks in either mode.

- Use source criteria directly for direct tasks without writing separate acceptance.
- Treat a missing requirement as a defect, even if all listed checks pass.
- Choose checks that fit the change and test observable behaviour.
- Include relevant regression tests.
- Run required manual checks.
- Run required checks against real dependencies.
- Cover test gaps through public interfaces.
- Record why mocks fit, what they replace and what remains untested in check evidence.
- Assess internal tests and mocks by the failures they can detect.
- Consider isolation, cost and realism.
- Require meaningful assertions about the code under test.
- Reject production hooks added only for tests.

## Assess results

Apply when reporting checks or accepting work.

- Use `PASS` only with passing required checks, adequate requirement coverage and no actionable findings.
- Check coverage separately from test success.
- Use `FAIL` when the work breaks a requirement or an applicable rule.
- Use `BLOCKED` for unavailable required tools or capabilities, or unresolved requirements.
- Mark skipped checks `NOT_RUN`, or `BLOCKED` when their absence prevents acceptance.
- Block acceptance with `INDEPENDENT_REVIEW_NOT_RUN` when a required fresh review has not run.
- Report substitute checks and coverage gaps without lowering the requirements.
- Save evidence using the [result template](../templates/result.md).
- For manual judgments, name the rule and the item inspected.
- Report cleanup errors separately from the failure being checked.

## Independent checks

Apply to independent review and validation.

- Start with a fresh context and no inherited conversation.
- Choose checks from original requirements and guidelines before reading acceptance or code.
- Limit inputs to requirements, applicable acceptance, candidate work, factual results, contracts, justified guideline exceptions and prior findings.
- Allow focused mock justifications as review inputs.
- Assess mock justifications independently.
- Exclude plans, implementation suggestions, conversations, project memory, design explanations and claims of correctness.
- Exclude copies of these from other files too.
- Keep the work being checked unchanged, including relevant dependencies, configuration and check inputs.
- Record its location and revision when available.
- Use existing version information.
- Do not require a new commit or lock.
- Report candidate changes during checking.
- Rerun affected independent checks in a fresh context.
- Run relevant checks yourself.
- Reproduce reported problems where feasible.
- Follow the stated setup, cleanup, pass criteria, sampling rules and thresholds.

## Keep results current

Apply while running checks and when stopping work.

- Batch reads and commands that do not depend on each other.
- Repeat successful checks only for relevant changes, failures, new concerns or required independent checks.
- Reassess affected results when requirements, guidelines, dependencies or implementation change.
- Save unfinished work and blockers when cancelled or stopped by a limit.
