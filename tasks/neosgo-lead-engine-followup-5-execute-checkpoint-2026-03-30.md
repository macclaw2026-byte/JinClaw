# neosgo-lead-engine-followup-5 execute checkpoint

## What I built
- Created a local multi-site bakeoff runner at `tmp/crawler-bakeoff/run_multisite_bakeoff.py`.
- The runner fixes the scope to four target sites for this measured pass:
  - Amazon
  - Walmart
  - Temu
  - 1688
- It runs the existing five crawler stacks against each site one by one:
  1. `official_api`
  2. `http_static`
  3. `scrapy_cffi`
  4. `crawl4ai_extract`
  5. `playwright_stealth`
- It stores raw per-site outputs plus a site-centric summary with tool ranking.

## Concrete run evidence
- Multi-site run output directory: `tmp/crawler-bakeoff/runs/20260330-062415/`
- Site summary file: `tmp/crawler-bakeoff/runs/20260330-062415/summary.json`
- Raw per-site files present under the same directory:
  - `amazon.json`
  - `walmart.json`
  - `temu.json`
  - `1688.json`

## Verified comparison results from this run

### Amazon
- `crawl4ai_extract`: **strong** (`status_code=200`, very large HTML/markdown capture)
- `official_api`: failed (`No module named 'httpx'`)
- `http_static`: failed (`No module named 'httpx'`)
- `scrapy_cffi`: failed (`No module named 'curl_cffi'`)
- `playwright_stealth`: failed (`No module named 'playwright'`)
- Current site-best tool in this environment: `crawl4ai_extract`

### Walmart
- `crawl4ai_extract`: **blocked** (`status_code=307`, robot/human verification page detected)
- `official_api`: failed (`No module named 'httpx'`)
- `http_static`: failed (`No module named 'httpx'`)
- `scrapy_cffi`: failed (`No module named 'curl_cffi'`)
- `playwright_stealth`: failed (`No module named 'playwright'`)
- Current site-best tool in this environment: `crawl4ai_extract`, but the site result is still blocked by anti-bot controls

### Temu
- `crawl4ai_extract`: **strong** (`status_code=200`, large HTML capture)
- `official_api`: failed (`No module named 'httpx'`)
- `http_static`: failed (`No module named 'httpx'`)
- `scrapy_cffi`: failed (`No module named 'curl_cffi'`)
- `playwright_stealth`: failed (`No module named 'playwright'`)
- Current site-best tool in this environment: `crawl4ai_extract`

### 1688
- `crawl4ai_extract`: **strong** (`status_code=200`, large HTML capture)
- `official_api`: failed (`No module named 'httpx'`)
- `http_static`: failed (`No module named 'httpx'`)
- `scrapy_cffi`: failed (`No module named 'curl_cffi'`)
- `playwright_stealth`: failed (`No module named 'playwright'`)
- Current site-best tool in this environment: `crawl4ai_extract`

## Important execution finding
- The requested “every site × every tool” bakeoff was executed structurally, but this environment currently lacks several Python modules required by four of the five stacks when invoked via the current runner path:
  - `httpx`
  - `curl_cffi`
  - `playwright`
- Therefore, the run is valid as an execution checkpoint and proves per-site/per-tool attempt coverage, but it is **not yet a fair quality comparison of all five stacks** because four stacks failed at environment/module level instead of site-behavior level.

## Security posture
- Stayed inside the local workspace.
- No new third-party downloads or installs were performed.
- No login bypass, captcha bypass, or high-risk external adoption was attempted.
- Security boundary preserved.

## Next recommended move
- Normalize the execution environment so all five stacks can run successfully from the same local interpreter path, then rerun the multi-site bakeoff to obtain a fair per-site comparative benchmark instead of a mostly dependency-failure benchmark.
