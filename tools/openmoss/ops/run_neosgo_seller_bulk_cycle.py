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
CONTROL_CENTER_ROOT = WORKSPACE_ROOT / "tools/openmoss/control_center"
RUNNER_PATH = WORKSPACE_ROOT / "tools/bin/neosgo-seller-bulk-runner.py"
STATE_PATH = WORKSPACE_ROOT / "data/neosgo-seller-bulk-state.json"
OUTPUT_ROOT = WORKSPACE_ROOT / "output/neosgo-seller-bulk"
STAMP_PATH = OUTPUT_ROOT / "last_scheduled_run_ny.txt"
OPENCLAW_BIN = "/opt/homebrew/bin/openclaw"
DEFAULT_CHAT = "8528973600"
NY_TZ = ZoneInfo("America/New_York")

import sys

if str(CONTROL_CENTER_ROOT) not in sys.path:
    sys.path.insert(0, str(CONTROL_CENTER_ROOT))

from control_plane_builder import build_control_plane
from memory_writeback_runtime import record_memory_writeback
from paths import SELLER_BULK_SCHEDULER_STATE_PATH


def parse_args():
    parser = argparse.ArgumentParser(description="Run Neosgo seller bulk submission and emit a report.")
    parser.add_argument("--force", action="store_true", help="Run regardless of schedule gate.")
    parser.add_argument("--no-telegram", action="store_true", help="Generate report but skip Telegram delivery.")
    parser.add_argument("--limit", type=int, default=9999, help="Maximum number of importable candidates to process.")
    parser.add_argument("--page-size", type=int, default=50, help="Candidates page size.")
    parser.add_argument("--max-pages", type=int, default=10, help="Maximum candidate pages to scan.")
    parser.add_argument("--chat-id", default=os.environ.get("NEOSGO_SELLER_REPORT_CHAT", DEFAULT_CHAT), help="Telegram direct chat target.")
    return parser.parse_args()


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _ny_now() -> datetime:
    return _utc_now().astimezone(NY_TZ)


def _read_json(path: Path, default: dict) -> dict:
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return default


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _parse_iso(value: str) -> datetime | None:
    raw = str(value or "").strip()
    if not raw:
        return None
    try:
        return datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        return None


def _seconds_since(value: str) -> int | None:
    dt = _parse_iso(value)
    if not dt:
        return None
    return max(0, int((_utc_now() - dt).total_seconds()))


def _load_scheduler_state() -> dict:
    return _read_json(SELLER_BULK_SCHEDULER_STATE_PATH, {})


def _write_scheduler_state(payload: dict) -> None:
    _write_json(SELLER_BULK_SCHEDULER_STATE_PATH, payload)


def _load_scheduler_policy() -> dict:
    try:
        control_plane = build_control_plane()
    except Exception:
        return {}
    return (control_plane.get("project_scheduler_policy", {}) or {}).get("seller_bulk", {}) or {}


def should_run_now(force: bool, scheduler_policy: dict | None = None, scheduler_state: dict | None = None) -> tuple[bool, str]:
    if force:
        return True, "forced"
    scheduler_policy = scheduler_policy or {}
    scheduler_state = scheduler_state or {}
    if scheduler_policy and not bool(scheduler_policy.get("start_tasks", True)):
        return False, "scheduler_policy_start_tasks_false"
    now_ny = _ny_now()
    window_hour = int(scheduler_policy.get("window_hour_new_york", 23) or 23)
    if bool(scheduler_policy.get("skip_outside_window", True)) and now_ny.hour != window_hour:
        return False, f"outside_window:{now_ny.strftime('%Y-%m-%d %H:%M:%S %Z')}"
    today = now_ny.strftime("%Y-%m-%d")
    if STAMP_PATH.exists() and STAMP_PATH.read_text(encoding="utf-8").strip() == today:
        return False, f"already_ran:{today}"
    suggested_interval = int(scheduler_policy.get("suggested_interval_seconds", 0) or 0)
    since_last_started = _seconds_since(str(scheduler_state.get("last_started_at", "")))
    if suggested_interval > 0 and since_last_started is not None and since_last_started < suggested_interval:
        return False, f"scheduler_backoff_active:{suggested_interval}"
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


