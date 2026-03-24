---
name: domain-data-harvester
description: Gather public data from different sites through a shared trunk plus domain-specific branches, then route cleaned evidence into the right in-house skills. Use when the system needs website-specific or domain-specific data acquisition for product selection, marketing research, customer research, competitor analysis, trend analysis, or other multi-source intelligence tasks, especially when different target skills need different data fields and noise control matters.
---

# Domain Data Harvester

Use `../self-cognition-orchestrator/references/monitoring-and-retrofit-framework.md` as the shared monitoring standard when applying this skill's monitoring, backstop, and retrofit logic.
Use `../self-cognition-orchestrator/references/problem-solving-default.md` as the default behavior when acquisition paths fail, go stale, or produce weak evidence.

Build a shared data-acquisition trunk, attach domain/site branches, normalize the output, and route the right evidence to the right local skills.

## Purpose

This skill exists to solve two problems:

1. different missions need different websites, data fields, and extraction patterns
2. once data is gathered, the system needs to know which skill should receive which fields

The goal is not “scrape everything.”
The goal is precise, stable, low-noise evidence delivery.

## Core model

Use a four-layer architecture:

### 1. Shared trunk
Responsible for:
- mission definition
- source-family selection
- safety/compliance checks
- extraction method choice
- evidence normalization
- confidence and noise handling

### 2. Domain branches
Each branch defines:
- which sites matter
- which fields matter
- how to extract them
- how to validate them
- which target skill(s) benefit

Examples:
- product-selection branch
- marketing-intelligence branch
- competitor-landing-page branch
- customer-voice branch
- crowdfunding-blue-ocean branch

### 3. Evidence schema layer
Normalize extracted data into structured fields rather than dumping raw page text.

Each branch should define:
- required fields
- optional fields
- confidence rules
- rejection/noise rules

### 4. Skill-routing layer
Route the normalized evidence to the right destination skill(s), for example:
- product-selection-engine
- us-market-growth-engine
- resilient-external-research
- guarded-agent-browser-ops
- safe-learning-log
- runtime-evolution-loop


## Multi-tool acquisition and evidence arbitration

Do not rely on a single extraction tool or one-shot scrape when better redundancy is possible.

For important missions, prefer a multi-tool acquisition pattern:
- primary method
- backup method A
- backup method B
- normalized comparison
- best-evidence selection

Possible method families include:
- `web_fetch`
- built-in `browser`
- `resilient-external-research`
- `guarded-agent-browser-ops`
- local `crawl4ai` wrapper when installed and appropriate
- local patterns inspired by audited/open-source tooling when justified

### Rule

If one tool gives weak, partial, blocked, or suspicious output:
- do not stop at the first result
- compare against one or more backup methods when the mission matters
- normalize outputs into the same field schema
- prefer the strongest, freshest, most internally consistent evidence

### Evidence arbitration

When multiple tools disagree, compare them on:
- completeness
- freshness
- source fidelity
- structural cleanliness
- consistency with other source families
- downstream usefulness for the target skill

Then select one of:
- best single source
- merged structured record
- unresolved conflict with downgraded confidence

### Cleaning and de-noising

After gathering from multiple methods:
- remove duplicate facts
- collapse equivalent records
- keep provenance for each surviving field
- discard noisy fields that are unsupported or low-value
- label approximate/inferred fields clearly


## Shared trunk workflow

### Step 1: Define the mission
Clarify:
- what decision is this data meant to support?
- which downstream skill is the main consumer?
- what data fields are required versus merely nice to have?

### Step 2: Choose the branch
Pick the branch that best fits the mission.

If none fit, define a temporary branch pattern and consider whether a reusable local branch should be created.

### Step 3: Select source families
Choose which source families matter:
- trend sources
- marketplace/product pages
- search/discovery surfaces
- review/comparison pages
- communities/forums
- supplier/manufacturer sources
- crowdfunding/new-product sources
- official docs/data sources

### Step 4: Select extraction method stack
Choose the lightest compliant method stack that can still get the needed fields:
- primary extraction method
- one or more backup methods for important or fragile targets
- multi-source synthesis when no single tool is strong enough

Common methods:
- web_fetch
- browser
- local Crawl4AI
- resilient-external-research
- guarded-agent-browser-ops
- audited/open-source-inspired local patterns when justified

### Step 5: Normalize, compare, and arbitrate evidence
Convert raw findings into structured records, compare them across tools, and select or merge the best surviving evidence.

Each record should try to include:
- source
- page/surface type
- extracted field names
- extracted values
- confidence
- freshness
- downstream target skill

### Step 6: Route the evidence
Do not dump all gathered data into every skill.

Instead, route only the useful subset to each consumer.

### Step 7: Reflect and evolve
After a meaningful run:
- log which sources were useful
- log which fields were noisy or misleading
- log which branch logic needs improvement
- promote recurring patterns into references, templates, or new branch files

## Routing discipline

Different target skills need different data.

### Product-selection-engine should receive data such as:
- trend strength
- search volume / intent clues
- marketplace activity proxies
- competitor density
- review depth
- price ladder
- manufacturability clues
- blue-ocean / crowdfunding inspiration signals

### us-market-growth-engine should receive data such as:
- customer segments
- buyer pain points
- message angles
- channel clues
- competitor positioning
- landing-page/conversion observations
- review/complaint clusters

### resilient-external-research should receive:
- source-quality issues
- missing fields
- conflict notes
- fallback opportunities

### safe-learning-log / runtime-evolution-loop should receive:
- repeated source failures
- repeated branch mismatches
- recurring noisy fields
- successful new field/routing patterns worth promoting

## Guardrails

- do not send raw noisy page dumps downstream when normalized fields would do
- do not mix marketing data with product-selection fields without labeling purpose clearly
- do not force one site pattern onto all missions
- do not over-trust a single source family
- do not bypass access controls or protected pages

## References

Read these as needed:
- `references/architecture.md`
- `references/branch-map.md`
- `references/evidence-schema.md`
- `references/routing-map.md`
- `references/branch-amazon-marketplace.md`
- `references/branch-walmart-marketplace.md`
- `references/branch-crowdfunding-blue-ocean.md`
- `references/branch-customer-voice.md`
- `references/branch-competitor-pages.md`
- `references/tool-redundancy-and-arbitration.md`
