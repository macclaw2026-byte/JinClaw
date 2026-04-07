#!/bin/zsh
set -euo pipefail
ROOT="/Users/mac_claw/.openclaw/workspace"
LOG_DIR="$ROOT/.logs"
mkdir -p "$LOG_DIR"
LOG_FILE="$LOG_DIR/amazon-premium-wholesale-maintenance.log"
PID_FILE="$ROOT/.state/amazon-premium-wholesale-maintenance.pid"
LOCK_DIR="$ROOT/.state/amazon-premium-wholesale-maintenance.lock"
BACKUP_DIR="$ROOT/.state/amazon-premium-wholesale-backups"
mkdir -p "$BACKUP_DIR"
RAW_FILE="$ROOT/data/amazon-premium-wholesale/raw_candidates.json"
OUT_FILE="$ROOT/output/amazon-premium-wholesale/latest.json"
STATE_FILE="$ROOT/.state/amazon-premium-wholesale.json"
RAW_BACKUP="$BACKUP_DIR/raw_candidates.last_good.json"
OUT_BACKUP="$BACKUP_DIR/latest.last_good.json"
STATE_BACKUP="$BACKUP_DIR/state.last_good.json"
STOP_AT_HHMM="${STOP_AT_HHMM:-}"
SLEEP_SECONDS="${SLEEP_SECONDS:-1200}"
export TZ="America/Los_Angeles"
cd "$ROOT"
acquire_lock() {
  if mkdir "$LOCK_DIR" 2>/dev/null; then
    echo $$ > "$PID_FILE"
    return 0
  fi

  if [[ -f "$PID_FILE" ]]; then
    local existing_pid
    existing_pid="$(cat "$PID_FILE" 2>/dev/null || true)"
    if [[ -n "$existing_pid" ]] && kill -0 "$existing_pid" 2>/dev/null; then
      echo "[$(date -Iseconds)] existing-wrapper-alive pid=$existing_pid, exiting-duplicate pid=$$" >> "$LOG_FILE"
      exit 0
    fi
  fi

  rm -rf "$LOCK_DIR"
  mkdir "$LOCK_DIR"
  echo $$ > "$PID_FILE"
}
cleanup() {
  local current_pid=""
  if [[ -f "$PID_FILE" ]]; then
    current_pid="$(cat "$PID_FILE" 2>/dev/null || true)"
  fi
  if [[ "$current_pid" == "$$" ]]; then
    rm -f "$PID_FILE"
    rm -rf "$LOCK_DIR"
  fi
}
trap cleanup EXIT INT TERM
acquire_lock

snapshot_last_good() {
  cp "$RAW_FILE" "$RAW_BACKUP"
  cp "$OUT_FILE" "$OUT_BACKUP"
  cp "$STATE_FILE" "$STATE_BACKUP"
}

restore_last_good() {
  [[ -f "$RAW_BACKUP" ]] && cp "$RAW_BACKUP" "$RAW_FILE"
  [[ -f "$OUT_BACKUP" ]] && cp "$OUT_BACKUP" "$OUT_FILE"
  [[ -f "$STATE_BACKUP" ]] && cp "$STATE_BACKUP" "$STATE_FILE"
}

run_attempt() {
  python3 skills/product-selection-engine/scripts/extract_amazon_public_candidates.py
  python3 skills/product-selection-engine/scripts/amazon_premium_wholesale_pipeline_v1.py
}

inspect_cycle() {
  local prev_raw_mtime="$1"
  local prev_out_mtime="$2"
  local prev_state_mtime="$3"
  PREV_RAW_MTIME="$prev_raw_mtime" PREV_OUT_MTIME="$prev_out_mtime" PREV_STATE_MTIME="$prev_state_mtime" python3 - <<'PY'
import json, os, pathlib, sys
root = pathlib.Path('/Users/mac_claw/.openclaw/workspace')
raw_path = root/'data/amazon-premium-wholesale/raw_candidates.json'
out_path = root/'output/amazon-premium-wholesale/latest.json'
state_path = root/'.state/amazon-premium-wholesale.json'
raw = json.loads(raw_path.read_text())
out = json.loads(out_path.read_text())
summary = {
  'summary': 'cycle-complete',
  'raw_candidate_count': raw.get('candidate_count'),
  'quality_gate': raw.get('quality_gate', {}),
  'qualified_candidate_count': out.get('candidate_count'),
  'pre_dedupe_count': out.get('pre_dedupe_count'),
  'post_family_dedupe_count': out.get('post_family_dedupe_count'),
  'input_mode': out.get('input_mode'),
  'run_at': out.get('run_at'),
  'artifact_freshness': {
    'raw_mtime': raw_path.stat().st_mtime,
    'out_mtime': out_path.stat().st_mtime,
    'state_mtime': state_path.stat().st_mtime,
  },
}
print(json.dumps(summary, ensure_ascii=False))
prev_raw = float(os.environ.get('PREV_RAW_MTIME', '0') or 0)
prev_out = float(os.environ.get('PREV_OUT_MTIME', '0') or 0)
prev_state = float(os.environ.get('PREV_STATE_MTIME', '0') or 0)
raw_advanced = raw_path.stat().st_mtime > prev_raw
out_advanced = out_path.stat().st_mtime > prev_out
state_advanced = state_path.stat().st_mtime > prev_state
passed = bool(raw.get('quality_gate', {}).get('passed')) and out.get('input_mode') == 'raw_input' and raw_advanced and out_advanced and state_advanced
sys.exit(0 if passed else 1)
PY
}

