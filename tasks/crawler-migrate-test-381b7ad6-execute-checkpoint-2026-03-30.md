# crawler-migrate-test-381b7ad6 execute checkpoint

- Time: 2026-03-30T09:41:44.530896-07:00
- Stage: execute
- Status: complete for current scope

## What was implemented

1. **First-run all-tools decision logic was wired into executable code**
   - `crawler/logic/crawler_runner.py` now treats `--first-run`, `--refresh-profile`, or missing site profile as a full-evaluation trigger.
   - Full evaluation runs the matrix, then auto-refreshes the site record instead of only reading a stale manual profile.

2. **Site profile generation was rebuilt from current matrix evidence**
   - Added `summarize_site_from_matrix()` in `crawler/logic/crawler_contract.py`.
   - This function converts latest matrix evidence into:
     - JSON site profile entries in `crawler/logic/site_profiles.json`
     - per-site markdown records in `crawler/site-profiles/*.md`
   - Preferred tool order is now derived from measured outcomes instead of stale handwritten assumptions.

3. **Compare/normalize contract remains executable**
   - `crawler/reports/*-contract.json` regenerated for Amazon / Walmart / Temu / 1688.
   - The contract still records:
     - first-run rule
     - repeat-run rule
     - tested tools
     - preferred tool order
     - blocked tools
     - task-ready fields
     - auth policy

4. **1688 authenticated mode stayed behind an explicit safety boundary**
   - Anonymous and authenticated handling remain separated.
   - Current anonymous profile continues to mark 1688 as blocked / truth-check-only for production extraction.
   - `crawler/site-profiles/1688-auth-policy.md` keeps the rule that credentials may only be used in an explicitly authorized browser login flow, with no slider/captcha bypass.

## Current recorded site preferences from this test wave

- **Amazon**: `local-agent-browser-cli` primary; then `scrapy-cffi`, `curl-cffi`, browser fallbacks, then weaker paths.
- **Walmart**: `direct-http-html` primary; most other routes currently blocked by human verification.
- **Temu**: `local-agent-browser-cli` primary; `crawl4ai-cli` secondary; others mostly blocked or weak.
- **1688**: all current anonymous routes blocked; no anonymous production primary selected.

## Verification evidence

- Python compile check passed for:
  - `crawler/logic/crawler_runner.py`
  - `crawler/logic/crawler_contract.py`
- Smoke run passed:
  - `run_site('amazon', 'wireless mouse')` returned best tool `local-agent-browser-cli` with status `usable`.
- Regenerated artifacts:
  - `crawler/logic/site_profiles.json`
  - `crawler/site-profiles/amazon.md`
  - `crawler/site-profiles/walmart.md`
  - `crawler/site-profiles/temu.md`
  - `crawler/site-profiles/1688.md`
  - `crawler/reports/amazon-contract.json`
  - `crawler/reports/walmart-contract.json`
  - `crawler/reports/temu-contract.json`
  - `crawler/reports/1688-contract.json`

## Security boundary decision for 1688 login question

- **Yes, it can be implemented in a limited, authorized form**: a browser-based login workflow can be added so tools reuse an authenticated browser session.
- **No, credentials alone do not guarantee stable unattended crawling**: 1688 may still require slider/captcha/device-risk verification.
- **Allowed safe direction**:
  - explicit user authorization
  - browser login only
  - separate authenticated site profile and reports
  - pause for human help if challenged
- **Not allowed**:
  - bypassing slider/captcha/device-risk controls
  - spraying username/password across every crawler stack

## Remaining next step

- Add a separate authenticated profile path for sites like 1688 so anonymous ranking and logged-in ranking are stored independently.
