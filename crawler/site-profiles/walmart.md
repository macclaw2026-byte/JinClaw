# Walmart Site Profile

- Last evaluated: 2026-04-12
- Confidence: low
- Recommended mode: anonymous_public_crawl

## Preferred tool order
1. curl-cffi
2. crawl4ai-cli
3. scrapy-cffi

## Recommended default
- Primary: none
- Extraction decision: blocked_or_insufficient_evidence

## Task-ready fields from current best result
- No task-ready fields survived arbitration in the current anonymous run

## Known behavior
- crawl4ai-cli: status=blocked, arbitration_score=0, field_completeness=0.0, false_positive_reasons=['robot or human', 'confirm that you.?re human', 'activate and hold the button']
- curl-cffi: status=blocked, arbitration_score=0, field_completeness=0.25, false_positive_reasons=['robot or human']
- scrapy-cffi: status=blocked, arbitration_score=0, field_completeness=0.0, false_positive_reasons=['robot or human', 'confirm that you.?re human', 'activate and hold the button']

## Repeat-run policy
- Start with the first preferred tool
- If blocked or weak, try the next fallback in order
- If the top path degrades materially, trigger a fresh all-tools first-run evaluation