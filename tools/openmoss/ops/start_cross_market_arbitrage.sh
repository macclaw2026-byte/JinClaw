#!/bin/zsh
# RULES-FIRST NOTICE:
# Before modifying this file, first read:
# - `JINCLAW_CONSTITUTION.md`
# - `AI_OPTIMIZATION_FRAMEWORK.md`
# Follow the constitution and framework:
# brain-first, one-doctor, fail-closed, evidence-over-narration,
# validate locally, then use the required PR workflow.
# 中文说明：
# - 文件路径：`tools/openmoss/ops/start_cross_market_arbitrage.sh`
# - 文件作用：启动 cross-market-arbitrage-engine 常驻服务。
# - 包含 shell 函数：无显式 shell 函数。
#
set -euo pipefail

source /Users/mac_claw/.openclaw/workspace/tools/openmoss/ops/openmoss_launch_env.sh
unset CROSS_MARKET_TELEGRAM_CHAT

cd /Users/mac_claw/.openclaw/workspace
exec /Users/mac_claw/.openclaw/workspace/tools/matrix-venv/bin/python /Users/mac_claw/.openclaw/workspace/skills/cross-market-arbitrage-engine/scripts/run_cross_market_arbitrage_cycle.py --mode daemon