def _effective_runner_settings(
    scheduler_policy: dict | None,
    *,
    requested_limit: int,
    requested_page_size: int,
    requested_max_pages: int,
) -> dict[str, int]:
    scheduler_policy = scheduler_policy or {}

    def _clamp(name: str, requested: int) -> int:
        hinted = scheduler_policy.get(name)
        try:
            hinted_int = int(hinted)
        except (TypeError, ValueError):
            return requested
        if hinted_int <= 0:
            return requested
        return min(requested, hinted_int)

    return {
        "limit": _clamp("effective_limit", requested_limit),
        "page_size": _clamp("effective_page_size", requested_page_size),
        "max_pages": _clamp("effective_max_pages", requested_max_pages),
    }


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


def _extract_import_failure_labels(raw_row: dict) -> list[str]:
    labels: list[str] = []
    results = (
        raw_row.get("import", {})
        .get("resp", {})
        .get("data", {})
        .get("results")
        or []
    )
    for item in results:
        if not isinstance(item, dict):
            continue
        if str(item.get("status") or "").strip().upper() != "FAILED":
            continue
        message = str(item.get("message") or "").strip()
        lowered = message.lower()
        if not message:
            continue
        if "non-draft listing" in lowered:
            labels.append("SKU_EXISTS_ON_NON_DRAFT")
        elif "unique constraint failed" in lowered:
            labels.append("SKU_UNIQUE_CONSTRAINT")
        else:
            labels.append(message)
    return labels


def _extract_request_failure_labels(raw_row: dict) -> list[str]:
    labels: list[str] = []
    for step in ("import", "patch", "readiness", "submit"):
        error = (raw_row.get(step) or {}).get("error") or {}
        if not isinstance(error, dict):
            continue
        http_status = error.get("http_status")
        if http_status:
            labels.append(f"{step.upper()}_HTTP_{http_status}")
        network_error = str(error.get("network_error") or "").strip()
        exception = str(error.get("exception") or "").strip()
        joined = f"{network_error} {exception}".strip().lower()
        if "timed out" in joined or "timeout" in joined:
            labels.append(f"{step.upper()}_TIMEOUT")
        elif joined:
            labels.append(f"{step.upper()}_REQUEST_ERROR")
    return labels


def _is_auto_repairable_label(label: str) -> bool:
    normalized = str(label or "").strip().lower()
    return normalized in {
        "imported product id not found",
        "only_draft_supported",
        "sku_exists_on_non_draft",
        "sku_unique_constraint",
        "import_timeout",
        "patch_timeout",
        "readiness_timeout",
        "submit_timeout",
        "import_request_error",
        "patch_request_error",
        "readiness_request_error",
        "submit_request_error",
    } or "unique constraint" in normalized or "draft" in normalized or "timeout" in normalized


