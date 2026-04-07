# neosgo-lead-engine-followup-12 understand checkpoint

## Goal anchored
1. Add a permanent task rule: product descriptions must not contain HTML traces and must always be plain text.
2. Re-check all current SUBMITTED and REJECTED listings in the seller listing scope and repair descriptions that still contain HTML traces.

## Security / execution boundary
- Used only local workspace code and the approved Neosgo seller automation API.
- No destructive local operations performed.
- No credential changes, no boundary expansion.

## Concrete move completed
- Confirmed the existing bulk runner already normalizes descriptions with `html_to_plain_text(...)` and `pick_description(...)`.
- Added an explicit hard-rule code comment in `tools/bin/neosgo-seller-bulk-runner.py` so future maintenance keeps the plain-text-only requirement in place.
- Queried current seller listings for `SUBMITTED` and `REJECTED` statuses.
- Audited each listing description for HTML tags/entities.
- Attempted direct PATCH repair where HTML traces were found.

## Result summary
- SUBMITTED listings scanned: 469
- REJECTED listings scanned: 1
- Listings with HTML-trace descriptions found: 9
- PATCH repairs succeeded: 0
- PATCH repairs blocked: 9
- Common blocker: API returns `LISTING_NOT_EDITABLE` / `Only DRAFT listings can be edited or submitted through automation.` for non-DRAFT listings.

## Verification artifacts
- Audit / repair proof JSON: `data/output/neosgo-lead-engine-followup-12-proof.json`
- Enforced script location: `tools/bin/neosgo-seller-bulk-runner.py`

## User-facing issue to report
The permanent rule is now explicitly baked into the runner, but the current submitted/rejected listings that still contain HTML could not be auto-fixed because the platform rejects edits on non-DRAFT listings.
