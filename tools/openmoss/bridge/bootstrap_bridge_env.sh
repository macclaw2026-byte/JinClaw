#!/bin/zsh

set -euo pipefail

ROOT="/Users/mac_claw/.openclaw/workspace/tools/openmoss/bridge"
VENV="$ROOT/.venv"
PYTHON_BIN="${PYTHON_BIN:-/opt/homebrew/bin/python3.11}"

if [ ! -x "$PYTHON_BIN" ]; then
  echo "python not found: $PYTHON_BIN" >&2
  exit 1
fi

"$PYTHON_BIN" -m venv "$VENV"
"$VENV/bin/python" -m pip install --upgrade pip
"$VENV/bin/pip" install -r "$ROOT/requirements.txt"

echo "bridge venv ready: $VENV"