def summarize(state: dict) -> dict:
    processed = state.get("processed", [])
    rows = []
    for raw_row in processed:
        readiness = raw_row.get("readiness", {}).get("resp", {}).get("data", {}).get("submissionReadiness", {})
        import_failure_labels = _extract_import_failure_labels(raw_row)
        request_failure_labels = _extract_request_failure_labels(raw_row)
        submit_resp = raw_row.get("submit", {}).get("resp", {}).get("data", {})
        rows.append(
            {
                "sku": raw_row.get("sku"),
                "product_name": _row_name(raw_row),
                "product_id": raw_row.get("productId"),
                "submitted": bool(raw_row.get("submit", {}).get("ok")),
                "review_status": submit_resp.get("reviewStatus"),
                "status": submit_resp.get("status") or raw_row.get("patch", {}).get("resp", {}).get("data", {}).get("listing", {}).get("status"),
                "submission_price_usd": raw_row.get("payload", {}).get("basePrice"),
                "blocking_issue_codes": readiness.get("issueCodes") or [],
                "blocking_issues": readiness.get("issues") or [],
                "error": raw_row.get("error"),
                "exception": raw_row.get("exception"),
                "import_failure_labels": import_failure_labels,
                "request_failure_labels": request_failure_labels,
            }
        )
    success = [row for row in rows if row["submitted"]]
    failed = [row for row in rows if not row["submitted"]]
    failure_categories: dict[str, int] = {}
    auto_repairable_examples: list[dict] = []
    manual_review_examples: list[dict] = []
    auto_repairable_count = 0
    manual_review_count = 0
    for row in failed:
        labels: list[str] = []
        if row["blocking_issue_codes"]:
            labels.extend(str(code).strip() for code in row["blocking_issue_codes"] if str(code).strip())
        if row["import_failure_labels"]:
            labels.extend(str(label).strip() for label in row["import_failure_labels"] if str(label).strip())
        if row.get("request_failure_labels"):
            labels.extend(str(label).strip() for label in row["request_failure_labels"] if str(label).strip())
        if row["error"]:
            labels.append(str(row["error"]).strip())
        if row["exception"]:
            labels.append(str(row["exception"]).strip())
        if not labels:
            labels.append(str(row["status"] or "unknown_failure").strip())
        for label in labels:
            failure_categories[label] = failure_categories.get(label, 0) + 1
        normalized_labels = {label.lower() for label in labels}
        sample = {
            "sku": row["sku"],
            "product_name": row["product_name"],
            "labels": labels,
            "status": row["status"],
            "submission_price_usd": row["submission_price_usd"],
        }
        if any(_is_auto_repairable_label(label) for label in labels):
            auto_repairable_count += 1
            if len(auto_repairable_examples) < 8:
                auto_repairable_examples.append(sample)
        else:
            manual_review_count += 1
            if len(manual_review_examples) < 8:
                manual_review_examples.append(sample)
    primary_blocker = ""
    if failure_categories:
        primary_blocker = sorted(failure_categories.items(), key=lambda item: (-item[1], item[0]))[0][0]
    governance_status = "healthy"
    if failed and not success:
        governance_status = "blocked"
    elif failed:
        governance_status = "degraded"
    next_actions = []
    if primary_blocker:
        next_actions.append(f"resolve:{primary_blocker}")
    if failure_categories.get("ONLY_DRAFT_SUPPORTED"):
        next_actions.append("rebuild_or_skip_non_draft_listings")
    if any("unique constraint" in key.lower() for key in failure_categories):
        next_actions.append("deduplicate_listing_import_targets")
    if any("product id not found" in key.lower() for key in failure_categories):
        next_actions.append("backfill_imported_product_ids_before_submit")
    return {
        "generated_at_utc": _utc_now().isoformat(),
        "generated_at_ny": _ny_now().isoformat(),
        "processed_count": len(rows),
        "success_count": len(success),
        "failure_count": len(failed),
        "state_processed_count": state.get("processedCount"),
        "state_success_count": state.get("successCount"),
        "state_failure_count": state.get("failureCount"),
        "governance": {
            "status": governance_status,
            "primary_blocker": primary_blocker,
            "failure_categories": failure_categories,
            "next_actions": next_actions,
            "auto_repairable_count": auto_repairable_count,
            "manual_review_count": manual_review_count,
            "auto_repairable_examples": auto_repairable_examples,
            "manual_review_examples": manual_review_examples,
        },
        "rows": rows,
    }


