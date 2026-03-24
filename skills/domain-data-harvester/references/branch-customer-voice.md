# Customer Voice Branch

Use this branch for review mining, complaint clustering, unmet-need discovery, and buyer-language extraction.

## Goal

Turn scattered review/community text into structured fields useful for product selection and marketing.

## Good source surfaces
- review pages
- complaint threads
- community discussions
- comparison pages
- public Q&A

## Recommended tool stack
- primary: web_fetch or local Crawl4AI
- backup: browser
- backup: resilient-external-research

## Key fields
- recurring complaint theme
- desired benefit
- missing feature
- exact buyer-language phrase
- severity/frequency estimate
- positive proof themes

## Downstream targets
- product-selection-engine
- us-market-growth-engine
- safe-learning-log when a recurring complaint pattern suggests a reusable heuristic
