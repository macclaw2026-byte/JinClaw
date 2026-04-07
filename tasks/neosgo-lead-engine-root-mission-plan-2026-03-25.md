# Neosgo Lead Engine Root Mission Plan

日期：2026-03-25
阶段：plan
状态：drafted from verified local evidence

## 1. Root mission

在本机安全边界内，搭建并持续运行一个 Neosgo lead engine，使其能够：
1. 自动发现并导入 Downloads 与本机既有数据源到统一 DuckDB
2. 完成原始层、标准化层、公司/联系人去重层
3. 识别 Neosgo 高价值潜客并输出可解释打分
4. 形成客户画像、营销策略、开发队列与动作记录
5. 支持持续自动执行与每日进展汇报
6. 当外部执行条件不足时，能精确阻塞并持续报告

## 2. Verified planning anchors

### Confirmed local assets
- Raw warehouse candidate: `data/neosgo_leads.duckdb`
- Mature business-model warehouse candidate: `projects/ma-data-workbench/data/db/ma_data.duckdb`
- Bulk source archives in `~/Downloads`, including multi-part US business email datasets
- Existing in-house importer and batch-runner under `skills/neosgo-lead-engine/scripts/`
- Existing ideal architecture, scoring model, and implementation roadmap references under `skills/neosgo-lead-engine/references/`

### Confirmed constraints
- Stay inside local security boundaries
- Prefer approved in-house rebuild over opaque external tooling
- Use DuckDB as the local analysis/warehouse engine
- Do not assume outbound execution channels without explicit local evidence

## 3. Canonical execution path selected

### Selected path
Adopt a **two-zone DuckDB design** and rebuild the missing layers locally:
- Zone A: `data/neosgo_leads.duckdb` as the Neosgo-specific ingestion, normalization, scoring, and reporting warehouse
- Zone B: `projects/ma-data-workbench/data/db/ma_data.duckdb` as an evidence-bearing historical/business-model reference source, to be inspected and selectively mirrored rather than treated as implicitly canonical

### Why this path
- `data/neosgo_leads.duckdb` already contains import-job and raw-contact tables aligned with the in-house Neosgo importer
- Current verified importer writes into this DB directly
- `ma_data.duckdb` appears useful as an upstream reference/business layer, but canonical ownership is not yet verified
- This minimizes unsafe migration assumptions while preserving reusable prior work

## 4. Phased root mission

## Phase 0 — warehouse role decision and source registry

### Goal
Freeze system roles so later implementation does not drift.

### Deliverables
- Canonical warehouse decision note
- Source inventory / registry table
- Archive/member/header fingerprint inventory
- Source-to-ingestion mapping

### Tasks
1. Read-only inspect `ma_data.duckdb` table schema, counts, and derivations
2. Compare `ma_data.duckdb` against `data/neosgo_leads.duckdb`
3. Declare final role split:
   - raw/staging DB
   - normalized/scored DB
   - or unified single DB if safe
4. Build/verify `raw_import_files` + `import_job_files` + archive/member inventory coverage
5. Register all discovered Downloads zip/csv sources with resumable status

### Exit criteria
- Every known source archive has a registered inventory row
- Canonical warehouse role is documented with evidence
- No ambiguity remains about where future phases write

## Phase 1 — ingress and raw preservation

### Goal
Get all source archives into a resumable raw layer without losing provenance.

### Deliverables
- Import queue runner for all Downloads business archives
- Raw preservation tables with checksums, source path, member path, row counts, header signatures
- Import verification report

### Tasks
1. Extend current importer coverage if needed for header variants
2. Ensure per-archive/per-member row accounting
3. Ensure duplicate archive detection via checksum/signature
4. Persist import run metrics
5. Record failures per archive with resumable status

### Exit criteria
- All readable source archives imported or explicitly marked failed with reason
- Raw row totals and file/member counts are reproducible
- Provenance is queryable for every imported row

## Phase 2 — normalization and dedupe

### Goal
Transform raw rows into reusable business/contact entities.

### Deliverables
- `normalized_contacts`
- `normalized_companies`
- Dedupe rules and confidence columns
- Standardized fields for name, title, website/domain, email, location, industry

### Tasks
1. Normalize company names
2. Normalize titles and profession signals
3. Normalize website/domain and email quality
4. Normalize phone/state/city/zip
5. Build contact-level dedupe:
   - exact email
   - exact direct phone
   - website/domain + company
6. Build company-level dedupe:
   - normalized company + city/state
   - domain-based merge
7. Preserve raw-to-normalized lineage

### Exit criteria
- Normalized contact/company tables exist and are populated
- Dedupe logic is auditable and versioned
- Coverage metrics show usable normalized fields

## Phase 3 — Neosgo prospect classification and scoring

