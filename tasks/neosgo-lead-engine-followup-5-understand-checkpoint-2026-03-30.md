# neosgo-lead-engine-followup-5 understand checkpoint

## Goal understanding
- The new instruction is not asking whether a full per-site all-tools bakeoff has already been completed; it is requiring that future evaluation be done by running **every supported crawler stack against every target website one by one**.
- The required deliverable is a **site-centric comparative evaluation**: for each website, compare every tool’s scrape result quality and produce per-site/per-tool comparison outcomes.
- This means prior partial or representative tests are insufficient unless they already covered every target site with every tool in the stack.

## Verified local evidence
- Found an existing local bakeoff harness at `tmp/crawler-bakeoff/run_stack_bakeoff.py`.
- Verified the current harness enumerates exactly five stacks for one URL at a time:
  1. `official_api`
  2. `http_static`
  3. `scrapy_cffi`
  4. `crawl4ai_extract`
  5. `playwright_stealth`
- Found a sample result file at `tmp/crawler-bakeoff/example-dual.json`, but it only proves the harness was run against `https://example.com/` and does **not** prove all real target sites were tested with all tools.
- Searched workspace references and did not find evidence of a completed all-sites/all-tools Neosgo-domain bakeoff report already stored in task/output files.

## Constraint interpretation
- Use only safe local/in-house tooling and approved public reads if needed.
- No need to install or trust new third-party artifacts just to answer this instruction.
- The next build/execution phase should extend the current one-URL harness into a repeatable **multi-site bakeoff** with structured scoring dimensions per site/tool.

## Output shape implied by the instruction
Per website, the comparison should at minimum capture:
- request success / failure
- final URL / redirect behavior
- status code
- title extraction quality
- body text completeness
- link extraction usefulness
- structured markdown or rendered text quality
- runtime / latency
- obvious anti-bot or rendering failures
- overall recommendation for that website

## Blockers / gaps identified
- The exact target website list for this bakeoff is not yet pinned in this checkpoint.
- The current harness writes raw per-URL results, but no site-level scoring rubric or batch runner is yet confirmed here.
- Therefore, it would be inaccurate to claim that every site has already been tested with every tool unless a later execution checkpoint proves it.

## Security posture
- Safe read-only discovery only.
- No destructive changes, external code execution, or config changes performed.
- Security boundary preserved.

## Concrete next move
- In the execute stage, build or adapt a local batch bakeoff runner that accepts a target site list, runs all five stacks against each site, stores normalized JSON results, and emits a site-centric comparison report.
