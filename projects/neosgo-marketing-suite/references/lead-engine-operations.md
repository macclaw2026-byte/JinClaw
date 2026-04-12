<!--
RULES-FIRST NOTICE:
Before modifying this file, first read:
- `JINCLAW_CONSTITUTION.md`
- `AI_OPTIMIZATION_FRAMEWORK.md`
Follow the constitution and framework:
brain-first, one-doctor, fail-closed, evidence-over-narration,
validate locally, then use the required PR workflow.
-->
# NEOSGO Lead Engine Operations

This document turns the local NEOSGO lead-engine draft notes into a stable project-side operating reference.

## Purpose

Keep the `Google Maps -> website -> validated email -> lead-engine reporting` lane inspectable and refreshable without relying on ad-hoc root-level scratch scripts.

## Canonical assets

- Warehouse: `/Users/mac_claw/.openclaw/workspace/data/neosgo_leads.duckdb`
- View rebuild SQL:
  `/Users/mac_claw/.openclaw/workspace/skills/neosgo-lead-engine/scripts/build_lead_engine_views.sql`
- Daily report generator:
  `/Users/mac_claw/.openclaw/workspace/skills/neosgo-lead-engine/scripts/generate_daily_report.py`
- Project wrapper to refresh views and report:
  `/Users/mac_claw/.openclaw/workspace/projects/neosgo-marketing-suite/scripts/refresh_lead_engine_daily_report.py`
- Project wrapper to read metrics:
  `/Users/mac_claw/.openclaw/workspace/projects/neosgo-marketing-suite/scripts/read_lead_engine_metrics.py`

## Default execution environment

The wrappers auto-discover a DuckDB-capable Python interpreter. The default preferred path is:

- `/Users/mac_claw/.openclaw/workspace/projects/ma-data-workbench/.venv/bin/python`

This avoids the earlier failure mode where the system `python3` existed but did not have `duckdb` installed.

## Standard commands

Refresh views and write the latest project-local report:

```bash
python3 /Users/mac_claw/.openclaw/workspace/projects/neosgo-marketing-suite/scripts/refresh_lead_engine_daily_report.py
```

Read the current metrics snapshot:

```bash
python3 /Users/mac_claw/.openclaw/workspace/projects/neosgo-marketing-suite/scripts/read_lead_engine_metrics.py --pretty
```

If a different DuckDB-capable interpreter is required:

```bash
python3 /Users/mac_claw/.openclaw/workspace/projects/neosgo-marketing-suite/scripts/refresh_lead_engine_daily_report.py \
  --python /path/to/python
```

## Project-local outputs

- Daily report:
  `/Users/mac_claw/.openclaw/workspace/projects/neosgo-marketing-suite/output/prospect-data-engine/lead-engine-daily-report-latest.md`
- Metrics snapshot:
  `/Users/mac_claw/.openclaw/workspace/projects/neosgo-marketing-suite/runtime/prospect-data-engine/lead-engine-metrics-latest.json`

## Metric interpretation

The metrics wrapper reports:

- `raw_contacts`: raw imported contact rows available in the warehouse
- `deduped_contacts`: cleaned company/contact rows after normalization and de-duplication
- `scored_prospects`: prospects that made it through the explainable scoring layer
- `outreach_queue_pending`: current pending outreach-ready queue size
- `top_segments`: highest-volume `segment_primary` groups
- `major_blockers.missing_email_or_website_in_deduped`: contacts still missing a valid email or website
- `major_blockers.non_target_industry_patterns_in_deduped`: rows that likely still need industry mapping refinement
- `major_blockers.sa_without_campaign_variant`: S/A prospects missing an active campaign variant

## Operational stance

- Treat report refresh as a safe local maintenance action, not as a substitute for the live outreach cycle.
- If the metrics show healthy counts but the task surface still claims a live stall, suspect runtime/control-plane interpretation before assuming the business pipeline failed.
- Keep the warehouse, report, and metrics paths stable so doctor/runtime layers can reference the same evidence bundle repeatedly.