def _top_success_rows(summary: dict, limit: int = 3) -> list[dict]:
    rows = [row for row in summary.get("rows", []) if row.get("submitted")]
    return rows[:limit]


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
        "## Governance",
        "",
        f"- Status: {summary.get('governance', {}).get('status', 'unknown')}",
        f"- Primary blocker: {summary.get('governance', {}).get('primary_blocker') or 'none'}",
    ]
    next_actions = summary.get("governance", {}).get("next_actions") or []
    failure_categories = summary.get("governance", {}).get("failure_categories") or {}
    if next_actions:
        lines.append(f"- Next actions: {', '.join(next_actions)}")
    lines.append(f"- Auto-repairable failures: {summary.get('governance', {}).get('auto_repairable_count', 0)}")
    lines.append(f"- Manual-review failures: {summary.get('governance', {}).get('manual_review_count', 0)}")
    if failure_categories:
        lines.append("- Failure categories:")
        for label, count in sorted(failure_categories.items(), key=lambda item: (-item[1], item[0])):
            lines.append(f"  - {label}: {count}")
    auto_repairable_examples = summary.get("governance", {}).get("auto_repairable_examples") or []
    manual_review_examples = summary.get("governance", {}).get("manual_review_examples") or []
    if auto_repairable_examples:
        lines.append("- Auto-repairable examples:")
        for row in auto_repairable_examples:
            lines.append(f"  - {row['sku']} :: {', '.join(row['labels'])}")
    if manual_review_examples:
        lines.append("- Manual-review examples:")
        for row in manual_review_examples:
            lines.append(f"  - {row['sku']} :: {', '.join(row['labels'])}")
    lines.extend(
        [
            "",
        "## Processed Listings",
        "",
        ]
    )
    for row in summary["rows"]:
        lines.append(f"- SKU `{row['sku']}` | {row['product_name']} | submit_price=${row['submission_price_usd']} | submitted={row['submitted']} | status={row['status']} | review={row['review_status']}")
        if row["blocking_issue_codes"]:
            lines.append(f"  blockers={', '.join(row['blocking_issue_codes'])}")
        if row["import_failure_labels"]:
            lines.append(f"  import_failures={', '.join(row['import_failure_labels'])}")
        if row.get("request_failure_labels"):
            lines.append(f"  request_failures={', '.join(row['request_failure_labels'])}")
        if row["error"] or row["exception"]:
            lines.append(f"  error={row['error'] or row['exception']}")
    md_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    json_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    return md_path, json_path


