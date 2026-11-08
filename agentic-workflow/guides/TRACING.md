# Tracing workflows

## Enable OpenCode capture

- Context: use OpenCode 2.2.6 for workflow execution.
- Inputs: the installed CLI and its native `OPENCODE_SESSION_ID` environment variable.
- Effects:
  1. Allocate or resolve records from the agent's shell.
  2. Start live capture below and keep it running through completion.
- Outputs: selected native turns and their observed subagent dispatches.
- Next: inspect capture diagnostics and the generated reports.

No plugin is required. The helpers invoke `opencode session export SESSION_ID`
using `PATH`, or the standard `~/.opencode/bin/opencode` installation.
The V1 plugin previously provided here must be removed from
`.opencode/plugins/agentic-workflow.js` when updating an existing installation.

Allocation and resolution select the current turn using native idle boundaries;
steered prompts before an idle marker remain in that turn. Refresh follows
subagent calls with matching parent identities and unambiguous prompt timing.
Later turns require `records.py resolve` to join the implementation's scope.
Sessions are never selected by working directory or recency.

OpenCode exports only settled assistant messages, so running tools and model
steps appear after settlement. Keep capture running until the final idle marker
is saved; an unfinished-turn diagnostic means completion has not been observed.
Canonical captures use `native/<session-id>/<first-user-message-id>.json`.
Keep manual exports at other paths under `native/` so they remain unchanged.
Missing CLI access or ambiguous dispatches produce coverage diagnostics while
preserving saved evidence. Existing V1 saved exports remain readable; live
capture targets V2. The checked release and native contracts are
[2.2.6](https://github.com/anomalyco/opencode/releases/tag/v2.2.6),
[agent shell identity](https://github.com/anomalyco/opencode/blob/v2.2.6/packages/core/src/tool/plugin/shell.ts),
[message schema](https://github.com/anomalyco/opencode/blob/v2.2.6/packages/schema/src/session-message.ts),
and [token accounting](https://github.com/anomalyco/opencode/blob/v2.2.6/packages/schema/src/token-usage.ts).

## Capture live work

- Context: apply [Records](../policies/RECORDS.md) when starting or resuming execution.
- Inputs: allocated implementation path and available native host storage, with [OpenCode capture](#enable-opencode-capture) configured when applicable.
- Effects:
  1. Run `python3 agentic-workflow/helpers/trace_view.py IMPLEMENTATION --interval 5`.
  2. Keep the process running during execution.
- Outputs: captured native turns, refreshed reports and a local dashboard.
- Next: inspect progress or report final usage before stopping capture with `Ctrl+C`.

## Import saved traces

- Context: use when analyzing saved Codex records or OpenCode exports.
- Inputs: implementation path and native records for the intended work.
- Effects:
  - Copy selected Codex records with their metadata into `IMPLEMENTATION/native/`.
  - For OpenCode, save `opencode session export SESSION_ID` JSON under `IMPLEMENTATION/native/`.
  - Include only intended turns, excluding unrelated work and inherited fork history.
  - Preserve original records when preparing imports.
- Outputs: saved native evidence under the implementation root.
- Next: [generate usage reports](#report-usage) or [open the viewer](#inspect-traces).

## Inspect traces

- Context: use when inspecting execution, recorded content or timing.
- Inputs: implementation path with captured or imported traces.
- Effects:
  1. Open the running dashboard or launch `python3 agentic-workflow/helpers/trace_view.py IMPLEMENTATION`.
  2. Open the printed URL if the browser does not launch.
  3. Use **Group by** and search to find relevant tasks, agents or tools.
  4. Inspect **Recorded content** for messages and tool activity.
  5. Use **Open timeline in Perfetto** when timing details are needed.
- Outputs: execution observations and identified evidence gaps.
- Unfinished agent bars indicate an observed start without an observed end, including interrupted captures, and do not establish process liveness or a measured duration.
- Parallel Perfetto tracks preserve overlapping operations without asserting call nesting between tracks.
- Perfetto lists sessions by earliest recorded time, keeps each session's parallel tracks together, and places untimed sessions last.
- Model variant labels describe the host's selected variant separately from observed reasoning effort.
- Next:
  - Reopen Perfetto for updated timing snapshots.
  - [Recover assignments](#recover-assignments) when task or role attribution is missing.

## Recover assignments

- Context: apply [Records](../policies/RECORDS.md) when reports lack assignments for opaque handoffs.
- Inputs: selected session/turn IDs and saved evidence of task/role assignments.
- Effects:
  1. Verify missing assignments against saved evidence.
  2. Add verified assignments to `IMPLEMENTATION/assignment-annotations.json` using the format below.
  3. Reference existing evidence files inside the implementation.
  4. Resolve duplicate or conflicting annotations before refreshing reports.
- Outputs: annotations for missing assignments on exact selected turns.
- Next: [regenerate reports](#report-usage), leaving unsupported assignments unknown.

```json
{
  "version": 1,
  "assignments": [{
    "adapter": "codex",
    "session_id": "SESSION",
    "turn_id": "TURN",
    "task": "01_business_logic",
    "role": "implementer",
    "purpose": "Implement business logic",
    "evidence": ["runs/01_business_logic/build/result.md"]
  }]
}
```

## Report usage

- Context: apply [Records](../policies/RECORDS.md) when work finishes, is blocked or needs a usage report.
- Inputs: implementation path with saved native evidence and any assignment annotations.
- Effects:
  1. Run `python3 agentic-workflow/helpers/usage_report.py IMPLEMENTATION`.
  2. Read usage totals and coverage diagnostics.
  3. Report measured usage with missing or ambiguous evidence identified.
  4. Link permitted reports in the role's result under Records' disclosure rules.
- Outputs:
  - Usage reports: `reports/usage.json` and `reports/usage.md`.
  - Content and timing exports: `reports/events.json` and `reports/timeline.json`.
