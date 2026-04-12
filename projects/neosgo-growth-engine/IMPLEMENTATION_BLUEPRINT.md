<!--
RULES-FIRST NOTICE:
Before modifying this file, first read:
- `JINCLAW_CONSTITUTION.md`
- `AI_OPTIMIZATION_FRAMEWORK.md`
Follow the constitution and framework:
brain-first, one-doctor, fail-closed, evidence-over-narration,
validate locally, then use the required PR workflow.
-->
# Neosgo Growth Engine — Implementation Blueprint

Generated: 2026-03-25

## Verified local evidence

### Existing database
- Path: `/Users/mac_claw/.openclaw/workspace/projects/ma-data-workbench/data/db/ma_data.duckdb`
- Tables:
  - `businesses`
  - `v_businesses`

### Existing `businesses` schema
- source_file
- row_id
- company_name
- address
- city
- state
- zip
- county
- phone
- contact_first
- contact_last
- contact_full_name
- title
- direct_phone
- email
- website
- employee_count
- annual_sales
- sic_code
- industry
- has_email
- has_website
- domain

### Existing `v_businesses` extras
- city_state
- employee_bucket

## Verified source data archives in Downloads
- `MA_Business_Email_Data.zip`
- `NY_Business_Email_Data.zip`
- `US_Business_Email_Data_01.zip` ... `US_Business_Email_Data_08.zip`
- Duplicate observed: `US_Business_Email_Data_08.zip` and `US_Business_Email_Data_08 (1).zip`

## Verified source CSV header patterns

### 2023 pattern
`Company Name,Address,City,State,Zip,County,Phone,Contact First,Contact Last,Title,Direct Phone,Email,Website,Employee Count,Annual Sales,SIC Code,Industry`

### Older NY pattern
`Company,Address,City,State,Zip,County,Phone,Website,Contact,Title,Direct Phone,Email,Sales,Employees,SIC Code,Industry`

## Safe execution path selected
Build locally on top of the verified DuckDB database and import all archive data through a staging-and-normalization pipeline instead of trusting any opaque third-party tooling.

## Import design

### Stage 1: inventory
Create archive inventory metadata table:
- archive_name
- member_path
- member_size
- state_hint
- year_hint
- header_signature
- import_status
- imported_at

### Stage 2: raw staging
Create raw staging table for direct CSV loads:
- source_archive
- source_member
- raw_line_number
- raw_company_name
- raw_address
- raw_city
- raw_state
- raw_zip
- raw_county
- raw_phone
- raw_contact_first
- raw_contact_last
- raw_contact
- raw_title
- raw_direct_phone
- raw_email
- raw_website
- raw_employee_count
- raw_annual_sales
- raw_sales
- raw_employees
- raw_sic_code
- raw_industry

### Stage 3: normalized business/contact model
Normalize into target columns matching existing `businesses` table:
- company_name
- address
- city
- state
- zip
- county
- phone
- contact_first
- contact_last
- contact_full_name
- title
- direct_phone
- email
- website
- employee_count
- annual_sales
- sic_code
- industry
- has_email
- has_website
- domain

### Stage 4: dedupe rules
Priority order:
1. exact email match
2. exact direct_phone match
3. exact website/domain match + normalized company_name
4. fuzzy company_name + same city/state

### Stage 5: lead scoring tables for Neosgo
Create:
- `lead_scores`
- `lead_segments`
- `outreach_events`
- `feedback_events`
- `daily_progress_reports`

## Neosgo ICP and scoring logic (initial)

Neosgo verified website signals:
- modern lighting
- U.S. homes
- designers, builders, homeowners
- trade-ready support
- projects and sourcing

### Priority customer profiles
1. Interior designers / design studios
2. Builders / contractors / renovation firms
3. Trade buyers / sourcing teams / showroom buyers
4. High-value residential buyers with active renovation intent

### Scoring dimensions
- industry_fit_score
- trade_signal_score
- project_signal_score
- website_quality_score
- contactability_score
- company_maturity_score
- geo_fit_score
- risk_penalty_score
- total_score

### Positive signals
- industry contains lighting, interior design, home decor, furniture, construction, renovation, architecture, showroom
- title contains owner, founder, purchaser, procurement, sourcing, project, designer, operations, sales manager, buyer
- has website
- has company email/domain
- employee_count > micro-business threshold
- annual_sales present

### Negative signals
- missing email and website
- generic/invalid website
- duplicate record cluster
- irrelevant industry
- obvious low-intent or non-business contact

## Marketing system design

### Funnel
1. database import and cleanup
2. scoring and segmentation
3. outreach list generation
4. personalized messaging drafts
5. follow-up cadence
6. inquiry / quote / sample / close tracking
7. feedback-driven reweighting

### Segment actions
- A leads: personalized outbound + manual review
- B leads: semi-automated outreach and nurture
- C leads: holdout / low-frequency nurture / exclude

## Automation design

### Daily automation
- archive scan for new files
- import job
- dedupe job
- lead score refresh
- new A-lead report
- progress summary

### Daily report fields
- records imported today
- valid contacts added
- duplicates merged
- new A leads
- outreach drafted/sent
- replies
- qualified opportunities
- quotes/samples/orders
- blockers
- next optimization step

## Immediate next build steps
1. create SQL/Python inventory script for all zip members
2. create staging tables in DuckDB
3. build importer for both header variants
4. dedupe and normalize into `businesses`
5. add Neosgo lead-scoring tables and first-pass SQL model
6. add daily cron reporting

## External conditions still needed for full closed-loop sales execution
- confirmation that `ma_data.duckdb` is the approved master DB
- approved outbound channel(s): email / forms / LinkedIn / other
- Neosgo commercial specifics:
  - top SKUs or collections
  - MOQ
  - price band
  - shipping/lead time
  - preferred target segments
  - geographic priorities
- if actual outbound email is desired: sender mailbox/domain and deliverability setup
