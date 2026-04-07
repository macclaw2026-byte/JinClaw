# Crawler Decision Policy v1

## Goal
For a website's first observed run, execute all known crawler tools, compare the outputs, normalize the evidence, choose the best surviving result set for the task, and record the preferred tools plus fallback order for later runs.

## Current known tools
1. crawl4ai-cli
2. direct-http-html
3. curl-cffi
4. playwright
5. playwright-stealth
6. scrapy-cffi
7. local-agent-browser-cli

## First-run rule
When a site has no existing profile, or the profile is marked stale / low-confidence / changed:
- run all known tools
- store raw outcomes per tool
- score each outcome on:
  - accessibility success
  - anti-bot / login / verification signals
  - product/data signal density
  - structural cleanliness
  - downstream usefulness for the task
- classify each tool result as:
  - usable
  - partial
  - blocked
  - failed

## Comparison and arbitration workflow
After running all tools:
1. remove clear false positives (captcha pages, login pages, punish scripts, empty shells)
2. normalize surviving outputs into task fields
3. compare field completeness across tools
4. choose one of:
   - best single tool output
   - merged multi-tool output
   - blocked / insufficient evidence

## Downstream output rule
Do not dump raw page text to the task.
Instead output task-ready information only, such as:
- product candidates
- price / title / rating / listing links
- supplier references
- structured evidence records
- confidence + provenance notes

## Repeat-run rule
For repeat runs on a known site:
- start with the recorded primary tool
- if blocked or weak, try the next fallback in order
- if the top tools degrade materially, trigger a full re-evaluation with all tools

## Re-evaluation triggers
Force full all-tools re-run when any of these happen:
- primary tool becomes blocked
- page structure changes sharply
- output completeness drops materially
- site profile is older than the chosen freshness window
- the task asks for a new page type not covered by the profile

## Site-profile file contract
Each site profile should record:
- site name
- last evaluation date
- tested tools
- preferred tool order
- blocked tools
- notes about known failure modes
- first-choice extraction mode
- fallback policy
- confidence level

## Authentication policy
Anonymous and authenticated modes must be treated separately.
A site that is blocked anonymously must not automatically be assumed solvable by credentials alone.
For authenticated support:
- require explicit user authorization
- prefer browser-based login flows over raw credential replay
- do not bypass sliders / captchas / intended access controls
- credentials should only be used if the user explicitly wants that site automated and the workflow can stay within ordinary login boundaries

## Current standing note on 1688
Based on current evidence, 1688 is blocked anonymously by login / slider / punish flows.
Providing a username and password may help with login-gated content, but does not guarantee the tools can clear slider / captcha / device-risk checks unattended. It may require a browser-based authorized session workflow and still may need human verification if the site challenges login.
