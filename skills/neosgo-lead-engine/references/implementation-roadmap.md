# Implementation roadmap

## Phase 1
- locate or define the local warehouse path
- create a resumable archive import queue
- import archive contents into DuckDB
- profile row counts, nulls, and field coverage

## Phase 2
- normalize emails, domains, titles, industries, company names
- dedupe contact/company rows

## Phase 3
- implement prospect-type classification
- implement scoring model
- generate top-prospect views

## Phase 4
- create outreach strategy docs and queue generation
- define daily report cron
- add learning loop from replies/conversions

## Daily report contents
- newly imported rows
- deduped companies/contacts
- high-score prospects added
- outreach-ready count
- major blockers
