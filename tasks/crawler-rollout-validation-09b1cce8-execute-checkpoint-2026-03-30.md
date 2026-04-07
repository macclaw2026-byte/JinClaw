# Execute Checkpoint — crawler-rollout-validation-09b1cce8

Date: 2026-03-30
Stage: execute

## What was completed
- Confirmed the crawler-layer already contains the required first-run decision policy in `crawler/logic/crawler-decision-policy.md`.
- Confirmed execution support already exists in `crawler/logic/crawler_runner.py`:
  - first-time sites trigger all-tools evaluation,
  - site profiles are refreshed from the matrix,
  - repeat runs use recorded preferred order.
- Audited current site profiles and latest run artifacts for Amazon, Walmart, Temu, and 1688.
- Added a new rollout-facing summary file: `crawler/logic/first-run-tooling-playbook.md`.
- Seeded explicit site records in that playbook for Amazon, Walmart, Temu, and 1688.
- Preserved the 1688 security boundary: credentials may support browser login, but do not justify bypassing slider/captcha/device-risk checks and do not make unattended crawling guaranteed.

## Practical decision captured
- First-time site rule: run all known tools, compare outputs, normalize evidence, select task-ready result, and record preferred tool order.
- Repeat-run rule: start from recorded primary tool and fall back in order; if quality degrades, re-run all tools.
- 1688 must keep anonymous and authenticated profiles separated.

## Current seeded site choices
- Amazon → primary `crawl4ai-cli`
- Walmart → primary `direct-http-html`
- Temu → primary `local-agent-browser-cli`
- 1688 anonymous → no production primary; diagnostic order only

## Security boundary verification
- `crawler/logic/crawler-decision-policy.md` explicitly requires user authorization for authenticated mode and forbids bypassing intended controls.
- `crawler/site-profiles/1688-auth-policy.md` explicitly requires browser-based login, separate authenticated profiles, and human-in-the-loop for slider/captcha/device-risk.

## Key artifacts
- `crawler/logic/first-run-tooling-playbook.md`
- `crawler/logic/crawler-decision-policy.md`
- `crawler/logic/crawler_runner.py`
- `crawler/site-profiles/1688-auth-policy.md`

## Remaining gap
- If Jacken wants actual 1688 authenticated crawling next, the next implementation step is to add a dedicated authenticated-session path and storage/profile separation, not to reuse the anonymous profile or broadcast credentials across stacks.
