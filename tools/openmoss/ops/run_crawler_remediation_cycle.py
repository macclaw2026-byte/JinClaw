#!/usr/bin/env python3

from __future__ import annotations

import argparse
import json
import os
import subprocess
from datetime import datetime, timezone
from pathlib import Path
import sys


WORKSPACE_ROOT = Path("/Users/mac_claw/.openclaw/workspace")
CONTROL_CENTER_ROOT = WORKSPACE_ROOT / "tools/openmoss/control_center"
OUTPUT_ROOT = WORKSPACE_ROOT / "output/crawler-remediation"
LATEST_REPORT_PATH = OUTPUT_ROOT / "latest-report.json"
OPENCLAW_BIN = "/opt/homebrew/bin/openclaw"
DEFAULT_CHAT = "8528973600"

if str(CONTROL_CENTER_ROOT) not in sys.path:
    sys.path.insert(0, str(CONTROL_CENTER_ROOT))

from control_plane_builder import build_control_plane
from crawler_remediation_executor import execute_crawler_remediation_plan
from memory_writeback_runtime import record_memory_writeback
from paths import CRAWLER_REMEDIATION_SCHEDULER_STATE_PATH
from system_doctor import run_system_doctor


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run project-level crawler remediation cycle.")
    parser.add_argument("--force", action="store_true", help="Ignore scheduler backoff and run immediately.")
    parser.add_argument("--no-start", action="store_true", help="Refresh remediation plan but do not run remediation tasks.")
    parser.add_argument("--skip-doctor", action="store_true", help="Skip doctor refresh after execution.")
    parser.add_argument("--no-telegram", action="store_true", help="Do not send remediation summary to Telegram.")
    parser.add_argument("--chat-id", default=os.environ.get("CRAWLER_REMEDIATION_REPORT_CHAT", DEFAULT_CHAT), help="Telegram chat target.")
    return parser.parse_args()


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _read_json(path: Path, default: dict) -> dict:
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return default


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
    return max(0, int((datetime.now(timezone.utc) - dt).total_seconds()))


def _load_scheduler_state() -> dict:
    return _read_json(CRAWLER_REMEDIATION_SCHEDULER_STATE_PATH, {})


def _write_scheduler_state(payload: dict) -> None:
    _write_json(CRAWLER_REMEDIATION_SCHEDULER_STATE_PATH, payload)


def _extract_summary(control_plane: dict) -> dict:
    summary = control_plane.get("summary", {}) or {}
    if summary:
        return summary
    crawler_profile = control_plane.get("crawler_capability_profile", {}) or {}
    crawler_summary = crawler_profile.get("summary", {}) or {}
    return {
        "crawler_sites_total": crawler_summary.get("sites_total", 0),
        "crawler_sites_ready": crawler_summary.get("sites_production_ready", 0),
        "crawler_width_score": crawler_summary.get("width_score", 0.0),
        "crawler_breadth_score": crawler_summary.get("breadth_score", 0.0),
        "crawler_depth_score": crawler_summary.get("depth_score", 0.0),
        "crawler_stability_score": crawler_summary.get("stability_score", 0.0),
    }


