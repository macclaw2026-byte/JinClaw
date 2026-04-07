# neosgo-lead-engine-followup-12 final checkpoint

## Goal result
- Added and anchored the plain-text-only description rule for future Neosgo seller bulk work.
- Re-checked current seller listings in `SUBMITTED` and `REJECTED` status for HTML traces in descriptions.
- Attempted direct repair on every affected listing found during the scan.

## Concrete enforcement added
File: `tools/bin/neosgo-seller-bulk-runner.py`
- Existing enforcement already normalized description content via `html_to_plain_text(...)` and `pick_description(...)`.
- Added an explicit hard-rule comment so future maintenance keeps this as a non-optional rule: descriptions must always be plain text only.
- Workspace guardrail doc already matches this rule: `tasks/neosgo-upload-guardrails.md`.

## Verification evidence
Artifacts:
- `data/output/neosgo-lead-engine-followup-12-proof.json`
- `data/output/neosgo-lead-engine-followup-12-summary.json`
- `tasks/neosgo-lead-engine-followup-12-understand-checkpoint.md`

Scan summary:
- Total scanned: 101
- SUBMITTED scanned: 100
- REJECTED scanned: 1
- HTML-trace descriptions found: 101
- Successful repairs: 0
- Blocked repairs: 101

## Blocker
Every attempted patch on non-DRAFT listings was rejected by the seller automation API with the same platform-side blocker:
- HTTP 409
- `LISTING_NOT_EDITABLE`
- `Only DRAFT listings can be edited or submitted through automation.`

## Conclusion
- Future-task rule is in place.
- Current submitted/rejected listings were successfully audited.
- Repair attempts could not be completed because the platform forbids automation edits on non-DRAFT listings.
- Security boundaries were preserved throughout.
