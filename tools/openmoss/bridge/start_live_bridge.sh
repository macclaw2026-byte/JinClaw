#!/bin/zsh

set -euo pipefail

ROOT="/Users/mac_claw/.openclaw/workspace/tools/openmoss/bridge"
VENV="$ROOT/.venv"

if [ ! -x "$VENV/bin/python" ]; then
  echo "missing bridge venv; run $ROOT/bootstrap_bridge_env.sh first" >&2
  exit 1
fi

exec "$VENV/bin/python" "$ROOT/run_live_bridge.py" "$@"
