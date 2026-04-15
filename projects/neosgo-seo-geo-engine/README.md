<!--
RULES-FIRST NOTICE:
Before modifying this file, first read:
- `JINCLAW_CONSTITUTION.md`
- `AI_OPTIMIZATION_FRAMEWORK.md`
Follow the constitution and framework:
brain-first, one-doctor, fail-closed, evidence-over-narration,
validate locally, then use the required PR workflow.
-->
# Neosgo SEO + GEO Marketing Engine

This project automates admin-side SEO and GEO operations for Neosgo through the
Admin Marketing API described in the OpenClaw Admin Marketing API Guide.

Primary goals:

- maintain a backlog of high-intent Design Notes
- identify content gaps against Neosgo's category and room-based navigation
- ingest historical performance and feedback before every run
- distill prior runs and optional analytics snapshots into a reusable strategy signal
- do one market-research pass before deciding what to create next
- create or update draft Design Notes through the admin API
- create or update GEO variants for priority markets
- optionally run a separate interior-designer daily article queue for trade-facing professional content
- produce one daily operating report to chat at 9:00 AM New York time

Default safety mode:

- `draft_only`
- no auto-publish unless explicitly enabled in config

Core entrypoint:

- `scripts/run_neosgo_seo_geo_cycle.py`

Execution order:

1. sync Google Search Console snapshots when configured
2. ingest history and optional feedback files
3. distill historical signal
4. build an opportunity registry across create/refresh/expand/build-geo actions
5. run market-gap research against note inventory and GEO coverage
6. compute an adaptive topic strategy
7. create/update draft notes and GEO variants
8. run a technical release gate before any publish call
9. write state and deliver a daily report

Optional feedback drop folder:

- `/Users/mac_claw/.openclaw/workspace/projects/neosgo-seo-geo-engine/runtime/feedback`

Hardcore automation upgrade reference:

- `references/seo-geo-hardcore-automation-plan-2026-04.md`

New output artifacts:

- `output/<run_id>/opportunity-registry.json`
- `output/<run_id>/page-action-plan.json`
- `output/<run_id>/maintenance-plan.json`
- `output/<run_id>/consolidation-plan.json`
- `output/<run_id>/technical-release-gates.json`

Interior designer daily article program:

- configured under `designer_daily_program` in `config/strategy.json`
- default is `enabled: false` so no new trade article auto-publishes until explicitly turned on
- publishes base Design Notes only; it intentionally does **not** auto-create GEO variants for trade/editorial pieces
- queue items can define stronger `requiredPatterns`, `qualityThreshold`, and `customInternalLinks`
- recommended rollout: enable only after reviewing the first queued articles in draft/staging or after a one-time manual check

Accepted snapshot fields:

- `slug`
- `clicks`
- `impressions`
- `ctr`
- `avgPosition`
- `feedbackScore`
- `conversionRate`
- `city`
- `state`

Required secret file:

- `/Users/mac_claw/.openclaw/secrets/neosgo-marketing.env`

Expected secret names:

- `NEOSGO_ADMIN_MARKETING_KEY`
- `NEOSGO_ADMIN_MARKETING_KEY_TEST` (optional)
- `NEOSGO_ADMIN_MARKETING_API_BASE` (optional, defaults to production)
- `NEOSGO_SEO_GEO_TELEGRAM_CHAT` (optional, defaults to existing main chat)
- `NEOSGO_GSC_ENABLED` (`true` to turn on automatic GSC sync)
- `NEOSGO_GSC_SITE_URL` (for example `sc-domain:neosgo.com` or the verified URL-prefix property)
- `NEOSGO_GSC_CLIENT_ID`
- `NEOSGO_GSC_CLIENT_SECRET`
- `NEOSGO_GSC_REFRESH_TOKEN`
- `NEOSGO_GSC_LOOKBACK_DAYS` (optional, defaults to 28)
- `NEOSGO_GSC_ROW_LIMIT` (optional, defaults to 250)

Recommended long-term GSC automation flow:

1. In Google Cloud, enable the Search Console API.
2. Create an OAuth client for a desktop app or web app.
3. Use the Google account that already has access to the `neosgo.com` Search Console property to complete one OAuth consent flow and obtain a refresh token.
4. Put the client ID, client secret, refresh token, and property identifier into `/Users/mac_claw/.openclaw/secrets/neosgo-marketing.env`.
5. The daily SEO+GEO cycle will then pull `pages`, `queries`, `countries`, and `page_queries` snapshots automatically before every content run.
