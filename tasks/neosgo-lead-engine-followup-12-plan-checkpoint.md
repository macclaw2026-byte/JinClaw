# neosgo-lead-engine-followup-12 plan checkpoint

## Planning objective
Compare safe execution paths for enforcing plain-text-only descriptions and remediating existing HTML-trace descriptions in current seller listings.

## Candidate plans considered

### Plan A — Update future-runner only, skip historical audit
- Pros: fastest, lowest API activity
- Cons: does not satisfy the explicit requirement to re-check current `SUBMITTED` and `REJECTED` listings
- Decision: rejected

### Plan B — Audit current listings and patch every affected listing through the seller automation API
- Pros: directly satisfies the requested remediation goal if the platform allows edits
- Cons: depends on platform editability for non-DRAFT statuses
- Decision: selected as the primary execution path because it is the safest direct in-house path and uses approved local code plus the existing seller automation API

### Plan C — Attempt unsupported/browser/manual mutation path for non-DRAFT listings
- Pros: might bypass the API limitation if the web UI exposes something different
- Cons: higher fragility, uncertain legality/support boundary, unnecessary until the supported API path is proven blocked
- Decision: not selected at plan stage

## Selected path
1. Keep the plain-text-only rule explicitly anchored in the local Neosgo runner and guardrails.
2. Enumerate current `SUBMITTED` and `REJECTED` listings via the supported seller automation API.
3. Detect description fields that still contain HTML tags/entities/traces.
4. Attempt safe direct PATCH remediation through the same approved API.
5. If blocked, preserve exact blocker evidence and stop without boundary expansion.

## Why this is the best approved path
- Uses only approved local assets and existing seller automation endpoints.
- Preserves device/data/network safety.
- Directly tests whether supported remediation is possible before considering any higher-risk fallback.
- Produces verifiable evidence instead of assumptions.

## Verified outcome of selected path
- The rule is already functionally enforced in code and is now also explicitly documented in the runner.
- Historical listing audit was executed.
- Remediation attempts on non-DRAFT listings were blocked by platform response `LISTING_NOT_EDITABLE` (HTTP 409).
- Therefore the safest approved path reached the real platform boundary without crossing it.

## Evidence
- `tools/bin/neosgo-seller-bulk-runner.py`
- `tasks/neosgo-upload-guardrails.md`
- `data/output/neosgo-lead-engine-followup-12-proof.json`
- `data/output/neosgo-lead-engine-followup-12-summary.json`
- `tasks/neosgo-lead-engine-followup-12-final-checkpoint.md`
