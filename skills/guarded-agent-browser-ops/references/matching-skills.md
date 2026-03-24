# Matching Skills for Guarded Agent Browser Ops

Use the shared monitoring standard from `../../self-cognition-orchestrator/references/monitoring-and-retrofit-framework.md` when wiring browser capability into other skills so each match also defines validation and backstops.

## Strong matches

### resilient-external-research
Use when web fetch/search is incomplete and browser rendering or interaction is needed.

Recommended monitors:
- content completeness
- source trust
- delayed backstop when render output is ambiguous

### us-market-growth-engine
Use for:
- landing-page review
- website conversion-path review
- public competitor page inspection
- public directory browsing
- buyer journey inspection on public pages

Recommended monitors:
- page-state check
- interaction-result check
- conversion-friction check

### continuous-execution-loop
Use when a long task includes a browser-driven stage and needs repeatable local browser steps.

Recommended monitors:
- stage checkpoint review
- stall detection
- backstop validation before stage completion

### self-cognition-orchestrator
Use as an optional capability source when browser CLI workflows are the best execution path.

Recommended monitors:
- skill-selection fit
- sensitive-boundary drift

## Conditional matches

### future niche growth extensions
Examples:
- lighting B2B outreach extensions
- furniture buyer outreach extensions
- category-specific site review skills

## Not a strong default match

- safe-learning-log (logs learnings, does not need direct browser automation)
- skill-security-audit (audits tools/skills; does not need browser automation by default)
