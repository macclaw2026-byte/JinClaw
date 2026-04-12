#!/usr/bin/env bash
# RULES-FIRST NOTICE:
# Before modifying this file, first read:
# - `JINCLAW_CONSTITUTION.md`
# - `AI_OPTIMIZATION_FRAMEWORK.md`
# Follow the constitution and framework:
# brain-first, one-doctor, fail-closed, evidence-over-narration,
# validate locally, then use the required PR workflow.
set -euo pipefail

SRC="/Users/mac_claw/.openclaw/workspace/tools/openmoss/ops/ai.jinclaw.neosgo-admin-ops-daily-report.plist"
DST="$HOME/Library/LaunchAgents/ai.jinclaw.neosgo-admin-ops-daily-report.plist"

mkdir -p "$HOME/Library/LaunchAgents"
mkdir -p "/Users/mac_claw/.openclaw/workspace/output/neosgo-admin-ops"
cp "$SRC" "$DST"
launchctl unload "$DST" >/dev/null 2>&1 || true
launchctl load "$DST"
echo "$DST"
