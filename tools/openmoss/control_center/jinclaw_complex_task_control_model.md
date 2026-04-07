# JinClaw Complex Task Control Model

## Purpose

This model hardens JinClaw for complex delivery tasks such as:

- app / platform builds
- system integrations
- multi-stage coding missions
- productized workflows that must be tested before handoff

The goal is to prevent:

- silent drift
- fake completion
- stage skipping
- weak verification
- closure without postmortem

## What Counts As A Complex Task

A task is treated as a complex controlled mission when one or more of these are true:

- it matches a mission profile
- it looks like a multi-deliverable build
- it is a coding-heavy product/system/platform mission
- the goal implies real delivery, testing, and handoff

The orchestrator writes this into:

- `metadata.control_center.complex_task_controller`

## Core Guards

### 1. Goal Guardian

The doctor remains attached as the goal guardian until:

- stage work is complete
- verification passes
- postmortem is written

Without postmortem, completion is not final.

### 2. Stage Artifact Gate

Each key stage writes a structured artifact into:

- `state.metadata.stage_artifacts.<stage>`

Examples:

- `understand`
  - `mission_brief`
  - `scope_constraints`
  - `success_definition`
- `plan`
  - `execution_plan`
  - `module_breakdown`
  - `test_strategy`
- `execute`
  - `delivery_evidence`
  - `implementation_delta`
  - `test_signal`
- `verify`
  - `verification_report`
  - `acceptance_decision`
  - `remaining_risks`
- `learn`
  - `postmortem`
  - `reusable_rule`
  - `followup_risks`

### 3. Verify Gate

Complex tasks do not pass verify unless:

- required milestones are complete
- liveness is healthy
- conformance is healthy
- understand / plan / execute artifacts are all present and complete

### 4. Doctor Supervision

Active tasks continue to emit doctor heartbeat with:

- goal alignment
- stage consistency
- drift score
- completion gate status

## Runtime Upgrade Path

Historical tasks are upgraded in runtime so old contracts can inherit:

- complex task controller metadata
- stronger stage contracts
- stronger verify checks

## Release Logic

The intended flow is:

1. Understand
2. Plan
3. Execute
4. Verify
5. Learn
6. Postmortem
7. Final completion

Any missing artifact, failed verification, or missing postmortem keeps the task open or reopens it.

## Why This Matters

This model turns JinClaw from:

- "it appears to be making progress"

into:

- "it must produce staged evidence, pass verification, and close with a written postmortem before the mission is truly done"
