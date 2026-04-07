# data-followup-4 — Plan Stage

## Goal anchor
Continue the existing product-selection / Amazon premium wholesale workflow until completion or until a real blocker/decision point appears, while preserving local security boundaries and avoiding unnecessary user-facing chatter.

## Safe plan options considered

### Plan A — Local passive verification only
- Re-check the live maintenance loop, artifacts, and state files.
- Update task/memory checkpoints.
- Do not modify running code or network behavior.
- Best when the system is already healthy and the current stage is supervision rather than repair.

### Plan B — Local intervention / repair
- Inspect scripts and restart or patch the maintenance loop if liveness, freshness, or quality checks fail.
- Use only local files and host tools.
- Best when evidence shows dead PID, stale artifacts, failed quality gate, or fallback input mode.

### Plan C — External/public research fallback
- Use public reads only if local evidence becomes insufficient to diagnose a degraded extractor.
- Best when local logs show persistent anti-bot changes or parser breakage that cannot be understood from existing artifacts.

## Selected plan
**Plan A — Local passive verification only**

## Why this is best right now
- Current evidence shows the wrapper is alive and artifacts are refreshing on the expected cadence.
- Quality gate is passing, input remains `raw_input`, and no blocker threatens the report window.
- Any intervention now would add avoidable risk right before the nightly report window.
- This stays fully inside local security boundaries and matches the selected top-level `local_first` strategy.

## Decision rule for escalation
Switch from Plan A to Plan B only if one of the following appears:
- PID dies or pid file no longer points to a live wrapper process
- raw/output/state/log mtimes stop advancing beyond the normal cadence window
- quality gate fails
- input mode falls back away from `raw_input`
- restore-last-good / repeated failure signals appear near report time

Switch from Plan B to Plan C only if:
- local script/log analysis cannot explain or repair a persistent degradation, and
- only public, non-authenticated reads are needed to validate an Amazon page-behavior change

## Verification checkpoints for this stage
- verify_goal: selected path still advances the user goal without unnecessary interruption
- verify_security_boundary: chosen path remains local-first and non-destructive
- verify_output_schema: checkpoint written to a task file in the workspace
