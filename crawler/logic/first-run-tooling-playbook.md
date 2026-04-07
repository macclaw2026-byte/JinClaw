# Crawler First-Run Tooling Playbook

## Purpose

For a newly seen site, the crawler layer must:
1. run all currently known tools once,
2. compare outputs under the same task context,
3. normalize surviving evidence into task-required fields,
4. choose the best single-tool result or a justified merged result,
5. record the site's preferred tool order and fallback policy for repeat runs.

This file is the operator-facing rollout summary for the current validated sites.

## Current known tool set

1. `crawl4ai-cli`
2. `direct-http-html`
3. `curl-cffi`
4. `playwright`
5. `playwright-stealth`
6. `scrapy-cffi`
7. `local-agent-browser-cli`

## First-run execution rule

Use **all tools** on the first observed run for a site when any of the following is true:
- the site has no prior profile,
- the current profile is stale,
- the current profile confidence is low,
- the page type is materially different from the profile's previous evidence,
- the main tool begins failing or degrading.

## Output arbitration rule

After all tools run:
- discard login walls, captcha pages, slider pages, punish pages, empty shells, and other false positives;
- normalize all surviving outputs into task fields;
- compare field completeness, anti-bot stability, and downstream usefulness;
- choose one of:
  - `best_single_tool_output`
  - `merged_multi_tool_output`
  - `blocked_or_insufficient_evidence`

## Repeat-run rule

For later runs on the same site:
- start with the recorded primary tool;
- if blocked or weak, try fallbacks in the recorded order;
- if the top path degrades materially, force a new all-tools evaluation and refresh the site profile.

## Site records seeded from 2026-03-30 validation

### Amazon
- Mode: anonymous public crawl
- Current practical result: usable
- Primary tool: `crawl4ai-cli`
- Preferred order:
  1. `crawl4ai-cli`
  2. `local-agent-browser-cli`
  3. `scrapy-cffi`
  4. `playwright-stealth`
  5. `playwright`
  6. `curl-cffi`
  7. `direct-http-html`
- Notes:
  - Multiple tools are usable.
  - `crawl4ai-cli` is the current default because it gave the strongest task-side structured result in the latest site profile.
  - `direct-http-html` is not a good default here.

### Walmart
- Mode: anonymous public route-specific
- Current practical result: mostly blocked, but one route still produced usable HTML in current validation
- Primary tool: `direct-http-html`
- Preferred order:
  1. `direct-http-html`
  2. `crawl4ai-cli`
  3. `curl-cffi`
  4. `local-agent-browser-cli`
  5. `playwright`
  6. `playwright-stealth`
  7. `scrapy-cffi`
- Notes:
  - Walmart currently shows strong anti-bot pressure.
  - Treat repeat runs as fragile even if `direct-http-html` works.
  - Re-run full matrix quickly if output shape changes.

### Temu
- Mode: browser-first anonymous
- Current practical result: usable
- Primary tool: `local-agent-browser-cli`
- Preferred order:
  1. `local-agent-browser-cli`
  2. `curl-cffi`
  3. `direct-http-html`
  4. `crawl4ai-cli`
  5. `scrapy-cffi`
  6. `playwright`
  7. `playwright-stealth`
- Notes:
  - Browser-driven extraction currently wins clearly.
  - HTTP-oriented routes should be treated as weak probes unless they improve in later tests.

### 1688 (anonymous profile)
- Mode: anonymous blocked / truth-check only
- Current practical result: blocked or insufficient
- Primary tool: none for production extraction
- Preferred order for diagnostic retries:
  1. `curl-cffi`
  2. `scrapy-cffi`
  3. `crawl4ai-cli`
  4. `direct-http-html`
  5. `local-agent-browser-cli`
  6. `playwright`
  7. `playwright-stealth`
- Notes:
  - Anonymous results currently land in login, slider, punish, nocaptcha, or other challenged flows.
  - Do **not** treat current anonymous 1688 runs as task-usable extraction.
  - Authenticated mode must be handled as a separate profile.

## 1688 authenticated-mode policy

### Can username and password make the tools work?
Short answer: **maybe partly, not reliably by themselves**.

What credentials can help with:
- accessing content that is simply login-gated,
- establishing a valid user session,
- allowing browser-based post-login navigation when the site accepts the session normally.

What credentials do **not** guarantee:
- bypassing slider verification,
- bypassing captcha / nocaptcha flows,
- bypassing device-risk checks,
- bypassing punish / anti-bot enforcement,
- achieving unattended crawling with no human checkpoint.

### Safe implementation boundary
If Jacken explicitly authorizes 1688 login automation, the crawler layer may support:
- a **browser-based login workflow**,
- keeping an **authenticated 1688 profile separate from the anonymous profile**,
- using the logged-in browser session as an input to later extraction runs,
- pausing for human completion when slider/captcha/device verification appears.

The crawler layer must **not**:
- spray credentials into every crawler stack,
- attempt to bypass access controls,
- claim that username/password alone makes 1688 fully automatable.

## Required records per site going forward

Each site profile should keep:
- last evaluation date,
- tested tools,
- preferred tool order,
- blocked tools,
- known failure modes,
- recommended extraction mode,
- fallback policy,
- confidence,
- auth mode split where applicable.

## Verification references
- `crawler/logic/crawler-decision-policy.md`
- `crawler/logic/crawler_runner.py`
- `crawler/reports/amazon-latest-run.json`
- `crawler/reports/walmart-latest-run.json`
- `crawler/reports/temu-latest-run.json`
- `crawler/reports/1688-latest-run.json`
- `crawler/site-profiles/1688-auth-policy.md`
