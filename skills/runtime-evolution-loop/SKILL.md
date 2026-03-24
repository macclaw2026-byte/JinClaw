---
name: runtime-evolution-loop
description: Continuously improve the in-house runtime behavior by learning from recurring capability gaps, repeated recovery patterns, skill mismatches, and long-task execution friction. Use after meaningful runs, after repeated failures, after new skill creation, or when the system should decide how to evolve its own internal skill graph and execution pathways.
---

# Runtime Evolution Loop

Use `../self-cognition-orchestrator/references/monitoring-and-retrofit-framework.md` as the shared monitoring standard when applying this skill's monitoring, backstop, and retrofit logic.

Treat the working skill/runtime system as something that should improve over time.

## Purpose

Review what the system lacked, what repeated, and what should be strengthened.

## What to look for

- recurring capability gaps
- repeated need for external research
- repeated use of the same skill combination
- recurring long-task friction
- repeated cases where the system routed around a problem instead of really solving it
- repeated recoverable tool failures
- places where a guarded bridge or shared utility would help
- skill matching relationships that should be formalized
- hooks that were missing, misplaced, too weak, or too noisy
- legacy skills that need retrofit coverage

## Outputs

## Hook placement and retrofit framework

When evolving the runtime, decide not just *that* a hook is needed, but *where* it belongs and *how* it should be verified.

Evaluate hook placement across these layers:

1. **task-entry layer** — before execution begins
2. **skill-selection layer** — when choosing or composing skills
3. **stage-transition layer** — when moving between meaningful phases
4. **tool/error layer** — when commands, edits, fetches, or automations fail
5. **result-validation layer** — when checking whether the outcome is actually correct
6. **delayed-review layer** — when a later or secondary pass should catch missed signals
7. **learning/promotion layer** — when the miss should become durable guidance

For each proposed hook, specify:

- target condition
- trigger point
- monitoring mode
- expected signal
- backstop if the signal is missed
- promotion path if the gap recurs

Retrofit rule for existing skills:

- new mechanisms should be designed for both future skills and already-active older skills
- prioritize retrofits by risk, usage frequency, and recurrence of misses
- prefer a shared policy plus small targeted edits over many divergent one-off fixes

Possible outputs include:
- improve an existing skill
- create a niche extension
- add a guarded bridge skill
- add references/templates/policies
- improve skill matching relationships
- improve recovery or learning hooks
- split a generic product-selection model into stronger platform-specific branches when repeated evidence justifies it
- add backstop validation where primary monitoring is not enough
- schedule retrofits for older skills that lack the new monitoring model

## Default review questions

1. What repeated problem showed up?
2. Which skill or runtime layer should own the fix?
3. Is this a core-skill change, niche extension, or bridge skill?
4. Should the relationship be wired into other skills?
5. Should a new hook or report policy exist?
6. Did the existing monitors actually cover the scenario, or only appear to?
7. Which older skills should inherit the fix?

## Relationship to other skills

- use `safe-learning-log` for durable notes and reports
- use `self-cognition-orchestrator` for high-level route changes
- use `continuous-execution-loop` when evolution work itself spans multiple stages
- use `skill-creator` when a new in-house skill should be created


## Deep-resolution rule

Prefer runtime changes that increase the system's ability to truly solve recurring problems, not just avoid the exact prior symptom.


## Safety gate for runtime changes

Before applying runtime-wide self-improvements without fresh approval, use `../self-cognition-orchestrator/references/self-improvement-safety-gate.md` to judge whether the change is truly helpful, low-risk, internal, auditable, and non-deceptive.
