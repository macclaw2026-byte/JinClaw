<!--
RULES-FIRST NOTICE:
Before modifying this file, first read:
- `JINCLAW_CONSTITUTION.md`
- `AI_OPTIMIZATION_FRAMEWORK.md`
Follow the constitution and framework:
brain-first, one-doctor, fail-closed, evidence-over-narration,
validate locally, then use the required PR workflow.
-->
# Acquisition Hand Upgrade

## What Changed

JinClaw/OpenClaw now exposes a unified `acquisition_hand` contract in `metadata.control_center`.

This contract does not replace the existing `crawler` payload yet.
It wraps the current fetch/crawler chain in a more general, reusable control surface for any task that needs external data.

The current phase also extends that control surface into execution evidence:

- the adapter catalog is now a concrete adapter market instead of only stack-level labels
- execution results can be normalized into a route-aware `acquisition execution summary`
- verifier/runtime/doctor now have a shared artifact for planned-vs-executed route gaps and site-level consensus
- task-level `delivery_requirements` now define which fields are truly required for release versus only nice-to-have
- acquisition summaries now expose `release_readiness_status` so doctor/runtime can tell the difference between missing critical fields and missing stretch fields
- acquisition summaries now also expose `trusted_release_status`, making it explicit whether required fields are backed mainly by higher-trust sources or only by browser/public-fetch evidence
- acquisition hand now carries explicit `release_governance`, so the system can distinguish automatic release, guarded release with disclosure, user-confirmed guarded release, and must-recapture states
- acquisition summaries now expose `governed_release_status`, turning trust/freshness posture into an actual delivery rule instead of just passive metadata
- guarded results now emit structured `release_disclosure`, so user-facing caveats and operator-facing release blockers come from the same schema
- fresh tasks now support field-level `freshness_priority` resolution when competing routes have equal trust rank but different freshness posture
- acquisition summaries now also emit structured `answer_synthesis`, so downstream reply/runtime layers can directly consume a governed answer contract instead of reverse-engineering `final_fields`
- task snapshots and response policy now consume that answer contract directly, so user-visible authoritative replies can distinguish `auto_answer`, `guarded_answer`, `confirm_then_guarded_answer`, and `pause_and_recapture`
- stage context, ACP dispatch, and runtime execution prompts now consume a structured `response_handoff`, so acquisition answer governance reaches the execution chain instead of stopping at status receipts
- crawler execution truth is now explicitly reconciled across `site-profile`, `latest-run`, and `contract`, so router/doctor no longer treat those three layers as independent truths
- crawler capability health now exposes `sites_with_evidence_drift` and `evidence_alignment_score`, and the canonical doctor treats this execution-truth alignment as a first-class monitored contract

## New Core Structures

- `acquisition_adapter_registry`
  - Concrete adapter market built from the crawler stack registry, local capability availability, and observed-but-not-yet-wired anti-bot/browser adapters.
- `acquisition_hand`
  - Unified data-acquisition protocol with:
    - target profile
    - delivery requirements
    - release governance
    - governance binding
    - challenge assessment
    - routing policy
    - route candidates
    - execution strategy
    - result consensus
    - evidence contract
    - learning contract
- `acquisition_execution_summary`
  - Execution-time normalized artifact with:
    - planned routes
    - executed routes
    - planned-vs-executed gaps
    - per-site winner / validation status
    - required-field coverage and release readiness
    - trust posture and trusted-release status
    - freshness posture and governed-release decision
    - structured release disclosure
    - site-level and task-level answer synthesis contracts
    - overall consensus status
- crawler execution-truth alignment
  - Capability profile now derives a single execution truth from:
    - site profile cache
    - latest-run summary
    - contract-level field-gated execution decision
  - It also exposes:
    - `execution_truth_source`
    - `evidence_alignment.status`
    - `route_preference_strength`
    - summary-level `sites_with_evidence_drift`
    - summary-level `evidence_alignment_score`
- structured `challenge` signals
  - Challenge classification now emits severity, signals, safe next routes, and anti-bot posture hints.

## Compatibility Strategy

- keep `crawler` intact for current runtime execution and verifier paths
- map current crawler selected stack and fallback stacks into `acquisition_hand.compatibility`
- let stage context, ACP dispatch, task snapshot, and doctor consume `acquisition_hand`
- let execute-stage crawler runs write `crawler-acquisition-summary.json/.md` beside the existing crawler report
- let verifier/runtime treat missing acquisition summary as a first-class integration gap when acquisition hand is enabled
- preserve fail-closed behavior for human verification and authorized-session routes

## Why This Matters

Before this upgrade, the system had a crawler governance layer but not a general-purpose “data acquisition hand”.

After this upgrade, JinClaw can reason about external data collection as:

1. a governed capability
2. a multi-route decision problem
3. a consensus-and-evidence problem
4. a reusable learning surface

This makes future adapter additions such as stronger browser stacks or new structured-source connectors an adapter-registry task instead of a main-orchestrator rewrite.

It also means the system can now explain:

1. which route it planned
2. which route actually executed
3. whether multiple routes agreed
4. where route coverage is still missing
5. whether the current result may be auto-delivered, only guarded-delivered, or must first gather fresher / higher-trust evidence
6. what exact caveat text should accompany a guarded release
7. what response mode the downstream layer should use right now: auto answer, guarded answer, confirmation-first answer, or pause-and-recapture
8. whether a site's route preference is backed by aligned execution evidence or only guarded because profile/latest-run/contract still disagree
