# neosgo-lead-engine-followup-13 plan checkpoint

## Planning objective
Select the safest approved path to (1) keep plain-text-only description enforcement permanent for future Neosgo seller runs and (2) re-check current `SUBMITTED` / `REJECTED` listings for HTML-trace descriptions, attempting repair only through supported paths.

## Candidate plans considered

### Plan A — Future-only guardrail update, no historical re-check
- Pros: minimal API activity, low operational risk
- Cons: fails the explicit requirement to re-check current submitted/rejected listings
- Decision: rejected

### Plan B — Supported in-house API audit plus repair attempt
- Pros: directly satisfies the requested work using existing local capability, existing guardrails, and the seller automation API
- Cons: remediation depends on whether the platform allows edits on non-DRAFT listings
- Decision: selected as the best approved plan

### Plan C — Browser/UI mutation fallback for non-DRAFT listings
- Pros: might expose a different edit surface than the automation API
- Cons: higher fragility, higher ambiguity, unnecessary unless the supported API path is exhausted and explicitly justified
- Decision: not selected

## Selected execution path
1. Keep the plain-text-only rule anchored in local guardrails and runner logic.
2. Enumerate current `SUBMITTED` and `REJECTED` listings through the approved seller automation path.
3. Detect HTML traces in description fields.
4. Convert affected descriptions to clean plain text locally.
5. Attempt repair only via the supported seller automation API.
6. If blocked, preserve exact blocker evidence and stop without trying to bypass platform restrictions.

## Why this is the best approved path
- Fully in-house and already implemented.
- Uses the lowest-risk supported path first.
- Produces verifiable evidence instead of assumptions.
- Preserves security boundaries by refusing unsupported mutation work once the official platform boundary is confirmed.

## Verification evidence reviewed during planning
- Guardrail rule present in `tasks/neosgo-upload-guardrails.md`
- Historical summary confirms completed re-check in `data/output/neosgo-lead-engine-followup-12-summary.json`
- Final result captured in `tasks/neosgo-lead-engine-followup-13-final-checkpoint.md`

## Verified planning conclusion
- The plain-text-only rule is already anchored and should remain mandatory in future runs.
- The supported audit/remediation path has already been validated as the correct choice.
- Current non-DRAFT repairs are blocked by the seller automation API with:
  - HTTP 409
  - `LISTING_NOT_EDITABLE`
  - `Only DRAFT listings can be edited or submitted through automation.`
- Therefore the selected plan remains: continue enforcing plain text for all future flows, keep non-DRAFT work in audit/manual-remediation mode unless a new supported edit path is introduced.

## Security boundary check
- No boundary expansion selected.
- No unsupported browser-bypass or direct platform work chosen.
- Device, data, and network safety preserved.
