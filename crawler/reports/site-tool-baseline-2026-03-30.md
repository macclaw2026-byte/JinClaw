# Site Tool Baseline — 2026-03-30

## Decision rule now implemented
- First-time site: run all known crawler tools, compare outputs, normalize task-ready fields, classify each result as usable / partial / blocked / failed, then record preferred tool order and fallback order.
- Repeat site: start with the recorded primary tool and fall back in order; if output quality degrades or site structure changes, trigger a full all-tools re-evaluation.
- Anonymous and authenticated modes are tracked separately.

## Current known tools
1. crawl4ai-cli
2. direct-http-html
3. curl-cffi
4. playwright
5. playwright-stealth
6. scrapy-cffi
7. local-agent-browser-cli

## Amazon
- Mode: anonymous-public
- Current primary: crawl4ai-cli
- Current fallback order: local-agent-browser-cli → scrapy-cffi → playwright-stealth → playwright → curl-cffi → direct-http-html
- Current judgment: usable anonymously; first-run baseline recorded.
- Notes:
  - Several tools are usable.
  - crawl4ai currently wins because its captured output has the best task-field completeness in the latest matrix-derived arbitration.
  - direct-http-html is not a viable primary path in the current environment.

## Walmart
- Mode: anonymous-public-route-specific
- Current primary: none
- Current fallback order record: crawl4ai-cli → curl-cffi → direct-http-html → local-agent-browser-cli → playwright → playwright-stealth → scrapy-cffi
- Current judgment: blocked / insufficient evidence for reliable anonymous production use.
- Notes:
  - Current outputs are dominated by human-verification pages.
  - Existing direct-http success seen in older interpretation is not trusted as the current baseline after stricter false-positive filtering.

## TEMU
- Mode: browser-first-anonymous
- Current primary: local-agent-browser-cli
- Current fallback order: curl-cffi → direct-http-html → crawl4ai-cli → scrapy-cffi → playwright → playwright-stealth
- Current judgment: usable, but browser-led extraction is the only clearly task-usable route right now.
- Notes:
  - Browser output is stronger than HTTP-oriented outputs.
  - Non-browser stacks still need stronger normalize-time validation before they should be trusted for downstream product selection.

## 1688 anonymous
- Mode: anonymous-blocked
- Current primary: none
- Current fallback order record: scrapy-cffi → crawl4ai-cli → curl-cffi → direct-http-html → local-agent-browser-cli → playwright → playwright-stealth
- Current judgment: do not treat anonymous 1688 as task-usable.
- Notes:
  - Current runs still land in login / punish / nocaptcha / challenge-like flows.
  - local-agent-browser-cli is forcibly marked blocked for anonymous 1688 despite large output, to prevent false-positive promotion.

## 1688 authenticated feasibility
- Answer: 可以尝试做，但不能承诺“只要给用户名密码，几个工具就一定都能稳定抓到”。
- Safe implementation boundary:
  - only after explicit authorization
  - use browser-based login flow first
  - keep authenticated profile separate from anonymous profile
  - do not distribute credentials across every stack by default
  - do not bypass slider / captcha / device-risk / punish challenges
  - if challenged, require manual completion in-browser
- Practical expectation:
  - username + password may unlock some content
  - but 1688 often adds risk controls beyond credentials, so unattended login-and-crawl is not guaranteed
  - once a valid authorized browser session exists, some browser-led extraction paths may become usable for authenticated-mode crawling

## Files refreshed from this baseline
- crawler/logic/crawler-decision-policy.md
- crawler/logic/site_profiles.json
- crawler/site-profiles/amazon.md
- crawler/site-profiles/walmart.md
- crawler/site-profiles/temu.md
- crawler/site-profiles/1688.md
- crawler/site-profiles/1688-auth-policy.md
- crawler/reports/amazon-contract.json
- crawler/reports/walmart-contract.json
- crawler/reports/temu-contract.json
- crawler/reports/1688-contract.json
