#!/bin/bash
set -euo pipefail
BIN="/Users/mac_claw/.openclaw/workspace/tools/agent-browser-local/node_modules/agent-browser/bin/agent-browser-darwin-arm64"
exec "$BIN" "$@"
