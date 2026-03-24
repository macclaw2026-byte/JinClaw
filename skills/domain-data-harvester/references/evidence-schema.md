# Evidence Schema

Normalize data into records like this:

```text
mission:
branch:
source_family:
source_url:
page_type:
entity:
field_name:
field_value:
confidence:
freshness:
noise_risk:
downstream_skill:
notes:
```

## Rule

Downstream skills should receive fields, not unfiltered page dumps, unless raw text is specifically needed.

## Examples

### Product-selection record
- entity: toe spacers
- field_name: review_depth_proxy
- field_value: multiple Amazon first-page listings with 3.8K to 46.7K reviews
- downstream_skill: product-selection-engine

### Marketing record
- entity: competitor landing page
- field_name: message_angle
- field_value: convenience + premium simplicity
- downstream_skill: us-market-growth-engine


## Additional provenance fields for multi-tool runs

When multiple extraction methods are used, also try to keep:
- extraction_tool
- competing_values
- chosen_value
- arbitration_note
- supporting_sources
