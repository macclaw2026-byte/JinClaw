#!/usr/bin/env python3

from __future__ import annotations

import argparse
import json
import os
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo


WORKSPACE_ROOT = Path("/Users/mac_claw/.openclaw/workspace")
RUNNER_PATH = WORKSPACE_ROOT / "tools/bin/neosgo-seller-bulk-runner.py"
STATE_PATH = WORKSPACE_ROOT / "data/neosgo-seller-bulk-state.json"
OUTPUT_ROOT = WORKSPACE_ROOT / "output/neosgo-seller-bulk"
STAMP_PATH = OUTPUT_ROOT / "last_scheduled_run_ny.txt"
OPENCLAW_BIN = "/opt/homebrew/bin/openclaw"
DEFAULT_CHAT = "8528973600"
NY_TZ = ZoneInfo("America/New_York")


def parse_args():
    parser = argparse.ArgumentParser(description="Run Neosgo seller bulk submission and emit a report.")
    parser.add_argument("--force", action="store_true", help="Run regardless of schedule gate.")
    parser.add_argument("--limit", type=int, default=9999, help="Maximum number of importable candidates to process.")
    parser.add_argument("--page-size", type=int, default=50, help="Candidates page size.")
    parser.add_argument("--max-pages", type=int, default=10, help="Maximum candidate pages to scan.")
    parser.add_argument("--chat-id", default=os.environ.get("NEOSGO_SELLER_REPORT_CHAT", DEFAULT_CHAT), help="Telegram direct chat target.")
    return parser.parse_args()


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _ny_now() -> datetime:
    return _utc_now().astimezone(NY_TZ)


def should_run_now(force: bool) -> tuple[bool, str]:
    if force:
        return True, "forced"
    now_ny = _ny_now()
    if now_ny.hour != 23:
        return False, f"outside_window:{now_ny.strftime('%Y-%m-%d %H:%M:%S %Z')}"
    today = now_ny.strftime("%Y-%m-%d")
    if STAMP_PATH.exists() and STAMP_PATH.read_text(encoding="utf-8").strip() == today:
        return False, f"already_ran:{today}"
    return True, f"scheduled:{today}"


def run_runner(limit: int, page_size: int, max_pages: int) -> subprocess.CompletedProcess[str]:
    cmd = [
        "python3",
        str(RUNNER_PATH),
        "--limit",
        str(limit),
        "--page-size",
        str(page_size),
        "--max-pages",
        str(max_pages),
    ]
    return subprocess.run(cmd, capture_output=True, text=True, check=False)


def load_state() -> dict:
    if not STATE_PATH.exists():
        return {}
    return json.loads(STATE_PATH.read_text(encoding="utf-8"))


def _row_name(row: dict) -> str:
    return (
        row.get("patch", {})
        .get("resp", {})
        .get("data", {})
        .get("listing", {})
        .get("title")
        or row.get("patch", {})
        .get("resp", {})
        .get("data", {})
        .get("listing", {})
        .get("name")
        or row.get("sku")
        or ""
    )


def summarize(state: dict) -> dict:
    processed = state.get("processed", [])
    rows = []
    for row in processed:
        readiness = row.get("readiness", {}).get("resp", {}).get("data", {}).get("submissionReadiness", {})
        submit_resp = row.get("submit", {}).get("resp", {}).get("data", {})
        rows.append(
            {
                "sku": row.get("sku"),
                "product_name": _row_name(row),
                "product_id": row.get("productId"),
                "submitted": bool(row.get("submit", {}).get("ok")),
                "review_status": submit_resp.get("reviewStatus"),
                "status": submit_resp.get("status") or row.get("patch", {}).get("resp", {}).get("data", {}).get("listing", {}).get("status"),
                "submission_price_usd": row.get("payload", {}).get("basePrice"),
                "blocking_issue_codes": readiness.get("issueCodes") or [],
                "blocking_issues": readiness.get("issues") or [],
                "error": row.get("error"),
                "exception": row.get("exception"),
            }
        )
    success = [row for row in rows if row["submitted"]]
    failed = [row for row in rows if not row["submitted"]]
    return {
        "generated_at_utc": _utc_now().isoformat(),
        "generated_at_ny": _ny_now().isoformat(),
        "processed_count": len(rows),
        "success_count": len(success),
        "failure_count": len(failed),
        "state_processed_count": state.get("processedCount"),
        "state_success_count": state.get("successCount"),
        "state_failure_count": state.get("failureCount"),
        "rows": rows,
    }


