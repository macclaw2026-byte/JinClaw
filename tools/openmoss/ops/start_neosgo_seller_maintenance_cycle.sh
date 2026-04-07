#!/bin/zsh
set -euo pipefail

export PATH="/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin"

cd /Users/mac_claw/.openclaw/workspace
exec /usr/bin/env python3 /Users/mac_claw/.openclaw/workspace/tools/openmoss/ops/run_neosgo_seller_maintenance_cycle.py
