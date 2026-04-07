# Neosgo lead engine schema compatibility map (2026-04-04)

## Canonical live warehouse
- DB: `/Users/mac_claw/.openclaw/workspace/data/neosgo_leads.duckdb`

## Logical layer mapping
- `raw_import_files` -> live table `raw_import_files`
- `raw_contacts` -> live table `raw_contacts`
- `normalized_contacts` -> live table `normalized_contacts`
- `normalized_companies` -> compatibility view `normalized_companies` (created 2026-04-04 from `scored_prospects` grouped by `company_key`)
- `prospect_scores` / `neosgo_prospect_scores` -> compatibility view `prospect_scores` mapped from live table `scored_prospects`
- contact dedupe layer -> live table `deduped_contacts`
- outreach-ready layer -> live table `outreach_ready_leads`
- persona layer -> live table `persona_summary`
- queue layer -> live table `outreach_queue`
- events layer -> live table `outreach_events`

## Notes
- Compatibility views were chosen over destructive rebuild because the live warehouse already contains valid downstream outputs.
- This resolves schema drift between the ideal architecture docs and the current execution DB.
