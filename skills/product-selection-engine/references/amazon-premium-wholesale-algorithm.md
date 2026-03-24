# Amazon Premium Wholesale Algorithm

This is the core scoring and filtering logic.

## 1. Hard filter layer
Reject immediately if any are true:
- ingestible / food / supplement
- medicine / regulated health
- body-contact formulation-heavy category (shampoo/body wash/etc.)
- strong brand / trademark / IP dependence
- obvious high-liability or overly fragile category
- poor manufacturability / excessive operational burden

## 2. Weighted scoring model

Normalize each major component to 0-100.

### Demand score (25%)
Based on:
- trend strength
- search intent strength
- pain-point clarity
- evidence of repeat or evergreen need

### Proxy sales score (20%)
Based on:
- review depth proxy
- multiple active-looking listings
- price ladder maturity
- mid-tier seller presence
- repeated marketplace visibility

### Competition survivability score (20%)
Based on:
- not purely brand-dominated
- not pure same-product commodity warfare
- review moat not overwhelming
- room for smaller sellers

### Product simplicity score (15%)
Based on:
- ease of sourcing/manufacturing
- low fragility
- low returns complexity
- operational simplicity

### Margin / price ladder score (10%)
Based on:
- acceptable price band
- plausible room for margin
- not pure race-to-the-bottom

### Differentiation score (10%)
Based on:
- clear sub-niche or angle exists
- tool-gap / unmet-need signal exists
- competitor positioning gap exists
- room for structural or message improvement

## 3. Penalties
Apply score penalties for:
- high review moat
- visible price compression
- obvious big-brand dominance
- complex variants / fit / returns risk
- evidence conflicts

## 4. Evidence grading

### Grade A
- multiple strong source families agree
- marketplace proxies are strong
- competition looks survivable
- no major unresolved blocker

### Grade B
- evidence is directionally good
- some gaps remain
- candidate is worth validate/test rather than full confidence

### Grade C
- weak or conflicting evidence
- candidate should not be a top daily highlight

## 5. Daily sales range inference
Do not predict exact units.
Use rough buckets:
- 10-30/day
- 30-80/day
- 80-150/day
- 150-300/day

Inference logic:
- stronger review depth proxy + stronger marketplace maturity + stronger repeat need -> higher range bucket
- stronger crowding / review moat -> may keep demand high but survivability lower
- range should reflect niche/product-cluster plausibility, not false precision for one listing

## 6. Recommendation mapping

- total >= 75 and evidence grade A/B -> pursue
- total 60-74 and evidence grade B -> validate
- total 45-59 -> test
- total < 45 or hard-filter fail -> reject
