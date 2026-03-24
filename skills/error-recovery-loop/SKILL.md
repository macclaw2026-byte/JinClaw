---
name: error-recovery-loop
description: Automatically react to tool or workflow errors by investigating, retrying safely, repairing what can be repaired, and suppressing noisy intermediate failure chatter when the final state is healthy. Use when a tool call fails, an edit misses exact text, a command errors, a hook misfires, or any recoverable internal failure happens during work.
---

# Error Recovery Loop

Use `../self-cognition-orchestrator/references/monitoring-and-retrofit-framework.md` as the shared monitoring standard when applying this skill's monitoring, backstop, and retrofit logic.

When an internal tool or workflow step fails, do not stop at the first error unless the failure is clearly final or unsafe to retry.

## Purpose

Turn recoverable failures into a root-cause-oriented repair loop:

1. detect the error
2. identify what failed
3. classify whether it is recoverable
4. gather the minimum evidence needed
5. test the most reasonable safe solution path
6. verify the final state
7. reflect on what would prevent recurrence
8. only surface the issue to the user if it still matters

This includes failures in the monitoring system itself: missing hooks, hooks that fired too late, false negatives, and validation steps that never ran.

## Default rule

If an intermediate failure is repaired and the final result is healthy, do not foreground the noisy intermediate tool error. Report the final outcome instead.

## Recovery workflow

## Monitor-miss recovery policy

When a problem was not caught by the intended monitoring path, recover both layers:

1. recover the immediate task outcome if possible
2. recover the monitoring design by identifying where the hook should have lived

Check for these causes:

- hook missing entirely
- hook attached at the wrong lifecycle point
- monitor chosen was too weak for the scenario
- monitor fired but its signal was ignored
- validation existed but had no backstop

Default remediation actions:

- run a stronger verification step now
- add or recommend a compensating check
- log the miss as a durable runtime-improvement signal when it is non-trivial

### Step 1: Classify the error

Decide whether the error is:

- transient
- exact-match/edit mismatch
- permissions / file mode issue
- missing path / missing dependency
- network/source issue
- configuration issue
- logical/semantic issue
- security boundary issue
- monitoring gap / hook miss

### Step 2: Decide if safe to retry

Retry only when:

- the action is non-destructive
- a second attempt is unlikely to worsen state
- the retry can be better targeted

Examples of safe retries:
- re-read then re-edit using exact current text
- chmod then rerun a local binary
- switch to a better source page after an incomplete fetch

### Step 3: Gather evidence

Use the minimum needed:

- read current file content
- inspect logs
- inspect command output
- inspect local state

Do not guess when direct evidence is cheap to get.

### Step 4: Repair

Examples:

- edit mismatch -> re-read file and patch the exact text
- permission denied -> fix executable bit and retry
- missing path -> create required directories or correct the path
- incomplete external source -> switch to resilient-external-research flow

### Step 5: Verify

After repair, verify the final state.

Examples:

- rerun the command
- re-read the changed file
- confirm expected output exists
- confirm the tool version or result matches expectation

### Step 6: User-visible reporting

If repaired successfully:
- prefer reporting the final fixed result
- mention the transient issue only if it affected trust, timing, or outcome

If not repaired:
- explain clearly what failed
- explain what was tried
- explain the next options

## Hook behavior

Error hooks should not panic or spam.

They should:
- trigger investigation
- encourage repair
- encourage final verification
- avoid noisy chatter when the issue is already fixed

## Relationship to other skills

- use `safe-learning-log` to log recurring or durable errors
- use `continuous-execution-loop` when the failure occurs inside a long task stage
- use `resilient-external-research` when the failure is caused by weak external sources
- use `self-cognition-orchestrator` to decide whether the path itself should change after repeated failure
- use `runtime-evolution-loop` when the real fix is better hook placement, broader coverage, or a retrofit to older skills


## Anti-shallow-recovery rule

Do not confuse “got past the error” with “solved the problem.”

After a fix works, ask:

- did this solve the actual underlying issue or only this symptom?
- is the same problem likely to recur later in the run?
- should the fix become a reusable rule, hook, template, or skill update?
