#!/bin/zsh
# RULES-FIRST NOTICE:
# Before modifying this file, first read:
# - `JINCLAW_CONSTITUTION.md`
# - `AI_OPTIMIZATION_FRAMEWORK.md`
# Follow the constitution and framework:
# brain-first, one-doctor, fail-closed, evidence-over-narration,
# validate locally, then use the required PR workflow.
set -euo pipefail

source /Users/mac_claw/.openclaw/workspace/tools/openmoss/ops/openmoss_launch_env.sh
export NEOSGO_SELLER_REPORT_CHAT="${NEOSGO_SELLER_REPORT_CHAT:-8528973600}"

cd /Users/mac_claw/.openclaw/workspace
exec /usr/bin/env python3 /Users/mac_claw/.openclaw/workspace/tools/openmoss/ops/run_neosgo_seller_bulk_cycle.py
