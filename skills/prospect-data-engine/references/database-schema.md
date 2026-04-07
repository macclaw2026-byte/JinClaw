# Prospect Data Engine Database Schema

## Core tables

### accounts

- account_id
- company_name
- company_name_normalized
- website_url
- website_root_domain
- industry_raw
- industry_normalized
- company_type
- size_band
- country
- state
- city
- geo_confidence
- fit_tags
- source_confidence
- first_seen_at
- last_enriched_at
- lifecycle_status

### contacts

- contact_id
- account_id
- full_name
- first_name
- last_name
- role_raw
- role_normalized
- seniority
- persona_type
- email
- linkedin_url
- phone
- reachability_status
- confidence
- first_seen_at
- last_validated_at

### opportunity_signals

- signal_id
- account_id
- contact_id nullable
- signal_type
- signal_label
- signal_score
- freshness_days
- source_url
- source_excerpt
- observed_at

### reachability

- reachability_id
- account_id
- contact_id nullable
- channel
- endpoint
- validation_status
- validation_reason
- last_checked_at
- risk_flag

### lead_scores

- score_id
- account_id
- contact_id nullable
- fit_score
- intent_score
- reachability_score
- data_quality_score
- total_score
- score_tier
- scoring_version
- scored_at

### source_registry

- source_id
- source_family
- source_label
- source_url
- source_tier
- quality_rating
- last_success_at
- last_failure_at

### lifecycle_events

- event_id
- object_type
- object_id
- event_type
- payload_json
- created_at

## Design rules

- account-first, contact-second
- all high-value fields must remain traceable to source
- use enums for statuses where possible
- keep scoring dimensions separate
- keep lifecycle and source history append-only when feasible

