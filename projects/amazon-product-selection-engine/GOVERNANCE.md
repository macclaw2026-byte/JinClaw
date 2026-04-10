# Amazon Product Selection Governance

This project must operate inside JinClaw's three-layer AI operating framework.

## 1. Constitution Layer

Authoritative file:

- `/Users/mac_claw/.openclaw/workspace/JINCLAW_CONSTITUTION.md`

Non-negotiable implications for this project:

- long-running, multi-step work must stay brain-first and control-center aligned
- source-of-truth changes must go through Git, not only local runtime files
- no secrets, browser profiles, tokens, or local session state may enter Git
- meaningful changes must land on a feature branch and move through PRs instead of going straight to `main`

## 2. Rules Layer

Authoritative files:

- `/Users/mac_claw/.openclaw/workspace/projects/jinclaw-governance/jinclaw-live-guardrails.md`
- `/Users/mac_claw/.openclaw/workspace/tools/openmoss/control_center/doctor_coverage_contract.md`

Project rules derived from them:

- stage definitions, governance notes, and runner scripts must live in tracked project files
- local runtime state and exported business data stay outside Git
- stage 1 must produce the official SellerSprite account export, not a debug-only normalized CSV substitute
- any new execution path must either extend canonical doctor coverage or declare a temporary blind spot explicitly

## 3. Process Layer

Authoritative files:

- `/Users/mac_claw/.openclaw/workspace/compat/gstack/prompts/jinclaw-gstack-lite.md`
- `/Users/mac_claw/.openclaw/workspace/tools/openmoss/control_center/orchestrator.py`
- `/Users/mac_claw/.openclaw/workspace/tools/openmoss/autonomy/task_contract.py`
- `/Users/mac_claw/.openclaw/workspace/tools/openmoss/autonomy/preflight_engine.py`

Project process commitments:

- keep a versioned stage manifest in `config/stage-manifest.json`
- keep project shape and stage contracts in `config/project-config.json`
- keep the stage 1 runner and validator as executable scripts under `scripts/`
- validate touched behavior before PR creation

## Doctor Coverage Declaration

Component:
`amazon-product-selection-engine`

Direct coverage path:
Not yet wired directly into the canonical doctor snapshot.

Exported signal/artifact:
Versioned execution plan plus local validation output from `validate_stage1_export.py`.

Primary monitor:
`projects/amazon-product-selection-engine/scripts/validate_stage1_export.py`

Backstop monitor:
PR review plus explicit local validation commands recorded in the PR body.

Delayed verification:
Confirmed presence of a locally validated official SellerSprite `xlsx` artifact.

Blind spot:
The canonical JinClaw doctor does not yet ingest this project's local stage runtime automatically.

Retrofit owner:
`amazon-product-selection-engine`

## Git Boundary

Versioned source-of-truth:

- `README.md`
- `GOVERNANCE.md`
- `config/project-config.json`
- `config/stage-manifest.json`
- `scripts/*.py`
- `tests/*`
- `tasks/amazon-product-selection-execution-plan.md`

Local-only runtime state:

- `data/`
- `runtime/`
- `reports/`
- `output/`
- `tasks/amazon-product-selection-state.md`
