# crawler-remediation-cycle plan checkpoint — 2026-04-01

## User goal
Optimize product descriptions for all currently operable seller listings in `SUBMITTED` and `REJECTED` states, using product-image-derived information where safely available, while enforcing a strict plain-text-only output rule with no HTML.

## Safe execution plans compared

### Plan A — Browser-only manual editing through seller UI
- Pros:
  - Mirrors visible user workflow exactly
  - Could inspect page-level review messages directly
- Cons:
  - Slower and less reliable for 100+ listings
  - Higher risk of UI drift/timeouts
  - Harder to verify full-batch consistency
- Decision: not selected as primary path

### Plan B — Seller automation API batch patching using existing local auth + listing detail data
- Pros:
  - Uses already available in-house automation surface
  - Fast, consistent, auditable, repeatable
  - Supports direct listing enumeration by status and direct `PATCH` updates
  - Easy to enforce plain-text-only descriptions deterministically
- Cons:
  - Image understanding is limited by local capability unless OCR/vision is added
- Decision: selected as primary path

### Plan C — Build/attach a heavier local OCR/vision layer first, then patch listings
- Pros:
  - Potentially richer image-derived copy
- Cons:
  - Local OCR stack not preinstalled; increases setup time and moving parts
  - Not required to satisfy the core business constraint today
- Decision: kept as optional future enhancement, not the blocking path

## Selected path
Plan B with an image-aware but safety-first description builder:
- Enumerate all `SUBMITTED` and `REJECTED` listings through seller automation API
- Read each listing detail object, including image arrays and current metadata
- Generate improved plain-text-only descriptions with image-presence/image-signal support
- Patch each listing through the automation API
- Verify no HTML remains in any target description

## Why this is the best approved path
- Lowest operational risk
- Strongest batch consistency
- Best auditability in local workspace
- Directly satisfies the hard business rule: descriptions must contain text only, no HTML
- Preserves security boundaries by reusing local, already-authorized in-house automation instead of broader browser/session extraction

## Security boundary check
- No credential export
- No browser cookie/storage extraction
- No privilege escalation
- No cross-boundary data exfiltration

## Concrete move executed from this plan
- Implemented `tools/bin/neosgo_listing_description_optimizer.py`
- Started full-batch execution against current `SUBMITTED` + `REJECTED` listings
- Verified online that updated descriptions are appearing and remain plain text only
