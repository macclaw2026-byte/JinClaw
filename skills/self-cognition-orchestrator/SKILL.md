---
name: self-cognition-orchestrator
description: Meta-reasoning and execution-orchestration skill for any incoming prompt or instruction, regardless of source. Use on every new task or prompt round: when a request comes from the user, another AI, internal workflow, tool result, or follow-up context. First interpret the instruction, resolve ambiguity from available context, consider whether a better way exists to achieve the same goal, choose the best execution plan, decide whether an existing skill should be used, search local skills first, then search external skill sources (including the find-skills logic and ClawHub), audit any candidate skill before installation, prefer safer in-house replacements when needed, create a new skill with skill-creator if no suitable safe skill exists, execute the chosen plan, and then trigger safe-learning-log to improve future performance.
---

# Self Cognition Orchestrator

Use `../self-cognition-orchestrator/references/monitoring-and-retrofit-framework.md` as the shared monitoring standard when applying this skill's monitoring, backstop, and retrofit logic.

This skill is the front-door execution policy for any incoming prompt.

## Purpose

Whenever a new instruction arrives, do not jump straight into execution.

Instead:

1. understand the instruction
2. resolve ambiguity from context
3. think about whether there is a better way to achieve the same goal
4. choose the best plan
5. decide whether a skill should be used
6. if needed, find, audit, install, replace, or create the right skill
7. execute the plan
8. trigger safe-learning-log afterward for improvement

For every prompt round, also apply `references/problem-solving-default.md` as the default problem-handling policy.
Use `references/self-improvement-safety-gate.md` before making self-improving changes without fresh approval.

For every prompt round, also establish a monitoring and evolution posture before execution:

- decide which lifecycle hooks matter for this task
- choose the right monitoring mode for each hook instead of forcing one pattern everywhere
- check whether coverage is complete enough to avoid blind spots
- define what fallback or compensating check should catch a missed signal
- ensure any miss, gap, or repeated friction can feed error recovery, learning, and runtime evolution

## Trigger policy

Use this skill on every new prompt round, regardless of source:

- user message
- another AI or agent
- internal follow-up instruction
- tool output that effectively acts as a new task
- delegated or forwarded task

## Workflow

### Step 1: Interpret the instruction

Read the prompt carefully.

Identify:

- the actual goal
- the requested output
- constraints
- safety boundaries
- whether the task is explicit or implied

If something is unclear, use available context first before asking.

Use:

- current conversation
- files in workspace
- recent task state
- obvious tool results already available

### Step 2: Resolve ambiguity

If uncertainty exists, try to narrow it by context.

Examples:

- infer whether the user wants analysis, execution, or both
- infer whether a website action requires current browser state
- infer whether a file path refers to an existing project artifact

If ambiguity remains material after checking context, ask.

### Step 3: Consider better methods and likely failure modes

Before acting, ask internally:

- is there a simpler path?
- is there a safer path?
- is there a lower-cost path?
- is there a more stable or more automatable path?
- is there a reusable path that should become a skill?
- if I want to improve myself or the runtime during this task, does that change pass the self-improvement safety gate?
- where is this task most likely to fail, stall, or become low-confidence?
- if it fails, how will I analyze and solve it instead of casually bypassing it?

The goal is not cleverness. The goal is the best practical route.

### Step 4: Form the execution plan

Choose the best plan and keep it concrete.

Plan should answer:

- what to do first
- what tools or files are needed
- whether a skill should be used
- whether a skill would improve reliability or reuse
- which hooks should fire at entry, during execution, on low confidence, on failure, and on completion
- how each important state will be monitored
- what backstop check will run if the primary monitor misses

### Step 5: Decide whether a skill is needed

Use a skill when:

- the task matches a specialized workflow
- the task is repeated or likely to repeat
- a skill would reduce error or save time
- external ecosystem skills may already solve it well

Do not force skill usage when direct execution is simpler.

If a specialized workflow seems needed but no clear local skill matches, trigger `capability-gap-router` instead of silently skipping the gap.

### Step 6: Skill lookup order

If a skill is needed, use this order:

