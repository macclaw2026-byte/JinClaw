<!--
RULES-FIRST NOTICE:
Before modifying this file, first read:
- `JINCLAW_CONSTITUTION.md`
- `AI_OPTIMIZATION_FRAMEWORK.md`
Follow the constitution and framework:
brain-first, one-doctor, fail-closed, evidence-over-narration,
validate locally, then use the required PR workflow.
-->
# JinClaw Stability Model

This document explains how JinClaw now keeps complex tasks stable while still allowing adaptive rerouting.

## Core principle

JinClaw is no longer allowed to switch paths just because another plan scored higher.

A route change is only valid when three conditions are simultaneously true:

1. the current task still aligns with the original goal
2. the task state is internally consistent
3. the completion gate is not in a dangerous or contradictory state

If those conditions are not met, the system prefers to pause, re-plan, or recover instead of changing direction.

## The stability chain

The active stability chain now has six layers.

### 1. Doctor heartbeat

Every task in these statuses receives a heartbeat every doctor cycle:

- `running`
- `planning`
- `recovering`
- `blocked`
- `verifying`

Each heartbeat records:

- `goal_alignment`
- `stage_consistency`
- `drift_score`
- `completion_gate_status`
- `progress_evidence`

Write targets:

- per-task heartbeat file in `runtime/control_center/doctor/heartbeats/<task_id>.json`
- per-cycle summary in `runtime/control_center/doctor/heartbeats/last_cycle.json`
- task-local summary in `state.metadata.doctor_heartbeat`

### 2. Dynamic reselection guard

`mission_loop` is allowed to refresh `tool_scores` and `reselection` during live execution, but only if:

- heartbeat says goal alignment is safe
- heartbeat says stage consistency is safe
- completion gate is not blocked
- active drift is not detected

If these conditions fail, dynamic reselection is blocked and the current plan is preserved.

### 3. Transition snapshot

Whenever a live plan transition is allowed, `runtime_service` writes a transition snapshot before continuing.

This snapshot preserves:

- previous plan
- new plan
- current stage
- next action
- blockers
- guard context

Write target:

- `state.metadata.last_plan_transition_snapshot`

### 4. Rollback guard

If the newly selected plan later degrades task health, `mission_loop` can roll back to the previous plan.

Rollback signals currently include:

- goal alignment becomes `mismatch`
- stage consistency becomes invalid
- drift becomes active or near-active

Write targets:

- `state.metadata.last_plan_rollback_guard`
- `state.metadata.last_plan_rollback_snapshot`

### 5. Cooldown after rollback

After rollback, the task enters a cooldown window.

During cooldown:

- dynamic reselection is forbidden
- the task must continue on the restored plan

Write target:

- `state.metadata.plan_transition_cooldown`

Current default cooldown:

- 15 minutes

### 6. Post-cooldown stability gate

Even after cooldown expires, dynamic reselection still remains blocked until the task is stable again.

Current stability requirements:

- `goal_alignment_status` must not be `mismatch`
- `stage_consistency_status` must not be `inconsistent` or `unknown_stage`
- `completion_gate_status` must not be a hard-blocked state
- `drift_score` must be below `0.55`

This prevents plan flapping.

## Why this model exists

Without these layers, a complex task can fail in four common ways:

1. drift while trying a new path
2. state corruption during rerouting
3. repeated oscillation between two plans
4. losing the evidence needed to explain or undo a route change

The current model is designed to stop all four.

## Operational meaning

JinClaw now treats adaptive routing as a controlled maneuver, not as free improvisation.

The rule is:

- reroute only when healthy
- snapshot before reroute
- roll back if the new route degrades the mission
- cool down after rollback
- require renewed stability before another reroute

## Where to inspect the system

Key implementation files:

- `tools/openmoss/control_center/system_doctor.py`
- `tools/openmoss/control_center/mission_loop.py`
- `tools/openmoss/autonomy/runtime_service.py`

Key runtime artifacts:

- `runtime/control_center/doctor/heartbeats/last_cycle.json`
- `runtime/autonomy/tasks/<task_id>/state.json`

## Practical reading guide

If you want to understand one task's current stability state, check in this order:

1. `state.metadata.doctor_heartbeat`
2. `state.metadata.last_dynamic_reselection`
3. `state.metadata.last_plan_transition_snapshot`
4. `state.metadata.last_plan_rollback_snapshot`
5. `state.metadata.plan_transition_cooldown`

That sequence tells you:

- whether the task is healthy
- whether rerouting was attempted
- whether the route changed
- whether the route was rolled back
- whether the task is still cooling down
