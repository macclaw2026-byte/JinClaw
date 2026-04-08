#!/usr/bin/env bash
set -euo pipefail

SRC="/Users/mac_claw/.openclaw/workspace/tools/openmoss/ops/ai.jinclaw.neosgo-outreach-cycle-hourly.plist"
DST="$HOME/Library/LaunchAgents/ai.jinclaw.neosgo-outreach-cycle-hourly.plist"

mkdir -p "$HOME/Library/LaunchAgents"
cp "$SRC" "$DST"
launchctl unload "$DST" >/dev/null 2>&1 || true
launchctl load "$DST"
echo "$DST"
