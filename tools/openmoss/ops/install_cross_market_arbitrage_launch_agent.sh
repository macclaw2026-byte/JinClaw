#!/bin/zsh
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

cp "$SOURCE" "$TARGET"
launchctl bootout "gui/${UID}" "$TARGET" >/dev/null 2>&1 || true
launchctl bootstrap "gui/${UID}" "$TARGET"
launchctl kickstart -k "gui/${UID}/${LABEL}"
