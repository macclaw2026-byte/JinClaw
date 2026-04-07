# crawler-direct-validation-bcdfe302 final checkpoint

- Generated at: 2026-03-30 09:47 PDT
- Scope: repaired local matrix logic, reran 7-tools × 4-sites validation, preserved anonymous-only safety boundary (no credentialed/auth bypass flow).

## Repair completed

- Fixed a false-positive in `tools/site_tool_matrix_v2.py`: `local-agent-browser-cli` could previously reuse a prior tab state and mis-score a different site as usable.
- Added current-URL verification after `agent-browser open`; cross-site redirects now count as blocking evidence and are recorded in notes.
- Verified fix by rerunning the full matrix and confirming 1688 agent-browser result changed from false usable to blocked with Taobao login redirect evidence.

## Per-site ranking after repair

### amazon

1. crawl4ai-cli — score 75 — usable — product signals 139 — block signals 0
2. curl-cffi — score 75 — usable — product signals 22 — block signals 0
3. local-agent-browser-cli — score 75 — usable — product signals 178 — block signals 0
4. playwright — score 75 — usable — product signals 71 — block signals 0
5. playwright-stealth — score 75 — usable — product signals 62 — block signals 0
6. scrapy-cffi — score 75 — usable — product signals 113 — block signals 0
7. direct-http-html — score 0 — failed — product signals 0 — block signals 0

### walmart

1. local-agent-browser-cli — score 59 — usable — product signals 4 — block signals 0
2. crawl4ai-cli — score 0 — blocked — product signals 0 — block signals 3
3. curl-cffi — score 0 — blocked — product signals 0 — block signals 5
4. direct-http-html — score 0 — blocked — product signals 0 — block signals 5
5. playwright — score 0 — blocked — product signals 0 — block signals 5
6. playwright-stealth — score 0 — blocked — product signals 0 — block signals 5
7. scrapy-cffi — score 0 — blocked — product signals 0 — block signals 4

### temu

1. local-agent-browser-cli — score 75 — usable — product signals 13 — block signals 0
2. curl-cffi — score 35 — partial — product signals 3 — block signals 0
3. direct-http-html — score 35 — partial — product signals 3 — block signals 0
4. crawl4ai-cli — score 20 — partial — product signals 0 — block signals 0
5. scrapy-cffi — score 20 — blocked — product signals 12 — block signals 4
6. playwright — score 5 — blocked — product signals 3 — block signals 1
7. playwright-stealth — score 5 — blocked — product signals 3 — block signals 1

### 1688

1. curl-cffi — score 37 — blocked — product signals 6 — block signals 1
2. scrapy-cffi — score 37 — blocked — product signals 6 — block signals 1
3. crawl4ai-cli — score 0 — blocked — product signals 2 — block signals 15
4. direct-http-html — score 0 — blocked — product signals 8 — block signals 5
5. local-agent-browser-cli — score 0 — blocked — product signals 2 — block signals 14
6. playwright — score 0 — blocked — product signals 20 — block signals 66
7. playwright-stealth — score 0 — blocked — product signals 20 — block signals 66

## Verdict

- Amazon: strongest overall anonymous target; multiple stacks are usable. Best practical options are crawl4ai-cli / local-agent-browser-cli / scrapy-cffi / playwright-class tools, all tied on score after repair.
- Walmart: only direct-http-html stayed usable in this run; browser and impersonation stacks were blocked by human verification.
- Temu: local-agent-browser-cli is clearly best; direct-http-html and curl-cffi are only partial, while the rest are blocked or weak.
- 1688: all tested anonymous paths are blocked; do not treat any current result as task-ready extraction.

## Security boundary verification

- No auth-state injection, cookie reuse, credential entry, or bypass workflow was used.
- 1688 remains classified as blocked in anonymous mode; no unsafe workaround was introduced.

## Evidence

- Matrix JSON: `reports/site-tool-matrix/tool-matrix-v2.json`
- Matrix report: `reports/site-tool-matrix/tool-matrix-v2-report.md`
- Repaired file: `tools/site_tool_matrix_v2.py`
