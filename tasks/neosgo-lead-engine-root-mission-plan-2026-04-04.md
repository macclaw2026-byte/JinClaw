# Neosgo Lead Engine Root Mission Plan (2026-04-04)

日期：2026-04-04  
阶段：plan  
状态：updated from live warehouse evidence and reference-DB inspection

## 1. Root mission

在本机安全边界内，把 Neosgo lead engine 落成并持续运行成一个可验证的 root mission：
1. 自动发现并增量导入 Downloads 与本机参考库中的可用客户数据到统一 DuckDB
2. 完成原始层、标准化层、去重层、潜客分类与打分层
3. 输出客户画像、营销策略、开发队列、开发事件与日报
4. 在外部发送条件不足时，保持“可开发但不盲发”的 draft-ready 模式
5. 通过每日自动运行持续产出真实结果，或给出精确阻塞说明

## 2. Verified planning anchors

### Confirmed live assets
- Canonical live warehouse: `data/neosgo_leads.duckdb` (`80,337,711,104` bytes)
- Reference business-model DB: `projects/ma-data-workbench/data/db/ma_data.duckdb` (`352,858,112` bytes)
- Live Neosgo tables already present:
  - `raw_import_files` = 96
  - `raw_contacts` = 67,382,866
  - `normalized_contacts` = 67,382,866
  - `deduped_contacts` = 40,800,031
  - `scored_prospects` = 40,422,503
  - `outreach_ready_leads` = 2,391,788
  - `outreach_queue` = 2,990,884
  - `outreach_events` = 53
- Recent daily reports exist under `reports/neosgo/` for 2026-04-01 through 2026-04-03
- Downloads archive inventory is nearly complete; business-data ZIP gap currently reduced to one not-yet-imported archive: `~/Downloads/MA_Business_Email_Data/CSV_Software.zip`

### Confirmed reference-DB value
`ma_data.duckdb` contains reusable scoring/view logic worth mirroring safely, not treating as the canonical warehouse:
- `businesses` = 2,987,364
- `v_professional_leads` = 2,987,364
- `v_professional_lead_signals` = 2,987,364
- `v_neosgo_priority_leads` = 186,669

This confirms the selected plan should preserve high-value design patterns from the prior business-model DB while rebuilding execution locally in the Neosgo warehouse.

### Confirmed constraints
- Never break local security boundaries
- Use approved in-house rebuild, not opaque third-party execution
- Preserve seller.neosgo browser dependency on host browser + `chrome-relay` profile when browser work is needed
- Do not assume outbound email/CRM execution just because queue tables exist

## 3. Canonical execution path selected

### Final selected path
Adopt a **single canonical Neosgo warehouse + reference-model mirror** approach:
- Canonical system-of-record and execution DB: `data/neosgo_leads.duckdb`
- Reference-only model/evidence DB: `projects/ma-data-workbench/data/db/ma_data.duckdb`

### Why this path is now final
- The Neosgo warehouse already contains the real ingest, queue, event, and report pipeline outputs
- The reference DB is much smaller and view-centric, useful for logic borrowing but not authoritative for current execution
- This avoids accidental split-brain ownership while still reusing proven scoring/view structure safely

## 4. Phased executable root mission

## Phase 0 — freeze canonical schema + drift map

### Goal
Lock the live warehouse contract before any rebuild or incremental import.

### Deliverables
- live-schema snapshot
- schema-drift note against ideal architecture
- compatibility mapping between ideal names and live names

### Tasks
1. Capture live schema for key tables/views in `neosgo_leads.duckdb`
2. Map ideal/reference names to live names:
   - `normalized_companies` → currently missing
   - `prospect_scores` / `neosgo_prospect_scores` → currently represented by `scored_prospects`
   - contact dedupe layer → currently `deduped_contacts`
3. Decide whether missing ideal layers should be materialized or represented as views
4. Record row-count drift vs 2026-03-28 verification artifacts

### Exit criteria
- No ambiguity remains about which live table satisfies each logical layer
- Drift items are explicitly listed and prioritized

## Phase 1 — complete source registry and incremental ingress

### Goal
Make ingestion complete, resumable, and provenance-safe.

### Deliverables
- complete source registry
- imported-vs-missing archive ledger
- importer coverage note for header variants
- incremental import plan for any missing archive/member

### Tasks
1. Register every business-data ZIP/CSV under Downloads
2. Verify imported archives already represented in `raw_import_files`
3. Inspect the one missing archive `CSV_Software.zip` for relevance and ingestability
4. Confirm whether any untracked CSV members exist inside already-imported ZIP families
5. Keep import logic incremental only; do not full-rebuild without evidence

### Exit criteria
- Every relevant Downloads archive is either imported, intentionally excluded, or blocked with reason
- Raw provenance remains queryable by source archive + member path

