---
name: capability-gap-router
description: Detect and route capability gaps when a task appears to need a specialized workflow but no suitable local skill is clearly available. Use when current skills do not match well, when a task feels underpowered by generic execution, or when the agent should explicitly decide whether to compose existing skills, search external sources, or create a new in-house skill.
---

# Capability Gap Router

Use `../self-cognition-orchestrator/references/monitoring-and-retrofit-framework.md` as the shared monitoring standard when applying this skill's monitoring, backstop, and retrofit logic.

When a task needs specialized capability and no good skill match is obvious, do not silently skip the gap.

## Purpose

Turn missing-skill situations into an explicit decision point.

Do not merely label the gap. Also decide how the gap will be monitored, how a wrong routing choice will be detected, and how the lesson will propagate into future skill matching.

## When to trigger

Trigger when any of these are true:

- no local skill is a clear match
- existing skills only partially cover the task
- the workflow feels repeated enough that a skill would help
- the task has fragile or domain-specific steps that generic execution may handle poorly

## Output of this skill

Always classify the gap and choose one route:

1. **compose existing skills**
2. **search external skill sources**
3. **create a new in-house skill**
4. **continue without a skill** if the overhead is not justified

## Decision process

### Step 1: Define the missing capability

State clearly:
- what the task needs
- what is missing
- why current local skills are insufficient

### Step 2: Check whether existing skills can be composed

Look for adjacent skills that can be combined.

Prefer composition when:
- the missing part is small
- the workflow is still reliable with existing pieces
- no repeated long-term gap exists

### Step 3: Decide whether external search is worth it

Search externally when:
- the workflow looks like a common public pattern
- there may already be a mature skill/tool for it
- building locally from scratch would waste time

### Step 4: Decide whether in-house creation is better

Create a new local skill when:
- the task is likely to repeat
- the workflow is specific to this environment or user
- external options are weak, unsafe, or niche-misaligned
- the missing capability should become part of the internal system

## Monitoring and remediation model

For each routed gap, define:

- **primary routing signal** — why this route seems right now
- **backstop signal** — what later evidence would reveal the route was wrong or incomplete
- **gap-severity level** — minor, meaningful, or structural
- **retrofit target** — whether the fix belongs in one skill, many skills, or shared runtime policy

Recommended monitoring patterns:

- **composition check** — verify the composed skills actually cover the missing step
- **discovery check** — verify external search is producing better capability, not just more noise
- **creation check** — verify the new in-house skill would truly recur and save effort
- **no-skill backstop** — verify direct execution did not quietly struggle because a skill should have existed

If the route later proves weak, trigger:

- `safe-learning-log` for durable gap notes
- `runtime-evolution-loop` when the mismatch suggests broader routing policy changes
- `skill-discovery-or-create-loop` when the gap is confirmed and should be actively resolved

## Relationship to other skills

- use `self-cognition-orchestrator` before this skill for high-level interpretation
- use `skill-discovery-or-create-loop` if the decision is search-or-create
- use `skill-creator` when the chosen route is local creation
- use `safe-learning-log` to record recurring capability gaps
