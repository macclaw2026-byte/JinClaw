# Amazon Premium Wholesale Data Model

Use this as the canonical schema for candidate products in the local pipeline.

## Raw evidence record

```json
{
  "source_family": "amazon_public|customer_voice|competitor_page|crowdfunding|saas_tool|other",
  "source_name": "amazon_search|reddit|kickstarter|helium10|junglescout|sellersprite|...",
  "source_url": "https://...",
  "collected_at": "ISO timestamp",
  "query": "toe spacers",
  "entity": "Toe Spacers",
  "field_name": "review_count_proxy",
  "field_value": "Multiple listings with thousands of reviews",
  "confidence": "low|medium|high",
  "notes": "..."
}
```

## Candidate record

```json
{
  "candidate_id": "slugified-name",
  "product_name": "Toe Spacers",
  "sub_niche": "professional foot function direction",
  "platform": "amazon",
  "query_terms": ["toe spacers", "bunion toe spacer", "foot alignment spacer"],
  "source_mix": ["amazon_public", "customer_voice", "competitor_page"],
  "category_flags": {
    "excluded": false,
    "brand_risk": false,
    "regulated": false,
    "body_contact_formula": false,
    "ingestible": false
  },
  "demand_features": {
    "trend_strength": 0.0,
    "search_intent_strength": 0.0,
    "customer_pain_clarity": 0.0,
    "repeat_need_strength": 0.0
  },
  "marketplace_features": {
    "review_depth_proxy": 0.0,
    "price_ladder_strength": 0.0,
    "listing_density": 0.0,
    "mid_tier_survival_signal": 0.0,
    "competition_crowding": 0.0
  },
  "business_features": {
    "simplicity": 0.0,
    "margin_viability": 0.0,
    "fragility_risk": 0.0,
    "return_risk": 0.0,
    "manufacturability": 0.0
  },
  "differentiation_features": {
    "clear_angle_exists": 0.0,
    "tool_gap_signal": 0.0,
    "improvement_room": 0.0,
    "competitor_positioning_gap": 0.0
  },
  "scores": {
    "demand_score": 0.0,
    "proxy_sales_score": 0.0,
    "competition_survivability_score": 0.0,
    "simplicity_score": 0.0,
    "margin_score": 0.0,
    "differentiation_score": 0.0,
    "total_score": 0.0
  },
  "sales_range": "30-80/day",
  "evidence_grade": "A|B|C",
  "recommendation": "pursue|validate|test|reject",
  "competitor_links": ["https://..."],
  "why_fit": "...",
  "novelty_status": "new|refined|repeat-suppressed",
  "last_seen": "YYYY-MM-DD"
}
```
