# Marketing Automation System Design

This document is the consolidated reusable design for the three-skill marketing automation system.

It is written to be:
- cross-project reusable
- professionally structured
- engineering-friendly
- operationally safe

It should be read alongside:
- `architecture.md`
- `interfaces.md`
- `task-lifecycle.md`
- the individual `SKILL.md` files

## Concept Layer

### Design philosophy

The system is intentionally split into three skills because marketing growth fails for three different reasons:

1. the wrong data is collected
2. the right data is collected but translated into weak strategy
3. the right strategy exists but execution is unsafe, noisy, or unlearned

So the reusable capability stack is:

1. `Prospect Data Engine`
2. `Marketing Strategy Engine`
3. `Outreach Feedback Engine`

This creates a closed-loop operating system:

- discover and structure the market
- generate segmented conversion strategy
- execute under risk control
- feed outcomes back into data and strategy

### Why this is reusable

The system does not hardcode:
- brand copy
- one channel
- one product category
- one project like NEOSGO

A new project should only need to swap:
- business goal
- product/service type
- ICP
- target regions
- channel priorities
- conversion target

The skills, schemas, reports, and control logic remain reusable.

## Spec Layer

# Part A. Overall Architecture

## 1. Three-skill positioning

### Skill 1: Prospect Data Engine
- defines target accounts
- ingests public-source lead data
- normalizes, deduplicates, validates, scores
- outputs database-ready prospect assets

### Skill 2: Marketing Strategy Engine
- reads prospect assets
- segments the market
- maps value to persona/context
- selects channels and conversion paths
- outputs strategy cards and executable strategy tasks

### Skill 3: Outreach Feedback Engine
- applies risk gates
- builds execution queues
- processes replies and failures
- maintains suppression and approval queues
- feeds results back into data and strategy

## 2. Relationship between the skills

- Skill 1 -> Skill 2:
  structured prospect records, scores, source quality, review queue
- Skill 2 -> Skill 3:
  strategy cards, strategy tasks, conversion path, CTA logic, approval rules
- Skill 3 -> Skill 1/2:
  feedback classification, suppression updates, data patches, strategy patches

## 3. Runtime chain

1. import and merge raw public lead inputs
2. run quality gate and review queue generation
3. score and structure prospects
4. create strategy brief
5. create account-level strategy cards
6. compile strategy tasks
7. process feedback events
8. build execution queue with suppression awareness

## 4. Why this split is effective

- separates data quality from message quality
- keeps outreach risk independent from discovery logic
- allows each skill to evolve independently
- makes engineering interfaces stable

## 5. Why this split is reusable

Because:
- account discovery exists in almost every B2B growth motion
- strategy generation exists in almost every ABM/outbound motion
- outreach feedback exists in almost every controlled execution system

# Part B. Skill 1 Design

## 1. Goal

Build a durable, explainable, high-quality prospect database from public evidence.

## 2. Inputs

- project config
- ICP definitions
- `data/prospect-seeds.json`
- `data/raw-imports/*.csv|json|jsonl`

## 3. Outputs

- `merged-prospect-seeds.json`
- `prospect-records.json`
- `accounts.json`
- `contacts.json`
- `lead-scores.json`
- `source-registry.json`
- `source-attribution.json`
- `duplicate-conflicts.json`
- `import-quality-gate.json`
- `review-queue.json`

## 4. Workflow

1. load seed and import files
2. normalize incoming records
3. infer source family and source tier
4. deduplicate by domain/company/source
5. compute source quality
6. compute import gate decision
7. build review queue
8. score prospects
9. publish database-ready files

## 5. Search / discovery / acquisition strategy

The current engineering layer supports imported public-source files.

Recommended source families:
- official websites
- Google Business Profile
- LinkedIn company pages
- trade / partner directories
- association lists
- exhibitor lists

Recommended recipes:
- ICP keyword + geo
- account-type + region
- signal-driven searches

`Assumption`: live search/crawling orchestration will be added later; current system is import-first, not autonomous web crawling.

## 6. Cleaning / dedupe / validation / normalization

