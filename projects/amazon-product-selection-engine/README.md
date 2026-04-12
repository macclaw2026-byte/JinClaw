<!--
RULES-FIRST NOTICE:
Before modifying this file, first read:
- `JINCLAW_CONSTITUTION.md`
- `AI_OPTIMIZATION_FRAMEWORK.md`
Follow the constitution and framework:
brain-first, one-doctor, fail-closed, evidence-over-narration,
validate locally, then use the required PR workflow.
-->
# Amazon Product Selection Engine

This project is the versioned JinClaw task framework for the local OpenClaw-based Amazon product-selection workflow.

## Governance Alignment

This project is governed by the same three-layer framework as the rest of JinClaw:

- Constitution layer: `JINCLAW_CONSTITUTION.md`
- Rules layer: `projects/jinclaw-governance/jinclaw-live-guardrails.md` and `tools/openmoss/control_center/doctor_coverage_contract.md`
- Process layer: `compat/gstack/prompts/jinclaw-gstack-lite.md`, `tools/openmoss/control_center/orchestrator.py`, `tools/openmoss/autonomy/task_contract.py`, and `tools/openmoss/autonomy/preflight_engine.py`

Project-specific mapping and compliance notes live in `GOVERNANCE.md`.

## Versioned Source of Truth

Only reproducible source assets belong in Git:

- `config/project-config.json`
- `config/stage-manifest.json`
- `GOVERNANCE.md`
- `scripts/run_stage1_sellersprite_official_export.py`
- `scripts/extract_stage2_primary_keywords.py`
- `scripts/run_stage3_amazon_keyword_collection.py`
- `scripts/run_stage3_all_alternate_keyword_collection.py`
- `scripts/validate_stage1_export.py`
- `tests/fixtures/sellersprite_export_sample.csv`
- `tests/test_amazon_product_selection_engine.py`

## Local-Only Runtime Artifacts

These remain local OpenClaw runtime assets and must not be committed:

- `data/`
- `runtime/`
- `reports/`
- `output/`

## Goal

Build a staged workflow that:

1. exports SellerSprite candidate products as the official account-level Excel artifact
2. extracts product-level primary keywords plus every alternate keyword from the exported records
3. analyzes Amazon front-end competition for every alternate keyword
4. aggregates keyword-level metrics
5. exports a final results table with representative product URLs

## Browser Policy

For this task, browser automation must stay within the global JinClaw budget of 3 open tabs and a single browser window during SellerSprite and Amazon execution. Stability comes before speed. The preferred stage-3 pattern is:

- keep one working page
- use random inter-keyword delays
- run in small batches
- cool down between batches
- stop immediately on Amazon error pages, robot checks, or suspicious empty-result runs
- reset the browser session before resuming if the site degrades

## Stage Summary

### Stage 1

Run the official SellerSprite export flow inside an OpenClaw-controlled, logged-in browser session:

- open Product Research
- use United States
- use 30-Day
- apply the `中件FBM` preset when it is available, otherwise use the canonical FBM medium-parcel query mapping
- run the search
- click `Export`
- open `My Exported Data`
- download the official `xlsx`
- validate the saved file structure

Stage 1 is complete only when the official SellerSprite Excel exists locally and passes `validate_stage1_export.py`.

### Stage 2

Extract primary keywords from the validated SellerSprite export, then expand every product's `alternate_keyword` values into the official stage-3 handoff.

### Stage 3

Search Amazon by every `alternate_keyword` and capture first-page competition signals. The official stage-3 runner deduplicates repeated keyword strings at query time, then expands the collected metrics back onto every alternate-keyword entry so no alternate keyword is skipped in the final data.

### Stage 4

Aggregate keyword metrics and choose representative URLs.

### Stage 5

Export the final keyword-level table.