def write_report(payload: dict) -> tuple[Path, Path]:
    OUTPUT_ROOT.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    md_path = OUTPUT_ROOT / f"crawler-remediation-{stamp}.md"
    json_path = OUTPUT_ROOT / f"crawler-remediation-{stamp}.json"
    execution = payload.get("execution", {}) or {}
    doctor_summary = payload.get("doctor_summary", {}) or {}
    summary = payload.get("after_summary", {}) or {}
    lines = [
        "# Crawler Remediation Cycle",
        "",
        f"- Generated: {payload.get('generated_at', '')}",
        f"- Started tasks: {execution.get('started_total', 0)} / {execution.get('items_total', 0)}",
        f"- Existing tasks reused: {execution.get('existing_total', 0)}",
        f"- New tasks created: {execution.get('created_total', 0)}",
        "",
        "## Project Summary",
        "",
        f"- Sites total: {summary.get('crawler_sites_total', 0)}",
        f"- Sites ready: {summary.get('crawler_sites_ready', 0)}",
        f"- Width score: {summary.get('crawler_width_score', 0)}",
        f"- Breadth score: {summary.get('crawler_breadth_score', 0)}",
        f"- Depth score: {summary.get('crawler_depth_score', 0)}",
        f"- Stability score: {summary.get('crawler_stability_score', 0)}",
        "",
        "## Priority Actions",
        "",
    ]
    for item in (doctor_summary.get("priority_actions", []) or [])[:6]:
        site = item.get("site") or "project"
        lines.append(f"- {site}: {item.get('action', '')} ({item.get('reason', '')})")
    lines.extend(["", "## Remediation Execution", ""])
    for item in execution.get("items", []) or []:
        task_state = item.get("task_state", {}) or {}
        lines.append(
            f"- {item.get('task_id', '')} | {item.get('status', '')} | "
            f"started={bool(item.get('started'))} | "
            f"task_status={task_state.get('status', '')} | "
            f"stage={task_state.get('current_stage', '')} | "
            f"next={task_state.get('next_action', '')}"
        )
    md_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return md_path, json_path


def send_to_telegram(chat_id: str, payload: dict, attachments: list[Path]) -> list[dict]:
    execution = payload.get("execution", {}) or {}
    doctor_summary = payload.get("doctor_summary", {}) or {}
    scheduler_policy = payload.get("scheduler_policy", {}) or {}
    priority_actions = doctor_summary.get("priority_actions", []) or []
    text = (
        "Crawler remediation cycle finished.\n"
        f"Started: {execution.get('started_total', 0)}/{execution.get('items_total', 0)}\n"
        f"Existing: {execution.get('existing_total', 0)}\n"
        f"Created: {execution.get('created_total', 0)}"
    )
    if scheduler_policy:
        text += (
            f"\nMode: {scheduler_policy.get('recommended_mode', 'unknown')}"
            f" | start={bool(payload.get('effective_start_tasks'))}"
        )
    if priority_actions:
        text += "\nTop priorities:"
        for item in priority_actions[:3]:
            site = item.get("site") or "project"
            text += f"\n- {site}: {item.get('action', '')}"
    deliveries = []
    for index, attachment in enumerate(attachments):
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
        if index == 0:
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


