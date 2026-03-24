---
name: product-selection-engine
description: General-purpose ecommerce product-selection skill for US-focused product research, validation, and decision-making across platforms such as Amazon, Walmart, independent sites, and other ecommerce channels. Use when selecting products, evaluating niches, comparing category opportunities, studying trends, estimating competition and demand, analyzing public sales signals, or building a repeatable product-selection framework that can later branch into platform-specific skills.
---

# Product Selection Engine

Use `../self-cognition-orchestrator/references/monitoring-and-retrofit-framework.md` as the shared monitoring standard when applying this skill's monitoring, backstop, and retrofit logic.

Build product-selection decisions from evidence, not vibes.

## Purpose

This is the core in-house product-selection skill.

It should work as a general model first, then support future platform-specific extensions such as:

- Amazon product selection
- Walmart product selection
- independent-site product selection
- niche/category extensions

## Core principle

Do not pick products only because they look popular.

Also do not trust one metric, one marketplace clue, or one research method. Product-selection decisions need layered monitoring because different categories fail in different ways.

Prefer products that are:

- backed by real demand signals
- commercially viable
- platform-appropriate
- operationally manageable
- not fatally overcrowded
- capable of supporting repeatable growth


## Automatic exclusion rules

Before scoring or recommending any candidate, apply these exclusion gates automatically:

### 1. Exclude food, ingestible, body-contact, and regulated health products by default

Do not recommend any of the following as default product-selection outputs for this skill, even if they are trending or high-volume:

- food
- beverages
- edible supplements
- ingestible consumables
- pharmaceuticals / drug-like products
- health products with material compliance burden
- body-contact formulations or personal-care chemistry-heavy items such as shampoo, conditioner, body wash, and similar products applied to the body

This default exclusion includes examples such as:
- snacks
- drinks
- mushroom coffee
- gummies consumed as supplements or wellness products
- edible health products
- medicines or quasi-medicinal products
- shampoo
- body wash
- similar personal-care / body-contact formulation categories

Reason:
- higher compliance and claims risk
- shelf-life and storage complexity
- formulation and quality-control burden
- elevated return, safety, and trust risk
- greater manufacturing and liability complexity

If such products appear in trend research, they may be logged as market signals, but should be automatically filtered out from the final shortlist unless the user explicitly requests that regulated/body-contact domain.

### 2. Exclude strong brand / IP / infringement-risk products

Automatically reject product ideas that depend on another company's protected brand, character, franchise, design language, or obvious trademark/IP association.

Examples to avoid include products built around or strongly tied to names or IP such as:
- Apple
- Disney
- Nike
- Sony
- Pokemon
- other clearly protected brands, franchises, characters, or trade dress

Use public branded products only as inspiration for:
- feature patterns
- consumer pain points
- design language at an abstract level
- product category insight

Do not recommend copying:
- logos
- character likenesses
- brand names
- proprietary visual identity
- distinctive protected trade dress
- obvious knockoff positioning

### 3. Exclude ideas with unresolved manufacturing reality

If a product concept looks attractive in theory but there is weak evidence that existing manufacturing or supply-chain capability can produce it affordably and reliably, downgrade or reject it until feasibility is clearer.


## Data-source model

Use a broader multi-layer acquisition model. Do not rely on only one or two obvious public sources.

### 1. External methodology layer

Study how experienced sellers, operators, and researchers publicly approach product selection.

Gather:
- public product-research frameworks
- public selection heuristics
- public niche-analysis methods
- public ecommerce research playbooks
- marketplace-specific seller discussions and operating advice

Use this layer to improve the skill itself, not to copy blindly.

### 2. Macro trend layer

Gather broad trend signals from sources such as:

- Google Trends
- Pinterest Trends
- Reddit
- public platform trend pages
- public social/discovery trend signals
- platform search suggestions and autocomplete
- search-result theme clustering across multiple public surfaces

