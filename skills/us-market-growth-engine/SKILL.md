---
name: us-market-growth-engine
description: General-purpose US market growth and customer development skill. Use when the goal is to market, sell, or develop customers for a website, product line, service, niche, or business in the US market — including B2B, B2C, trade, local business, ecommerce, and category-specific scenarios such as lighting, furniture, home decor, commercial products, or other verticals. Interpret the target market, identify customer segments, determine whether the motion is acquisition, outreach, conversion, retention, or research, and build the best channel/offer/website/conversion strategy with room for ongoing optimization.
---

# US Market Growth Engine

Use `../self-cognition-orchestrator/references/monitoring-and-retrofit-framework.md` as the shared monitoring standard when applying this skill's monitoring, backstop, and retrofit logic.

A reusable marketing and growth skill for US-focused customer development.

## Purpose

Do not lock marketing thinking to one product category.

This skill should provide a reusable marketing framework that can adapt to:

- lighting websites
- furniture brands
- home decor products
- trade / wholesale outreach
- commercial buyers
- niche B2B segments
- end consumers in specific US verticals

## Core operating model

For any target, first answer these questions:

1. What is being sold?
2. Who is the buyer?
3. Is the buyer B2B, B2C, or hybrid?
4. What triggers their purchase?
5. What channels are most likely to reach them?
6. What makes them trust the offer?
7. What is the desired conversion event?
8. What feedback loop will improve performance?

## Primary jobs

This skill should help with:

- customer segmentation
- target market definition
- ICP and persona building
- channel selection
- outreach strategy
- offer positioning
- website conversion improvement
- lead qualification
- contact discovery strategy
- content angle development
- campaign iteration

## Execution order

### Step 1: Classify the mission

Identify which of these applies:

- market research
- customer discovery
- lead generation
- outreach
- website conversion optimization
- retention / follow-up
- end-to-end acquisition funnel design

A task may involve more than one.

### Step 2: Define the target customer

For the current target, identify:

- buyer type
- company type or consumer type
- role / decision maker
- pain points
- buying triggers
- objections
- desired outcome

### Step 3: Define the conversion path

Map the exact desired path.

Examples:

- search -> website -> inquiry
- outreach -> website -> quote request
- social content -> product page -> purchase
- directory lead -> email -> trade account application

### Step 4: Choose channels

Possible channels include:

- Google / search intent
- SEO
- LinkedIn
- email outreach
- website contact forms
- directories
- social discovery (Pinterest / Instagram / Facebook / TikTok)
- paid ads
- remarketing
- local / niche commercial databases

Pick channels based on the buyer, not habit.

### Step 5: Build the message

Develop:

- positioning angle
- first-contact message
- landing-page angle
- CTA
- trust elements
- follow-up sequence

### Step 6: Measure what matters

Track:

- response rate
- click-through to site
- inquiry rate
- quote/sample/trade-account requests
- purchases
- which segment/channel/message performs best

### Step 7: Improve continuously

After each real task, use `safe-learning-log` to capture:

- which segment responded best
- which channels underperformed
- what message angle worked
- what website friction appeared
- whether a niche-specific extension should be added

## Monitoring and optimization model

Different growth motions need different monitors. Do not assume one KPI or one hook is enough.

Monitor across these layers when relevant:

- **audience-fit monitor** — are we targeting the right buyer and decision-maker?
- **message-fit monitor** — does the value proposition match the buyer's trigger and objection pattern?
- **channel-fit monitor** — is the chosen channel actually suited to the segment and offer?
- **conversion-friction monitor** — where does the buyer path break: attention, trust, click, inquiry, quote, purchase, or follow-up?
- **learning-backstop monitor** — what delayed review should catch false optimism, weak attribution, or silent underperformance?

Coverage rule:

- do not judge channel success only by traffic if conversion quality is weak
- do not judge offer success only by anecdotal feedback if no conversion signal exists
- when a path underperforms, identify whether the failure is audience, message, channel, or conversion friction before changing everything at once

Remediation and evolution rule:

- if a growth recommendation later underperforms because the wrong thing was monitored, record that monitoring miss explicitly
- route repeat misses into `runtime-evolution-loop` so the core growth framework and niche extensions gain better checks
- when the same niche repeatedly needs special audience/channel/conversion logic, create or improve a focused extension skill instead of bloating the core

## Niche adaptation rule

This skill is intentionally generic.

When a niche becomes important enough, create or improve a niche extension rather than bloating this core skill.

Examples:

- lighting-focused extension
- furniture-focused extension
- contractor/designer outreach extension
- local commercial buyer extension

Keep the core universal and adapt the edges.

When the same niche appears repeatedly and the buyer logic, channel logic, and messaging become specialized, create a dedicated extension skill.

Examples:

- lighting-focused extension
- furniture-focused extension
- contractor/designer outreach extension
- local commercial buyer extension

Keep the core universal and adapt the edges.

## When working with websites

Always consider:

- site trust and credibility
- page structure
- inquiry path
- purchase friction
- professional vs consumer landing paths
- whether a visitor should buy now, request quote, request sample, or contact sales

When website review or buyer-path inspection needs a real browser workflow, prefer:

1. built-in OpenClaw `browser` tool
2. `guarded-agent-browser-ops` for repeatable local browser CLI workflows

## When working with outreach

Always consider:

- who exactly should be contacted
- how contact info may be found ethically and effectively
- what first message matches the role
- what follow-up cadence is reasonable
- how to move them from contact -> site -> conversion event

## Relationship to other skills

- use `self-cognition-orchestrator` to interpret the assignment and select the best path
- use `continuous-execution-loop` for long, multi-stage growth projects
- use `resilient-external-research` when buyer, market, competitor, directory, or website information must be gathered from external sources
- use `product-selection-engine` when the growth task depends on choosing or validating products/categories before marketing execution
- use `skill-security-audit` before any third-party skill install
- use `skill-creator` if a reusable niche sub-skill should be created
- use `safe-learning-log` after each execution cycle to improve the system

## Good operating style

Prefer:

- customer clarity before channel execution
- narrow ICP before broad outreach
- clear offer before aggressive promotion
- measurable loops over vague marketing ideas
- reusable frameworks over niche lock-in

Avoid:

- generic spray-and-pray marketing
- using the same message for every audience
- treating B2B and B2C as identical
- channel choice without buyer logic
- running campaigns with no learning loop
