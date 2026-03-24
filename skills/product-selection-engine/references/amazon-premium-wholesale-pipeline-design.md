# Amazon Premium Wholesale Pipeline Design

This document defines the end-to-end local pipeline for the Amazon premium wholesale product-selection branch.

## Objective

Build a daily local pipeline that:
- gathers Amazon-adjacent evidence from multiple source families
- normalizes data into a stable schema
- filters out bad-fit categories and noisy candidates
- scores and ranks candidates using a transparent weighted model
- infers a daily sales range instead of fake exact sales
- suppresses repeats unless there is meaningful novelty
- produces a structured daily report input for final assistant review

## Core principle

The pipeline should remove low-value token work.

Scripts should do:
- collection
- normalization
- de-duplication
- hard filtering
- scoring
- novelty detection
- daily report candidate generation

The assistant should do:
- final review
- edge-case judgment
- conflict interpretation
- user-facing strategic explanation

## Pipeline stages

### Stage 0: Trigger
Possible triggers:
- scheduled daily run (target: 20:00 America/New_York)
- manual run
- rerun after data-source or scoring update

### Stage 1: Collection
Collect raw records from:
- Amazon search/category/product surfaces
- customer-voice branch
- competitor-page branch
- crowdfunding/blue-ocean branch when relevant
- optional SaaS tool exports or browser-assisted observations when available

### Stage 2: Normalization
Convert source outputs into unified candidate records.

### Stage 3: Hard filtering
Reject obvious bad-fit candidates.

### Stage 4: Feature extraction
Compute scoring features and flags.

### Stage 5: Score + infer daily sales range
Use weighted scoring plus range inference.

### Stage 6: Novelty / anti-repeat check
Compare against prior daily reports and recent surfaced products.

### Stage 7: Daily candidate selection
Select at least 20 candidates for the Amazon premium wholesale sheet.

### Stage 8: Output build
Write a structured JSON/CSV/MD intermediate plus daily-sheet-ready rows.

### Stage 9: Reflection hooks
Record recurring failures, weak sources, and false positives into learning/evolution loops.
