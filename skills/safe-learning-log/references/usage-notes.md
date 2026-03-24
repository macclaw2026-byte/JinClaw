# Safe Learning Log Notes

## Why this exists

This skill is a controlled self-improvement workflow.

It intentionally allows more than a conservative logger:

- local learning capture
- selective durable improvements
- approved hooks
- approved in-house skill creation

But it adds auditability:

- change reports
- user-visible summaries
- review-before-install gates
- rollback guidance

Use the shared monitoring standard from `../../self-cognition-orchestrator/references/monitoring-and-retrofit-framework.md` when deciding whether a lesson is local, structural, or retrofit-worthy.

## Trigger model

The self-improvement mechanism should be considered triggered when any of the following happens:

1. a new task round starts
2. a command or tool fails
3. a worth-learning event occurs
4. a monitor, hook, or validator misses something important

Worth-learning events include:
- correction from the user
- non-obvious lesson
- repeated mistake
- useful workflow improvement
- stable recurring fix
- capability request worth tracking
- creation or promotion of durable guidance
- structural monitoring gap
- discovery that a different monitoring mode is needed

## Decision model

### Log only
Use when something is useful but not stable enough to become a rule.

### Promote
Use when a pattern is recurring, clearly valuable, or explicitly requested by the user.

### Hook
Use when automation is lightweight and the trigger/side effects are well understood.

### New skill
Use when the workflow is stable and repeatedly useful.

### Retrofit shared policy
Use when the miss or lesson should improve multiple skills, hooks, or templates rather than just one local workflow.

## Never skip

- third-party skill audit before install
- hook review before install/enable
- change report after high-impact changes
- user summary after high-impact changes
- backstop review when a primary monitor plausibly missed something important
