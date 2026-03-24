---
name: safe-learning-log
description: Capture learnings, errors, feature requests, and safe self-improvements in a local, auditable way. Use when recurring mistakes, corrections, failures, workflow improvements, or candidate skill ideas should be logged, promoted, or turned into safer in-house skills with clear change reports and rollback-friendly records.
---

# Safe Learning Log

Use `../self-cognition-orchestrator/references/monitoring-and-retrofit-framework.md` as the shared monitoring standard when applying this skill's monitoring, backstop, and retrofit logic.

Capture useful learnings and allow controlled self-improvement with audit trails.

## Purpose

This skill is a safer, auditable replacement for aggressive self-improvement skills.

It allows:

- logging to `.learnings/`
- installing approved hooks
- improving selected high-impact markdown files
- creating safer in-house skills
- promoting recurring learnings into durable guidance
- retrofitting older skills with safer monitoring, remediation, and evolution mechanisms

But every high-impact action must be reviewable and reversible.

## Core policy

The goal is not to block self-improvement. The goal is to make it:

- explicit
- logged
- reviewable
- reversible

## Allowed targets

### Local learning files

Use these freely when appropriate:

- `.learnings/LEARNINGS.md`
- `.learnings/ERRORS.md`
- `.learnings/FEATURE_REQUESTS.md`

### High-impact files

These may be improved when justified, but every change must generate a change report:

- `AGENTS.md`
- `SOUL.md`
- `TOOLS.md`
- `MEMORY.md`
- `CLAUDE.md`
- `.github/copilot-instructions.md`
- other durable instruction markdown files explicitly approved by the user

### Hook files

Hooks may be created or installed, but only after review and with a change report.

### Skills

New skills may be created when useful. Third-party skills may only be installed after passing `skill-security-audit`.

## Mandatory guardrails

### 1. Hook installation gate

Before installing, enabling, or adding any hook:

- review the hook with `skill-security-audit` logic
- assess trigger scope, side effects, file writes, network calls, and persistence
- if the hook is third-party, do not install unless audit allows it
- if the hook is in-house, keep it narrow and auditable

### 2. Third-party skill installation gate

Before installing any third-party skill:

- run `skill-security-audit`
- follow its decision strictly
- if result is `B` or `C`, prefer building a safer in-house alternative

### 3. Change report requirement

Every time this skill changes a high-impact markdown file, installs a hook, creates a skill, installs a skill, or promotes content into durable guidance, write a report file.

Default report directory:

- `.learnings/reports/`

Filename format:

- `CHANGE-YYYYMMDD-HHMMSS-short-name.md`

Each report must include:

- what changed
- why it changed
- which files were touched
- what was added/removed/updated
- whether rollback is easy
- suggested rollback path

### 4. User-visible summary requirement

After any high-impact change, tell the user plainly:

- what changed
- why
- where it was written
- how to revert if they dislike it

## Logging model

### LEARNINGS.md

Use for:

- user corrections
- non-obvious discoveries
- repeated mistakes
- better approaches
- stable process improvements

### ERRORS.md

Use for:

- command failures
- integration failures
- unexpected behavior
- reproducible operational issues

### FEATURE_REQUESTS.md

Use for:

- requested capabilities
- workflow ideas
- skill ideas
- automation ideas

## Promotion rules

## Monitoring-gap logging policy

Treat missed monitoring as first-class learning material.

Whenever a monitor, hook, or validation path misses something important, consider logging:

- what should have been detected
- which monitor failed or was absent
- what compensating check eventually caught it
- whether the fix belongs in one skill, many skills, or the shared runtime policy

Prefer promotion when the gap is structural, not merely accidental.

Retrofit policy:

- do not reserve upgraded monitoring and evolution logic for brand-new skills
- when an older skill is still in active use, extend it to participate in the same learning, recovery, and evolution loops where justified
- when many skills share the same weakness, prefer shared policy updates plus targeted retrofits

Promote a learning into a high-impact file only when at least one of these is true:

1. it has recurred multiple times
2. it clearly prevents future mistakes
3. it improves workflow quality or safety
4. the user explicitly asked for the change

When promoting:

- prefer concise rules over long diary text
- update only the most appropriate target file
- avoid duplicating the same rule across many files unless necessary
- create a change report in `.learnings/reports/`

## Trigger policy

This skill should actively participate in self-improvement at these trigger points:

### 1. Every new task / prompt round

At the start of each new task round, insert a self-improvement reminder.

