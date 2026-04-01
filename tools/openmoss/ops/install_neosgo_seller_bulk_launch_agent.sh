#!/bin/zsh
set -euo pipefail

SOURCE="/Users/mac_claw/.openclaw/workspace/tools/openmoss/ops/ai.jinclaw.neosgo-seller-bulk.plist"
TARGET="/Users/mac_claw/Library/LaunchAgents/ai.jinclaw.neosgo-seller-bulk.plist"

mkdir -p "$(dirname "$TARGET")"
cp "$SOURCE" "$TARGET"

launchctl bootout "gui/$(id -u)" ai.jinclaw.neosgo-seller-bulk >/dev/null 2>&1 || true
launchctl bootstrap "gui/$(id -u)" "$TARGET"
launchctl kickstart -k "gui/$(id -u)/ai.jinclaw.neosgo-seller-bulk"
