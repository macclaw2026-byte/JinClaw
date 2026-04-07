# Prospect Data Engine Scoring Model

## Score components

### Fit score (0-40)

- industry fit
- size fit
- geo fit
- role fit
- use-case fit

### Intent / signal score (0-30)

- project signal
- purchase signal
- partner signal
- timing freshness

### Reachability score (0-20)

- valid domain
- real entrypoint exists
- direct channel quality

### Data quality score (0-10)

- completeness
- contradiction-free record
- source confidence

## Tiering

- A: 85-100
- B: 70-84
- C: 55-69
- D: below 55

## Guardrails

- no score promotion without provenance
- do not let one strong field outweigh multiple contradictions
- downgrade stale signals aggressively

