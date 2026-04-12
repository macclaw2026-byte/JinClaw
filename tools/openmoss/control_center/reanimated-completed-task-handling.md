<!--
RULES-FIRST NOTICE:
Before modifying this file, first read:
- `JINCLAW_CONSTITUTION.md`
- `AI_OPTIMIZATION_FRAMEWORK.md`
Follow the constitution and framework:
brain-first, one-doctor, fail-closed, evidence-over-narration,
validate locally, then use the required PR workflow.
-->
# Reanimated Completed Task Handling

This note formalizes the control-center rule that came out of the `neosgo-lead-engine-followup-10` ghost-task investigation.

## Problem class

A task can look active long after the business work is already done when:

- workspace completion guards exist
- governance memory/writeback residue still exists
- autonomy runtime task files are gone
- doctor/supervisor logic keeps reasoning from stale waiting metadata

This is not a live blocked task. It is a reanimated or orphaned completed record.

## Canonical signal contract

Treat a task as reanimated-completed when all of these hold:

1. completion guard evidence exists in the workspace
2. governance memory or writeback history still exists
3. autonomy runtime files such as `state.json`, `contract.json`, or `events.jsonl` are missing
4. no live execution record exists
5. no fresh business-progress evidence indicates a real resumed run

## Layer ownership

- `run_liveness_verifier.py`
  - exposes missing-runtime plus completion-guard evidence
- `progress_evidence.py`
  - produces the stable non-live classification
- `mission_supervisor.py`
  - closes the task back to terminal state instead of rerunning it
- `system_doctor.py`
  - diagnoses and repairs the reanimated-completed condition
- `control_plane_builder.py`
  - surfaces reconciled status instead of stale waiting state

## Required behavior

When the reanimated-completed condition is met:

- do not treat `waiting_external` as a live wait loop
- do not replan for goal drift
- do not restart execution
- preserve the evidence trail
- prefer terminal/completed interpretation in control-plane surfaces

## Non-goals

- do not fix this by deleting governance memory first
- do not hide the symptom only at the response layer
- do not rerun the business pipeline as a substitute for runtime reconciliation
- do not special-case a single task id

## Verification cues

The repair is considered healthy when:

- completed tasks with guard evidence no longer appear as active waiting runs
- doctor stops generating drift churn for this condition
- evidence paths remain readable for audit and retrospection