run_cycle() {
  local stamp attempt ok prev_raw_mtime prev_out_mtime prev_state_mtime
  stamp="$(date -Iseconds)"
  ok=0
  prev_raw_mtime=$(python3 - <<PY
import pathlib
p = pathlib.Path(r'''$RAW_FILE''')
print(p.stat().st_mtime if p.exists() else 0)
PY
)
  prev_out_mtime=$(python3 - <<PY
import pathlib
p = pathlib.Path(r'''$OUT_FILE''')
print(p.stat().st_mtime if p.exists() else 0)
PY
)
  prev_state_mtime=$(python3 - <<PY
import pathlib
p = pathlib.Path(r'''$STATE_FILE''')
print(p.stat().st_mtime if p.exists() else 0)
PY
)
  {
    echo "[$stamp] cycle-start"
    for attempt in 1 2; do
      echo "[$(date -Iseconds)] attempt-$attempt-start"
      if run_attempt && inspect_cycle "$prev_raw_mtime" "$prev_out_mtime" "$prev_state_mtime"; then
        snapshot_last_good
        echo "[$(date -Iseconds)] attempt-$attempt-passed"
        ok=1
        break
      fi
      echo "[$(date -Iseconds)] attempt-$attempt-failed"
      if [[ "$attempt" -lt 2 ]]; then
        sleep 90
      fi
    done
    if [[ "$ok" -ne 1 ]]; then
      echo "[$(date -Iseconds)] restoring-last-good-snapshot"
      restore_last_good
      python3 - <<'PY'
import json, pathlib
root = pathlib.Path('/Users/mac_claw/.openclaw/workspace')
out = root/'output/amazon-premium-wholesale/latest.json'
raw = root/'data/amazon-premium-wholesale/raw_candidates.json'
summary = {'summary': 'restored-last-good-snapshot'}
if raw.exists():
    payload = json.loads(raw.read_text())
    summary['raw_candidate_count'] = payload.get('candidate_count')
    summary['quality_gate'] = payload.get('quality_gate', {})
if out.exists():
    payload = json.loads(out.read_text())
    summary['qualified_candidate_count'] = payload.get('candidate_count')
    summary['post_family_dedupe_count'] = payload.get('post_family_dedupe_count')
    summary['input_mode'] = payload.get('input_mode')
    summary['run_at'] = payload.get('run_at')
print(json.dumps(summary, ensure_ascii=False))
PY
    fi
    echo "[$(date -Iseconds)] cycle-end"
  } >> "$LOG_FILE" 2>&1
}

if [[ -f "$RAW_FILE" && -f "$OUT_FILE" && -f "$STATE_FILE" ]]; then
  python3 - <<'PY' >/dev/null 2>&1
import json, pathlib, sys
root = pathlib.Path('/Users/mac_claw/.openclaw/workspace')
raw = json.loads((root/'data/amazon-premium-wholesale/raw_candidates.json').read_text())
out = json.loads((root/'output/amazon-premium-wholesale/latest.json').read_text())
sys.exit(0 if raw.get('quality_gate', {}).get('passed') and out.get('input_mode') == 'raw_input' else 1)
PY
  if [[ $? -eq 0 ]]; then
    snapshot_last_good
  fi
fi

while true; do
  if [[ -n "$STOP_AT_HHMM" ]]; then
    hour_min="$(date +%H%M)"
    if [[ "$hour_min" -ge "$STOP_AT_HHMM" ]]; then
      echo "[$(date -Iseconds)] stop-window-reached" >> "$LOG_FILE"
      break
    fi
  fi
  run_cycle || {
    echo "[$(date -Iseconds)] cycle-failed" >> "$LOG_FILE"
    exit 1
  }
  sleep "$SLEEP_SECONDS"
done