def run_cycle(*, start_tasks: bool = True, run_doctor: bool = True, force: bool = False) -> dict:
    control_plane_before = build_control_plane()
    scheduler_policy = (control_plane_before.get("project_scheduler_policy", {}) or {}).get("crawler_remediation", {}) or {}
    scheduler_state = _load_scheduler_state()
    effective_start_tasks = bool(start_tasks)
    effective_max_start_tasks = scheduler_policy.get("max_start_tasks")
    effective_start_bias = str(scheduler_policy.get("start_bias", "")).strip() or "balanced"
    if effective_max_start_tasks is not None:
        try:
            effective_max_start_tasks = max(0, int(effective_max_start_tasks))
        except (TypeError, ValueError):
            effective_max_start_tasks = None
    skip_reason = ""
    if start_tasks and scheduler_policy and not bool(scheduler_policy.get("start_tasks", True)):
        effective_start_tasks = False
        skip_reason = "scheduler_policy_start_tasks_false"
    suggested_interval = int(scheduler_policy.get("suggested_interval_seconds", 0) or 0)
    since_last_started = _seconds_since(str(scheduler_state.get("last_started_at", "")))
    if (
        not force
        and effective_start_tasks
        and suggested_interval > 0
        and since_last_started is not None
        and since_last_started < suggested_interval
    ):
        effective_start_tasks = False
        skip_reason = f"scheduler_backoff_active:{suggested_interval}"
    if effective_start_tasks and effective_max_start_tasks == 0:
        effective_start_tasks = False
        skip_reason = "scheduler_policy_max_start_tasks_zero"
    execution = execute_crawler_remediation_plan(
        start_tasks=effective_start_tasks,
        max_start_tasks=effective_max_start_tasks if effective_start_tasks else None,
        start_bias=effective_start_bias if effective_start_tasks else "balanced",
    )
    doctor = run_system_doctor() if run_doctor and not skip_reason else {}
    control_plane_after = build_control_plane()
    payload = {
        "generated_at": _utc_now_iso(),
        "force": force,
        "start_tasks": start_tasks,
        "effective_start_tasks": effective_start_tasks,
        "skip_reason": skip_reason,
        "doctor_ran": run_doctor,
        "scheduler_policy": scheduler_policy,
        "repair_focus": str(scheduler_policy.get("repair_focus", "")).strip(),
        "repair_mode": str(scheduler_policy.get("repair_mode", "")).strip(),
        "effective_start_bias": effective_start_bias if effective_start_tasks else "balanced",
        "effective_max_start_tasks": effective_max_start_tasks if effective_start_tasks else None,
        "scheduler_state_before": scheduler_state,
        "before_summary": _extract_summary(control_plane_before),
        "execution": execution,
        "after_summary": _extract_summary(control_plane_after),
        "doctor_summary": doctor.get("crawler_health", {}),
    }
    payload["memory_writeback"] = record_memory_writeback(
        "project-crawler-remediation-cycle",
        source="crawler_remediation_cycle",
        summary={
            "attention_required": bool((payload.get("doctor_summary", {}) or {}).get("attention_sites")),
            "state_patch": {},
            "governance_patch": {},
            "next_actions": [
                str(item.get("action", "")).strip()
                for item in (payload.get("doctor_summary", {}) or {}).get("priority_actions", [])[:5]
                if str(item.get("action", "")).strip()
            ],
            "warnings": [
                f"attention:{item.get('site', 'project')}"
                for item in (payload.get("doctor_summary", {}) or {}).get("attention_sites", [])[:5]
            ],
            "errors": [],
            "decisions": ["crawler_remediation_cycle_completed"],
            "memory_targets": ["project", "runtime"],
            "memory_reasons": ["crawler_remediation_cycle", "project_crawler_feedback"],
        },
    )
    next_eligible_at = ""
    if suggested_interval > 0:
        next_eligible_at = datetime.fromtimestamp(
            datetime.now(timezone.utc).timestamp() + suggested_interval,
            tz=timezone.utc,
        ).isoformat()
    scheduler_state_after = {
        "updated_at": payload["generated_at"],
        "last_mode": scheduler_policy.get("recommended_mode", ""),
        "last_repair_focus": str(scheduler_policy.get("repair_focus", "")).strip(),
        "last_repair_mode": str(scheduler_policy.get("repair_mode", "")).strip(),
        "last_interval_seconds": suggested_interval,
        "last_force": force,
        "last_requested_start_tasks": start_tasks,
        "last_effective_start_tasks": effective_start_tasks,
        "last_effective_start_bias": effective_start_bias if effective_start_tasks else "balanced",
        "last_effective_max_start_tasks": effective_max_start_tasks if effective_start_tasks else None,
        "last_skip_reason": skip_reason,
        "last_started_at": payload["generated_at"] if effective_start_tasks else scheduler_state.get("last_started_at", ""),
        "next_eligible_at": next_eligible_at,
    }
    payload["scheduler_state_after"] = scheduler_state_after
    _write_scheduler_state(scheduler_state_after)
    _write_json(LATEST_REPORT_PATH, payload)
    return payload


def main() -> int:
    args = parse_args()
    payload = run_cycle(start_tasks=not args.no_start, run_doctor=not args.skip_doctor, force=args.force)
    md_path, json_path = write_report(payload)
    if not args.no_telegram:
        payload["telegram_deliveries"] = send_to_telegram(args.chat_id, payload, [md_path, json_path])
        json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
