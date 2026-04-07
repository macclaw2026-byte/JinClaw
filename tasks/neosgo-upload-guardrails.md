# Neosgo Upload Guardrails

## Purpose
Prevent duplicate or invalid product uploads from Giga into seller draft listings.

## Bottom-layer rules
These rules must be treated as hard guards for any current or future upload path:

1. **Only upload `new import` products**
   - When selecting products from the Giga candidate pool, the product upload/import status must be checked first.
   - Only candidates whose status is exactly equivalent to `new import` / `new_import` are eligible.
   - Any non-`new import` status must be skipped.

2. **Never upload if a draft listing with the same SKU already exists**
   - Before import/upload, the system must check existing seller draft listings.
   - If the target SKU already exists in DRAFT listings, skip the upload.
   - This rule applies even if the candidate also appears importable from Giga.

3. **Product descriptions must be plain text only**
   - Product descriptions must not contain HTML tags, HTML fragments, markup wrappers, or visible HTML syntax traces.
   - Descriptions must be stored and submitted as plain text content only.
   - Before patching/submitting a listing, any HTML description must be normalized into clean plain text.
   - This rule applies to all future upload, patch, repair, or re-submission flows.

## Required enforcement points
These guards must be enforced in both places:

### A. Candidate selection layer
Filter candidate list so that only items satisfying both conditions survive:
- `canImport = true`
- status is `new import`
- SKU does not already exist in DRAFT listings

### B. Pre-import execution layer
Immediately before calling the import API, re-run both checks:
- status is still `new import`
- SKU still does not already exist in DRAFT listings

This second pass exists as a race-condition / drift guard.

### C. Description normalization layer
Before any listing patch or submission:
- inspect description content
- strip HTML tags and markup traces
- submit plain text only

## Reason
This is a double-insurance policy:
- first guard reduces bad candidates early
- second guard prevents accidental duplicate draft creation if state changed between fetch and upload
- description normalization prevents malformed/non-compliant listing copy from leaking into submitted inventory

## Current implementation
Implemented in:
- `tools/bin/neosgo-seller-bulk-runner.py`

## Notes for future changes
If upload logic is moved to another script, service, automation loop, sub-agent workflow, or API wrapper, these same guardrails must be copied or centralized before that path is considered valid.
