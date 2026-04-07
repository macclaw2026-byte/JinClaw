# Tool name mapping for neosgo-lead-engine-followup-6

Date: 2026-03-30

## Question
- raw-http-fetch 是哪个工具？
- agent-browser-cli 是哪个工具？

## Verified local findings

### 1) `agent-browser-cli`
Not found as a first-class OpenClaw tool name in the current environment.

Closest verified local equivalent:
- local guarded `agent-browser` installation referenced by skill `guarded-agent-browser-ops`
- skill path: `/Users/mac_claw/.openclaw/workspace/skills/guarded-agent-browser-ops/SKILL.md`
- local binary path recorded in the skill:
  `/Users/mac_claw/.openclaw/workspace/tools/agent-browser-local/node_modules/agent-browser/bin/agent-browser-darwin-arm64`

Important policy from the skill:
1. prefer the built-in OpenClaw `browser` tool when it already solves the task cleanly
2. use the local `agent-browser` CLI workflow only when a repeatable local CLI browser workflow is better

Therefore mapping:
- `agent-browser-cli` -> semantic alias for local `agent-browser` CLI/browser automation capability
- current OpenClaw first choice -> `browser`
- secondary local implementation path -> guarded-agent-browser-ops skill using local `agent-browser`

### 2) `raw-http-fetch`
Not found as a first-class OpenClaw tool name in the current environment.

Closest safe local equivalent:
- `web_fetch` for direct page fetch + readable extraction
- if truly raw network behavior is needed, implement a narrow in-house HTTP request path rather than trusting unknown third-party artifacts

Therefore mapping:
- `raw-http-fetch` -> semantic alias for direct HTTP fetch capability
- current OpenClaw first choice -> `web_fetch`

## Final mapping table

| External/legacy name | Current environment mapping | Notes |
|---|---|---|
| `raw-http-fetch` | `web_fetch` | Not a registered first-class tool here |
| `agent-browser-cli` | `browser` (preferred), local `agent-browser` via guarded-agent-browser-ops (secondary) | Not a registered first-class tool here |

## Security boundary verification
- No third-party artifact was executed.
- No auth/cookie/storage/profile browser state was touched.
- Mapping was derived from local skill documentation and local environment inspection only.
