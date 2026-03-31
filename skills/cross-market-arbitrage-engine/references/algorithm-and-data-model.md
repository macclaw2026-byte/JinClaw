# Algorithm And Data Model

## System purpose

The system is not optimized for "finding many products".
It is optimized for continuously identifying products that are:

- likely to keep generating orders
- likely to remain profitable after sourcing + logistics + platform fees
- not too concentrated in a monopolized head market
- still open to differentiation
- not in a collapsing price-war path

## Five-step decision funnel

### 1. Demand validation

Every 30 minutes:

- fetch sell-side search/category/detail surfaces
- extract candidate product entities
- normalize title / price / link / platform
- estimate demand using:
  - monthly bought / sold signals when present
  - review count and rating
  - search-position / result density hints

Hard demand gates:

- estimated daily orders >= 30
- listing age <= 730 days

### 2. Source matching

Every 60 minutes:

- query 1688, Yiwugo, and Made-in-China for each new candidate
- generate multiple source query variants
- fetch search page + one detail hop when needed
- compute entity-match score from:
  - title similarity
  - attribute overlap
  - price-band sanity
  - weight-band sanity

### 3. Unit economics

Compute:

- gross_profit_amount = sell_price - purchase_cost - 59*weight_kg - 35*weight_kg - platform_fee - 1.4
- gross_margin_rate = gross_profit_amount / sell_price

Hard profit gates:

- base margin >= 45%
- conservative margin >= 45%

### 4. Market-structure viability

Compute whether the category looks too concentrated using:

- top-result duplication
- ad / sponsored density
- brand repetition hints

Low-competition / fragmented head markets score higher.

### 5. Differentiation + price stability

Compute:

- pain-point opportunity score from complaints / negative wording
- price stability score from local historical price observations

Only products with enough differentiation room and acceptable price stability should survive.

## Final ranking

The launchability score is a weighted composite:

- demand score: 25%
- margin score: 25%
- competition score: 20%
- differentiation score: 15%
- price stability score: 15%

## Confidence model

Recommended score composition:

- demand extraction quality: 15
- source extraction quality: 20
- entity-match confidence: 20
- weight evidence quality: 20
- restricted-product confidence: 10
- price stability evidence: 10
- re-check consistency: 5

Only emit shortlist rows when:

- confidence score >= 80
- weight evidence grade in {A, B}
- estimated daily orders >= 30
- listing age <= 730 days
- base margin >= 45%
- conservative margin >= 45%
- launchability score >= 70

## Weight evidence grades

- A: explicit shipping/package weight from source detail
- B: explicit product weight or structured shipping clues
- C: inferred from similar products
- D: no trustworthy weight evidence

Reject shortlist output for C/D grades.

## Restricted-product filtering

Apply three layers:

1. category blacklist
2. title / attribute keyword blacklist
3. source-detail evidence blacklist

## Source-platform policy

- 1688: primary high-value source, but operationally highest-risk and should prefer authorized-session workflows
- Yiwugo: primary supplementary source for cross-check and alternative factory discovery
- Made-in-China: stable public source and structured evidence fallback
