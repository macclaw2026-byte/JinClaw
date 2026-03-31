# Algorithm And Data Model

## Demand discovery

Every 30 minutes:

- fetch sell-side search/category surfaces
- extract candidate product entities
- normalize title / price / link / platform
- dedupe by normalized product family

## Source matching

Every 60 minutes:

- query multiple source marketplaces for each new candidate
- extract supplier candidates
- compute entity-match score from:
  - title similarity
  - attribute overlap
  - image-hint overlap when available
  - price-band sanity
  - weight-band sanity

## Confidence model

Recommended score composition:

- demand extraction quality: 15
- source extraction quality: 20
- entity-match confidence: 20
- weight evidence quality: 20
- restricted-product confidence: 10
- price stability: 10
- re-check consistency: 5

Only emit shortlist rows when:

- confidence score >= 80
- weight evidence grade in {A, B}
- base margin >= 45%
- conservative margin >= 45%

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

- 1688: high-value source, but currently treated as authorized-session / high-risk source
- Yiwugo: supplementary source
- Made-in-China: stable public source and useful primary source
