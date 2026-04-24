<!--
RULES-FIRST NOTICE:
Before modifying this file, first read:
- `JINCLAW_CONSTITUTION.md`
- `AI_OPTIMIZATION_FRAMEWORK.md`
Follow the constitution and framework:
brain-first, one-doctor, fail-closed, evidence-over-narration,
validate locally, then use the required PR workflow.
-->
# NEOSGO Social + GEO Operating Blueprint

## Goal

Build a continuous operating line that turns NEOSGO's public website, social
surfaces, and off-site mentions into a compounding SEO + GEO + brand-reputation
 system.

This line is not "post more social content." It is:

1. one factual source of truth
2. one content package that can be distributed across multiple surfaces
3. one measurement loop that turns public signals back into the next weekly plan

## Operating Thesis

For NEOSGO, social media helps SEO and GEO in four ways:

1. it grows branded search demand
2. it strengthens brand-entity consistency across public surfaces
3. it creates public content that search engines and LLMs can cite or learn from
4. it increases third-party mentions, reviews, and authority signals

Social content should therefore serve the site, not drift away from it.

Every major topic should become a reusable content package:

- answer page on site
- category or product refresh on site
- FAQ block on site
- Pinterest pin set
- Instagram carousel
- short video script

## Phase Plan

### Phase 0: Recovery and Instrumentation

Goal: restore the existing SEO + GEO pipeline and make the social extension observable.

Actions:

- validate `NEOSGO_ADMIN_MARKETING_KEY`
- validate `NEOSGO_ADMIN_AUTOMATION_KEY`
- restore daily SEO + GEO delivery
- connect Bing AI Performance
- connect Google Search Console if not already enabled
- add readiness checks for social prerequisites

Done when:

- daily SEO + GEO run is no longer blocked by inactive token errors
- readiness report exists and lists missing operator inputs

### Phase 1: Brand Truth Source

Goal: create one canonical public-facts layer for NEOSGO.

Required facts:

- brand name and summary
- primary categories
- top SKUs / collections
- styles
- rooms / use cases
- material / finish / dimension facts
- price bands
- shipping / returns / warranty / lead time
- differentiators
- approved claims
- forbidden claims

Artifacts:

- `brand-facts-master.json`
- `brand-asset-library.json`
- `top-sku-priority-list.json`

Done when:

- content generation no longer relies on ad-hoc copy
- social posts and site pages derive from the same fact set

### Phase 2: Surface Buildout

Goal: establish the first durable public surfaces.

Priority order:

1. Google Brand Profile or Business Profile
2. Pinterest Business
3. Instagram Business
4. authority / review / mention monitoring

Site surfaces to strengthen in parallel:

- homepage trust section
- about page
- category pages
- product pages
- FAQ pages
- comparison / answer pages

Done when:

- public profiles exist and are consistent
- `sameAs` targets are known and ready for structured data

### Phase 3: Weekly Content Packages

Goal: create repeatable growth instead of one-off posts.

Each weekly package should contain:

- one site answer page or major refresh
- one Pinterest board update
- 3 to 5 Pinterest pins
- one Instagram carousel
- one short-form video script
- one FAQ or product-spec enhancement

The first 30-day topic families should focus on:

- chandelier sizing and placement
- vanity light sizing and mirror fit
- entryway and foyer lighting choices
- black vs brass finish decisions
- dining-room statement lighting
- layered living-room lighting

Done when:

- weekly cadence can run without new prompt design every week

### Phase 4: Measurement and Iteration

Goal: decide what to expand, refresh, merge, or stop.

Primary KPIs:

- branded search growth
- cited pages
- AI citation count
- social-to-site sessions
- assisted revenue
- review volume and sentiment
- page-level organic click growth

Weekly review should answer:

- which pages are getting discovered
- which social themes are generating clicks
- which products are mentioned or saved most often
- which pages or posts deserve expansion
- which pages remain invisible and need stronger answers or entities

## Database Contract

Recommended tables in the local PostgreSQL platform:

- `core.brand_fact`
- `core.social_asset`
- `core.social_post`
- `core.offsite_mention`
- `core.geo_citation`
- `core.review_event`
- `mart.brand_visibility_daily`
- `mart.social_to_search_lift`

## What The Operator Must Provide First

These are the first concrete things needed from the human side:

1. Pinterest Business access
2. Instagram Business access
3. Google Brand Profile or Business Profile access
4. Bing Webmaster Tools access
5. brand facts master file
6. brand asset library file
7. top SKU priority list

The project now expects those files under:

- `projects/neosgo-seo-geo-engine/runtime/operator-inputs/`

## 30-Day Rollout

### Week 1

- restore SEO + GEO daily health
- complete readiness check
- gather operator inputs
- connect Bing AI Performance and GSC

### Week 2

- publish first 10 answer-led site updates
- finalize Pinterest and Instagram templates
- ship first three weekly content packages

### Week 3

- begin daily mention and citation monitoring
- publish another three weekly content packages
- review top-performing pages and posts

### Week 4

- compare branded search, citations, clicks, and social traffic
- prune low-value themes
- expand the top-performing product / room / style clusters

## Fail-Closed Rules

- no social content should assert facts that are not in the brand truth source
- no mass AI content should publish without factual validation
- no channel should be treated as "ready" without explicit access evidence
- no weekly plan should expand a theme without measurement evidence
