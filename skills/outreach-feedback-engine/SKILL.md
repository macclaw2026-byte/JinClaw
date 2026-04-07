---
name: outreach-feedback-engine
description: Reusable outreach execution, feedback collection, suppression, classification, and optimization-loop skill for B2B growth systems. Use when a project needs controlled outbound execution, multi-channel task queues, risk controls, reply handling, suppression management, reporting, and structured feedback back into the database and strategy layers.
---

# Outreach Feedback Engine

Use `../self-cognition-orchestrator/references/monitoring-and-retrofit-framework.md` as the shared monitoring standard when applying this skill's monitoring, backstop, and retrofit logic.
Use `../self-cognition-orchestrator/references/problem-solving-default.md` as the default behavior when outreach execution hits failure, suppression spikes, channel degradation, or reply ambiguity.

This skill turns strategy packages into controlled execution and learning loops.

## Purpose

Do not treat outreach as “send message, hope for best.”

Treat it as:

- queued execution
- governed risk
- controlled automation
- reply classification
- suppression discipline
- feedback loop

## Core jobs

- channel execution
- approval enforcement
- throttling and pacing
- blacklist / suppression handling
- retry control
- reply capture
- reply classification
- feedback writeback
- reporting

## Operating model

### Step 1: Intake strategy tasks

Receive structured tasks from the strategy layer.

Each task must already specify:

- target
- channel
- strategy
- CTA
- cadence
- risk level
- approval state

### Step 2: Run risk gates

Before execution, evaluate:

- suppression
- invalid history
- complaint history
- domain / channel risk
- frequency limits
- approval requirements

### Step 3: Execute by channel

Differentiate:

- manual
- semi-automated
- controlled automated

Do not assume full automation is best.

### Step 4: Capture outcomes

Track:

- attempted
- sent/submitted
- delivered where available
- failed
- bounced
- replied
- unsubscribed
- suppressed

### Step 5: Classify feedback

Classify replies and failures into operational categories.

### Step 6: Feed the loop

Write structured feedback back into:

- prospect database
- strategy layer
- suppression registry
- reporting layer

## Non-negotiable rules

- No re-send to known invalid recipients.
- No re-send after unsubscribe/do-not-contact.
- No unrestricted automation for high-risk or brand-sensitive motions.
- Always preserve execution and feedback history.

## Outputs

Primary outputs should include:

- execution logs
- suppression updates
- reply classifications
- feedback patches
- daily report
- weekly report
- anomaly report
- approval queue

## Quality and risk model

Monitor:

- invalid rate
- bounce rate
- complaint-risk signals
- unsubscribe rate
- repeated channel failure
- positive reply quality

Require human review for:

- all high-value positive replies
- all complaints / legal-sensitive replies
- partner / pricing / rebate discussions
- abnormal bounce or suppression spikes

## Recommended references

- execution and risk: `references/execution-and-risk.md`
- reply classification: `references/reply-classification.md`
- feedback loop: `references/feedback-loop.md`
- execution queue scaffold: `scripts/build_execution_queue.py`
