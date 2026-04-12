<!--
RULES-FIRST NOTICE:
Before modifying this file, first read:
- `JINCLAW_CONSTITUTION.md`
- `AI_OPTIMIZATION_FRAMEWORK.md`
Follow the constitution and framework:
brain-first, one-doctor, fail-closed, evidence-over-narration,
validate locally, then use the required PR workflow.
-->
# JinClaw Live Guardrails

## Core risk

The biggest operational risk is:

JinClaw appears to run, but enhancement layers are silently bypassed and the system has effectively degraded to native OpenClaw.

## Guardrails

### 1. Brain-first required

All actionable instructions must pass through JinClaw's brain-routing layer first.

### 2. No silent fallback

If:

- brain routing is inactive
- main-session enforcement is inactive
- autonomy/control-center task creation is skipped
- event bus hooks are not firing

then JinClaw should report degraded mode instead of pretending everything is healthy.

### 3. Runtime assertions

At minimum, status checks should assert:

- brain router can build a route
- main-session enforcer is active
- mission packages are being created
- task links still point at JinClaw-managed tasks
- self-heal is active
- challenge/approval/recovery chain remains reachable

### 4. Upgrade assertions

After any upstream adoption:

- run upgrade monitoring
- run regression checks
- confirm JinClaw mode is still active
- confirm no silent reversion to upstream-only behavior

### 5. Browser tab budget

For any JinClaw or OpenClaw browser automation path:

- never allow uncontrolled tab growth
- keep the active browser budget at 3 tabs or fewer per task/session
- prefer reusing the current working tab before opening a new one
- close finished, duplicate, or stale tabs before opening more
- if a task needs stricter discipline than the global budget, that stricter rule must be declared explicitly at the task layer

### 6. Stability-first browser automation

For any JinClaw or OpenClaw browser automation path that touches a live third-party site:

- stability outranks throughput by default
- if the target site shows degradation signals such as robot checks, repeated "Something went wrong" pages, or abnormal empty-result pages, stop the active batch instead of forcing progress
- when degradation is detected, reduce concurrency, cool down, and recover a clean browser session before resuming
- do not continue a run just to maximize coverage if the current page quality is already compromised
- task-level workflows may be stricter than the global browser budget and should prefer one working page when site stability is at risk
- if repeated browser recovery attempts still fail on the same live-site step, stop retrying the same browser-only tactic and switch to a different technical path such as direct HTTP collection, a verified API route, or a hybrid collector when one exists