def send_to_telegram(chat_id: str, summary: dict, attachments: list[Path]) -> list[dict]:
    governance = summary.get("governance", {}) or {}
    governance_line = f"Governance: {governance.get('status', 'unknown')}"
    if governance.get("primary_blocker"):
        governance_line += f" | blocker={governance['primary_blocker']}"
    next_actions = governance.get("next_actions") or []
    text = (
        f"Neosgo seller bulk run finished.\n"
        f"Processed: {summary['processed_count']}\n"
        f"Success: {summary['success_count']}\n"
        f"Failed: {summary['failure_count']}\n"
        f"{governance_line}"
    )
    if next_actions:
        text += f"\nNext: {', '.join(next_actions)}"
    auto_count = governance.get("auto_repairable_count", 0)
    manual_count = governance.get("manual_review_count", 0)
    text += f"\nFailure split: auto={auto_count} manual={manual_count}"
    top_success = _top_success_rows(summary)
    if top_success:
        text += "\nTop success:"
        for row in top_success:
            text += f"\n- {row['sku']} ${row['submission_price_usd']}"
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
    scheduler_policy = _load_scheduler_policy()
    scheduler_state_before = _load_scheduler_state()
    runner_settings = _effective_runner_settings(
        scheduler_policy,
        requested_limit=args.limit,
        requested_page_size=args.page_size,
        requested_max_pages=args.max_pages,
    )
    should_run, reason = should_run_now(force=args.force, scheduler_policy=scheduler_policy, scheduler_state=scheduler_state_before)
    if not should_run:
        suggested_interval = int(scheduler_policy.get("suggested_interval_seconds", 0) or 0)
        next_eligible_at = ""
        if suggested_interval > 0:
            next_eligible_at = datetime.fromtimestamp(
                _utc_now().timestamp() + suggested_interval,
                tz=timezone.utc,
            ).isoformat()
        scheduler_state_after = {
            "updated_at": _utc_now().isoformat(),
            "last_mode": scheduler_policy.get("recommended_mode", ""),
            "last_repair_focus": str(scheduler_policy.get("repair_focus", "")).strip(),
            "last_repair_mode": str(scheduler_policy.get("repair_mode", "")).strip(),
            "last_interval_seconds": suggested_interval,
            "last_force": args.force,
            "last_requested_start_tasks": True,
            "last_effective_start_tasks": False,
            "last_effective_limit": runner_settings["limit"],
            "last_effective_page_size": runner_settings["page_size"],
            "last_effective_max_pages": runner_settings["max_pages"],
            "last_skip_reason": reason,
            "last_started_at": scheduler_state_before.get("last_started_at", ""),
            "next_eligible_at": next_eligible_at,
        }
        _write_scheduler_state(scheduler_state_after)
        print(
            json.dumps(
                {
                    "ran": False,
                    "reason": reason,
                    "scheduler_policy": scheduler_policy,
                    "runner_settings": runner_settings,
                    "scheduler_state_before": scheduler_state_before,
                    "scheduler_state_after": scheduler_state_after,
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        return 0
    proc = run_runner(
        limit=runner_settings["limit"],
        page_size=runner_settings["page_size"],
        max_pages=runner_settings["max_pages"],
    )
    state = load_state()
    summary = summarize(state)
    summary["runner_returncode"] = proc.returncode
    summary["runner_stdout_tail"] = proc.stdout[-4000:]
    summary["runner_stderr_tail"] = proc.stderr[-4000:]
    summary["scheduler_policy"] = scheduler_policy
    summary["repair_focus"] = str(scheduler_policy.get("repair_focus", "")).strip()
    summary["repair_mode"] = str(scheduler_policy.get("repair_mode", "")).strip()
    summary["runner_settings"] = {
        "requested_limit": args.limit,
        "requested_page_size": args.page_size,
        "requested_max_pages": args.max_pages,
        **runner_settings,
    }
    summary["scheduler_state_before"] = scheduler_state_before
    summary["memory_writeback"] = record_memory_writeback(
        "project-neosgo-seller-bulk",
        source="seller_bulk_cycle",
        summary={
            "attention_required": bool(summary.get("failure_count", 0)),
            "state_patch": {},
            "governance_patch": {},
            "next_actions": [str(item).strip() for item in (summary.get("governance", {}) or {}).get("next_actions", []) if str(item).strip()],
            "warnings": [str((summary.get("governance", {}) or {}).get("primary_blocker", "")).strip()] if str((summary.get("governance", {}) or {}).get("primary_blocker", "")).strip() else [],
            "errors": [],
            "decisions": ["seller_bulk_cycle_completed"],
            "memory_targets": ["project", "runtime"],
            "memory_reasons": ["seller_bulk_cycle", "project_seller_feedback"],
        },
    )
    md_path, json_path = write_report(summary)
    deliveries = [] if args.no_telegram else send_to_telegram(args.chat_id, summary, [md_path, json_path])
    summary["telegram_deliveries"] = deliveries
    suggested_interval = int(scheduler_policy.get("suggested_interval_seconds", 0) or 0)
    next_eligible_at = ""
    if suggested_interval > 0:
        next_eligible_at = datetime.fromtimestamp(
            _utc_now().timestamp() + suggested_interval,
            tz=timezone.utc,
        ).isoformat()
    scheduler_state_after = {
        "updated_at": _utc_now().isoformat(),
        "last_mode": scheduler_policy.get("recommended_mode", ""),
        "last_repair_focus": str(scheduler_policy.get("repair_focus", "")).strip(),
        "last_repair_mode": str(scheduler_policy.get("repair_mode", "")).strip(),
        "last_interval_seconds": suggested_interval,
        "last_force": args.force,
        "last_requested_start_tasks": True,
        "last_effective_start_tasks": True,
        "last_effective_limit": runner_settings["limit"],
        "last_effective_page_size": runner_settings["page_size"],
        "last_effective_max_pages": runner_settings["max_pages"],
        "last_skip_reason": "",
        "last_started_at": _utc_now().isoformat(),
        "next_eligible_at": next_eligible_at,
    }
    summary["scheduler_state_after"] = scheduler_state_after
    _write_scheduler_state(scheduler_state_after)
    json_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    mark_schedule_run()
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
