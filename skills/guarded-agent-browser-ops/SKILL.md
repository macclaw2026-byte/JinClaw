---
name: guarded-agent-browser-ops
description: Use the locally installed guarded `agent-browser` tool for browser automation and structured page extraction when browser interaction is better than simple fetches. Use for dynamic pages, controlled snapshots, element interaction, screenshots, accessibility-tree extraction, and repeatable browser workflows — especially when `resilient-external-research`, `us-market-growth-engine`, or other in-house skills need a local browser operator. Prefer minimal-risk commands first. Do not use auth-state, cookies, storage, credentials, or browser-profile features unless a second sensitive-capability review explicitly justifies it.
---

# Guarded Agent Browser Ops

Use the local `agent-browser` installation in a controlled way.

## Local install path

Current local install root:

- `/Users/mac_claw/.openclaw/workspace/tools/agent-browser-local`

Primary binary for this machine:

- `/Users/mac_claw/.openclaw/workspace/tools/agent-browser-local/node_modules/agent-browser/bin/agent-browser-darwin-arm64`

## Purpose

This skill exposes browser-automation capability to in-house skills while preserving guarded-install boundaries.

Use `../self-cognition-orchestrator/references/monitoring-and-retrofit-framework.md` as the shared monitoring standard when deciding browser-state checks, result validation, delayed backstops, and retrofit expectations for browser-heavy workflows.

## Allowed default use cases

These are allowed by default:

- open a public page
- snapshot page structure
- click / fill / type on public or authorized pages when appropriate
- get text / html / title / url
- screenshot / pdf
- wait for page or text
- batch multi-step browser actions
- run browser workflows that do not require sensitive auth-state features

## Restricted capabilities

Do not use these by default:

- `state save`
- `state load`
- cookie export / manual cookie management
- storage inspection (`localStorage`, `sessionStorage`) on sensitive sites
- credentials / basic auth
- browser-profile import
- remote debugging auth import

If any of the above is needed, require a second sensitive-capability review first.

## Operating order

1. prefer the built-in OpenClaw `browser` tool when it already solves the task cleanly
2. use `guarded-agent-browser-ops` when a repeatable local CLI browser workflow is better
3. start with low-risk commands
4. keep outputs focused on the requested data
5. if the task would touch auth/session state, stop and reassess before continuing

## Suggested command patterns

Low-risk examples:

```bash
<agent-browser-bin> open <url>
<agent-browser-bin> snapshot
<agent-browser-bin> get title
<agent-browser-bin> get url
<agent-browser-bin> screenshot <path>
<agent-browser-bin> wait --text "..."
```

Prefer batch mode for multi-step flows when practical.

## Output expectations

When using this skill, try to return structured results such as:

- extracted text
- page structure / refs
- screenshots
- selected attributes
- step-by-step browser outcomes

## Relationship to other skills

- `resilient-external-research` can use this when browser rendering is required
- `us-market-growth-engine` can use this for website review, conversion checks, and public buyer-path analysis
- `continuous-execution-loop` can use this inside staged browser workflows
- `skill-security-audit` still governs any expansion into sensitive auth/state features

## Monitoring and safety backstops

Browser automation can look successful while silently missing content or interacting with the wrong state.

Monitor these layers when relevant:

- **page-state monitor** — did the intended page, tab, or UI state actually load?
- **interaction-result monitor** — did the click/type/fill action have the expected visible effect?
- **content-completeness monitor** — was the requested information actually revealed, not just nearby chrome or placeholders?
- **sensitive-boundary monitor** — did the workflow drift toward cookies, auth state, credentials, or storage-sensitive behavior?
- **backstop monitor** — what second-pass snapshot, selector check, or alternate method confirms the result?

If browser actions appear to succeed but evidence is weak, verify again before concluding.

If repeated browser misses occur, feed them into `safe-learning-log` and `runtime-evolution-loop` so browser-heavy skills gain better guardrails over time.