- normalize company/domain/persona/geo/signals
- preserve source provenance
- dedupe by root domain or normalized company
- separate source registry from source attribution
- send conflicts to review queue

## 7. Scoring model

Current scoring dimensions:
- fit
- intent
- reachability
- data quality

Current tiers:
- A
- B
- C
- D

## 8. Database structure

Primary schemas are aligned to:
- account
- contact
- scoring
- source registry
- attribution
- lifecycle / feedback compatibility

See:
- `references/database-schema.md`
- `schemas/prospect-record.schema.json`

## 9. Quality control

Current checks:
- source quality rating
- duplicate rate
- missing source URL
- missing domain
- review queue count
- allowed-for-strategy gate

## 10. Risks and boundaries

- no private or covert data collection
- no unverifiable record should be outreach-ready
- no source should silently enter strategy without provenance

## 11. Human supervision points

- review queue
- source quality review
- duplicate conflict review
- missing critical field review

## 12. Success criteria

- lower duplicate drift
- cleaner source registry
- lower invalid/suppression feedback downstream
- stable A/B tier generation with explainable provenance

# Part C. Skill 2 Design

## 1. Goal

Turn scored prospect assets into segmented, channel-aware, conversion-aware strategy objects.

## 2. Inputs

- project config
- prospect records
- score tiers
- reachability states
- source signals

## 3. Outputs

- `strategy-brief.json`
- `strategy-tasks.json`
- `strategy-cards.json`

## 4. Workflow

1. summarize prospect pool
2. derive segment counts
3. derive buying context
4. derive channel readiness
5. select conversion path type
6. generate account-level value and proof maps
7. emit strategy cards
8. compile execution-friendly strategy tasks

## 5. Customer segmentation logic

Current segmentation axes:
- score tier
- account type
- persona type
- buying context
- channel readiness

## 6. Strategy generation logic

For each target:
- infer why now
- infer best-fit channel
- infer best conversion path
- map primary angle
- map supporting angle
- define anti-angle
- define CTA and fallback CTA

## 7. Customization mechanism

Customization is driven by:
- account type
- persona type
- signal evidence
- score tier
- channel readiness
- path type

The system avoids pure variable swap personalization.

## 8. Multi-channel strategy

Current supported recommendation logic:
- email
- form
- linkedin/social-friendly path placeholder

Rules:
- email only if channel readiness supports it
- form preferred when email is weak or unknown
- partner path used for distributor/dealer/channel contexts

## 9. Conversion path design

Current path types:
- `direct_response_path`
- `quote_path`
- `partner_path`
- `education_to_conversion_path`

Each strategy task includes:
- path_type
- CTA
- fallback_CTA
- follow-up steps

## 10. Follow-up and cadence

Follow-up is currently generated per task using:
- channel cooldown rules
- path type
- initial message focus
- fallback CTA

## 11. Optimization and learning

Current structure supports:
- strategy hypothesis
- per-account strategy cards
- future feedback patches from Skill 3

`Assumption`: automatic angle win-rate reweighting is the next engineering layer, not yet fully implemented.

## 12. Human supervision points

- A-tier strategy tasks
- approval-required strategy cards
- partner/pricing-sensitive motions

## 13. Success criteria

- strategy tasks are channel-aware and path-aware
- strategy cards are explainable
- approval routing matches account risk
- Skill 3 can consume the output without manual reshaping

# Part D. Skill 3 Design

## 1. Goal

Execute outreach tasks under control and turn outcomes into structured learning.

## 2. Inputs

- strategy tasks
- feedback events
- suppression registry
- project risk rules

## 3. Outputs

- execution queue
- classified feedback
- suppression registry
- feedback patches
- daily report
- weekly report
- anomaly report
- approval queue

## 4. Workflow

1. process feedback events
2. classify outcomes
3. generate suppression decisions
4. generate data/strategy patches
5. generate daily/weekly/anomaly reports
6. generate approval queue
7. apply suppression to execution queue creation

## 5. Execution mechanism

Execution queue currently includes:
- task metadata
- risk level
- approval state
- path type
- CTA
- suppression state