Use this layer to understand:
- rising vs falling interest
- seasonal vs durable demand
- keyword/theme momentum
- buyer-intent language

### 3. Marketplace demand layer

Study public marketplace signals such as:

- bestseller and ranking clues
- review count
- review recency / likely velocity clues
- recent sales badges or purchase hints when publicly shown
- price bands
- buy-box and offer count clues where public
- variant count
- listing density
- new listing volume
- repeated presence across search, category, and related-product surfaces

### 4. Search-and-discovery layer

Use search/discovery behavior as an additional signal layer:

- autocomplete phrases
- related searches
- category breadcrumbs
- “customers also bought/viewed” style public relationships
- forum / community problem-language patterns
- gift-guide / roundup / comparison-page recurrence

This layer helps identify:
- problem framing
- how buyers naturally describe the need
- adjacent use cases and bundles

### 5. Competition-intelligence layer

Estimate how crowded and survivable the niche is:

- number of similar offers
- homogeneity of listings
- review moat intensity
- pricing compression
- obvious brand dominance
- repeated same-product packaging with little differentiation
- whether smaller sellers appear to coexist or get squeezed out

### 6. Product-structure layer

Examine the product itself as a system:

- materials
- dimensions / weight class
- fragility
- refill vs one-time purchase
- accessory / consumable / bundle potential
- customization potential
- sourcing/manufacturing plausibility

### 7. Customer-problem layer

Look for evidence of the underlying job-to-be-done:

- pain points
- convenience needs
- comfort / organization / storage / safety / gifting / aesthetics drivers
- frequent complaint themes
- missing-feature patterns

### 8. Internal/business layer

Use internal logic and available first-party reasoning to judge:

- margin model
- shipping burden
- breakage risk
- return risk
- support complexity
- compliance/certification issues
- long-term category fit

### 9. Cross-verification layer

Before concluding, cross-check the candidate across multiple independent layers so the final decision is not being carried by one noisy source.

## Research workflow

### Step 1: Define the selection mission

Clarify:
- target platform
- target customer type
- short-term test vs long-term brand play
- price band
- margin expectations
- fulfillment constraints

### Step 2: Gather public methodology

Use `resilient-external-research` and browser/search capabilities to collect how experienced sellers/researchers evaluate products.

Do not blindly trust one source. Extract patterns and compare methods.

### Step 3: Expand source coverage before narrowing

When gathering candidate data, intentionally widen source coverage.

Try to collect from multiple source families when possible:
- trend sources
- marketplace public pages
- search/autocomplete/discovery surfaces
- community/forum/problem-language sources
- comparison/review/roundup sources
- supplier/manufacturing plausibility sources

The goal is broader evidence, not just more volume.

### Step 4: Gather trend and discovery data

Use trend and discovery sources to collect:
- category terms
- keyword momentum
- theme/style momentum
- seasonal pattern clues
- discussion/interest signals
- autocomplete and related-search language
- adjacent problem/use-case language

### Step 5: Gather platform behavior data

For sample candidate products/categories, collect:
- review counts
- visible sales clues
- price bands
- competitor count or density clues
- listing similarity
- new product volume
- offer-count / variant / repetition clues

### Step 6: Estimate real demand quality

Use proxy signals to estimate whether products are actually moving, not just visible.

Good proxy signals include:
- review count + likely recency
- recent sales badges / purchase counts when publicly shown
- bestseller/rank clues
- new listing velocity
- repeated presence across competitors

### Step 6.5: Deepen evidence and cross-verify

Before moving on, ask whether the candidate has enough multi-source support.

Strengthen the case by checking:
- whether different source families tell the same story
- whether marketplace clues align with search/discovery clues
- whether buyer-problem language aligns with the proposed product use case
- whether manufacturability and product structure support the idea

If evidence is still shallow, continue gathering rather than scoring too early.

### Step 7: Evaluate competition

Ask:
- is competition intense but still differentiated?
- or is it a saturated same-product war?
- can brand/story/quality/channel positioning still create room?

