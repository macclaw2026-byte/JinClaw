<!--
RULES-FIRST NOTICE:
Before modifying this file, first read:
- `JINCLAW_CONSTITUTION.md`
- `AI_OPTIMIZATION_FRAMEWORK.md`
Follow the constitution and framework:
brain-first, one-doctor, fail-closed, evidence-over-narration,
validate locally, then use the required PR workflow.
-->
# Operator Inputs

Put the first-round NEOSGO social + GEO prerequisite files in this directory.

Expected files:

- `brand-facts-master.json`
- `brand-asset-library.json`
- `top-sku-priority-list.json`
- `pinterest-business-access.json`
- `instagram-business-access.json`
- `google-brand-profile-access.json`
- `bing-webmaster-access.json`
- `review-monitoring-targets.json` (optional)

These file names are referenced by:

- `config/social_geo_program.json`
- `scripts/social_geo_readiness_check.py`
