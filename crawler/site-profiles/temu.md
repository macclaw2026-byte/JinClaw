# Temu Site Profile

- Last evaluated: 2026-04-12
- Confidence: medium
- Recommended mode: anonymous_public_crawl

## Preferred tool order
1. crawl4ai-cli
2. curl-cffi
3. scrapy-cffi

## Recommended default
- Primary: crawl4ai-cli
- Extraction decision: best_single_tool_output

## Task-ready fields from current best result
- title: (empty)
- price: (empty)
- promo: (empty)
- link: (empty)

## Known behavior
- crawl4ai-cli: status=partial, arbitration_score=25, field_completeness=0.0, false_positive_reasons=['none']
- curl-cffi: status=blocked, arbitration_score=0, field_completeness=0.0, false_positive_reasons=['login']
- scrapy-cffi: status=blocked, arbitration_score=0, field_completeness=0.0, false_positive_reasons=['none']

## Repeat-run policy
- Start with the first preferred tool
- If blocked or weak, try the next fallback in order
- If the top path degrades materially, trigger a fresh all-tools first-run evaluation