### Goal
Produce explainable, tuneable prospect intelligence.

### Deliverables
- Prospect-type classification rules
- `prospect_scores`
- `v_neosgo_priority_leads`
- Score reasons / component fields
- Grade tiers and priority queues

### Initial target segments
- interior designers
- builders / developers
- general contractors / remodelers
- electricians / electrical contractors / installers
- real-estate agents / brokerages
- adjacent trade buyers / sourcing roles

### Scoring dimensions
- industry_fit_score
- influence_score
- business_scale_score
- pro_program_fit_score
- contactability_score
- market_priority_score
- penalty_score
- total_score
- grade / tier

### Tasks
1. Map titles and industries into target segments
2. Add positive and negative signals
3. Store human-readable scoring reasons
4. Version the scoring model
5. Export top leads per segment/state/grade

### Exit criteria
- Priority lead view exists and queries successfully
- Top leads have transparent reason fields
- Segment counts and grade distribution are reproducible

## Phase 4 — customer portraits and strategy layer

### Goal
Convert scored leads into commercially useful development logic.

### Deliverables
- Segment portraits / ICP notes
- Neosgo channel and value-proposition strategy
- Outreach sequencing plan by segment
- Messaging-angle matrix

### Tasks
1. Create first-pass portraits for each high-value segment
2. Define Neosgo offer framing:
   - professional account
   - commission/referral logic
   - project sourcing support
3. Define channel priority:
   - email-first if local outbound path exists
   - otherwise draft-only queue
4. Define cadence and follow-up rules
5. Define qualification states and pipeline stages

### Exit criteria
- Every A/B-tier segment has a usable strategy note
- Outreach queue fields align with strategy design
- External channel dependencies are explicitly marked

## Phase 5 — outreach operating layer

### Goal
Create an operational queue even if sending remains blocked.

### Deliverables
- `outreach_queue`
- `outreach_events`
- draft message templates by segment
- status machine for lead handling

### Tasks
1. Build queue generation rules from scored leads
2. Generate first-touch drafts per segment
3. Add statuses: queued / drafted / reviewed / sent / replied / qualified / closed / blocked
4. Add feedback capture columns/events
5. If no approved outbound channel exists, keep system in “draft-ready” mode

### Exit criteria
- Outreach-ready leads can be generated daily
- Every queue item has segment, priority, reason, and next action
- System works even without live sending credentials

## Phase 6 — daily reporting and continuous execution

### Goal
Make the engine durable and self-reporting.

### Deliverables
- daily report artifact generator
- report storage table or markdown archive
- cron-ready execution checklist
- blocker reporting format

### Daily report contents
- archives discovered/imported today
- rows imported today
- normalized contacts/companies added
- duplicates merged
- new high-priority leads
- outreach-ready queue count
- drafted/sent/replied counts if available
- blockers
- next optimization step

### Tasks
1. Create repeatable report query set
2. Write report to markdown and/or DB table
3. Prepare cron-safe run order:
   - discover
   - import
   - normalize
   - score
   - queue
   - report
4. Emit exact blocker text when an upstream condition is missing

### Exit criteria
- End-to-end run can produce a daily report without manual assembly
- Reports reflect real DB state, not guessed status
- Failures degrade into precise blocker reports

## 5. Execution order for the next build loop

1. Inspect `projects/ma-data-workbench/data/db/ma_data.duckdb` read-only
2. Decide canonical warehouse role split
3. Build complete archive inventory for Downloads packages
4. Verify or extend importer for all observed header variants
5. Run/prepare full raw import path into Neosgo warehouse
6. Add normalized and dedupe layers
7. Add scoring tables/views
8. Add strategy and queue artifacts
9. Add daily report generation
10. Add scheduled or loop-based execution only after output correctness is verified

## 6. Explicit blockers and dependency gates

### Currently unresolved but non-fatal
- Whether `ma_data.duckdb` should remain reference-only or be merged into the Neosgo warehouse
- Whether any local approved outbound email or CRM channel exists
- Which Neosgo commercial specifics should shape market-priority weighting

### Hard block only for true closed-loop outbound
- No approved sender/channel evidence yet for actual automated outreach

### Not a block for build-out
- Importing, normalization, scoring, segmentation, queue generation, and daily reporting can proceed locally without outbound credentials

## 7. Verification checklist

A plan phase is complete only if:
- execution phases are ordered and bounded
- each phase has deliverables and exit criteria
- blockers are separated from non-blockers
- local security posture is preserved
- the plan can be executed incrementally with real evidence collection

## 8. Immediate next action

Read-only inspect `projects/ma-data-workbench/data/db/ma_data.duckdb` to finalize the warehouse role decision before implementing the next phase.
