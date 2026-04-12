#!/usr/bin/env python3
# RULES-FIRST NOTICE:
# Before modifying this file, first read:
# - `JINCLAW_CONSTITUTION.md`
# - `AI_OPTIMIZATION_FRAMEWORK.md`
# Follow the constitution and framework:
# brain-first, one-doctor, fail-closed, evidence-over-narration,
# validate locally, then use the required PR workflow.
import argparse
import json
import os
import subprocess
from datetime import datetime
from pathlib import Path

OPENCLAW_BIN = "/opt/homebrew/bin/openclaw"
DEFAULT_PATH = "/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin"
DEFAULT_CHAT = "8528973600"
LATEST_REPORT = Path("/Users/mac_claw/.openclaw/workspace/output/cross-market-arbitrage-engine/latest-report.json")
STATE_PATH = Path("/Users/mac_claw/.openclaw/workspace/output/cross-market-arbitrage-engine/daily-report-state.json")


def _subprocess_env() -> dict[str, str]:
    env = os.environ.copy()
    env["PATH"] = f"{DEFAULT_PATH}:{env.get('PATH', '')}".strip(":")
    return env


def _send(chat_id: str, text: str, attachments: list[Path]) -> list[dict]:
    deliveries = []
    text_proc = subprocess.run(
        [OPENCLAW_BIN, "message", "send", "--channel", "telegram", "--target", chat_id, "--message", text, "--json"],
        capture_output=True,
        text=True,
        timeout=120,
        env=_subprocess_env(),
    )
    deliveries.append({"kind": "text", "returncode": text_proc.returncode, "stdout": text_proc.stdout, "stderr": text_proc.stderr})
    for path in attachments:
        proc = subprocess.run(
            [OPENCLAW_BIN, "message", "send", "--channel", "telegram", "--target", chat_id, "--media", str(path), "--force-document", "--json"],
            capture_output=True,
            text=True,
            timeout=180,
            env=_subprocess_env(),
        )
        deliveries.append({"kind": "media", "path": str(path), "returncode": proc.returncode, "stdout": proc.stdout, "stderr": proc.stderr})
    return deliveries


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--chat-id", default=DEFAULT_CHAT)
    ap.add_argument("--latest-report", default=str(LATEST_REPORT))
    ap.add_argument("--state-path", default=str(STATE_PATH))
    ap.add_argument("--force", action="store_true")
    args = ap.parse_args()

    latest_path = Path(args.latest_report)
    if not latest_path.exists():
        print(json.dumps({"ok": False, "reason": "latest_report_missing", "path": str(latest_path)}, ensure_ascii=False))
        return 1

    payload = json.loads(latest_path.read_text(encoding="utf-8"))
    state_path = Path(args.state_path)
    state = {}
    if state_path.exists():
        try:
            state = json.loads(state_path.read_text(encoding="utf-8"))
        except Exception:
            state = {}

    run_id = str(payload.get("run_id") or "").strip()
    generated_at = str(payload.get("generated_at") or "").strip()
    generated_date = generated_at[:10] if generated_at else ""
    last_run_id = str(state.get("last_run_id") or "").strip()
    last_sent_date = str(state.get("last_sent_date") or "").strip()
    today = datetime.now().date().isoformat()
    if not args.force and ((run_id and run_id == last_run_id) or (generated_date and generated_date == last_sent_date) or last_sent_date == today):
        print(json.dumps({"ok": True, "skipped": True, "reason": "already_sent_today", "run_id": run_id, "last_sent_date": last_sent_date}, ensure_ascii=False))
        return 0

    governance = payload.get("governance") or {}
    failures = governance.get("failure_categories") or {}
    summary = (
        "Cross-market daily report\n"
        f"Run: {run_id}\n"
        f"Qualified: {payload.get('qualified_count', 0)}\n"
        f"Primary blocker: {governance.get('primary_blocker', '')}\n"
        f"Top failures: {json.dumps(failures, ensure_ascii=False)}"
    )
    attachments = []
    for key in ("markdown_path", "json_path", "excel_path"):
        raw = str(payload.get(key) or "").strip()
        if raw:
            path = Path(raw)
            if path.exists():
                attachments.append(path)
    deliveries = _send(args.chat_id, summary, attachments)
    state_path.parent.mkdir(parents=True, exist_ok=True)
    state_path.write_text(
        json.dumps(
            {
                "last_run_id": run_id,
                "last_generated_at": generated_at,
                "last_sent_at": datetime.now().isoformat(),
                "last_sent_date": today,
                "deliveries": deliveries,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    print(json.dumps({"ok": True, "run_id": run_id, "deliveries": deliveries}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
