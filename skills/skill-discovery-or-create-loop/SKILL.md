---
name: skill-discovery-or-create-loop
description: Resolve a missing capability by checking local skills first, then external discovery, then security review, then installation or safe replacement, and finally local skill creation when needed. Use after capability-gap-router decides that a skill should be found or created.
---

# Skill Discovery Or Create Loop

Use `../self-cognition-orchestrator/references/monitoring-and-retrofit-framework.md` as the shared monitoring standard when applying this skill's monitoring, backstop, and retrofit logic.

This skill resolves missing capabilities through an explicit search-or-create workflow.

## Workflow

1. check local skills first
2. search external sources if needed
3. audit any candidate before installation
4. install only if allowed by policy
5. prefer safer replacements for B/C candidates
6. create a new in-house skill if no suitable safe candidate exists
7. validate that the chosen resolution actually closed the capability gap
8. if validation fails, escalate through a stronger fallback path instead of silently accepting weak closure

## External sources

Use:
- local/workspace/bundled skills first
- find-skills style discovery logic
- ClawHub when relevant
- GitHub/public sources when needed

## Security rule

Every third-party candidate must go through `skill-security-audit`.

Decision handling:
- `ALLOW` -> install may proceed
- `ALLOW WITH CAUTION` -> prefer replacement first
- `GUARDED INSTALL` -> install only with restrictions and post-install review
- `BLOCK` -> do not install; create a safe local alternative if the function is useful

## End state

This loop should always end in one of these states:

- found and safely usable local skill
- found and safely installed external skill/tool
- safe in-house replacement created
- justified decision to proceed without creating or installing a skill

## Relationship to other skills

- use `capability-gap-router` first
- use `resilient-external-research` for external discovery support
- use `skill-security-audit` before any install
- use `skill-creator` for local creation
- use `safe-learning-log` to record durable discoveries and decisions

## Monitoring and closure policy

Treat discovery/create work as incomplete until the capability gap is actually closed.

For each run, define or infer:

- **entry check** — what exact missing capability must be resolved
- **candidate-quality check** — how to tell whether a found skill/tool is genuinely relevant
- **security gate** — whether the install/usage path remains policy-compliant
- **closure check** — whether the final skill or replacement really enables the intended task
- **backstop check** — what to do if a candidate looked good but failed in practice

Fallback pattern:

1. local match weak -> search externally
2. external candidate weak or risky -> replace locally
3. local replacement still too generic -> tighten scope and create a narrower in-house skill
4. if all paths remain weak -> record justified no-skill decision and mark the gap as still partially open

Miss-handling rule:

- if a candidate passed early filters but later fails the real task, log that as a routing/validation miss
- if this happens repeatedly, push the pattern into `runtime-evolution-loop` so matching and closure logic improve system-wide

Retrofit expectation:

- older skills discovered through this loop should also be evaluated for missing monitors, recovery hooks, and learning hooks before being considered mature