Purpose:
- remind the agent to watch for durable workflow improvements
- remind the agent to produce change reports for high-impact changes
- remind the agent to run `skill-security-audit` before any third-party skill install

### 2. Command/tool failure

When commands or tools fail, automatically trigger an error-review reminder.

Purpose:
- encourage logging durable or recurring failures to `.learnings/ERRORS.md`
- encourage creation of a change report if the eventual fix changes workflow or high-impact files

### 3. Worth-learning events

Whenever a worth-learning event happens, trigger the self-improvement mechanism.

Worth-learning events include:
- user correction
- non-obvious discovery
- recurring mistake
- better workflow discovered
- stable fix for recurring error
- requested capability worth tracking
- decision to modify durable guidance or create a new in-house skill
- repeated product-selection signals that should improve `product-selection-engine` or trigger a platform-specific extension
- a monitor, hook, or validator that missed something important
- discovery that different scenarios need different monitoring modes
- a non-trivial problem was solved after root-cause analysis and the solution should reduce recurrence

Triggering the mechanism does not always mean immediately editing high-impact files. It means:
- consider logging
- consider promotion
- consider a change report
- consider whether a safer in-house skill should be created

## Hook policy

Hooks are allowed, but keep them narrow.

Good hook behavior:

- emit reminders
- detect obvious errors
- generate lightweight review prompts
- log safe local metadata

Riskier hook behavior that needs stronger justification:

- automatic edits to high-impact files
- installing dependencies
- network calls
- secret access
- background persistence

Do not create stealth hooks.
Always document hook purpose, trigger, and side effects in a change report.

## Skill creation policy

Creating in-house skills is allowed when:

- the pattern is recurring
- the solution is stable
- the skill would save time repeatedly

When creating a new in-house skill:

- keep scope narrow
- prefer local-first behavior
- avoid unnecessary hooks or network access
- create a change report describing why the skill was created

## Sensitive data rule

Do not log raw secrets, tokens, passwords, API keys, or private credentials.
If sensitive information matters, summarize it safely.

## Suggested directory structure

```text
.learnings/
  LEARNINGS.md
  ERRORS.md
  FEATURE_REQUESTS.md
  reports/
    CHANGE-YYYYMMDD-HHMMSS-short-name.md
```

## Logging format

### Learning entry

```markdown
## [LRN-YYYYMMDD-XXX] category

**Logged**: ISO-8601 timestamp
**Priority**: low | medium | high
**Status**: pending

### Summary
One-line description

### Details
Short explanation of what was learned

### Suggested Action
Optional next step

### Metadata
- Source: conversation | error | user_feedback
- Related Files: path/to/file.ext
- Tags: tag1, tag2
```

### Error entry

```markdown
## [ERR-YYYYMMDD-XXX] command_or_tool

**Logged**: ISO-8601 timestamp
**Priority**: medium | high
**Status**: pending

### Summary
Short failure description

### Error
Actual error text or safe excerpt

### Context
Short context

### Suggested Fix
Likely resolution if known
```

### Feature request entry

```markdown
## [FEAT-YYYYMMDD-XXX] capability_name

**Logged**: ISO-8601 timestamp
**Priority**: low | medium | high
**Status**: pending

### Requested Capability
What is wanted

### User Context
Why it matters

### Suggested Implementation
Optional idea
```

### Change report

```markdown
# CHANGE-YYYYMMDD-HHMMSS-short-name

## Summary
What changed

## Reason
Why the change was made

## Files Touched
- path/to/file

## Change Details
- added:
- updated:
- removed:

## Rollback
- Easy rollback: yes | no
- Suggested rollback: how to revert
```

## Operating style

Prefer:

- narrow changes
- clear reports
- reversible edits
- explicit user summaries

Avoid invisible self-modification.

## Review policy

When unsure whether to promote or automate, log first and promote later.

When repeated capability gaps, repeated skill mismatches, or repeated workflow friction appear, prefer handing those patterns to `runtime-evolution-loop` so the internal skill graph can improve over time.


## Problem-resolution promotion rule

When a meaningful problem is successfully solved, do not stop at success alone.

Consider whether to record:
- the root cause
- the successful fix
- the prevention rule
- the correct owner layer (skill, multi-skill reference, hook policy, runtime)


## Self-improvement decision gate

Before making self-improving changes under standing permission, apply `../self-cognition-orchestrator/references/self-improvement-safety-gate.md`.

If the gate fails, ask first or keep the learning at log-only level.