### Step 8: Evaluate commercial viability

Check:
- gross margin potential
- logistics cost
- return risk
- breakage risk
- support complexity
- regulatory or certification burden
- manufacturing feasibility
- whether current market supply suggests the concept can actually be produced and sourced

### Step 9: Abstract winning selling points

When market data is strong, do not only copy visible product forms. Also extract the underlying selling logic:
- what pain point is being solved
- what convenience or delight is driving demand
- what material / format / use-case is resonating
- what emotional or functional promise appears to matter

Turn those observations into abstract product principles first.

### Step 10: Reverse-map into producible concepts

After abstracting the selling points, ask:
- are there already similar non-infringing products in market?
- can this selling point be expressed through a safer, more brandable, lower-risk product concept?
- does current manufacturing/sourcing capability appear able to produce it?
- can the idea be differentiated without copying protected IP or branded trade dress?

This reverse path is allowed and encouraged:

1. find data signal
2. abstract the real selling point
3. search for comparable non-infringing market examples
4. judge production feasibility
5. only then score the concept

### Step 11: Score and decide

Use a structured score across:
- demand
- trend quality
- competition density
- differentiation room
- margin quality
- logistics friendliness
- support/return risk
- platform fit
- long-term expandability

## Amazon and Walmart branch strategy

When the target platform is Amazon or Walmart, do not optimize for the hottest or most glamorous products. Optimize for durable, manageable, low-friction opportunities.

### Target profile for Amazon / Walmart

Prefer products that look capable of:
- selling steadily rather than explosively
- reaching roughly tens to low hundreds of orders per day, not necessarily breakout viral volume
- operating without heavy brand power
- operating without complex compliance or certification burden
- operating without strong patent / trademark / IP dependence
- maintaining acceptable margin without needing premium luxury positioning

### Avoid on Amazon / Walmart by default

Avoid products that depend on:
- major brand affinity
- strong visual/IP copying
- heavy ingredient/formulation trust barriers
- pharma/health claims
- body-contact chemistry/formulation categories
- unusually high certification, safety, or gating burden
- hyper-competitive mass markets where differentiation is weak

### Amazon branch focus

For Amazon, prioritize:
- boring but useful products
- stable demand over explosive demand
- lighter, simpler, easier-to-ship items
- niches with enough demand to support steady daily sales but not so much attention that competition becomes brutal
- products where listing quality, bundle design, or small product improvements can create an edge

Amazon-specific questions:
- does this look like a stable seller rather than a short-lived spike?
- can a small seller plausibly win some share without strong brand power?
- is review competition survivable?
- is the niche crowded with obvious same-product sellers?
- can the product sustain steady orders with modest differentiation?

### Walmart branch focus

For Walmart, use a similar lens:
- practical mass-market usefulness
- steady replenishment or repeatable demand
- simpler categories with broad household relevance
- lower barrier products that do not require strong premium branding
- products that fit value-conscious but still quality-sensitive shoppers

Walmart-specific questions:
- is this understandable and useful to a broad mainstream shopper?
- can the product compete on practical value without racing to the bottom?
- is the category stable enough to support consistent sales without excessive brand dependence?

### Marketplace scoring shift

On Amazon and Walmart, weight these more heavily:
- stable demand quality
- competition survivability
- low barrier / low compliance
- low brand dependence
- operational simplicity

Weight these less heavily:
- social-media heat alone
- trend excitement without durable demand
- categories that need high brand trust to convert

Read these references when platform-specific logic matters:
- `references/amazon-marketplace-branch.md`
- `references/walmart-marketplace-branch.md`
- `references/main-trunk-acquisition-optimization.md`

## Monitoring and validation model

For each product-selection run, monitor across multiple layers instead of relying on one universal check:

