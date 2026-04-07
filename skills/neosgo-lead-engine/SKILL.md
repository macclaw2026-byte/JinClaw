---
name: neosgo-lead-engine
description: Build and operate a local Neosgo lead-engine workflow. Use when importing large business-contact datasets into a local database, cleaning and deduplicating them, scoring likely Neosgo professional-account prospects such as interior designers, builders, contractors, electricians, and real-estate professionals, generating daily progress reports, and preparing repeatable customer-development workflows.
---

# Neosgo Lead Engine

Use this skill when the goal is to turn large raw business-contact datasets into a continuously improving Neosgo prospecting system.

## Core workflow

1. discover local source data and archives
2. register import jobs and archive status
3. import raw records into a local warehouse with resume support
4. normalize and deduplicate company/contact data
5. classify high-value Neosgo prospect types
6. score prospects with an explainable model
7. produce outreach-ready queues and daily reports

## Current recommended architecture

- Use a local DuckDB warehouse as the analysis/import layer.
- Preserve raw imports before aggressive cleaning.
- Keep scoring logic explainable and versioned.
- Prefer batch imports and incremental reruns over manual spreadsheet handling.

## Prospect priority

Prioritize these groups for Neosgo professional-account and commission-driven outreach:
- interior designers
- builders
- general contractors / remodelers
- electricians / electrical contractors
- real-estate agents / brokerages

## Trigger phrases

This skill should trigger for requests like:
- import all these customer data archives into our local database
- build a Neosgo prospecting engine
- score likely Neosgo professional customers
- create daily progress reports for customer development
- build an outreach system for builders/designers/contractors/electricians/realtors

## Resources
- data architecture: `references/data-architecture.md`
- scoring logic: `references/scoring-model.md`
- implementation roadmap: `references/implementation-roadmap.md`
- mail integration: `references/mail-integration.md`
- importer script: `scripts/import_archives_to_duckdb.py`
- mail batch export: `scripts/export_outreach_mail_batch.py`
- Apple Mail bridge: `scripts/apple_mail_bridge.py`
