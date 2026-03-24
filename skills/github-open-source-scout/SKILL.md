---
name: github-open-source-scout
description: Scout GitHub for newly relevant open-source projects that could improve in-house skills, workflows, research depth, product-selection, marketing, ecommerce intelligence, data analysis, browser automation, scraping resilience, or operational tooling. Use when periodically scanning for useful open-source tools, when asked to find GitHub projects that could strengthen product-selection-engine or us-market-growth-engine, or when converting discovered tools into concrete skill/runtime improvement ideas.
---

# GitHub Open Source Scout

Use `../self-cognition-orchestrator/references/monitoring-and-retrofit-framework.md` as the shared monitoring standard when applying this skill's monitoring, backstop, and retrofit logic.
Use `../self-cognition-orchestrator/references/self-improvement-safety-gate.md` before proposing autonomous self-improving changes based on discovered tools.

Find useful open-source projects on GitHub, evaluate whether they can strengthen the local skill graph, and convert findings into concrete, safe improvement proposals.

## Purpose

This skill is not for random GitHub browsing.

It exists to answer:
- what new open-source projects could improve our product-selection, marketing, research, analysis, browser, or automation capabilities?
- how should those discoveries map into existing in-house skills?
- should we adopt, adapt, learn from, or ignore each project?

## Search focus

Prioritize projects that could improve these capability areas:

- ecommerce product research
- market research and trend analysis
- marketing intelligence and customer research
- Amazon / Walmart analysis workflows
- browser automation and structured extraction
- public-web data collection quality
- review analysis / text clustering / complaint mining
- keyword clustering / demand estimation / sales proxy modeling
- supplier / sourcing / catalog analysis
- dashboards, notebooks, and lightweight analytics tooling

## Workflow

### Step 1: Define the scouting mission

Clarify:
- which capability area is being improved
- which in-house skill(s) might benefit
- whether the goal is direct adoption, workflow inspiration, or replacement/extension

### Step 2: Search broadly on GitHub and adjacent public sources

Search for:
- active repositories
- newer or recently updated tools
- tools with clear practical usage rather than hype-only demos
- projects with readable source and focused purpose

Also consider:
- GitHub topics
- GitHub trending/recently active repos
- public issue discussions
- related docs sites when they explain the tool clearly

### Step 3: Evaluate relevance

For each candidate, ask:
- what exact problem does it solve?
- which in-house skill or workflow would improve if this existed locally?
- is this better as inspiration, a reference, a script pattern, a new skill, or not useful?

### Step 4: Evaluate quality and safety posture

Check at minimum:
- repo activity / freshness
- clarity of purpose
- code visibility
- practical usefulness
- maintenance quality
- integration complexity
- security sensitivity

If installation or direct use is under consideration, route through `skill-security-audit` before any third-party install decision.

### Step 5: Convert findings into local improvement proposals

For each worthwhile project, produce:
- short summary of what it does
- why it matters to us
- which local skill(s) it could improve
- recommended action:
  - ignore
  - monitor
  - learn-from-only
  - build local reference/pattern from it
  - evaluate for guarded install
  - create a new in-house extension skill

### Step 6: Feed the evolution loop

After a useful scouting run:
- log durable findings with `safe-learning-log`
- trigger `runtime-evolution-loop` if repeated discoveries suggest a broader capability gap
- improve `product-selection-engine`, `us-market-growth-engine`, `resilient-external-research`, or other affected skills when justified


## Recommended cadence

Default recommendation:
- run every **2 days** as the baseline cadence
- run **daily** only when we are actively evolving product-selection, marketing, research, or automation skills at high speed
- run **weekly** if the system is stable and we only want lower-noise strategic updates

Practical default: every **2 days** is the best balance between freshness and noise.

## De-duplication and incremental tracking

Do not treat each scouting run as a blank slate.

Maintain a local memory/state record so repeated repos are handled intelligently.

For each project, track at least:
- repo url
- first seen date
- last seen date
- last updated status when known
- current disposition
  - ignored
  - monitoring
  - learned-from
  - already integrated
  - already audited
  - already installed/used
- last meaningful action taken

On each new run:
- suppress projects that were already integrated and have no meaningful update
- suppress projects already fully learned-from unless something material changed
- suppress projects already installed/used unless there is a notable update, issue, fork, or new feature that matters
- keep previously seen projects only when they have a meaningful freshness or relevance delta

Preferred output sections:
- **new high-value discoveries**
- **previously seen but meaningfully updated**
- **no-action repeats suppressed from main report**

Read these as needed:
- `references/cadence-and-dedup-policy.md`
- `references/state-schema.md`
- `references/report-template.md`

## Output format

Prefer a table-like or spreadsheet-ready output with fields such as:
- project
- repo url
- category
- what it does
- why it matters
- likely beneficiary skill
- adoption mode
- security / integration caution
- priority

## Hook expectations

This skill should connect to:
- `product-selection-engine`
- `us-market-growth-engine`
- `resilient-external-research`
- `safe-learning-log`
- `runtime-evolution-loop`
- `skill-security-audit`

Useful trigger situations:
- periodic capability scan
- repeated pain in a workflow
- recurring external-research weakness
- repeated data-analysis friction
- need for a stronger platform-specific product-research branch

## Guardrails

- do not install third-party tools automatically without audit
- do not confuse popularity with usefulness
- do not adopt tools that are opaque, risky, abandoned, or badly scoped
- prefer learning from a tool over blindly depending on it
- convert discoveries into local durable improvements when safer and more reusable

## References

Read these as needed:
- `references/evaluation-rubric.md`
- `references/search-areas.md`
- `references/report-template.md`
