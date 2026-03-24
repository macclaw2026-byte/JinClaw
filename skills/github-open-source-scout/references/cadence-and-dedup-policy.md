# Cadence and De-dup Policy

Use this reference to control how often GitHub scouting runs and how repeated repos are filtered.

## Recommended cadence

### Default
Run every **2 days**.

Why:
- catches useful new or updated repos reasonably quickly
- reduces daily noise
- avoids wasting effort re-reporting unchanged projects too often

### Faster mode
Run **daily** when:
- product-selection-engine is being actively expanded
- us-market-growth-engine is under active iteration
- repeated workflow pain suggests fast capability scouting is valuable
- we are in a heavy tooling-improvement phase

### Slower mode
Run **weekly** when:
- current capabilities are stable
- recent scouting has produced mostly repeats
- maintenance burden is higher than fresh discovery value

## De-dup levels

### Level 1: Exact repo de-dup
If the same repo URL appears again, do not treat it as new.

### Level 2: Already-acted-on suppression
Suppress or downgrade reporting when a repo has already been:
- fully learned from
- converted into a local reference/pattern
- audited and rejected
- audited and installed
- incorporated into an existing skill design

### Level 3: Meaningful-update exception
Re-surface a previously seen repo only when at least one is true:
- major new release or substantial update
- materially improved docs or usability
- new feature highly relevant to our workflows
- project health improved significantly
- a new problem in our system makes the repo newly relevant

## Report hygiene

Do not flood the user with unchanged repeats.

Prefer sections like:
- New
- Meaningfully updated
- Watchlist
- Already integrated / no-action repeats (optional short appendix only)
