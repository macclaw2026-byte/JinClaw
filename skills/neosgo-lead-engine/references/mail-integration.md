# Neosgo Mail Integration

## Goal
Connect `outreach_queue` to a real sender mailbox so the lead engine can:

1. export a batch of pending outreach emails
2. create drafts in Apple Mail using a local mailbox such as `cs@neosgo.com`
3. let a human review/send or later automate sending
4. import reply / sent / bounce feedback back into `outreach_events`

## Current local path

### 1. Export a mail batch from DuckDB

```bash
python3 skills/neosgo-lead-engine/scripts/export_outreach_mail_batch.py \
  --db /Users/mac_claw/.openclaw/workspace/data/neosgo_leads.duckdb \
  --sender-email cs@neosgo.com \
  --limit 25 \
  --csv-out /Users/mac_claw/.openclaw/workspace/output/neosgo/mail-batch.csv \
  --json-out /Users/mac_claw/.openclaw/workspace/output/neosgo/mail-batch.json
```

### 2. Inspect Apple Mail accounts

```bash
python3 skills/neosgo-lead-engine/scripts/apple_mail_bridge.py list-accounts
```

### 3. Create Mail drafts in Apple Mail

```bash
python3 skills/neosgo-lead-engine/scripts/apple_mail_bridge.py create-drafts \
  --account-name "cs@neosgo.com" \
  --csv /Users/mac_claw/.openclaw/workspace/output/neosgo/mail-batch.csv \
  --limit 10
```

## Why drafts first

- safer than immediate bulk send
- lets us validate copy and recipient quality
- keeps Mail deliverability and human review in the loop
- makes it easy to record `sent` only after actual human approval

## Recommended next step

After drafts are working:

1. add a script that marks drafted queue items as `scheduled`
2. add a feedback importer from Mail mailbox folders or CSV exports
3. map reply states into `outreach_events`

## Added reporting and reply monitoring

### Daily delivery report

```bash
python3 skills/neosgo-lead-engine/scripts/generate_outreach_delivery_report.py \
  --db /Users/mac_claw/.openclaw/workspace/data/neosgo_leads.duckdb \
  --date 2026-04-03 \
  --out /Users/mac_claw/.openclaw/workspace/output/neosgo/outreach-delivery-report.md \
  --json-out /Users/mac_claw/.openclaw/workspace/output/neosgo/outreach-delivery-report.json
```

This report summarizes:
- sent
- delivered
- bounced
- opened
- clicked
- replied
- quote/sample/meeting/won/lost

### Mail reply monitoring

```bash
python3 skills/neosgo-lead-engine/scripts/watch_mail_replies.py \
  --account-name "Neosgo" \
  --mailbox INBOX \
  --limit 10 \
  --unread-only \
  --json-out /Users/mac_claw/.openclaw/workspace/output/neosgo/mail-replies.json
```

To forward full reply content to Telegram:

```bash
python3 skills/neosgo-lead-engine/scripts/watch_mail_replies.py \
  --account-name "Neosgo" \
  --mailbox INBOX \
  --limit 10 \
  --unread-only \
  --send-telegram
```

## State-targeted launch workflow

Prepare a state-targeted batch:

```bash
python3 skills/neosgo-lead-engine/scripts/prepare_state_outreach_batch.py \
  --db /Users/mac_claw/.openclaw/workspace/data/neosgo_leads.duckdb \
  --state CA \
  --segment designer \
  --fit-tier S \
  --min-fit-score 90 \
  --limit 25
```

Launch a state-targeted batch and create Apple Mail drafts:

```bash
python3 skills/neosgo-lead-engine/scripts/launch_state_outreach.py \
  --db /Users/mac_claw/.openclaw/workspace/data/neosgo_leads.duckdb \
  --state CA \
  --segment designer \
  --fit-tier S \
  --min-fit-score 90 \
  --limit 25 \
  --account-name Neosgo \
  --create-drafts
```

## Six-hour task report

```bash
python3 skills/neosgo-lead-engine/scripts/generate_outreach_task_report.py \
  --db /Users/mac_claw/.openclaw/workspace/data/neosgo_leads.duckdb \
  --manifest /Users/mac_claw/.openclaw/workspace/output/neosgo/batches/CA-designer/<timestamp>/batch-manifest.json \
  --hours 6 \
  --out /Users/mac_claw/.openclaw/workspace/output/neosgo/reports/ca-designer-6h.md \
  --json-out /Users/mac_claw/.openclaw/workspace/output/neosgo/reports/ca-designer-6h.json \
  --send-telegram
```

## Reply monitoring with event import

```bash
python3 skills/neosgo-lead-engine/scripts/watch_mail_replies.py \
  --account-name Neosgo \
  --mailbox INBOX \
  --limit 20 \
  --unread-only \
  --db /Users/mac_claw/.openclaw/workspace/data/neosgo_leads.duckdb \
  --json-out /Users/mac_claw/.openclaw/workspace/output/neosgo/mail-replies.json \
  --event-csv-out /Users/mac_claw/.openclaw/workspace/output/neosgo/mail-replies-events.csv \
  --import-events \
  --send-telegram
```
