<!--
RULES-FIRST NOTICE:
Before modifying this file, first read:
- `JINCLAW_CONSTITUTION.md`
- `AI_OPTIMIZATION_FRAMEWORK.md`
Follow the constitution and framework:
brain-first, one-doctor, fail-closed, evidence-over-narration,
validate locally, then use the required PR workflow.
-->
# NEOSGO Feedback Loop SOP

## Goal

Turn real outreach outcomes into structured feedback so the NEOSGO marketing suite can automatically:

- suppress bad or risky targets
- improve channel and strategy weighting
- improve discovery query weighting
- reduce repeated low-quality outreach

## When to use this SOP

Use this after any real operator action on:

- `form` submissions
- `LinkedIn` outreach
- manual partner/dealer applications
- manual business contact attempts

## Step 1. Choose the latest execution queue

Find the newest cycle under:

- `output/marketing-automation-suite/<cycle_id>/execution-queue.json`

## Step 2. Generate a feedback template

```bash
python3 /Users/mac_claw/.openclaw/workspace/skills/outreach-feedback-engine/scripts/build_feedback_event_template.py \
  --execution-queue /Users/mac_claw/.openclaw/workspace/projects/neosgo-marketing-suite/output/marketing-automation-suite/<cycle_id>/execution-queue.json \
  --output /Users/mac_claw/.openclaw/workspace/projects/neosgo-marketing-suite/data/feedback-events.template.json \
  --limit 40
```

This creates a working file for operators:

- `data/feedback-events.template.json`

## Step 3. Fill in real outcomes

For each touched row, fill:

- `outcome_type`
- `classification`
- `evidence` or `evidence_excerpt`
- `operator_notes`
- `captured_at`
- set `template_status` to something other than `awaiting_operator_input`

## Allowed classifications

- `positive_interest`
- `referral`
- `neutral_question`
- `not_now`
- `not_fit`
- `unsubscribe`
- `invalid_contact`
- `hard_bounce`
- `auto_reply`
- `spam_complaint_risk`

## Suggested mapping

- Prospect replied and wants to talk:
  - `outcome_type = positive_reply`
  - `classification = positive_interest`
- Prospect referred another contact:
  - `outcome_type = referral`
  - `classification = referral`
- Prospect asked a clarification question:
  - `outcome_type = question`
  - `classification = neutral_question`
- Prospect said later / not now:
  - `outcome_type = not_now`
  - `classification = not_now`
- Prospect said wrong fit:
  - `outcome_type = not_fit`
  - `classification = not_fit`
- Prospect asked to stop:
  - `outcome_type = unsubscribe`
  - `classification = unsubscribe`
- Contact route is dead / wrong:
  - `outcome_type = invalid`
  - `classification = invalid_contact`
- Strong spam/complaint risk:
  - `outcome_type = complaint_risk`
  - `classification = spam_complaint_risk`

## Step 4. Validate completed rows

```bash
python3 /Users/mac_claw/.openclaw/workspace/skills/outreach-feedback-engine/scripts/validate_feedback_events.py \
  --source /Users/mac_claw/.openclaw/workspace/projects/neosgo-marketing-suite/data/feedback-events.template.json \
  --output /Users/mac_claw/.openclaw/workspace/projects/neosgo-marketing-suite/runtime/feedback-loop/validation.json
```

If validation returns `blocked`, fix the rows before merging.

## Step 5. Merge completed rows into live feedback

```bash
python3 /Users/mac_claw/.openclaw/workspace/skills/outreach-feedback-engine/scripts/merge_feedback_events.py \
  --source /Users/mac_claw/.openclaw/workspace/projects/neosgo-marketing-suite/data/feedback-events.template.json \
  --target /Users/mac_claw/.openclaw/workspace/projects/neosgo-marketing-suite/data/feedback-events.json \
  --archive /Users/mac_claw/.openclaw/workspace/projects/neosgo-marketing-suite/data/feedback-events.template.archive.json
```

## Step 6. Run a new suite cycle

```bash
python3 /Users/mac_claw/.openclaw/workspace/skills/marketing-automation-suite/scripts/run_marketing_suite_cycle.py \
  --project-root /Users/mac_claw/.openclaw/workspace/projects/neosgo-marketing-suite
```

## One-command version

```bash
python3 /Users/mac_claw/.openclaw/workspace/skills/marketing-automation-suite/scripts/run_feedback_loop.py \
  --project-root /Users/mac_claw/.openclaw/workspace/projects/neosgo-marketing-suite
```

This command will:

- validate completed rows
- merge valid rows
- rerun the full marketing suite cycle
- rebuild the next feedback template from the new execution queue

## What should change after a healthy feedback cycle

- `feedback-events.json` count goes up
- `classified-feedback.json` shows real classifications
- `suppression-registry.json` starts recording stop actions
- `strategy-weights.json` begins to shift
- `query-weights.json` begins to shift
- weaker channels / paths / angles begin to lose priority

## Operator rules

- Never fabricate outcomes
- Never mark `positive_interest` without evidence
- Always use `unsubscribe` for explicit stop requests
- Always use `invalid_contact` or `hard_bounce` for bad endpoints
- Escalate `spam_complaint_risk` immediately

## Success criteria

- feedback events are added every operating cycle
- suppression actions start reducing bad future attempts
- channel/path/angle priorities begin changing from real outcomes
- query weighting stops staying near zero across the board
