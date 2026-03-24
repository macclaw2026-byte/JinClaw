#!/bin/zsh

set -euo pipefail

ROOT="/Users/mac_claw/.openclaw/workspace/tools/openmoss/autonomy"

exec python3 "$ROOT/runtime_service.py" "$@"
