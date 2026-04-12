#!/bin/zsh
# RULES-FIRST NOTICE:
# Before modifying this file, first read:
# - `JINCLAW_CONSTITUTION.md`
# - `AI_OPTIMIZATION_FRAMEWORK.md`
# Follow the constitution and framework:
# brain-first, one-doctor, fail-closed, evidence-over-narration,
# validate locally, then use the required PR workflow.
set -euo pipefail

SOURCE="/Users/mac_claw/.openclaw/workspace/tools/openmoss/ops/ai.jinclaw.neosgo-seller-bulk.plist"
TARGET="/Users/mac_claw/Library/LaunchAgents/ai.jinclaw.neosgo-seller-bulk.plist"

mkdir -p "$(dirname "$TARGET")"
cp "$SOURCE" "$TARGET"

launchctl bootout "gui/$(id -u)" ai.jinclaw.neosgo-seller-bulk >/dev/null 2>&1 || true
launchctl bootstrap "gui/$(id -u)" "$TARGET"
launchctl kickstart -k "gui/$(id -u)/ai.jinclaw.neosgo-seller-bulk"
