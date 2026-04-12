<!--
RULES-FIRST NOTICE:
Before modifying this file, first read:
- `JINCLAW_CONSTITUTION.md`
- `AI_OPTIMIZATION_FRAMEWORK.md`
Follow the constitution and framework:
brain-first, one-doctor, fail-closed, evidence-over-narration,
validate locally, then use the required PR workflow.
-->
# Interior Designer Daily Article Program

Purpose:

- add one separate daily content lane for interior designers and design studios
- keep the article style more professional and specification-aware than the current consumer-facing SEO guides
- publish through the existing Neosgo Design Notes pipeline so the content lands on `neosgo.com/notes/<slug>`

Why this should be a separate lane:

- the existing note backlog is optimized for high-intent consumer SEO guides
- trade readers need different questions answered: specification logic, finish coordination, client approval, procurement risk, and sourcing flow
- GEO expansion is useful for consumer/local search, but it is not the right default for professional editorial pieces

Recommended stable publishing model:

1. Keep designer articles as base notes only.
2. Use a curated article queue instead of open-ended freeform generation.
3. Require stronger editorial checks before publish.
4. Send each article through the existing admin API publish path.

Current implementation shape:

- config key: `designer_daily_program`
- switch: `enabled`
- queue: `article_queue`
- one article max per local day
- timezone control: `state_timezone`
- output path: normal Design Notes publish flow

Why a curated queue is the safest first step:

- higher quality than trying to synthesize a brand-new trade topic blindly every day
- easier to review and tune voice, section structure, and CTAs
- lower risk of repetitive or shallow posts
- predictable for operations and reporting

Quality controls that matter for this lane:

- audience must explicitly target interior designers or trade buyers
- sections should cover project reality, specification checkpoints, client communication, and procurement
- internal links should include the trade program and the most relevant collection path
- avoid retail-only language and vague inspiration copy
- avoid markdown artifacts in body copy that render awkwardly on the public note page

Recommended editorial structure:

- why this matters on a real project
- specification checkpoints to lock early
- how to discuss the choice with clients
- procurement and coordination notes
- what to do next inside Neosgo

Rollout plan:

1. Keep `enabled: false` while reviewing the seeded queue.
2. Turn it on for one daily article after reviewing the first 3-5 briefs.
3. Watch indexing, click-through rate, page engagement, and whether trade-program traffic increases.
4. Expand the queue only after confirming the first batch reads like real professional guidance rather than padded SEO copy.

What not to do first:

- do not auto-generate GEO variants for designer articles by default
- do not rely on thin FAQ padding as a quality substitute
- do not publish a large batch at once; daily pacing keeps review and signal cleaner