## Phase 2 — normalization + company/contact entity stabilization

### Goal
Turn the raw layer into stable reusable entities without losing lineage.

### Deliverables
- validated `normalized_contacts`
- validated `deduped_contacts`
- company-level entity layer (`normalized_companies` table or compatibility view)
- field-quality profiling report

### Tasks
1. Profile nulls/coverage for title, email, website, phone, company, state, industry
2. Review current dedupe logic for exact-email / phone / domain-company collision behavior
3. Materialize or define company-level normalized entity layer if still missing
4. Preserve raw-to-normalized-to-deduped lineage keys

### Exit criteria
- Contact and company layers both exist logically and are queryable
- Dedupe method is explainable and reproducible

## Phase 3 — prospect classification and explainable scoring refresh

### Goal
Keep scoring explainable while aligning live outputs with ideal architecture and reference logic.

### Deliverables
- scoring contract document
- `scored_prospects` validation or rebuild plan
- compatibility view/table for `prospect_scores`
- top-priority lead exports by segment/state

### Tasks
1. Compare `scored_prospects` columns against reference view columns from `ma_data.duckdb`
2. Reconcile live segment/tier distribution drift
3. Ensure score components and reason text remain queryable
4. Add or verify high-value target segments:
   - interior designers
   - builders / developers
   - contractors / remodelers
   - electricians / lighting installers
   - real-estate / brokerage
5. Reduce `other/C` inflation through tighter classification rules

### Exit criteria
- Priority leads are reproducible from documented scoring logic
- Score outputs remain explainable and segment-aware

## Phase 4 — strategy, portraits, and outreach operating model

### Goal
Convert scored prospects into commercially actionable development logic.

### Deliverables
- updated ICP/persona notes
- segment-specific strategy matrix
- outreach operating states and next-action rules
- draft template coverage by segment

### Tasks
1. Refresh persona summaries from live high-score segments
2. Map Neosgo value proposition to each target segment
3. Confirm queue priority logic matches scoring and buyer type
4. Keep outbound execution in draft-ready mode unless approved send path is verified

### Exit criteria
- Every priority segment has a usable strategy + queue logic
- The queue can operate safely without assuming live sending credentials

## Phase 5 — daily reporting and durable automation

### Goal
Ensure the engine continues producing trustworthy daily outputs.

### Deliverables
- durable run order
- report-generation verification
- blocker-reporting contract
- schedule verification note

### Tasks
1. Verify existing daily reports reflect live DB counts rather than stale snapshots
2. Confirm report generator/runbook still matches current schema
3. Verify cron/scheduled execution path for daily Neosgo reporting
4. Make failures degrade into exact blockers, not silent staleness

### Exit criteria
- A daily run can complete or fail loudly with precise evidence
- Reports are grounded in current DB state

## Phase 6 — optional closed-loop outbound activation gate

### Goal
Separate build completion from outbound-channel readiness.

### Deliverables
- outbound-readiness gate note
- approved-channel checklist
- safe activation plan if/when sender credentials are verified

### Tasks
1. Verify whether a local approved email/CRM channel truly exists
2. If absent, keep system in draft-only queue mode
3. If present, require explicit activation boundary before scaling outreach

### Exit criteria
- Outbound automation is either safely gated or explicitly enabled with evidence

## 5. Ordered next-build sequence

1. Freeze live schema and write compatibility mapping
2. Inspect the sole missing Downloads archive (`CSV_Software.zip`) and decide import/exclude
3. Reconcile row-count drift between current DB and 2026-03-28 verification artifacts
4. Validate/materalize company-level normalized layer
5. Validate scoring contract against reference DB views
6. Refresh priority-lead and strategy outputs
7. Verify report generator + schedule against current schema
8. Only then decide whether any rebuild is necessary

## 6. Explicit blockers and non-blockers

### Non-blockers
- Lack of outbound credentials does not block ingest, normalization, scoring, queue generation, or daily reporting
- Reference DB not being canonical is not a blocker; it is an input for logic mirroring

### Current actionable blocker candidates to verify
- Schema drift between ideal docs and live warehouse may block unattended maintenance if not mapped
- Report/runbook logic may be stale if still expecting old table counts or names

### Hard block for true autonomous outreach
- No verified approved outbound send path yet

## 7. Verification checklist for this plan stage

Plan stage is complete only if:
- root mission is phased and executable
- each phase has concrete deliverables, tasks, and exit criteria
- live-vs-ideal drift is acknowledged, not ignored
- reference DB role is finalized
- missing-source coverage is explicit
- security and browser boundaries remain preserved

## 8. Immediate next action

Perform Phase 0 schema-freeze work: capture compatibility mapping and reconcile row-count drift so the next execute stage can act on the live warehouse safely instead of rebuilding from stale assumptions.
