# Data architecture

## Recommended layers

### 1. raw_import_files
One row per source file or archive member.

### 2. raw_contacts
Raw rows exactly as imported, with source metadata attached.

### 3. normalized_contacts
Normalized names, emails, websites, titles, company names, states, industries.

### 4. normalized_companies
Company-level dedupe layer.

### 5. prospect_scores
Explainable scoring output with component scores and reason text.

### 6. outreach_queue
Actionable development queue.

### 7. outreach_events
Actual touches, replies, status changes, conversions.

## Why DuckDB first
- free
- great for CSV/Parquet at million-row scale
- simple local deployment
- easy SQL-based profiling and dedupe work

## Current known raw fields
Observed sample headers include fields like:
- Company Name / Company
- Address
- City
- State
- Zip
- County
- Phone
- Contact First / Contact Last / Contact
- Title
- Direct Phone
- Email
- Website
- Employee Count / Employees
- Annual Sales / Sales
- SIC Code
- Industry
