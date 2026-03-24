#!/bin/zsh

set -euo pipefail

ROOT="/Users/mac_claw/.openclaw/workspace/tools/openmoss/autonomy"
export PATH="/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin:${PATH:-}"

exec python3 "$ROOT/runtime_service.py" "$@"
