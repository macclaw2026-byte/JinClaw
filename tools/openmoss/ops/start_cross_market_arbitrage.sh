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

ROOT=/Users/mac_claw/.openclaw/workspace
PYTHON_BIN="$ROOT/tools/matrix-venv/bin/python"
SCRIPT_PATH="$ROOT/skills/cross-market-arbitrage-engine/scripts/run_cross_market_arbitrage_cycle.py"
PRECHECK_LOG="$ROOT/output/cross-market-arbitrage-engine/startup-preflight.log"
DISABLED_SENTINEL="$ROOT/tools/openmoss/runtime/control_center/governance/disabled_services/cross_market_arbitrage.json"

mkdir -p "$(dirname "$PRECHECK_LOG")"

if [[ -f "$DISABLED_SENTINEL" ]]; then
  echo "[$(date -u +%Y-%m-%dT%H:%M:%SZ)] cross-market arbitrage disabled by sentinel: $DISABLED_SENTINEL" | tee -a "$PRECHECK_LOG" >&2
  exit 0
fi

if [[ ! -x "$PYTHON_BIN" ]]; then
  echo "[$(date -u +%Y-%m-%dT%H:%M:%SZ)] missing python interpreter: $PYTHON_BIN" | tee -a "$PRECHECK_LOG" >&2
  exit 1
fi

if [[ ! -f "$SCRIPT_PATH" ]]; then
  echo "[$(date -u +%Y-%m-%dT%H:%M:%SZ)] missing arbitrage script: $SCRIPT_PATH" | tee -a "$PRECHECK_LOG" >&2
  exit 1
fi

if ! "$PYTHON_BIN" - <<'PY' >> "$PRECHECK_LOG" 2>&1
import sys
from pathlib import Path
import importlib.util

root = Path('/Users/mac_claw/.openclaw/workspace')
control_center_root = root / 'tools/openmoss/control_center'
if str(control_center_root) not in sys.path:
    sys.path.insert(0, str(control_center_root))

required = [
    'openpyxl',
    'control_plane_builder',
    'memory_writeback_runtime',
    'paths',
]
missing = [name for name in required if importlib.util.find_spec(name) is None]
if missing:
    print('missing modules:', ', '.join(missing))
    raise SystemExit(1)
print('cross-market-arbitrage preflight ok')
PY
then
  echo "[$(date -u +%Y-%m-%dT%H:%M:%SZ)] preflight failed for cross-market arbitrage" | tee -a "$PRECHECK_LOG" >&2
  exit 1
fi

cd "$ROOT"
exec "$PYTHON_BIN" "$SCRIPT_PATH" --mode daemon