- **signal-quality monitor** — are the inputs strong enough or mostly vanity/noise signals?
- **cross-source monitor** — do trend, marketplace, and business signals agree or conflict?
- **competition monitor** — is the category becoming too saturated, commoditized, or price-compressed?
- **commercial-risk monitor** — do margin, logistics, return, compliance, or manufacturing issues invalidate the apparent opportunity?
- **exclusion-gate monitor** — is the candidate actually disallowed because it is food/ingestible, brand/IP-dependent, or infringement-prone?
- **production-feasibility monitor** — can an abstracted idea realistically be manufactured or sourced?
- **decision-backstop monitor** — if the shortlist still looks uncertain, what second-pass check should be run before recommending pursue/test/reject?

Coverage rule:

- no candidate should be recommended on trend evidence alone
- any food/ingestible candidate should be filtered out by default unless the user explicitly asks for that domain
- any candidate with strong brand/IP dependency or imitation risk should be filtered out by default
- abstracted ideas should not be recommended until non-infringing market comparables and production feasibility look plausible
- no candidate should be rejected on one weak negative signal alone if stronger verification is practical
- when signals conflict, downgrade confidence and run a stronger second-pass review

Miss and remediation rule:

- if a later review shows a product was overrated because a monitor was missing or too weak, record which layer failed
- promote recurring false-positive or false-negative patterns into `safe-learning-log` and `runtime-evolution-loop`
- when a platform repeatedly needs specialized checks, create or improve a platform-specific extension instead of stretching the core skill

## Standard outputs

Produce concrete outputs such as:

- product opportunity shortlist
- category scorecard
- trend summary
- competition summary
- platform-fit recommendation
- decision memo: pursue / test / reject
- next research step
- competitor/product-page link set for each selected product when public links can be gathered

When the user asks for Amazon or Walmart branch output, default to a larger candidate set unless the user requests otherwise:

- Amazon branch: aim to return at least 20 product candidates
- Walmart branch: aim to return at least 20 product candidates
- if confidence is mixed, still provide the full 20 with clear ranking, confidence, and reasons instead of stopping at only a few high-confidence items
- where exact product-level confidence is limited, expand through practical sub-niches and closely related product forms rather than repeating one generic category label

When possible, also include for each selected or shortlisted product:

- at least one public Amazon competitor/product link for Amazon-oriented runs
- at least one public Walmart competitor/product link for Walmart-oriented runs
- if both marketplaces are relevant, prefer one link from each
- if exact product-page links are not reliably available, provide the strongest public search/category/product surface link you can verify and label confidence clearly

## Relationship to other skills

- use `self-cognition-orchestrator` to interpret the product-selection assignment and decide the route
- use `continuous-execution-loop` for multi-stage product research projects
- use `resilient-external-research` for external data gathering
- use `guarded-agent-browser-ops` when browser-driven public page analysis is needed
- use `safe-learning-log` after each real run to capture improved heuristics and repeated signals
- use `runtime-evolution-loop` when recurring product-selection patterns suggest the core skill or extensions should evolve
- use `capability-gap-router` if a platform-specific workflow is missing
- use `skill-discovery-or-create-loop` if a niche/platform extension should be found or created

## Hook/trigger expectations

This skill should be ready to work with hooks and trigger chains.

Important trigger situations:
- a new product-selection task starts
- a candidate category lacks enough signal
- platform-specific logic is missing
- a repeated pattern suggests an extension skill should exist
- a run finishes and should feed learning/evolution loops

## Evolution rule

This skill should improve over time.

After meaningful product-selection runs:
- log what signals were actually useful
- log what signals were misleading
- note which proxies best predicted product viability
- note whether a platform-specific branch is now justified

If the same platform or category repeatedly appears, create or improve a focused extension skill rather than overloading this core skill.


## Amazon premium wholesale branch

When the goal is Amazon-focused broad-catalog selection for stable natural daily sales, also read:
- `references/amazon-premium-wholesale-branch.md`
- `references/amazon-premium-wholesale-scoring.md`
- `references/amazon-tooling-strategy.md`
- `references/amazon-daily-sheet-schema.md`
