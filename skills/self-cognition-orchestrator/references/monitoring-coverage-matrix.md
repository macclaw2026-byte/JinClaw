# Monitoring Coverage Matrix

Use this matrix to track how completely each in-house skill family participates in the shared monitoring-and-retrofit framework.

## Status legend

- **covered** — primary monitoring/backstop/remediation/evolution language is explicit and reusable
- **partially covered** — core intent is aligned, but some helper references, scripts, or operational policies still rely on implicit judgment
- **not yet covered** — major monitoring/backstop language is still missing

## Skill matrix

| Skill / area | Status | Retrofit priority | Notes |
|---|---|---:|---|
| self-cognition-orchestrator | covered | low | owns shared framework, decision table, coverage audit |
| continuous-execution-loop | covered | low | templates and integration notes now carry monitor/backstop fields |
| error-recovery-loop | covered | low | recoverable-errors reference now distinguishes monitor misses |
| runtime-evolution-loop | covered | low | explicit hook-placement and retrofit framework |
| safe-learning-log | covered | low | usage notes + delayed backstop example included |
| skill-security-audit | covered | low | checklist + guarded install + replacement trigger aligned |
| guarded-agent-browser-ops | covered | medium | core guidance aligned; future enablement review needed if sensitive flows expand |
| resilient-external-research | covered | low | fallback patterns and confidence controls aligned |
| capability-gap-router | covered | medium | core SKILL aligned; future references could be added if it grows |
| skill-discovery-or-create-loop | covered | medium | closure/backstop logic present; could gain helper references later |
| product-selection-engine | covered | low | SKILL + decision/data references + learning hook aligned |
| us-market-growth-engine | covered | low | SKILL + framework/deliverables/improvement/niche policy aligned |

## Hook / example matrix

| Hook example | Status | Enable-by-default posture | Notes |
|---|---|---:|---|
| post-tool-error-recovery.sh | covered | no | good low-risk example; enable only where tool-failure review is wanted |
| post-tool-review.sh | covered | no | useful reminder hook; keep narrow |
| delayed-backstop-review.sh | covered | no | best kept opt-in until a real delayed-review trigger is defined |
| post-run-selection-learning.sh | covered | no | domain-specific post-run hook |
| user-prompt-reminder.sh | covered | no | reminder now references primary monitor / backstop / blind spots |

## Remaining low-priority follow-up ideas

- add capability-gap-router / discovery loop helper references only if those skills grow in complexity
- review any future non-example hook enablement through `skill-security-audit` and the hook activation policy
