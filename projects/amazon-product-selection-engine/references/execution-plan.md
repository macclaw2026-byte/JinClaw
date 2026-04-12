<!--
RULES-FIRST NOTICE:
Before modifying this file, first read:
- `JINCLAW_CONSTITUTION.md`
- `AI_OPTIMIZATION_FRAMEWORK.md`
Follow the constitution and framework:
brain-first, one-doctor, fail-closed, evidence-over-narration,
validate locally, then use the required PR workflow.
-->
# Amazon Product Selection Execution Plan

Updated: 2026-04-12

## Goal

Build a sustainable Amazon product-selection workflow that:

1. exports SellerSprite candidate products through the official account export path
2. extracts primary and alternate keywords from the exported rows
3. gathers Amazon first-page competition data for each alternate keyword
4. aggregates keyword-level metrics
5. exports a final results table with representative product URLs

## Governance alignment

This execution plan is part of the tracked project source of truth and must stay aligned with:

- `JINCLAW_CONSTITUTION.md`
- `projects/jinclaw-governance/jinclaw-live-guardrails.md`
- `tools/openmoss/control_center/doctor_coverage_contract.md`
- `compat/gstack/prompts/jinclaw-gstack-lite.md`
- `tools/openmoss/control_center/orchestrator.py`
- `tools/openmoss/autonomy/task_contract.py`
- `tools/openmoss/autonomy/preflight_engine.py`

## Stage plan

### Stage 1: SellerSprite official export

Input:

- logged-in SellerSprite browser session
- United States market
- last 30 days
- saved `中件FBM` preset when present, otherwise the canonical medium-parcel fallback query

Required output:

- official SellerSprite `xlsx`
- validated local file path
- proof that the file can be opened and inspected

### Stage 2: Keyword extraction

Input:

- validated SellerSprite export

Required output:

- normalized product rows
- primary keyword per product
- every alternate keyword expanded for stage-3 processing

### Stage 3: Amazon competition collection

Input:

- alternate keyword list

Required output:

- search-result counts
- first-page product URLs
- review ranges
- 30-day sales ranges
- listing-age signals

Current stable operating stance:

- if the browser path degrades, do not keep brute-forcing clicks
- switch to the hybrid collection path
- fetch Amazon search HTML directly for result counts and first-page cards
- use the authenticated SellerSprite extension API to backfill sales/listing-age signals for the collected ASINs
- run serially with checkpoints and doctor monitoring

### Stage 4: Keyword analysis

Input:

- stage-3 result set

Required output:

- per-keyword analysis rows
- a representative product URL per keyword

### Stage 5: Final export

Input:

- keyword-level analysis output

Required output:

- final table suitable for direct filtering and review

## Stage interfaces

- Stage 1 -> Stage 2:
  export file path, format, and header validation result
- Stage 2 -> Stage 3:
  alternate keyword list and source-product linkage
- Stage 3 -> Stage 4:
  keyword search details and first-page product details
- Stage 4 -> Stage 5:
  keyword-level metrics plus representative URL

## Execution rules

- Keep all versioned task definitions in tracked project files, not only in local runtime artifacts.
- Preserve the original SellerSprite export before any transformation.
- Keep stage outputs auditable and resumable.
- Stay within the JinClaw browser budget of one window and at most three tabs.
- Prefer one working tab at a time during SellerSprite and Amazon execution.
- When browser stability drops, fall back to the hybrid path instead of masking degraded results as progress.

## Local-only runtime locations

These remain outside Git:

- `/Users/mac_claw/.openclaw/workspace/data/amazon-product-selection/`
- `/Users/mac_claw/.openclaw/workspace/output/amazon-product-selection`
- `/Users/mac_claw/.openclaw/workspace/projects/amazon-product-selection-engine/runtime/`
- `/Users/mac_claw/.openclaw/workspace/projects/amazon-product-selection-engine/reports/`
