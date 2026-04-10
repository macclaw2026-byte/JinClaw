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
2. extracts primary keywords from the exported records
3. analyzes Amazon front-end competition by keyword
4. aggregates keyword-level metrics
5. exports a final results table with representative product URLs

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

Extract primary keywords from the validated SellerSprite export.

### Stage 3

Search Amazon by keyword and capture first-page competition signals.

### Stage 4

Aggregate keyword metrics and choose representative URLs.

### Stage 5

Export the final keyword-level table.
