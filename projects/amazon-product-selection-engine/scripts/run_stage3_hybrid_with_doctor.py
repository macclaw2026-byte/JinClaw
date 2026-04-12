#!/usr/bin/env python3
# RULES-FIRST NOTICE:
# Before modifying this file, first read:
# - `JINCLAW_CONSTITUTION.md`
# - `AI_OPTIMIZATION_FRAMEWORK.md`
# Follow the constitution and framework:
# brain-first, one-doctor, fail-closed, evidence-over-narration,
# validate locally, then use the required PR workflow.
from __future__ import annotations

import argparse
import json
import os
import random
import signal
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path("/Users/mac_claw/.openclaw/workspace")
PROJECT_ROOT = ROOT / "projects/amazon-product-selection-engine"
HYBRID_SCRIPT = PROJECT_ROOT / "scripts/run_stage3_hybrid_keyword_collection.py"
DEFAULT_UNIQUE_JSON = ROOT / "data/amazon-product-selection/processed/stage2-unique-alternate-keywords.json"
DEFAULT_ALT_JSON = ROOT / "data/amazon-product-selection/processed/stage2-alternate-keyword-entries.json"
DEFAULT_METRICS_JSON = ROOT / "data/amazon-product-selection/processed/stage3-amazon-keyword-metrics.json"
DEFAULT_REPORT_DIR = PROJECT_ROOT / "reports/stage3-hybrid-doctor"
DEFAULT_LOG_DIR = PROJECT_ROOT / "reports/stage3-hybrid-runner-logs"
DEFAULT_RUNTIME_STATE = PROJECT_ROOT / "runtime/stage3-hybrid-monitor-state.json"
COMPLETED_STATUSES = {"ok", "empty"}


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def read_json(path: Path, default: object) -> object:
    if not path.exists():
        return default
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def run_cmd(command: list[str], *, timeout: int | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(command, capture_output=True, text=True, check=False, timeout=timeout)


def slugify(value: str) -> str:
    cleaned = "".join(ch.lower() if ch.isalnum() else "-" for ch in value)
    while "--" in cleaned:
        cleaned = cleaned.replace("--", "-")
    return cleaned.strip("-") or "snapshot"


def load_total_keywords(input_path: Path) -> int:
    payload = read_json(input_path, {})
    assert isinstance(payload, dict)
    rows = payload.get("keywords") or []
    return len(rows) if isinstance(rows, list) else 0


def load_metric_rows(metrics_json: Path) -> list[dict]:
    payload = read_json(metrics_json, {})
    if not isinstance(payload, dict):
        return []
    rows = payload.get("rows") or payload.get("metrics") or []
    return rows if isinstance(rows, list) else []


def completed_keyword_count(metrics_json: Path) -> int:
    rows = load_metric_rows(metrics_json)
    return sum(1 for row in rows if str((row or {}).get("collection_status") or "").strip() in COMPLETED_STATUSES)


def blocked_keyword_count(metrics_json: Path) -> int:
    rows = load_metric_rows(metrics_json)
    return sum(1 for row in rows if str((row or {}).get("collection_status") or "").strip() not in COMPLETED_STATUSES)


def doctor_snapshot(report_dir: Path, reason: str) -> Path:
    report_dir.mkdir(parents=True, exist_ok=True)
    completed = run_cmd(["openclaw", "doctor", "--non-interactive"], timeout=300)
    timestamp = utc_now().replace(":", "").replace("-", "")
    path = report_dir / f"{timestamp}-{slugify(reason)}-doctor.json"
    write_json(
        path,
        {
            "captured_at": utc_now(),
            "reason": reason,
            "returncode": completed.returncode,
            "stdout": completed.stdout,
            "stderr": completed.stderr,
        },
    )
    return path


def tasks_audit_snapshot(report_dir: Path, reason: str) -> Path:
    report_dir.mkdir(parents=True, exist_ok=True)
    completed = run_cmd(["openclaw", "tasks", "audit", "--json"], timeout=300)
    timestamp = utc_now().replace(":", "").replace("-", "")
    path = report_dir / f"{timestamp}-{slugify(reason)}-tasks-audit.json"
    if completed.returncode == 0:
        try:
            payload = json.loads(completed.stdout or "{}")
        except json.JSONDecodeError:
            payload = {
                "captured_at": utc_now(),
                "reason": reason,
                "returncode": completed.returncode,
                "stdout": completed.stdout,
                "stderr": completed.stderr,
            }
    else:
        payload = {
            "captured_at": utc_now(),
            "reason": reason,
            "returncode": completed.returncode,
            "stdout": completed.stdout,
            "stderr": completed.stderr,
        }
    write_json(path, payload)
    return path


def write_runtime_state(path: Path, payload: dict) -> None:
    existing = read_json(path, {})
    if not isinstance(existing, dict):
        existing = {}
    merged = {**existing, **payload, "updated_at": utc_now()}
    write_json(path, merged)


def terminate_process_group(proc: subprocess.Popen[str]) -> None:
    if proc.poll() is not None:
        return
    try:
        os.killpg(proc.pid, signal.SIGTERM)
    except ProcessLookupError:
        return
    deadline = time.time() + 15
    while time.time() < deadline:
        if proc.poll() is not None:
            return
        time.sleep(0.5)
    try:
        os.killpg(proc.pid, signal.SIGKILL)
    except ProcessLookupError:
        return


def build_batch_command(args: argparse.Namespace) -> list[str]:
    return [
        sys.executable,
        str(HYBRID_SCRIPT),
        "--unique-keywords-json",
        str(args.unique_keywords_json),
        "--alternate-entries-json",
        str(args.alternate_entries_json),
        "--details-json",
        str(args.details_json),
        "--metrics-json",
        str(args.metrics_json),
        "--metrics-csv",
        str(args.metrics_csv),
        "--expanded-json",
        str(args.expanded_json),
        "--expanded-csv",
        str(args.expanded_csv),
        "--final-csv",
        str(args.final_csv),
        "--sleep-min-seconds",
        str(args.sleep_min_seconds),
        "--sleep-max-seconds",
        str(args.sleep_max_seconds),
        "--save-every",
        str(args.save_every),
        "--max-new-keywords",
        str(args.batch_keyword_goal),
    ]


def run_batch(args: argparse.Namespace, attempt: int, total_keywords: int) -> dict:
    args.log_dir.mkdir(parents=True, exist_ok=True)
    stdout_log = args.log_dir / f"attempt-{attempt:03d}.stdout.log"
    stderr_log = args.log_dir / f"attempt-{attempt:03d}.stderr.log"
    before_completed = completed_keyword_count(args.metrics_json)
    command = build_batch_command(args)
    with stdout_log.open("w", encoding="utf-8") as stdout_handle, stderr_log.open("w", encoding="utf-8") as stderr_handle:
        proc = subprocess.Popen(
            command,
            stdout=stdout_handle,
            stderr=stderr_handle,
            text=True,
            preexec_fn=os.setsid,
        )
        last_progress = before_completed
        last_progress_at = time.time()
        last_doctor_at = 0.0
        while proc.poll() is None:
            now = time.time()
            if now - last_doctor_at >= args.doctor_interval_sec:
                doctor_path = doctor_snapshot(args.report_dir, f"attempt-{attempt}-heartbeat")
                audit_path = tasks_audit_snapshot(args.report_dir, f"attempt-{attempt}-heartbeat")
                write_runtime_state(
                    args.runtime_state,
                    {
                        "status": "running",
                        "attempt": attempt,
                        "completed_keyword_count": last_progress,
                        "total_keyword_count": total_keywords,
                        "last_doctor_snapshot": str(doctor_path),
                        "last_tasks_audit_snapshot": str(audit_path),
                    },
                )
                last_doctor_at = now
            current_completed = completed_keyword_count(args.metrics_json)
            if current_completed > last_progress:
                last_progress = current_completed
                last_progress_at = now
                write_runtime_state(
                    args.runtime_state,
                    {
                        "status": "running",
                        "attempt": attempt,
                        "completed_keyword_count": current_completed,
                        "total_keyword_count": total_keywords,
                    },
                )
            if now - last_progress_at >= args.stall_timeout_sec:
                terminate_process_group(proc)
                raise RuntimeError(f"stage3_hybrid_stalled_no_progress_for_{args.stall_timeout_sec}s")
            time.sleep(10)
    return {
        "returncode": proc.returncode or 0,
        "stdout_log": stdout_log,
        "stderr_log": stderr_log,
        "completed_before": before_completed,
        "completed_after": completed_keyword_count(args.metrics_json),
        "blocked_after": blocked_keyword_count(args.metrics_json),
    }


def cooldown(reason: str, *, runtime_state: Path, min_sec: int, max_sec: int) -> int:
    delay = random.randint(min_sec, max_sec)
    write_runtime_state(
        runtime_state,
        {
            "status": "cooldown",
            "cooldown_reason": reason,
            "cooldown_seconds": delay,
        },
    )
    deadline = time.time() + delay
    while time.time() < deadline:
        time.sleep(min(15, max(1, deadline - time.time())))
    return delay


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run stage3 hybrid keyword collection with OpenClaw doctor monitoring, checkpoints, and retry recovery.")
    parser.add_argument("--unique-keywords-json", type=Path, default=DEFAULT_UNIQUE_JSON)
    parser.add_argument("--alternate-entries-json", type=Path, default=DEFAULT_ALT_JSON)
    parser.add_argument("--details-json", type=Path, default=ROOT / "data/amazon-product-selection/processed/stage3-amazon-keyword-details.json")
    parser.add_argument("--metrics-json", type=Path, default=DEFAULT_METRICS_JSON)
    parser.add_argument("--metrics-csv", type=Path, default=ROOT / "data/amazon-product-selection/processed/stage3-amazon-keyword-metrics.csv")
    parser.add_argument("--expanded-json", type=Path, default=ROOT / "data/amazon-product-selection/processed/stage3-amazon-expanded-alternate-metrics.json")
    parser.add_argument("--expanded-csv", type=Path, default=ROOT / "data/amazon-product-selection/processed/stage3-amazon-expanded-alternate-metrics.csv")
    parser.add_argument("--final-csv", type=Path, default=ROOT / "output/amazon-product-selection/amazon-product-selection-keyword-results.csv")
    parser.add_argument("--report-dir", type=Path, default=DEFAULT_REPORT_DIR)
    parser.add_argument("--log-dir", type=Path, default=DEFAULT_LOG_DIR)
    parser.add_argument("--runtime-state", type=Path, default=DEFAULT_RUNTIME_STATE)
    parser.add_argument("--batch-keyword-goal", type=int, default=50)
    parser.add_argument("--sleep-min-seconds", type=float, default=1.5)
    parser.add_argument("--sleep-max-seconds", type=float, default=4.0)
    parser.add_argument("--save-every", type=int, default=100)
    parser.add_argument("--doctor-interval-sec", type=int, default=300)
    parser.add_argument("--stall-timeout-sec", type=int, default=900)
    parser.add_argument("--batch-cooldown-min-sec", type=int, default=90)
    parser.add_argument("--batch-cooldown-max-sec", type=int, default=180)
    parser.add_argument("--failure-cooldown-min-sec", type=int, default=300)
    parser.add_argument("--failure-cooldown-max-sec", type=int, default=600)
    parser.add_argument("--max-attempts", type=int, default=500)
    args = parser.parse_args()
    if args.sleep_min_seconds < 0 or args.sleep_max_seconds < args.sleep_min_seconds:
        raise SystemExit("invalid sleep range")
    if args.batch_keyword_goal < 1:
        raise SystemExit("batch-keyword-goal must be >= 1")
    if args.batch_cooldown_max_sec < args.batch_cooldown_min_sec:
        raise SystemExit("invalid batch cooldown range")
    if args.failure_cooldown_max_sec < args.failure_cooldown_min_sec:
        raise SystemExit("invalid failure cooldown range")
    return args


def main() -> int:
    args = parse_args()
    total_keywords = load_total_keywords(args.unique_keywords_json)
    if total_keywords <= 0:
        raise SystemExit("no unique alternate keywords found")

    for attempt in range(1, args.max_attempts + 1):
        current_completed = completed_keyword_count(args.metrics_json)
        if current_completed >= total_keywords:
            doctor_path = doctor_snapshot(args.report_dir, f"attempt-{attempt}-already-complete")
            audit_path = tasks_audit_snapshot(args.report_dir, f"attempt-{attempt}-already-complete")
            write_runtime_state(
                args.runtime_state,
                {
                    "status": "completed",
                    "attempt": attempt,
                    "completed_keyword_count": current_completed,
                    "blocked_keyword_count": blocked_keyword_count(args.metrics_json),
                    "total_keyword_count": total_keywords,
                    "last_doctor_snapshot": str(doctor_path),
                    "last_tasks_audit_snapshot": str(audit_path),
                },
            )
            return 0

        doctor_path = doctor_snapshot(args.report_dir, f"attempt-{attempt}-preflight")
        audit_path = tasks_audit_snapshot(args.report_dir, f"attempt-{attempt}-preflight")
        write_runtime_state(
            args.runtime_state,
            {
                "status": "preflight",
                "attempt": attempt,
                "completed_keyword_count": current_completed,
                "blocked_keyword_count": blocked_keyword_count(args.metrics_json),
                "total_keyword_count": total_keywords,
                "last_doctor_snapshot": str(doctor_path),
                "last_tasks_audit_snapshot": str(audit_path),
                "batch_keyword_goal": args.batch_keyword_goal,
                "sleep_range_seconds": [args.sleep_min_seconds, args.sleep_max_seconds],
            },
        )

        try:
            result = run_batch(args, attempt, total_keywords)
        except Exception as exc:
            doctor_path = doctor_snapshot(args.report_dir, f"attempt-{attempt}-failure")
            audit_path = tasks_audit_snapshot(args.report_dir, f"attempt-{attempt}-failure")
            cooldown(
                "failure_recovery",
                runtime_state=args.runtime_state,
                min_sec=args.failure_cooldown_min_sec,
                max_sec=args.failure_cooldown_max_sec,
            )
            write_runtime_state(
                args.runtime_state,
                {
                    "status": "retrying",
                    "attempt": attempt,
                    "last_error": str(exc),
                    "completed_keyword_count": completed_keyword_count(args.metrics_json),
                    "blocked_keyword_count": blocked_keyword_count(args.metrics_json),
                    "total_keyword_count": total_keywords,
                    "last_doctor_snapshot": str(doctor_path),
                    "last_tasks_audit_snapshot": str(audit_path),
                },
            )
            continue

        current_completed = result["completed_after"]
        if result["returncode"] == 0 and current_completed >= total_keywords:
            doctor_path = doctor_snapshot(args.report_dir, f"attempt-{attempt}-success")
            audit_path = tasks_audit_snapshot(args.report_dir, f"attempt-{attempt}-success")
            write_runtime_state(
                args.runtime_state,
                {
                    "status": "completed",
                    "attempt": attempt,
                    "completed_keyword_count": current_completed,
                    "blocked_keyword_count": result["blocked_after"],
                    "total_keyword_count": total_keywords,
                    "stdout_log": str(result["stdout_log"]),
                    "stderr_log": str(result["stderr_log"]),
                    "last_doctor_snapshot": str(doctor_path),
                    "last_tasks_audit_snapshot": str(audit_path),
                },
            )
            return 0

        if result["returncode"] == 0 and current_completed > result["completed_before"]:
            doctor_path = doctor_snapshot(args.report_dir, f"attempt-{attempt}-batch-complete")
            audit_path = tasks_audit_snapshot(args.report_dir, f"attempt-{attempt}-batch-complete")
            cooldown(
                "batch_cooldown",
                runtime_state=args.runtime_state,
                min_sec=args.batch_cooldown_min_sec,
                max_sec=args.batch_cooldown_max_sec,
            )
            write_runtime_state(
                args.runtime_state,
                {
                    "status": "running",
                    "attempt": attempt,
                    "completed_keyword_count": current_completed,
                    "blocked_keyword_count": result["blocked_after"],
                    "total_keyword_count": total_keywords,
                    "stdout_log": str(result["stdout_log"]),
                    "stderr_log": str(result["stderr_log"]),
                    "last_doctor_snapshot": str(doctor_path),
                    "last_tasks_audit_snapshot": str(audit_path),
                },
            )
            continue

        doctor_path = doctor_snapshot(args.report_dir, f"attempt-{attempt}-retry")
        audit_path = tasks_audit_snapshot(args.report_dir, f"attempt-{attempt}-retry")
        cooldown(
            "retry_after_nonzero_or_no_progress_exit",
            runtime_state=args.runtime_state,
            min_sec=args.failure_cooldown_min_sec,
            max_sec=args.failure_cooldown_max_sec,
        )
        write_runtime_state(
            args.runtime_state,
            {
                "status": "retrying",
                "attempt": attempt,
                "last_error": f"hybrid runner exit={result['returncode']} progress={result['completed_before']}->{current_completed}",
                "completed_keyword_count": current_completed,
                "blocked_keyword_count": result["blocked_after"],
                "total_keyword_count": total_keywords,
                "stdout_log": str(result["stdout_log"]),
                "stderr_log": str(result["stderr_log"]),
                "last_doctor_snapshot": str(doctor_path),
                "last_tasks_audit_snapshot": str(audit_path),
            },
        )

    raise SystemExit("stage3 hybrid wrapper exceeded max attempts without finishing the full queue")


if __name__ == "__main__":
    raise SystemExit(main())
