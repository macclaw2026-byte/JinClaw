#!/bin/zsh
set -euo pipefail

SOURCE="/Users/mac_claw/.openclaw/workspace/tools/openmoss/ops/ai.openclaw.brain-enforcer.plist"
TARGET="/Users/mac_claw/Library/LaunchAgents/ai.openclaw.brain-enforcer.plist"
LABEL="ai.openclaw.brain-enforcer"
UID="$(id -u)"

cp "$SOURCE" "$TARGET"
launchctl bootout "gui/${UID}" "$TARGET" >/dev/null 2>&1 || true
launchctl bootstrap "gui/${UID}" "$TARGET"
launchctl kickstart -k "gui/${UID}/${LABEL}"
