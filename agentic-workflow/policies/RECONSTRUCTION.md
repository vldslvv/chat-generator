# Reconstruction

## Rebuild from allowed inputs

- Context:
  - Read before rebuilding without access to the previous implementation.
  - Apply [Checks](CHECKS.md), [Records](RECORDS.md) and the [separation guidelines](#separation-guidelines).
  - Describe work that uses prior code as a port.
- Inputs: approved behaviour, target, assets, data and services allowed for reuse, and compatibility checks.
- Effects:
  - Define required behaviour and reusable inputs.
  - Preserve expected outcomes, thresholds and fixtures.
  - Adapt commands to the new target without weakening checks.
  - Use a new workspace.
  - Use fresh contexts for every role, including Supervisor.
  - Give each role only allowed inputs.
  - Limit exports to approved requirements, acceptance, public contracts, examples, reusable inputs and applicable workflow and engineering guidance.
  - Inspect exports for excluded material.
  - Check for excluded material through files, parent instructions, session memory, caches, remotes and the network.
  - Apply access controls for the agreed boundary when enforced isolation is required.
  - Include excluded inputs and reviewer results within the required isolation boundary.
  - Test required access controls.
  - Block required isolation when access controls are unavailable.
  - Replace any worker that read excluded material.
  - Check real dependencies that will be reused.
- Outputs:
  - Report target changes, reused inputs, rebuilt outputs, access controls, limits and results under Records.
  - State what separation was achieved.

## Separation guidelines

Apply to every role and export when rebuilding without prior code.

- Exclude prior code, build products and repository history.
- Exclude old plans, conversations and caches containing prior code.
- Exclude all project memory and copies of it.
- Reject paths or symlinks that escape the allowed directory.
- Keep credentials out of exports and logs.
- Preserve the source workspace and historical evidence.
- Allow new reconstruction plans and code only where the role permits them.
- Follow Checks for independent workers.
- Use separation by instructions unless enforced isolation is required.
- Do not claim enforced isolation from instructions and a new directory alone.
- Withdraw reconstruction claims if prior code reaches the workspace or a worker's context.
- Report requirement conformance separately from reconstruction claims, when appropriate.
- Resume only work from this reconstruction.
- Label resumed work.
- Limit conclusions to what was checked.
- Do not claim universal equivalence or guaranteed reconstruction success from finite checks.
