# Customer Voice Output Schema

Use this schema when converting raw customer/community/review text into structured evidence.

## Record fields

```text
product_or_topic:
source_family:
source_url:
community_or_surface:
recurring_pain_points:
expected_benefits:
objections_or_dislikes:
buyer_language_patterns:
usage_contexts:
adjacent_needs:
fuzzy_or_explicit_demand_requests:
tool_gap_signals:
evidence_strength:
confidence:
downstream_skill:
notes:
```

## Routing rule

### Route to `product-selection-engine`
Use fields such as:
- recurring_pain_points
- expected_benefits
- objections_or_dislikes
- usage_contexts
- adjacent_needs

### Route to `us-market-growth-engine`
Use fields such as:
- buyer_language_patterns
- expected_benefits
- objections_or_dislikes
- usage_contexts
- notes about positioning/messaging

## Output discipline

- prefer clustered themes over raw post dumps
- keep a few representative phrases when useful
- label confidence honestly
- preserve source/community provenance


## Extra interpretation rule

Pay special attention to language like:
- “I wish there were…”
- “I need something that can…”
- “Where can I find…”
- “Nothing fits / works / is convenient”

These may reveal partially met or poorly served demand, even when the exact product idea is not yet clearly named.
