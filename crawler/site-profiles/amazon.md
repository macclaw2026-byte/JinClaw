# Amazon Site Profile

- Last evaluated: 2026-04-05
- Confidence: high
- Recommended mode: anonymous_public_crawl

## Preferred tool order
1. curl-cffi
2. playwright
3. scrapy-cffi

## Recommended default
- Primary: curl-cffi
- Extraction decision: best_single_tool_output

## Task-ready fields from current best result
- title: (empty)
- price: (empty)
- rating: (empty)
- reviews: (empty)
- link: (empty)

## Known behavior
- curl-cffi: status=usable, arbitration_score=90, field_completeness=0.0, false_positive_reasons=['none']
- playwright: status=usable, arbitration_score=90, field_completeness=0.0, false_positive_reasons=['none']
- scrapy-cffi: status=usable, arbitration_score=90, field_completeness=0.0, false_positive_reasons=['none']

## Repeat-run policy
- Start with the first preferred tool
- If blocked or weak, try the next fallback in order
- If the top path degrades materially, trigger a fresh all-tools first-run evaluation