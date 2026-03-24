---
name: continuous-execution-loop
description: Run long or multi-stage tasks as a durable execution loop instead of a one-shot prompt. Use when work must continue across phases, each phase needs feedback, progress must not silently stop, state must persist outside chat, failures must be surfaced instead of stalling, and task completion should trigger self-cognition-orchestrator and safe-learning-log to continuously improve the workflow and any skills involved.
---

# Continuous Execution Loop

Use `../self-cognition-orchestrator/references/monitoring-and-retrofit-framework.md` as the shared monitoring standard when applying this skill's monitoring, backstop, and retrofit logic.

Run long tasks as a staged, recoverable loop.

## Purpose

Do not treat long-running or multi-stage work as a single monolithic task.

Instead, turn it into a loop with:

- stages
- explicit outputs
- acceptance checks
- persistent state
- mandatory checkpoint reporting
- exception handling
- active problem-solving instead of passive downgrade
- post-stage learning
- post-task self-improvement
- layered monitoring
- compensating checks for missed signals
- retrofittable hooks that older skills can also adopt

## When to use

Use this skill when:

- the task spans multiple phases
- each phase should produce feedback before the next one
- the work may continue for a long time
- the task must not silently stall
- the task may need repeated refinement
- the user wants reliable progress and continuity

## Core model

Every task should move through a loop:

1. understand the task
2. split into stages
3. define outputs and acceptance checks
4. execute current stage
5. checkpoint and report
6. persist state
7. continue, ask, retry, or branch
8. run learning/improvement after each stage and after final completion

## Required artifacts

Maintain external task state. Do not rely on chat memory alone.

Preferred files inside the current project/workspace:

- `tasks/current-workflow.md`
- or `tasks/<task-name>-state.md`

If task-specific structure is needed, include:

- current stage
- completed stages
- pending stages
- acceptance criteria
- blockers
- next step
- last update time

## Stage design

## Monitoring coverage model

Do not rely on a single hook style for all stages.

For each stage, intentionally choose one or more monitoring modes:

- **state monitor** — inspect task files, outputs, or observable state
- **progress monitor** — confirm the task is still advancing and not silently stalled
- **quality monitor** — validate output quality against acceptance criteria
- **exception monitor** — detect tool, workflow, or integration failures
- **backstop monitor** — run a second-pass check to catch primary-monitor misses

Coverage requirement:

- every important stage must have at least one primary monitor
- every fragile or high-impact stage must also have a backstop monitor
- if a monitor can plausibly fail silently, define what later signal should detect that miss

Retrofit rule:

- do not limit this model to newly created skills
- when improving older skills, retrofit them with stage checks, validation hooks, and backstop review where practical

For each stage define:

- **Goal**
- **Expected output**
- **Acceptance check**
- **Next-stage trigger**
- **Fallback / retry rule**
- **Primary monitor**
- **Backstop monitor**
- **Miss-detection signal**

## Mandatory checkpoint reporting

At the end of every stage, output a checkpoint report.

Use this format:

```text
Current stage:
Completed:
Not completed:
Risks / issues:
Suggested next step:
Continuation mode: auto-continue | wait-for-confirmation
```

Do not silently jump across meaningful stages.

## Silent-stop prevention rule

Never stop without explanation.

If progress cannot continue, report:

- what blocked progress
- where it blocked
- what was attempted
- what the next options are

Every stop must be an explained stop, not a silent stop.

## State persistence rule

After every meaningful stage:

- update the task state file
- record the latest status
- make the next entry point obvious for future continuation

This is required so the task can survive:

- session loss
- model switch
- restart
- long pauses

## Exception handling

### If information is missing

- use context first
- infer only when safe
- if still blocked, ask the smallest necessary question
- do not stall silently

### If a command, website, or API fails

- record the failure
- analyze the likely cause instead of blindly retrying
- attempt one or more sensible stronger solution paths when appropriate
- if still blocked, report the blocker and options
- if the failure should have been caught earlier, record the monitoring gap and trigger `runtime-evolution-loop` or `safe-learning-log` as appropriate

### If a monitor fails or misses

- do not treat monitoring failure as invisible infrastructure noise
- run the defined backstop check or delayed review
- recover the task state as well as possible
- record what signal was missed and why
- propose where a better hook should live next time

### If a stage cannot be completed

- do not pretend the stage is done
- explicitly mark it blocked or partial
- explain the continuation condition

## Continuation modes

Choose one of these after each stage:

- **auto-continue** — safe to keep going without user confirmation
- **wait-for-confirmation** — meaningful decision boundary; user should confirm

Default to `wait-for-confirmation` when:

- external or high-impact action is next
- there are multiple strategic paths
- the next phase depends on user preference

## Relationship to other skills

### Before and during execution

- use `self-cognition-orchestrator` to interpret the incoming task, decide the best path, and judge whether other skills are needed

### During capability gaps

- if a needed workflow is missing, use the existing skill pipeline:
  - local skills first
  - `capability-gap-router` if no clear local match exists
  - `skill-discovery-or-create-loop` if the best next step is to search, audit, install, replace, or create
  - `skill-security-audit` before any third-party install
  - `skill-creator` for safer in-house replacements or new workflows
- if a stage needs repeatable browser automation, prefer the built-in OpenClaw `browser` tool first, then `guarded-agent-browser-ops` when a local CLI browser workflow is a better fit

### After each stage

- trigger `safe-learning-log`
- ask whether a worth-learning event occurred
- if so, log it and write a change report when required
- review whether the stage monitors worked, missed, or created noise
- reflect on any problem that was solved so the stage does not repeat the same weakness later

### After final completion

- trigger both:
  - `self-cognition-orchestrator` for meta-review of the overall execution strategy
  - `safe-learning-log` for learnings, recurring fixes, and skill-improvement opportunities

## Improvement loop

At the end of the whole task, review:

- what slowed the task down
- where ambiguity caused friction
- whether a repeated workflow should become or improve a skill
- whether checkpoints or state structure should be improved
- whether hooks or reminders should be refined

If durable workflow changes are made, create a change report.

## Good operating style

Prefer:

- small stages
- explicit checkpoints
- durable state
- reversible decisions
- visible blockers
- continuous improvement

Avoid:

- giant one-shot execution
- hidden stalls
- relying only on chat memory
- pretending progress was made when it was not

## Minimal task-state template

```markdown
# Task State

## Task
[short task name]

## Current Stage
[stage name]

## Completed Stages
- 

## Pending Stages
- 

## Acceptance Criteria
- 

## Blockers
- 

## Next Step
- 

## Last Updated
[ISO timestamp]
```
