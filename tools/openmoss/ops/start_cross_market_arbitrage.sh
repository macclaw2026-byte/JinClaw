#!/bin/zsh
# 中文说明：
# - 文件路径：`tools/openmoss/ops/start_cross_market_arbitrage.sh`
# - 文件作用：启动 cross-market-arbitrage-engine 常驻服务。
# - 包含 shell 函数：无显式 shell 函数。
#
set -euo pipefail

export PATH="/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin"
unset CROSS_MARKET_TELEGRAM_CHAT

cd /Users/mac_claw/.openclaw/workspace
exec /usr/bin/env python3 /Users/mac_claw/.openclaw/workspace/skills/cross-market-arbitrage-engine/scripts/run_cross_market_arbitrage_cycle.py --mode daemon
