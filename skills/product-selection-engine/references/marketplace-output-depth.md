# Marketplace Output Depth

Use this reference when the user wants fuller Amazon/Walmart product lists rather than a tiny shortlist.

Use the shared monitoring standard from `../../self-cognition-orchestrator/references/monitoring-and-retrofit-framework.md`.

## Default depth target

For marketplace-oriented runs:
- Amazon branch -> at least 20 ranked product candidates
- Walmart branch -> at least 20 ranked product candidates

## Expansion rule

If top-tier confidence only covers a handful of products, do not stop there.
Expand using:
- narrower sub-niches
- adjacent product forms
- bundle variants
- utility-focused variations
- use-case-driven alternatives

The goal is not filler. The goal is a broader but still decision-useful candidate field.

## Required fields for expanded candidate lists

For each candidate, try to include:
- rank
- product / sub-niche
- platform fit
- buyer problem
- selling point
- competition survivability
- manufacturability
- confidence
- recommendation

## Guardrail

Do not inflate the list with excluded categories, brand-dependent ideas, or obviously low-quality filler just to hit 20.


Also read `competitor-link-gathering.md` when the user wants live marketplace links for each candidate.
