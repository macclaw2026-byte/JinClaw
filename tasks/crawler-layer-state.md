# Crawler Layer State

## Task
Build and maintain a crawler-layer decision logic that, for a first-time website, runs all known tools, compares and normalizes results, outputs task-ready information, and records the preferred tool stack and fallback order for future runs.

## Current Stage
Stage 4 - Compare/normalize workflow contract is now executable and auto-written from latest site reports; next step is separating authenticated profiles where needed

## Completed Stages
- Stage 1: Repair tool matrix execution chain, including local agent-browser CLI CDP connectivity
- Stage 1: Run first 7-tools × 4-sites matrix on Amazon, Walmart, Temu, and 1688
- Stage 2: Confirm requirement to add crawler-layer first-run logic + site preference records
- Stage 2: Write crawler decision policy and site profile records
- Stage 2: Re-audit the latest matrix evidence and correct over-optimistic interpretation for 1688

## Pending Stages
- Stage 3: Build a reusable compare/normalize workflow contract for future tasks
- Stage 4: Integrate first-run-all-tools behavior into task execution scripts
- Stage 5: Add optional authenticated-site policy for authorized login workflows
- Stage 6: Separate anonymous site profiles from authenticated site profiles where needed

## Acceptance Criteria
- A crawler-layer policy exists describing first-run and repeat-run behavior
- Site profile files exist for Amazon, Walmart, Temu, and 1688 with preferred tool order
- The policy explains how outputs are compared and selected for downstream tasks
- Authenticated-site policy is explicit about what can and cannot be automated safely

## Current Site Reality Check
- Amazon: currently the clearest verified public-crawl win; `crawl4ai_extract` is the strongest measured path in the latest local run
- Walmart: current anonymous path is blocked by human-verification / anti-bot response
- Temu: latest verified repeat-run evidence now stabilizes on `local-agent-browser-cli` as the best anonymous public route; current contract records `best_status=usable`, `best_score=80`, with `crawl4ai-cli` only partial and the HTTP / Playwright family blocked by login-style responses
- 1688: anonymous mode must not be treated as stably usable for task extraction; large HTML alone was a false-positive signal and should not be considered sufficient evidence

## Blockers
- 1688 currently cannot be treated as a stable anonymous extraction target for task use
- Authenticated flows require explicit credential-handling policy and careful browser-state handling
- The latest all-tools bakeoff still contains environment-level module failures for several stacks, so cross-tool ranking is not yet fully fair

## Next Step
- Use the now-stable Temu anonymous best-tool result (`local-agent-browser-cli`) to push task-side evidence generation forward, while keeping authenticated-mode support as a separate, explicitly authorized workflow

## Last Updated
2026-03-30T07:45:00-07:00
