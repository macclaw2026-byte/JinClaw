# crawler-direct-validation-68d36d27 — execute checkpoint

## What was executed
- Updated crawler-layer arbitration code so first-run site evaluation can be regenerated from the all-tools matrix and written back into persistent site records.
- Refined selection behavior to prefer field completeness during arbitration instead of only raw signal volume.
- Added a forced anonymous false-positive guard for 1688 so large browser output does not get promoted to usable when it still reflects login/challenge flow.
- Regenerated site profiles and contract files for Amazon, Walmart, TEMU, and 1688 from the current baseline matrix.
- Wrote a consolidated baseline report for the four sites.

## Files changed
- crawler/logic/crawler_contract.py
- crawler/logic/crawler_runner.py
- crawler/site-profiles/amazon.md
- crawler/site-profiles/walmart.md
- crawler/site-profiles/temu.md
- crawler/site-profiles/1688.md
- crawler/logic/site_profiles.json
- crawler/reports/amazon-contract.json
- crawler/reports/walmart-contract.json
- crawler/reports/temu-contract.json
- crawler/reports/1688-contract.json
- crawler/reports/site-tool-baseline-2026-03-30.md

## Verification evidence
- Generated contracts successfully:
  - crawler/reports/amazon-contract.json
  - crawler/reports/walmart-contract.json
  - crawler/reports/temu-contract.json
  - crawler/reports/1688-contract.json
- Current recorded outcomes after regeneration:
  - Amazon: primary = crawl4ai-cli, mode = anonymous-public
  - Walmart: primary = none, result = blocked_or_insufficient_evidence
  - TEMU: primary = local-agent-browser-cli, mode = browser-first-anonymous
  - 1688: primary = none, mode = anonymous-blocked

## Security boundary check
- Preserved explicit separation between anonymous and authenticated modes.
- Did not introduce automatic credential replay across all tools.
- Kept 1688 login automation within browser-login-only and human-verification-required-if-challenged boundary.

## Remaining next step
- If approved later, add a dedicated authenticated profile workflow for 1688 that stores separate run history and only uses browser-led authorized sessions.
