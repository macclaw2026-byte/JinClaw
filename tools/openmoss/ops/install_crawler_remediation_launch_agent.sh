#!/bin/zsh
set -euo pipefail

SOURCE="/Users/mac_claw/.openclaw/workspace/tools/openmoss/ops/ai.jinclaw.crawler-remediation.plist"
TARGET="/Users/mac_claw/Library/LaunchAgents/ai.jinclaw.crawler-remediation.plist"
LABEL="ai.jinclaw.crawler-remediation"
UID="$(id -u)"

cp "$SOURCE" "$TARGET"
launchctl bootout "gui/${UID}" "$TARGET" >/dev/null 2>&1 || true
launchctl bootstrap "gui/${UID}" "$TARGET"
launchctl kickstart -k "gui/${UID}/${LABEL}"
