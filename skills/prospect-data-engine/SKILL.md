---
name: prospect-data-engine
description: Reusable prospect discovery, acquisition, cleaning, enrichment, qualification, and scoring skill for B2B growth systems. Use when a project needs to define target accounts, discover public leads, collect and normalize public evidence, validate reachability, score line quality, and output a database that downstream strategy and outreach modules can safely consume.
---

# Prospect Data Engine

Use `../self-cognition-orchestrator/references/monitoring-and-retrofit-framework.md` as the shared monitoring standard when applying this skill's monitoring, backstop, and retrofit logic.
Use `../self-cognition-orchestrator/references/problem-solving-default.md` as the default behavior when acquisition paths fail, evidence is weak, or source quality is unstable.

This skill turns a business goal into a reusable, high-quality prospect database.

## Purpose

Do not start from random contact lists.

Start from:

- business objective
- ICP definition
- public evidence strategy
- quality thresholds
- database structure
- explainable scoring

The goal is to produce a durable prospect asset, not a one-off scrape dump.

## Core jobs

This skill is responsible for:

- target-account definition
- public-source selection
- search and discovery strategy
- evidence acquisition
- cleaning and normalization
- deduplication
- enrichment
- reachability validation
- lead qualification
- explainable lead scoring
- database-ready output

## Operating model

### Step 1: Define the target customer

Always define:

- target account type
- target role/persona
- geographic scope
- fit rules
- exclusion rules
- success signal

Do not begin acquisition until these are written down.

### Step 2: Define source families

Prefer account-first public sources:

- company websites
- team/contact pages
- project/case-study pages
- Google Business Profile
- LinkedIn company pages
- partner/dealer/directories
- association and trade directories
- event/exhibitor directories

Use person/contact sources only after the account layer is anchored.

### Step 3: Run discovery and collection

For each source family, define:

- search recipe
- extraction fields
- validation rules
- rejection/noise rules

Prefer:

- public, stable pages
- identifiable business entities
- traceable source URLs

### Step 4: Normalize and deduplicate

Normalize:

- company name
- domain
- role title
- geography
- industry
- channel endpoints

Deduplicate by:

- root domain
- normalized company name
- person + company
- phone

### Step 5: Validate and enrich

Validate:

- business reality
- source coherence
- contactability
- project/channel relevance

Enrich:

- size band
- persona type
- partner fit
- buying context
- signal freshness

### Step 6: Score and publish to database

Score with separate components:

- fit
- intent/signal
- reachability
- data quality

Do not hide all logic in one opaque total score.

## Non-negotiable rules

- No untraceable records in the primary database.
- No single-field “lead” should be considered outreach-ready.
- No low-confidence email list should bypass validation.
- Prefer account-first and evidence-first over address-first.
- Always preserve source provenance.

## Outputs

Primary outputs should include:

- structured accounts table
- structured contacts table
- signal table
- reachability table
- scoring table
- source quality report
- suppression candidate report

## Reusable Google Maps lane

This skill now includes a reusable `Google Maps -> website -> validated contactability`
lane for public business discovery.

Use it when a project needs to:

- discover public Google Maps entities by keyword and geography
- keep a rolling crawl state instead of one-off search dumps
- enrich official websites for emails and contact forms
- write explainable discovery and enrichment quality reports

Canonical runner:

- `scripts/run_google_maps_capture_cycle.py`

Typical usage:

```bash
python3 /Users/mac_claw/.openclaw/workspace/skills/prospect-data-engine/scripts/run_google_maps_capture_cycle.py \
  --project-root /Users/mac_claw/.openclaw/workspace/projects/neosgo-marketing-suite \
  --keyword "interior designer" \
  --account-type designer \
  --persona-type founder
```

The runner preserves:

- query family
- capture route and fallback evidence
- discovery quality summary
- enrichment quality summary
- rolling project-local crawl state

## Quality and risk model

Monitor:

- duplicate rate
- no-domain rate
- no-contactability rate
- low-confidence source ratio
- invalid/contradicted record ratio
- score distribution drift

Require human review for:

- new source families
- bulk imports from unstable sources
- high-value A-tier records before sensitive outreach
- repeated source contradictions

## Recommended references

- source strategy: `references/source-strategy.md`
- database schema: `references/database-schema.md`
- scoring model: `references/scoring-model.md`
- workspace bootstrap: `scripts/bootstrap_prospect_workspace.py`
