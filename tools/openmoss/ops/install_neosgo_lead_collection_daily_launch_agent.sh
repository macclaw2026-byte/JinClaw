#!/usr/bin/env bash
set -euo pipefail

PLIST_SRC="/Users/mac_claw/.openclaw/workspace/tools/openmoss/ops/ai.jinclaw.neosgo-lead-collection-daily.plist"
PLIST_DST="$HOME/Library/LaunchAgents/ai.jinclaw.neosgo-lead-collection-daily.plist"

mkdir -p "$HOME/Library/LaunchAgents"
cp "$PLIST_SRC" "$PLIST_DST"

launchctl bootout "gui/$(id -u)" "$PLIST_DST" >/dev/null 2>&1 || true
launchctl bootstrap "gui/$(id -u)" "$PLIST_DST"
launchctl enable "gui/$(id -u)/ai.jinclaw.neosgo-lead-collection-daily"
launchctl kickstart -k "gui/$(id -u)/ai.jinclaw.neosgo-lead-collection-daily" >/dev/null 2>&1 || true

echo "Installed ai.jinclaw.neosgo-lead-collection-daily"
