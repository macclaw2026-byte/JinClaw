#!/bin/zsh

set -euo pipefail

ROOT="/Users/mac_claw/.openclaw/workspace/tools/openmoss/voice"
VENV="$ROOT/.venv"

if [ ! -x "$VENV/bin/python" ]; then
  echo "missing voice venv; run $ROOT/bootstrap_voice_env.sh first" >&2
  exit 1
fi

exec "$VENV/bin/python" "$ROOT/generate_voice.py" doctor
