<!--
RULES-FIRST NOTICE:
Before modifying this file, first read:
- `JINCLAW_CONSTITUTION.md`
- `AI_OPTIMIZATION_FRAMEWORK.md`
Follow the constitution and framework:
brain-first, one-doctor, fail-closed, evidence-over-narration,
validate locally, then use the required PR workflow.
-->
# NEOSGO SEO + GEO Hardcore Automation Plan

Date: 2026-04-14

## Why this plan exists

The current engine already runs daily and publishes notes plus GEO variants, but it is still closer to a productive content bot than a full search operating system.

The next stage should turn it into a durable loop that can:

- choose the right opportunity set
- decide whether to create, refresh, merge, or prune
- generate assets with stronger local differentiation
- validate technical readiness before release
- measure post-release outcome with the correct source of truth
- learn and reweight the backlog continuously

## Current-state diagnosis

Based on the live project files on this machine:

- execution entrypoint: `scripts/run_neosgo_seo_geo_cycle.py`
- current config mode: `publish_live`
- `publish_allowed: true`
- `daily_create_limit: 2`
- `daily_geo_variant_limit: 4`
- feedback ingestion is enabled
- GSC sync support exists
- Telegram reporting is working

What is good:

- the daily loop is real, not theoretical
- the system already ingests historical signal
- there is a concept of topic families and GEO clusters
- there is a quality gate and a reporting surface

What is still weak:

- topic selection is still too narrow and too manually framed
- publish risk is too high for a system that is still learning
- GEO differentiation can drift into templated city-page behavior
- there is no strong canonical cluster management layer
- there is no explicit create vs refresh vs merge vs prune decision engine
- there is no hard technical release gate for schema, internal links, crawlability, duplication risk, and canonical hygiene
- reporting is useful, but not yet a full operating scorecard

## Research basis

This plan is grounded in three source families: Google guidance, search/IR research, and practical system constraints.

### Google guidance

People-first content:

- Google Search Central, "Creating helpful, reliable, people-first content":
  https://developers.google.com/search/docs/fundamentals/creating-helpful-content

Search measurement and debugging:

- Google Search Central, "Using Search Console and Google Analytics data for SEO":
  https://developers.google.com/search/docs/monitor-debug/google-analytics-search-console
- Google Search Central, "Debugging drops in Google Search traffic":
  https://developers.google.com/search/docs/monitor-debug/debugging-search-traffic-drops

Canonicalization and crawl hygiene:

- Google Search Central, "What is canonicalization":
  https://developers.google.com/search/docs/crawling-indexing/canonicalization
- Google Search Central, "Troubleshoot crawling errors":
  https://developers.google.com/search/docs/crawling-indexing/troubleshoot-crawling-errors
- Google Search Central, "Crawl budget management for large sites":
  https://developers.google.com/search/docs/crawling-indexing/large-site-managing-crawl-budget

Local business and business detail signals:

- Google Business Profile Help, "Tips to improve your local ranking on Google":
  https://support.google.com/business/answer/7091
- Google Search Central, "Add business details to Google":
  https://developers.google.com/search/docs/appearance/establish-business-details
- Google Search Central, "LocalBusiness structured data":
  https://developers.google.com/search/docs/appearance/structured-data/local-business
- Google Search Central, "Organization structured data":
  https://developers.google.com/search/docs/appearance/structured-data/organization

### Retrieval and intent research

Intent-aware prioritization:

- ORCAS-I, weakly supervised intent classification for web queries:
  https://arxiv.org/abs/2205.00926

Exact plus semantic relevance matching:

- Duet / local plus distributed matching for web search:
  https://arxiv.org/abs/1610.08136
- DeepRank / local relevance plus aggregation:
  https://arxiv.org/abs/1710.05649

### Practical operating lesson

For this project, the most important practical lesson is that SEO and GEO should not be run as a pure content-generation queue. They should be run as a decision engine over a managed inventory.

## Design principles

- Search Console is the source of truth for search visibility.
- Analytics is the source of truth for on-site behavior and conversion.
- Google Business Profile and local business signals are a separate evidence family, not a substitute for site quality.
- GEO pages must earn their existence through differentiated utility, not city-name substitution.
- A page should be created only if it beats refresh, merge, redirect, or prune as the best move.
- Every release must pass both content quality gates and technical release gates.
- Every daily run must leave behind enough evidence to explain why each action was chosen.

## Target operating model

### Layer 1: Opportunity intelligence

Build a canonical `opportunity registry` with one row per:

- topic cluster
- page cluster
- geo cluster
- product/category cluster

Each row should track:

- demand signal from Search Console
- conversion signal from Analytics
- local business/entity support signal
- freshness decay
- overlap or cannibalization risk
- internal-link deficit
- schema deficit
- competition or SERP pattern notes
- recommended action

Valid actions:

- create
- refresh
- expand
- merge
- redirect
- prune
- hold

### Layer 2: Intent and cluster strategy

Instead of a small fixed list of topic families, maintain:

- informational decision clusters
- commercial investigation clusters
- comparison clusters
- local GEO landing clusters
- trade or specification clusters
- post-purchase or support clusters

