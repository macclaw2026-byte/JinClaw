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

