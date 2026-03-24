# Main Trunk Acquisition Optimization

Use this reference to improve the *front half* of product-selection work: what to gather first, what to ignore early, and how to reduce noise before scoring.

Use the shared monitoring standard from `../../self-cognition-orchestrator/references/monitoring-and-retrofit-framework.md`.

## Core idea

Do not begin with broad trend hunting and only filter later.

For Amazon and Walmart style selection, pre-filter the information stream so the system spends more time on candidates that look:
- stable rather than explosive
- moderate-demand rather than headline-demand
- lower-friction rather than higher-regulation
- non-brand-dependent rather than brand-led
- operationally simple rather than category-complex

## Upstream filtering order

Before deep research, apply this order:

1. **Domain exclusion first**
   - drop food / ingestible / body-contact formulation / medicine / regulated health categories early
   - drop obvious IP / brand-dependent ideas early

2. **Marketplace fit second**
   - ask whether the candidate could plausibly survive on Amazon/Walmart without premium brand trust
   - if not, deprioritize before collecting more detail

3. **Demand shape third**
   - prefer signs of stable movement, not just spikes
   - moderate durable demand is often better than flashy volume

4. **Competition survivability fourth**
   - avoid spending too much time on obvious commodity wars or giant review moats

5. **Only then run deep scoring**

## Better primary signals for Amazon / Walmart

Prioritize signals that suggest:
- steady sales rhythm
- repeatable mainstream use case
- low explanation burden
- manageable returns and breakage
- room for smaller sellers
- simple functional differentiation

Examples of more useful early questions:
- is this boring but useful?
- can it sell without major brand power?
- would a shopper understand it instantly?
- is the category likely to be stable for months, not days?
- does the category avoid special trust or compliance burden?

## Lower-value signals to downrank early

Do not over-invest in these early:
- pure virality
- social attention with weak buying-intent evidence
- broad “trending products” lists without marketplace survivability context
- hot categories that usually require major brand trust
- categories with formulation / ingredient / safety-sensitive complexity

## Suggested acquisition pipeline

### Pass 1: coarse reject
Drop:
- excluded categories
- obvious infringement/brand dependence
- clearly high-barrier categories

### Pass 2: stable-demand shortlist
Keep only candidates that appear to match:
- steady utility
- broad enough audience
- non-hype use case
- plausible daily sales rhythm

### Pass 3: survivability screen
Check:
- competition density
- review moat severity
- pricing compression
- operational simplicity

### Pass 4: abstraction layer
Extract:
- pain point
- convenience promise
- product job-to-be-done
- possible non-infringing implementation

### Pass 5: feasibility + score
Only now judge:
- sourcing/manufacturing feasibility
- final score
- pursue / test / reject

## Monitoring questions for the main trunk

- Did the acquisition path still spend too much attention on excluded categories?
- Did hype signals overwhelm stable-demand signals?
- Did brand-led examples distort what looked feasible for smaller sellers?
- Did we identify stable niches early enough, or too late?
- Which early filters saved the most time and improved shortlist quality?
