<!--
RULES-FIRST NOTICE:
Before modifying this file, first read:
- `JINCLAW_CONSTITUTION.md`
- `AI_OPTIMIZATION_FRAMEWORK.md`
Follow the constitution and framework:
brain-first, one-doctor, fail-closed, evidence-over-narration,
validate locally, then use the required PR workflow.
-->
# NEOSGO Seller Maintenance Canonical Workflow And Boundaries

This reference consolidates the useful parts of the draft `understand`, `plan`, and platform-boundary notes into one stable project document.

## Mission scope

`neosgo-seller-maintenance` is the single canonical lane for the daily `NEOSGO seller + GIGA` workflow.

The target outcome is not "run something once", but to keep one repeatable lane that is:

- documented
- runnable
- scheduled daily
- verifiable from local artifacts
- free from legacy `seller-neosgo*` active-task drift

## Canonical workflow

The daily workflow remains:

1. `Import New`
   - scan GIGA candidates
   - only import `NEW_IMPORT` rows with `canImport=true`
   - skip any SKU that already exists in `DRAFT`
2. `Optimize Draft`
   - normalize draft payloads
   - force description content to plain text
   - repair readiness-critical fields
   - submit ready drafts
3. `Repair Rejected`
   - enumerate current `REJECTED`
   - rebuild payload with the same guardrails
   - resubmit only when readiness passes
4. `Sync Uploaded Inventory`
   - sync inventory for `APPROVED` / `SUBMITTED` listings
   - use GIGA candidate availability as the source signal

## Hard boundaries

- Stable API behavior outranks browser-heavy or rich-media actions for the daily lane.
- Product descriptions must always be normalized to plain text before patch or submit.
- Legacy `seller-neosgo*` followup chains should stay retired; do not revive them as the canonical workflow.
- Daily maintenance should keep producing machine-checkable state/report artifacts.

## Verified platform boundary

The seller automation path can enforce plain-text descriptions for future work, but it cannot automatically edit current non-`DRAFT` listings once the platform rejects mutation.

Verified blocker:

- HTTP `409`
- `LISTING_NOT_EDITABLE`
- `Only DRAFT listings can be edited or submitted through automation.`

Implication:

- future runs must keep the plain-text-only rule in place
- current `SUBMITTED` / `REJECTED` listings may be audited and prepared for repair
- automatic repair must stop at the non-`DRAFT` edit boundary instead of attempting a bypass

## Release gate

Treat the workflow as healthy only when all of these remain true:

- `projects/neosgo-seller-maintenance/README.md` is still the canonical operator doc
- `tools/openmoss/ops/run_neosgo_seller_maintenance_cycle.py` remains runnable
- the daily LaunchAgent is installed and locally verifiable
- `data/neosgo-seller-maintenance-state.json` and `output/neosgo-seller-maintenance/` keep updating
- legacy `seller-neosgo*` residue stays retired from active task space

## Key evidence anchors

- README:
  `/Users/mac_claw/.openclaw/workspace/projects/neosgo-seller-maintenance/README.md`
- Guardrails:
  `/Users/mac_claw/.openclaw/workspace/tasks/neosgo-upload-guardrails.md`
- Final verification:
  `/Users/mac_claw/.openclaw/workspace/projects/neosgo-seller-maintenance/references/final-done-definition-verification-2026-04-12T06-03.md`
- Legacy retirement audit:
  `/Users/mac_claw/.openclaw/workspace/projects/neosgo-seller-maintenance/references/legacy-seller-neosgo-retirement-audit-2026-04-12.md`
