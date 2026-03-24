# Competitor Pages Output Schema

Use this schema when converting competitor sites or landing pages into structured evidence.

## Record fields

```text
brand_or_site:
source_url:
page_scope:
headline_or_primary_message:
target_customer_clues:
value_proposition:
key_selling_points:
proof_or_trust_elements:
cta_pattern:
price_presentation:
conversion_friction_or_gap:
positioning_style:
product_selection_implication:
marketing_implication:
evidence_strength:
confidence:
downstream_skill:
notes:
```

## Routing rule

### Route to `product-selection-engine`
Use fields such as:
- value_proposition
- key_selling_points
- positioning_style
- product_selection_implication

### Route to `us-market-growth-engine`
Use fields such as:
- headline_or_primary_message
- target_customer_clues
- proof_or_trust_elements
- cta_pattern
- price_presentation
- conversion_friction_or_gap
- marketing_implication