def write_report(summary: dict) -> tuple[Path, Path]:
    OUTPUT_ROOT.mkdir(parents=True, exist_ok=True)
    stamp = _utc_now().strftime("%Y%m%dT%H%M%SZ")
    md_path = OUTPUT_ROOT / f"neosgo-seller-bulk-{stamp}.md"
    json_path = OUTPUT_ROOT / f"neosgo-seller-bulk-{stamp}.json"
    lines = [
        f"# Neosgo Seller Bulk Report",
        "",
        f"- Generated (UTC): {summary['generated_at_utc']}",
        f"- Generated (NY): {summary['generated_at_ny']}",
        f"- Processed: {summary['processed_count']}",
        f"- Success: {summary['success_count']}",
        f"- Failed: {summary['failure_count']}",
        "",
        "## Processed Listings",
        "",
    ]
    for row in summary["rows"]:
        lines.append(f"- SKU `{row['sku']}` | {row['product_name']} | submit_price=${row['submission_price_usd']} | submitted={row['submitted']} | status={row['status']} | review={row['review_status']}")
        if row["blocking_issue_codes"]:
            lines.append(f"  blockers={', '.join(row['blocking_issue_codes'])}")
        if row["error"] or row["exception"]:
            lines.append(f"  error={row['error'] or row['exception']}")
    md_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    json_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    return md_path, json_path


def send_to_telegram(chat_id: str, summary: dict, attachments: list[Path]) -> list[dict]:
    text = (
        f"Neosgo seller bulk run finished.\n"
        f"Processed: {summary['processed_count']}\n"
        f"Success: {summary['success_count']}\n"
        f"Failed: {summary['failure_count']}"
    )
    deliveries = []
    for idx, attachment in enumerate(attachments):
        cmd = [
            OPENCLAW_BIN,
            "message",
            "send",
            "--channel",
            "telegram",
            "--target",
            str(chat_id),
            "--media",
            str(attachment),
            "--force-document",
            "--json",
        ]
        if idx == 0:
            cmd.extend(["--message", text])
        proc = subprocess.run(cmd, capture_output=True, text=True, check=False)
        deliveries.append(
            {
                "path": str(attachment),
                "returncode": proc.returncode,
                "stdout": proc.stdout.strip(),
                "stderr": proc.stderr.strip(),
            }
        )
    return deliveries


def mark_schedule_run():
    STAMP_PATH.parent.mkdir(parents=True, exist_ok=True)
    STAMP_PATH.write_text(_ny_now().strftime("%Y-%m-%d"), encoding="utf-8")


def main():
    args = parse_args()
    should_run, reason = should_run_now(force=args.force)
    if not should_run:
        print(json.dumps({"ran": False, "reason": reason}, ensure_ascii=False))
        return 0
    proc = run_runner(limit=args.limit, page_size=args.page_size, max_pages=args.max_pages)
    state = load_state()
    summary = summarize(state)
    summary["runner_returncode"] = proc.returncode
    summary["runner_stdout_tail"] = proc.stdout[-4000:]
    summary["runner_stderr_tail"] = proc.stderr[-4000:]
    md_path, json_path = write_report(summary)
    deliveries = send_to_telegram(args.chat_id, summary, [md_path, json_path])
    summary["telegram_deliveries"] = deliveries
    json_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    mark_schedule_run()
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
