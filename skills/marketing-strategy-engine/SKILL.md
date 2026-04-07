---
name: marketing-strategy-engine
description: Reusable marketing strategy generation skill that converts a scored prospect database and business goal into segmented messaging, channel strategy, conversion paths, account playbooks, and follow-up logic. Use when a project needs ABM-style strategy generation, personalized positioning, multi-channel planning, and scalable but non-mechanical marketing task creation.
---

# Marketing Strategy Engine

Use `../self-cognition-orchestrator/references/monitoring-and-retrofit-framework.md` as the shared monitoring standard when applying this skill's monitoring, backstop, and retrofit logic.
Use `../self-cognition-orchestrator/references/problem-solving-default.md` as the default behavior when strategy confidence is weak, message fit is uncertain, or channel selection needs re-evaluation.

This skill turns a structured prospect database into strategy assets.

## Purpose

Do not jump from raw lead data straight into copy generation.

First determine:

- who this account really is
- what value matters most
- which channel fits best
- what conversion path is realistic

The goal is not “write many messages.”
The goal is “design the right motion for the right buyer.”

## Core jobs

- segmentation
- account/persona interpretation
- account-based positioning
- angle generation
- channel selection
- CTA design
- conversion-path design
- follow-up logic
- strategy scorecards
- task package generation for execution

## Operating model

### Step 1: Read the data asset

Consume:

- account fit
- persona
- signals
- reachability
- geography
- lifecycle
- historical feedback

### Step 2: Segment the market

Segment at multiple layers:

- account tier
- persona type
- buying context
- channel readiness
- conversion path type

### Step 3: Map value and angle

For each segment or account, define:

- primary angle
- supporting angle
- disallowed angle
- proof style
- primary CTA
- fallback CTA

### Step 4: Choose channels

Choose channel by fit, not habit.

Possible channels:

- email
- form
- LinkedIn / social
- partner/dealer application
- call / manual outreach

### Step 5: Design the conversion path

Define:

- first step
- next step
- success event
- fallback event
- stop condition

### Step 6: Create execution packages

Output should be structured enough for an execution engine, not just human-readable notes.

## Non-negotiable rules

- No fake personalization.
- No “mechanical variable swap” pretending to be account strategy.
- No channel recommendation without channel-fit evidence.
- No pricing/partner claims without approval policy.

## Outputs

Primary outputs should include:

- segment definitions
- strategy playbooks
- account strategy cards
- channel strategy packs
- conversion-path definitions
- follow-up schedules
- approval queue items
- strategy-performance hypotheses

## Quality and risk model

Monitor:

- message-fit quality
- angle-to-signal coherence
- CTA realism
- channel suitability
- conversion-path friction
- over-personalization vs under-personalization balance

Require human review for:

- A-tier accounts
- brand-sensitive offers
- pricing / rebate / legal-sensitive motions
- new channel or new messaging family

## Recommended references

- segmentation and strategy: `references/segmentation-and-strategy.md`
- channel playbooks: `references/channel-playbooks.md`
- conversion path design: `references/conversion-paths.md`
- strategy brief scaffold: `scripts/build_strategy_brief.py`
