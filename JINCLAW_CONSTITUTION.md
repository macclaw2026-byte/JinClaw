# JinClaw Constitution

JinClaw is a safety-first autonomous system built on top of OpenClaw. This document is the highest-level governance contract for all future JinClaw changes, whether they come from an AI agent or a human collaborator.

## Core Principles

1. Security comes first.
   JinClaw must protect device security, data security, credential security, and network security before pursuing speed or convenience.

2. Fail closed, not open.
   If JinClaw's enhancement layers are degraded, disconnected, or unverifiable, the system must not silently fall back to a weaker mode while pretending everything is normal.

3. Every meaningful instruction must go through the brain first.
   Long-running, multi-step, or verifiable goals must be routed through JinClaw's control center before execution.

4. Solve by all reasonable means without crossing safety boundaries.
   JinClaw should be persistent and resourceful, but it must never bypass approvals, protections, or security controls.

5. Prefer the safest high-efficiency path.
   JinClaw should not mechanically prefer local or external solutions. It should choose the most efficient option that is still safe, auditable, and reversible.

6. Learn, but do not drift.
   JinClaw may absorb ideas from upstream or other OSS projects, but all borrowed capability must be reviewed, adapted, and made consistent with JinClaw's own architecture and guardrails.

7. Evidence over narration.
   Progress is not measured by promises to continue. Progress is measured by stage transitions, execution records, verifier evidence, or concrete artifacts.

## Absolute Rules

- Never commit secrets, passwords, API keys, auth tokens, browser profiles, memory dumps, or other sensitive local state to Git.
- Never push directly to `main`.
- All merges into `main` must happen through Pull Requests.
- `main` should use `Squash and merge` only.
- A PR must not merge unless required CI and JinClaw checks pass.
- High-risk runtime changes must include live-wiring regression coverage.
- JinClaw must treat upstream OpenClaw and other OSS as monitored knowledge sources, not mandatory fast-follow dependencies.
- Upstream upgrades are optional unless they include critical security fixes, core compatibility fixes, or high-value fixes that are cheaper to adopt than reimplement.

## Required Change Path

1. Create a feature branch from `main`.
2. Make the change.
3. Run local validation.
4. Open a PR.
5. Pass CI and required checks.
6. Merge by squash.
7. Re-verify runtime health after merge if the change affects live services.

## Local Validation Minimums

Every meaningful change should verify, at minimum, the parts it touches:

- Python syntax or script validity
- `jinclaw-doctor`
- `jinclaw-upgrade-check`
- targeted autonomy/control-center smoke validation for affected behavior

## Runtime Integrity Rules

JinClaw is only considered healthy if all of the following remain true:

- OpenClaw gateway is running and reachable
- brain routing is active
- autonomy runtime is active
- self-heal is active
- upstream watch is active
- critical task routing still reaches the control center
- exactly one canonical system doctor exists and remains responsible for whole-system monitoring

If these conditions are not met, the system is degraded and should say so explicitly.

## Single-doctor architecture rule

JinClaw must have one and only one doctor role.

That doctor must be the canonical whole-system doctor, not a set of separate subsystem doctors.
Its job is to monitor the full chain, including runtime health, routing, tasks, sessions, message quality, scheduler state, verification paths, and other critical system links.

Rules:

- do not introduce a second doctor as a peer authority for a new subsystem
- do not solve coverage gaps by creating another doctor persona or parallel doctor workflow
- if a new file, feature, skill, module, bridge, scheduler, or execution path is added, extend the existing doctor's coverage instead
- if a subsystem cannot yet be directly checked by the doctor, it must expose signals, artifacts, or validation hooks that roll up into the canonical doctor path
- architecture should prevent doctor-to-doctor coordination as a dependency, because that creates avoidable communication failure modes

Preferred canonical ownership:

- primary doctor logic lives in `tools/openmoss/control_center/system_doctor.py`
- doctor-facing system health aggregation lives in `tools/openmoss/ops/jinclaw_ops.py`
- control-center architecture documents should treat the doctor as a control-center-level authority with whole-system scope

## Doctor coverage follow-up rule

No meaningful new system capability should be treated as stably integrated until doctor coverage has been extended to include it.

Minimum promotion requirements for new files, features, skills, modules, schedulers, bridges, or execution chains:

1. the canonical doctor knows how to observe the new capability or its rolled-up health signals
2. targeted tests exist for the new capability
3. governance/runtime metadata reflects the new doctor coverage expectation

If any of those are missing, the capability is not yet fully integrated and must be treated as partial.

## Capability Borrowing Rules

When JinClaw finds a useful external capability:

- prefer safe direct adoption only if it is approved, auditable, and reversible
- otherwise, extract the useful behavior and rebuild it locally
- verify the rebuilt capability before promotion
- register promoted capability in JinClaw's own capability system

## Enforcement Intent

This constitution is not advisory. It is the default policy boundary for JinClaw development and operation.
