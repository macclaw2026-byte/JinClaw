#!/usr/bin/env python3

from __future__ import annotations

import argparse
import json
import os
import subprocess
from datetime import datetime
from pathlib import Path


PROJECT_ROOT = Path("/Users/mac_claw/.openclaw/workspace/projects/neosgo-marketing-suite")
OPENCLAW_BIN = "/opt/homebrew/bin/openclaw"
DEFAULT_CHAT = "8528973600"
DEFAULT_PATH = "/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin"
LATEST_SUMMARY_PATH = PROJECT_ROOT / "runtime" / "outreach" / "latest-summary.json"
STATE_PATH = PROJECT_ROOT / "runtime" / "outreach" / "telegram-summary-state.json"


def _subprocess_env() -> dict[str, str]:
    env = os.environ.copy()
    env["PATH"] = f"{DEFAULT_PATH}:{env.get('PATH', '')}".strip(":")
    return env


def _read_json(path: Path, default: dict) -> dict:
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default


def _send(chat_id: str, text: str) -> dict:
    proc = subprocess.run(
        [OPENCLAW_BIN, "message", "send", "--channel", "telegram", "--target", chat_id, "--message", text, "--json"],
        capture_output=True,
        text=True,
        timeout=120,
        env=_subprocess_env(),
        check=False,
    )
    return {"returncode": proc.returncode, "stdout": proc.stdout.strip(), "stderr": proc.stderr.strip()}


def main() -> int:
    parser = argparse.ArgumentParser(description="Send periodic NEOSGO outreach summary to Telegram.")
    parser.add_argument("--chat-id", default=os.environ.get("NEOSGO_OUTREACH_CHAT", DEFAULT_CHAT))
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()

    latest = _read_json(LATEST_SUMMARY_PATH, {})
    if not latest:
        print(json.dumps({"ok": False, "reason": "missing_latest_summary"}, ensure_ascii=False))
        return 1

    state = _read_json(STATE_PATH, {})
    generated_at = str(latest.get("generated_at") or "")
    if not args.force and generated_at and generated_at == str(state.get("last_generated_at") or ""):
        print(json.dumps({"ok": True, "skipped": True, "reason": "already_sent_for_latest_summary"}, ensure_ascii=False))
        return 0

    counts = dict(latest.get("counts") or {})
    text = (
        "NEOSGO outreach status update\n"
        f"Generated: {generated_at}\n"
        f"Touched: {latest.get('total_touched', 0)}\n"
        f"Counts: {json.dumps(counts, ensure_ascii=False)}"
    )
    attempts = list(latest.get("attempts") or [])
    if attempts:
        last = attempts[-1]
        text += f"\nLast action: {last.get('type')} | {last.get('company_name')}"
    failure = latest.get("failure") or {}
    if failure:
        text += f"\nFailure: {failure.get('company_name')} | {((failure.get('result') or {}).get('reason') or 'unknown')}"

    delivery = _send(args.chat_id, text)
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    STATE_PATH.write_text(
        json.dumps(
            {
                "last_generated_at": generated_at,
                "last_sent_at": datetime.now().isoformat(),
                "delivery": delivery,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    print(json.dumps({"ok": True, "delivery": delivery}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
