# Amazon Marketplace Branch

Use this branch for Amazon-oriented product-selection or marketplace evidence gathering.

## Goal

Collect structured public evidence that helps infer:
- demand strength
- review depth
- price ladder
- competition survivability
- likely stable-sales behavior

## Good source surfaces
- search results pages
- product pages when publicly accessible
- bestseller/category pages when useful
- visible ranking/review/variant structures

## Recommended tool stack
- primary: browser or local Crawl4AI
- backup: guarded-agent-browser-ops
- backup: resilient-external-research + alternative public surfaces

## Key fields
- query/product phrase
- top listing titles
- top listing prices
- review counts
- rating patterns
- variant depth clues
- category/rank clues when visible
- notable listing repetition / same-product saturation

## Downstream targets
- product-selection-engine
- resilient-external-research
- safe-learning-log when extraction repeatedly fails or conflicts
