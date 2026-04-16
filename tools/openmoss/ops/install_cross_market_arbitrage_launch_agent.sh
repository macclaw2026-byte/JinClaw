#!/bin/zsh
# RULES-FIRST NOTICE:
# Before modifying this file, first read:
# - `JINCLAW_CONSTITUTION.md`
# - `AI_OPTIMIZATION_FRAMEWORK.md`
# Follow the constitution and framework:
# brain-first, one-doctor, fail-closed, evidence-over-narration,
# validate locally, then use the required PR workflow.
# 中文说明：
# - 文件路径：`tools/openmoss/ops/install_cross_market_arbitrage_launch_agent.sh`
# - 文件作用：安装并重启 cross-market-arbitrage-engine 的 LaunchAgent。
# - 包含 shell 函数：无显式 shell 函数。
#
set -euo pipefail

SOURCE="/Users/mac_claw/.openclaw/workspace/tools/openmoss/ops/ai.jinclaw.cross-market-arbitrage.plist"
TARGET="/Users/mac_claw/Library/LaunchAgents/ai.jinclaw.cross-market-arbitrage.plist"
LABEL="ai.jinclaw.cross-market-arbitrage"
UID="$(id -u)"
DISABLED_SENTINEL="/Users/mac_claw/.openclaw/workspace/tools/openmoss/runtime/control_center/governance/disabled_services/cross_market_arbitrage.json"

if [[ -f "$DISABLED_SENTINEL" ]]; then
  echo "cross-market arbitrage is disabled by sentinel: $DISABLED_SENTINEL" >&2
  echo "refusing to install or start ${LABEL}; remove the sentinel intentionally before re-enabling" >&2
  exit 1
fi

cp "$SOURCE" "$TARGET"
launchctl bootout "gui/${UID}" "$TARGET" >/dev/null 2>&1 || true
launchctl bootstrap "gui/${UID}" "$TARGET"
launchctl kickstart -k "gui/${UID}/${LABEL}"
