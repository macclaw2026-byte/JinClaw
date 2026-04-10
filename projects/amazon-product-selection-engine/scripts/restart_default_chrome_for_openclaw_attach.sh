#!/bin/zsh
set -euo pipefail

CHROME_APP="/Applications/Google Chrome.app"
CHROME_BIN="$CHROME_APP/Contents/MacOS/Google Chrome"
CHROME_ROOT="/Users/mac_claw/Library/Application Support/Google/Chrome"
DEBUG_PORT="${1:-9222}"
TARGET_URL="${2:-https://www.sellersprite.com/v3/product-research}"

if [[ ! -x "$CHROME_BIN" ]]; then
  echo "chrome binary not found: $CHROME_BIN" >&2
  exit 1
fi

osascript <<'APPLESCRIPT'
tell application "Google Chrome"
  if it is running then
    quit
  end if
end tell
APPLESCRIPT

for _ in {1..40}; do
  if ! pgrep -x "Google Chrome" >/dev/null 2>&1; then
    break
  fi
  sleep 0.5
done

rm -f "$CHROME_ROOT/DevToolsActivePort"

"$CHROME_BIN" \
  --remote-debugging-port="$DEBUG_PORT" \
  --user-data-dir="$CHROME_ROOT" \
  --profile-directory="Default" \
  --restore-last-session \
  "$TARGET_URL" \
  >/tmp/openclaw-chrome-attach.log 2>&1 &

for _ in {1..60}; do
  if [[ -f "$CHROME_ROOT/DevToolsActivePort" ]]; then
    break
  fi
  sleep 0.5
done

if [[ ! -f "$CHROME_ROOT/DevToolsActivePort" ]]; then
  echo "DevToolsActivePort not created under $CHROME_ROOT" >&2
  exit 1
fi

echo "Chrome restarted with remote debugging."
echo "DevToolsActivePort:"
cat "$CHROME_ROOT/DevToolsActivePort"