#### 6.1 Check existing local skills first

Check:

- bundled skills
- managed/local skills
- workspace skills
- in-house replacement skills

Prefer already-approved in-house skills when available.

#### 6.2 Search external skill sources if no suitable local skill exists

Use the logic of `find-skills`:

- identify domain and task
- generate focused search terms
- search the open skill ecosystem

Also include ClawHub as a search path when relevant.

When presenting or evaluating candidates, prefer sources with readable code and clear provenance.

### Step 7: Audit before install

Before installing any third-party skill:

- run `skill-security-audit`
- follow its decision strictly

Rules:

- `A / ALLOW` -> can install
- `B / ALLOW WITH CAUTION` -> prefer safer in-house replacement first
- `C / BLOCK` -> do not install

If a candidate is `B` or `C`, prefer a safer local replacement.

### Step 8: Create a new skill if needed

If no suitable safe skill exists:

- use `skill-creator`
- create a focused in-house skill
- keep it narrow, local-first, and auditable
- avoid unnecessary hooks, persistence, secrets, or network access

If creation changes durable files or adds hooks, generate a change report.

### Step 9: Execute the chosen plan

After the best path is chosen:

- carry it through
- when friction appears, analyze the cause and pursue a reasonable solution path instead of treating the first failed method as final
- keep the user informed when changes are high-impact
- generate change reports when required by `safe-learning-log`

### Step 10: Trigger safe-learning-log

After execution, run the self-improvement judgment:

- was there a worth-learning event?
- should anything be logged?
- should a durable rule be updated?
- should a change report be written?
- should a new in-house skill be created for future reuse?

Use `safe-learning-log` to capture the improvement safely.

## Monitoring and hook coverage policy

Do not assume one universal hook pattern is enough.

For each meaningful task, decide coverage across these layers when relevant:

1. **entry hook** — validate task understanding, dependencies, constraints, and risk posture
2. **in-flight hook** — watch stage progress, state changes, and stall signals
3. **low-confidence hook** — fire when evidence is weak, ambiguous, or incomplete
4. **failure hook** — route recoverable issues into `error-recovery-loop`
5. **result-validation hook** — verify that the intended outcome actually happened
6. **delayed backstop hook** — perform a second-pass or delayed review to catch misses
7. **learning/evolution hook** — write lessons and propose durable changes

Choose the monitoring mode that fits the task:

- direct state check
- output validation
- stage checkpoint review
- time-based recheck
- cross-source verification
- error-triggered inspection
- human confirmation when impact is high

Coverage rule:

- do not proceed with a fragile plan that has obvious unmonitored failure paths unless the user accepts that risk
- if full coverage is impossible, name the blind spot and define the best compensating control
- when a miss is discovered later, treat that as a runtime-improvement signal, not just a one-off mistake

## Decision principles

Prefer, in order:

1. correct understanding
2. safer path
3. simpler path
4. reusable path
5. faster path

Do not sacrifice safety or clarity for cleverness.

## External skill policy

External skills are discovery candidates, not auto-trusted solutions.

Always:

- inspect source when possible
- audit before install
- prefer local replacements when risk is non-trivial

## Output style

When the user needs the result, present the best plan clearly and execute it.

Do not dump internal theory unless useful.

## Relationship to other skills

- use `find-skills` style logic for external discovery
- use `capability-gap-router` when no suitable skill is clearly available
- use `skill-discovery-or-create-loop` when the best next step is to search, audit, install, replace, or create a skill
- use `resilient-external-research` when outside information is needed and internal support is insufficient
- use `guarded-agent-browser-ops` when browser rendering or repeatable local browser CLI workflows are the best execution path
- use `product-selection-engine` when the task is about product research, product validation, niche selection, or platform-specific ecommerce selection logic
- use `skill-security-audit` before installation
- use `skill-creator` when a new safe in-house skill is needed
- use `safe-learning-log` after execution to improve future performance
- use `runtime-evolution-loop` after meaningful runs when the internal skill/runtime system should improve itself
- use `error-recovery-loop` when internal tool/workflow failures appear recoverable and should be repaired before surfacing them to the user
