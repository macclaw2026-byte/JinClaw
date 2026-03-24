#!/bin/zsh
set -euo pipefail

cd /Users/mac_claw
exec /usr/bin/python3 /Users/mac_claw/.openclaw/workspace/tools/openmoss/upstream_watch/watch_updates.py --once
