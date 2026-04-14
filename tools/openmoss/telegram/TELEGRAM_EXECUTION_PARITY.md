# RULES-FIRST NOTICE:
# Before modifying this file, first read:
# - `JINCLAW_CONSTITUTION.md`
# - `AI_OPTIMIZATION_FRAMEWORK.md`
# Follow the constitution and framework:
# brain-first, one-doctor, fail-closed, evidence-over-narration,
# validate locally, then use the required PR workflow.

# Telegram Execution Parity

## Problem statement

The same Ziniao / seller-console workflow could succeed in terminal-style collaboration but stall in the Telegram chat window.

## Root causes

### 1. Wrong plan selection

`workflow_planner.py` used to route any `marketplace` task into `local_image_pipeline`, even when the task was a seller-console navigation/export flow with no image work at all.

That meant a task like:

- open Ziniao
- log into Temu seller backend
- go to `对账中心`
- export `账务明细`

could start from the wrong mental model before execution even began.

### 2. Skill name discovered, but skill method not reliably delivered to runtime

The control center could discover local skills, but non-coding runtime prompts did not consistently carry the concrete local skill workflow into the final execution request.

In practice, the system might “know” `ziniao-assistant` exists while the actual runtime agent still improvised with generic browser tactics.

### 3. Seller-console tasks are fragile business workflows

These tasks are more brittle than ordinary browsing because they depend on:

- authenticated local browser state
- the correct tab and region
- component-driven controls
- business-result validation such as export history

Without a validated playbook, the runtime tends to stop too early or drift onto the wrong tab/page.

## Implemented fixes

### Planning fix

- Added an explicit `ziniao_bridge_ops` plan for Ziniao / Temu / seller-console work.
- Removed the bad default that pushed all `marketplace` tasks into `local_image_pipeline`.

### Runtime fix

- Added structured `skill_guidance` to orchestrator metadata and mission state.
- Threaded `skill_guidance` through stage context, ACP payload, and the native runtime dispatch prompt.
- For non-coding Telegram/browser tasks, the runtime prompt now explicitly carries:
  - matched skill names
  - bridge contract
  - validated seller-console rules
  - export verification expectations

### Skill fix

- Expanded `skills/ziniao-assistant` with reusable seller-console references.
- Added a validated Temu finance-export workflow so the system can reuse a proven path instead of guessing.

## What this means for Telegram users

After these fixes, the Telegram path is much closer to the terminal path because both now share:

- the same task planner
- the same selected-plan contract
- the same local skill guidance
- the same runtime dispatch rules

## Remaining practical guidance

To get the strongest results from Telegram, phrase the request with:

1. the target browser/store
2. the target page or business path
3. the exact result to verify

Example:

`用 ziniao 浏览器打开已绑定的 Temu 店铺，切到美国站，进入 对账中心 -> 财务明细，筛选 2026 年 3 月并导出，然后到导出历史确认新任务可下载。`

That gives the planner the exact business endpoint and completion proof, which further reduces drift.