## 6. Automation boundaries

Defined modes:
- manual
- semi-automated
- controlled automated

Current queue layer is execution-safe scaffolding, not channel sender automation.

## 7. Risk control and compliance

Stop conditions supported:
- unsubscribe
- do_not_contact
- hard_bounce
- complaint_risk

Suppression is generated before queue consumption where feedback exists.

## 8. Reply collection and classification

Supported classes:
- positive_interest
- referral
- neutral_question
- not_now
- not_fit
- unsubscribe
- invalid_contact
- hard_bounce
- auto_reply
- spam_complaint_risk
- unclassified

## 9. Feedback return flow

The engine outputs:
- `feedback-patches.json`

Patches target:
- prospect data updates
- strategy updates
- suppression updates

## 10. Daily / weekly / anomaly reporting

Generated files:
- `daily-report.json`
- `weekly-report.json`
- `anomaly-report.json`

## 11. Human supervision points

- approval queue
- positive_interest
- referral
- neutral_question
- spam_complaint_risk

## 12. Success criteria

- suppression-aware execution queue
- structured reply classification
- reproducible reporting outputs
- feedback can be consumed by upstream skills

# Part E. Interface Specifications

## 1. Skill 1 -> Skill 2

Core fields:
- account_id
- contact_id
- company_name
- website_root_domain
- account_type
- persona_type
- fit_score
- intent_score
- total_score
- score_tier
- reachability_status
- top_signals
- source_confidence

## 2. Skill 2 -> Skill 3

Core fields:
- outreach_task_id
- strategy_id
- account_id
- contact_id
- account_type
- persona_type
- buying_context
- channel_readiness
- path_type
- channel
- primary_angle
- support_angle
- anti_angle
- CTA
- fallback_CTA
- followup_plan
- risk_level
- approval_required
- stop_conditions

## 3. Skill 3 -> Skill 1/2

Core fields:
- feedback_id
- task_id
- account_id
- contact_id
- classification
- next_action
- suppression action
- data_patch
- strategy_patch

## 4. Suggested data field conventions

- IDs are stable string keys
- statuses are enum-like
- source provenance is never dropped
- paths and reports are emitted as JSON artifacts first

## 5. Suggested state and lifecycle fields

Suggested cross-skill lifecycle:
- discovered
- normalized
- scored
- strategized
- queued
- attempted
- classified
- suppressed / qualified / converted / recycled

# Part F. Project-Level Orchestration

When a new project starts:

1. initialize project from suite template
2. fill project config
3. drop seed data and/or raw-import files
4. run unified cycle
5. inspect quality gate and review queue
6. inspect strategy cards/tasks
7. inspect approval queue and execution queue
8. execute externally with appropriate human controls
9. feed real outcomes back into `data/feedback-events.json`
10. rerun cycle

# Part G. NEOSGO Example Mapping

For NEOSGO:

- Skill 1 identifies:
  - designers
  - contractors/builders
  - distributors/dealers/showrooms
- Skill 2 maps:
  - designer -> curated/design/trade support angles
  - contractor -> quote/project/repeat ordering angles
  - distributor -> partner economics/channel fit angles
- Skill 3 controls:
  - suppression and invalid handling
  - partner vs quote path execution
  - approval queue for risky outreach

## Execution Blueprint

### Current engineered layer

Already implemented:
- project initialization
- project config validation
- public URL discovery connector
- raw import + seed merge
- quality gate + review queue
- scored prospect generation
- strategy brief
- strategy tasks
- strategy cards
- feedback classification
- suppression registry
- reports
- unified cycle runner

### Next recommended engineering steps

1. live discovery connectors for Skill 1
2. strategy score reweighting from live feedback
3. richer channel-specific copy/output packs
4. feedback patch application back into prospect store/state
5. dashboards for suite artifacts

### Assumptions and validation points

- live crawling/search orchestration is not yet automated
- sender integrations are intentionally not re-enabled by default
- human approvals remain mandatory for sensitive motions
- campaign-grade metrics require real feedback data to become meaningful
