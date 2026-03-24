# Amazon Tooling Strategy

Use a tiered approach.

## Tier 1: Public and local tools (always available)
- browser
- Crawl4AI
- web_fetch
- resilient-external-research
- domain-data-harvester Amazon branch

Use for:
- listing extraction
- review-depth proxies
- price ladders
- competitor links
- public category signals

## Tier 2: External SaaS research tools (when user has access)
Examples:
- Helium 10
- Jungle Scout
- SellerSprite / 卖家精灵

Use for:
- keyword volume estimates
- BSR/sales estimates
- historical trend clues
- keyword competition clues

Important:
- these are not open-source local tools
- do not assume access exists
- if access exists, treat them as supplemental evidence, not unquestionable truth

## Tier 3: Local analysis layer
Use local scripts/spreadsheets/notebooks to:
- normalize data from multiple sources
- compare tool outputs
- infer daily sales range
- suppress weak candidates