Each cluster needs:

- primary intent type
- secondary intent type
- entity set
- recommended page type
- required proof elements
- internal-link targets

The research reason for this is straightforward:

- user intent is not one-dimensional
- exact term matching and semantic matching both matter
- local landing pages need both geographic relevance and decision utility

### Layer 3: Create vs refresh vs merge engine

Before writing anything new, score these options:

- refresh an existing strong page
- merge overlapping pages into a canonical winner
- create a new base page
- create a GEO derivative
- redirect weaker duplicates
- do nothing

Required signals:

- existing page clicks
- existing page impressions
- CTR opportunity
- average position band
- conversion contribution
- overlap similarity
- canonical conflict risk
- freshness age
- editorial quality score

Decision rule:

- create only when no existing page can absorb the demand efficiently
- GEO create only when the geo layer has unique value, not just place-name substitution

### Layer 4: GEO differentiation engine

Every GEO page should be built from a reusable local evidence packet:

- location-specific delivery or service relevance
- local style or project context
- product availability or assortment relevance
- local trust proof
- local FAQ or constraints
- internal links to matching category paths

If the page cannot clear a local differentiation threshold, it should not exist as a standalone GEO page.

Required GEO gates:

- differentiated intro
- differentiated recommendation logic
- differentiated FAQ or proof block
- unique internal link set
- unique schema values
- canonical reviewed

### Layer 5: Technical release gate

No page should be published without a machine-readable technical checklist:

- canonical present and correct
- indexability confirmed
- duplicate-risk score acceptable
- internal links inserted
- breadcrumb or hierarchy fit confirmed
- schema valid
- business/entity details consistent
- title and description within bounds
- no empty or placeholder sections

This should be evaluated before any publish call.

### Layer 6: Measurement and evaluation

Use a two-truth measurement model:

- Search Console for impressions, clicks, CTR, average position, query mix, page mix
- Analytics for engaged sessions, trade-program conversions, lead-form completion, downstream commercial signals

Score every page cluster with:

- visibility score
- traffic quality score
- conversion score
- freshness score
- local differentiation score
- technical hygiene score
- cannibalization risk score

### Layer 7: Reflection and continuous reweighting

Every completed cycle should emit:

- chosen actions
- rejected alternatives
- outcome scorecard
- losers and winners
- proposed weight updates
- reusable editorial lessons
- reusable technical lessons

This becomes the input for the next run.

## Automation cadence

### Daily

- sync Search Console when available
- sync Analytics export when available
- refresh page-cluster scorecards
- choose create or refresh actions
- generate drafts only unless promotion gate passes
- publish only low-risk actions that already have a strong history of quality
- send report

### Weekly

- detect cannibalization and overlap clusters
- identify stale pages to refresh
- identify thin GEO pages to merge or prune
- review schema coverage
- update internal-link deficits

### Monthly

- cluster consolidation
- redirect plan generation
- full canonical review
- archive or retire weak GEO pages
- re-estimate scoring weights from observed outcomes

## Recommended scoring system

Use a weighted scorecard at the page-cluster level:

- demand score: 0.22
- commercial value score: 0.20
- freshness decay score: 0.10
- gap severity score: 0.12
- local differentiation score: 0.12
- technical readiness score: 0.10
- internal-link leverage score: 0.06
- cannibalization penalty: -0.12
- duplication risk penalty: -0.10

Page actions should then be chosen from thresholds, not intuition.

## Safe rollout plan

### Phase 1: Observation-first

- switch default mode back to draft-first until the new scorecard is validated
- create the opportunity registry
- add technical release gate
- add daily outcome scorecard

### Phase 2: Controlled automation

- allow automatic refreshes for low-risk existing winners
- keep new GEO pages draft-only
- keep merge, redirect, and prune decisions human-reviewed

### Phase 3: Mature automation

- auto-refresh strong winners
- auto-publish only when content and technical gates are both green
- auto-prune only after repeated weak performance plus overlap proof

## Concrete implementation blueprint

1. Add `opportunity_registry.json` and `page_cluster_registry.json`.
2. Add a `page_action_decider` stage before content generation.
3. Add a `geo_differentiation_evaluator`.
4. Add a `technical_release_gate`.
5. Add a `post_publish_scorecard` fed by Search Console and Analytics.
6. Add weekly and monthly maintenance jobs.
7. Add rule promotion from reflection outputs into strategy weights.

## What should change first in this repo

Priority 1:

- change `publish_live` back to guarded draft-first rollout
- add create vs refresh vs merge scoring
- add a machine-readable technical release contract

Priority 2:

- expand topic-family logic into intent and page-cluster registries
- add local differentiation packets for GEO pages
- wire Search Console and Analytics into a single scorecard

Priority 3:

- add weekly and monthly maintenance jobs
- add prune and redirect planning
- add automatic reweighting from outcome history

## End-state definition

The system is mature when:

- every daily action is explainable
- new pages are created less often, but with higher hit rate
- refresh decisions outperform random new-page generation
- GEO pages are clearly differentiated and technically clean
- weak pages are merged, redirected, or retired instead of silently accumulating
- the engine learns from search and conversion outcomes every week
