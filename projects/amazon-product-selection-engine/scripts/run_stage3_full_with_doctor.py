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
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from math import ceil
from pathlib import Path


ROOT = Path("/Users/mac_claw/.openclaw/workspace")
PROJECT_ROOT = ROOT / "projects/amazon-product-selection-engine"
SCRIPT_STAGE3_ALL = PROJECT_ROOT / "scripts/run_stage3_all_alternate_keyword_collection.py"
DOCTOR_SCRIPT = ROOT / "tools/openmoss/ops/jinclaw_ops.py"
CONFIG_PATH = Path("/Users/mac_claw/.openclaw/openclaw.json")
DEFAULT_INPUT = ROOT / "data/amazon-product-selection/processed/stage2-unique-alternate-keywords.json"
CLONE_USER_DATA_DIR = ROOT / "tmp/sellersprite-actual-clone"
DEFAULT_CDP_URL = "http://127.0.0.1:9223"
DEFAULT_BROWSER_PROFILE = "sellersprite-amazon"
DEFAULT_WORKER_DIR = ROOT / "data/amazon-product-selection/processed/stage3-workers"
DEFAULT_RUNTIME_STATE = PROJECT_ROOT / "runtime/stage3-monitor-state.json"
DEFAULT_REPORT_DIR = PROJECT_ROOT / "reports/stage3-doctor"
DEFAULT_LOG_DIR = PROJECT_ROOT / "reports/stage3-runner-logs"
DEFAULT_BROWSER_SERVICE = "http://127.0.0.1:18791"
DEFAULT_MAX_PAGE_TABS = 3
DEFAULT_ACTIVE_WORKING_PAGES = 1
DEFAULT_BATCH_CHUNK_GOAL = 5
DEFAULT_BATCH_COOLDOWN_MIN_SEC = 180
DEFAULT_BATCH_COOLDOWN_MAX_SEC = 420
DEFAULT_FAILURE_COOLDOWN_MIN_SEC = 600
DEFAULT_FAILURE_COOLDOWN_MAX_SEC = 1200
DEFAULT_MIN_INTER_KEYWORD_WAIT_MS = 9000
DEFAULT_MAX_INTER_KEYWORD_WAIT_MS = 18000
DEFAULT_BROWSER_STARTUP_SETTLE_SEC = 6
DEFAULT_CDP_UNREADY_GRACE_SEC = 20
GOOGLE_CHROME_BINARY = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
AMAZON_ERROR_PATTERNS = (
    "sorry! something went wrong!",
    "sorry, we just need to make sure you're not a robot",
)


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def read_json(path: Path, default: object) -> object:
    if not path.exists():
        return default
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def slugify(value: str) -> str:
    cleaned = "".join(ch.lower() if ch.isalnum() else "-" for ch in value)
    while "--" in cleaned:
        cleaned = cleaned.replace("--", "-")
    return cleaned.strip("-") or "snapshot"


def gateway_token() -> str:
    payload = read_json(CONFIG_PATH, {})
    assert isinstance(payload, dict)
    token = (((payload.get("gateway") or {}).get("auth") or {}).get("token") or "").strip()
    if not token:
        raise RuntimeError(f"gateway auth token not found in {CONFIG_PATH}")
    return token


def browser_service_request(method: str, path: str, body: dict | None = None, timeout: int = 20) -> dict:
    data = json.dumps(body).encode("utf-8") if body is not None else None
    req = urllib.request.Request(
        f"{DEFAULT_BROWSER_SERVICE}{path}",
        data=data,
        headers={
            "Authorization": f"Bearer {gateway_token()}",
            "Content-Type": "application/json",
        },
        method=method,
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8") or "{}")


def run_cmd(command: list[str], *, timeout: int | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(command, capture_output=True, text=True, check=False, timeout=timeout)


def cdp_http_base(cdp_url: str) -> str:
    return cdp_url.rstrip("/")


def cdp_json(path: str, *, cdp_url: str, timeout: int = 10) -> dict:
    with urllib.request.urlopen(f"{cdp_http_base(cdp_url)}{path}", timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8") or "{}")


def cdp_ready(cdp_url: str) -> bool:
    try:
        cdp_json("/json/version", cdp_url=cdp_url, timeout=3)
        return True
    except Exception:
        return False


def clean_clone_runtime_files() -> list[str]:
    removed: list[str] = []
    for name in ("SingletonLock", "SingletonCookie", "SingletonSocket", "DevToolsActivePort"):
        path = CLONE_USER_DATA_DIR / name
        if path.exists() or path.is_symlink():
            path.unlink()
            removed.append(name)
    return removed


def wait_for_stable_cdp(cdp_url: str, stable_checks: int = 3, interval_sec: int = 2) -> None:
    consecutive = 0
    deadline = time.time() + max(15, stable_checks * interval_sec * 4)
    while time.time() < deadline:
        if cdp_ready(cdp_url):
            consecutive += 1
            if consecutive >= stable_checks:
                return
        else:
            consecutive = 0
        time.sleep(interval_sec)
    raise RuntimeError(f"cdp endpoint at {cdp_url} did not remain stable long enough")


def _wait_for_cdp_boot(cdp_url: str, timeout_sec: int = 45) -> bool:
    deadline = time.time() + timeout_sec
    while time.time() < deadline:
        if cdp_ready(cdp_url):
            try:
                wait_for_stable_cdp(cdp_url)
                return True
            except Exception:
                pass
        time.sleep(1)
    return False


def _launch_clone_browser_via_open(cdp_port: int) -> None:
    command = [
        "open",
        "-na",
        "Google Chrome",
        "--args",
        f"--user-data-dir={CLONE_USER_DATA_DIR}",
        f"--remote-debugging-port={cdp_port}",
        "--no-first-run",
        "--no-default-browser-check",
        "about:blank",
    ]
    subprocess.run(command, capture_output=True, text=True, check=False)


def _launch_clone_browser_via_binary(cdp_port: int) -> None:
    subprocess.Popen(
        [
            GOOGLE_CHROME_BINARY,
            f"--user-data-dir={CLONE_USER_DATA_DIR}",
            f"--remote-debugging-port={cdp_port}",
            "--no-first-run",
            "--no-default-browser-check",
            "about:blank",
        ],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True,
    )


def launch_clone_browser(cdp_url: str) -> None:
    cdp_port = urllib.parse.urlparse(cdp_url).port or 9223
    launch_errors: list[str] = []
    for label, launcher in (
        ("open", _launch_clone_browser_via_open),
        ("binary", _launch_clone_browser_via_binary),
    ):
        clean_clone_runtime_files()
        launcher(cdp_port)
        if _wait_for_cdp_boot(cdp_url):
            return
        launch_errors.append(f"{label}: clone browser did not become ready")
        stop_clone_browser(cdp_url)
    raise RuntimeError(f"clone browser did not become ready at {cdp_url}")


def listener_pids_for_cdp(cdp_url: str) -> list[int]:
    port = urllib.parse.urlparse(cdp_url).port or 9223
    completed = run_cmd(["lsof", "-nP", f"-iTCP:{port}", "-sTCP:LISTEN", "-t"], timeout=15)
    if completed.returncode != 0:
        return []
    pids: list[int] = []
    for line in (completed.stdout or "").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            pids.append(int(line))
        except ValueError:
            continue
    return pids


def stop_clone_browser(cdp_url: str) -> list[int]:
    stopped: list[int] = []
    for pid in listener_pids_for_cdp(cdp_url):
        try:
            os.kill(pid, signal.SIGTERM)
            stopped.append(pid)
        except ProcessLookupError:
            continue
    deadline = time.time() + 20
    while time.time() < deadline:
        if not cdp_ready(cdp_url):
            return stopped
        time.sleep(1)
    for pid in listener_pids_for_cdp(cdp_url):
        try:
            os.kill(pid, signal.SIGKILL)
            if pid not in stopped:
                stopped.append(pid)
        except ProcessLookupError:
            continue
    return stopped


def ensure_clone_browser(cdp_url: str) -> None:
    if cdp_ready(cdp_url):
        wait_for_stable_cdp(cdp_url)
        return
    launch_clone_browser(cdp_url)


def ensure_browser_profile(profile: str, cdp_url: str) -> dict:
    profiles = browser_service_request("GET", "/profiles").get("profiles") or []
    for entry in profiles:
        if entry.get("name") == profile:
            return entry
    return browser_service_request(
        "POST",
        "/profiles/create",
        body={
            "name": profile,
            "cdpUrl": cdp_url,
            "color": "#228B22",
        },
    )


def list_profile_tabs(profile: str) -> list[dict]:
    completed = run_cmd(["openclaw", "browser", "--json", "--browser-profile", profile, "tabs"], timeout=30)
    if completed.returncode != 0:
        raise RuntimeError(completed.stderr.strip() or completed.stdout.strip() or f"failed to list tabs for {profile}")
    payload = json.loads(completed.stdout or "{}")
    return payload.get("tabs") or []


def close_profile_tab(profile: str, target_id: str) -> None:
    completed = run_cmd(["openclaw", "browser", "--json", "--browser-profile", profile, "close", target_id], timeout=30)
    stderr = (completed.stderr or "").strip()
    if completed.returncode != 0 and "tab not found" not in stderr.lower():
        raise RuntimeError(stderr or (completed.stdout or "").strip() or f"failed to close tab {target_id}")


def visible_page_tabs(tabs: list[dict]) -> list[dict]:
    return [tab for tab in tabs if tab.get("type") == "page"]


def amazon_error_pages(tabs: list[dict]) -> list[dict]:
    degraded: list[dict] = []
    for tab in visible_page_tabs(tabs):
        title = str(tab.get("title", "") or "").lower()
        url = str(tab.get("url", "") or "").lower()
        if "amazon.com" not in url:
            continue
        if any(pattern in title for pattern in AMAZON_ERROR_PATTERNS):
            degraded.append(tab)
    return degraded


def prune_visible_page_tabs(profile: str, max_page_tabs: int) -> dict:
    tabs = list_profile_tabs(profile)
    pages = visible_page_tabs(tabs)
    closed: list[str] = []
    degraded_pages = amazon_error_pages(tabs)
    for tab in degraded_pages:
        target_id = str(tab.get("targetId") or "").strip()
        if target_id:
            close_profile_tab(profile, target_id)
            closed.append(target_id)
    if len(pages) > max_page_tabs:
        for tab in pages[max_page_tabs:]:
            target_id = str(tab.get("targetId") or "").strip()
            if not target_id or target_id in closed:
                continue
            close_profile_tab(profile, target_id)
            closed.append(target_id)
    return {
        "observed_total": len(tabs),
        "visible_page_tabs": len(pages),
        "degraded_page_tabs": len(degraded_pages),
        "closed_target_ids": closed,
    }


def doctor_snapshot(report_dir: Path, reason: str) -> Path:
    report_dir.mkdir(parents=True, exist_ok=True)
    completed = run_cmd([sys.executable, str(DOCTOR_SCRIPT), "doctor"], timeout=180)
    timestamp = utc_now().replace(":", "").replace("-", "")
    suffix = slugify(reason)
    path = report_dir / f"{timestamp}-{suffix}.json"
    payload = {
        "captured_at": utc_now(),
        "reason": reason,
        "returncode": completed.returncode,
        "stdout": completed.stdout,
        "stderr": completed.stderr,
    }
    write_json(path, payload)
    return path


def completed_chunk_count(worker_dir: Path) -> int:
    total = 0
    if not worker_dir.exists():
        return 0
    for child in worker_dir.iterdir():
        if not child.is_dir():
            continue
        if (child / "details.json").exists() and (child / "metrics.json").exists():
            total += 1
    return total


def completed_worker_names(worker_dir: Path) -> list[str]:
    names: list[str] = []
    if not worker_dir.exists():
        return names
    for child in sorted(worker_dir.iterdir()):
        if not child.is_dir():
            continue
        if (child / "details.json").exists() and (child / "metrics.json").exists():
            names.append(child.name)
    return names


def partial_worker_names(worker_dir: Path) -> list[str]:
    names: list[str] = []
    if not worker_dir.exists():
        return names
    for child in sorted(worker_dir.iterdir()):
        if not child.is_dir():
            continue
        has_details = (child / "details.json").exists()
        has_metrics = (child / "metrics.json").exists()
        if has_details != has_metrics:
            names.append(child.name)
    return names


def worker_names_with_non_ok_metrics(worker_dir: Path) -> list[str]:
    names: list[str] = []
    if not worker_dir.exists():
        return names
    for child in sorted(worker_dir.iterdir()):
        metrics_path = child / "metrics.json"
        if not child.is_dir() or not metrics_path.exists():
            continue
        payload = read_json(metrics_path, {})
        assert isinstance(payload, dict)
        rows = payload.get("metrics") or []
        if not isinstance(rows, list):
            continue
        for row in rows:
            status = str((row or {}).get("collection_status") or "").strip()
            if status != "ok":
                names.append(child.name)
                break
    return names


def remove_worker_dirs(worker_dir: Path, names: list[str]) -> list[str]:
    removed: list[str] = []
    for name in names:
        path = worker_dir / name
        if not path.exists():
            continue
        for child in path.rglob("*"):
            pass
        import shutil

        shutil.rmtree(path)
        removed.append(name)
    return removed


def write_monitor_state(path: Path, payload: dict) -> None:
    existing = read_json(path, {})
    if not isinstance(existing, dict):
        existing = {}
    merged = {
        **existing,
        **payload,
        "updated_at": utc_now(),
    }
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


def load_total_expected_chunks(input_path: Path, chunk_size: int) -> int:
    payload = read_json(input_path, {})
    assert isinstance(payload, dict)
    rows = payload.get("keywords") or payload.get("selected_keywords") or []
    count = len(rows) if isinstance(rows, list) else 0
    return ceil(count / chunk_size) if count and chunk_size > 0 else 0


def build_stage3_command(args: argparse.Namespace) -> list[str]:
    return [
        sys.executable,
        str(SCRIPT_STAGE3_ALL),
        "--input",
        str(args.input),
        "--cdp-url",
        args.cdp_url,
        "--worker-count",
        str(args.worker_count),
        "--chunk-size",
        str(args.chunk_size),
        "--wait-ms",
        str(args.wait_ms),
        "--min-inter-keyword-wait-ms",
        str(args.min_inter_keyword_wait_ms),
        "--max-inter-keyword-wait-ms",
        str(args.max_inter_keyword_wait_ms),
        "--worker-dir",
        str(args.worker_dir),
        "--resume-existing-workers",
    ]


def run_attempt(args: argparse.Namespace, attempt: int, batch_start_progress: int, total_expected_chunks: int) -> dict:
    args.log_dir.mkdir(parents=True, exist_ok=True)
    stdout_log = args.log_dir / f"attempt-{attempt:03d}.stdout.log"
    stderr_log = args.log_dir / f"attempt-{attempt:03d}.stderr.log"
    command = build_stage3_command(args)

    with stdout_log.open("w", encoding="utf-8") as stdout_handle, stderr_log.open("w", encoding="utf-8") as stderr_handle:
        proc = subprocess.Popen(
            command,
            stdout=stdout_handle,
            stderr=stderr_handle,
            text=True,
            preexec_fn=os.setsid,
        )

        last_progress = completed_chunk_count(args.worker_dir)
        last_progress_at = time.time()
        last_doctor_at = 0.0
        cdp_unready_since: float | None = None

        while proc.poll() is None:
            now = time.time()
            if now - last_doctor_at >= args.doctor_interval_sec:
                doctor_path = doctor_snapshot(args.report_dir, f"attempt-{attempt}-heartbeat")
                write_monitor_state(
                    args.runtime_state,
                    {
                        "status": "running",
                        "attempt": attempt,
                        "doctor_snapshot": str(doctor_path),
                    },
                )
                last_doctor_at = now

            progress = completed_chunk_count(args.worker_dir)
            if progress > last_progress:
                last_progress = progress
                last_progress_at = now
                write_monitor_state(
                    args.runtime_state,
                    {
                        "status": "running",
                        "attempt": attempt,
                        "completed_chunk_count": progress,
                    },
                )

            if not cdp_ready(args.cdp_url):
                if cdp_unready_since is None:
                    cdp_unready_since = now
                elif now - cdp_unready_since >= args.cdp_unready_grace_sec:
                    terminate_process_group(proc)
                    raise RuntimeError("browser_cdp_not_ready")
            else:
                cdp_unready_since = None

            tabs = list_profile_tabs(args.browser_profile)
            degraded_pages = amazon_error_pages(tabs)
            if degraded_pages:
                terminate_process_group(proc)
                raise RuntimeError("amazon_error_page_detected")

            if now - last_progress_at >= args.stall_timeout_sec:
                terminate_process_group(proc)
                raise RuntimeError(f"stage3_stalled_no_chunk_progress_for_{args.stall_timeout_sec}s")

            if (
                args.batch_chunk_goal > 0
                and progress - batch_start_progress >= args.batch_chunk_goal
                and progress < total_expected_chunks
            ):
                terminate_process_group(proc)
                return {
                    "outcome": "batch_complete",
                    "stdout_log": stdout_log,
                    "stderr_log": stderr_log,
                    "completed_chunk_count": progress,
                }

            time.sleep(10)

        return {
            "outcome": "process_exit",
            "returncode": proc.returncode or 0,
            "stdout_log": stdout_log,
            "stderr_log": stderr_log,
            "completed_chunk_count": completed_chunk_count(args.worker_dir),
        }


def cooldown(reason: str, min_sec: int, max_sec: int, runtime_state: Path) -> int:
    sleep_seconds = random.randint(min_sec, max_sec)
    write_monitor_state(
        runtime_state,
        {
            "status": "cooldown",
            "cooldown_reason": reason,
            "cooldown_seconds": sleep_seconds,
        },
    )
    deadline = time.time() + sleep_seconds
    while time.time() < deadline:
        time.sleep(min(15, max(1, deadline - time.time())))
    return sleep_seconds


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run stage3 full alternate-keyword collection with OpenClaw doctor snapshots, circuit breakers, and batch cooldowns.")
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--browser-profile", default=DEFAULT_BROWSER_PROFILE)
    parser.add_argument("--cdp-url", default=DEFAULT_CDP_URL)
    parser.add_argument("--worker-count", type=int, default=1)
    parser.add_argument("--chunk-size", type=int, default=10)
    parser.add_argument("--batch-chunk-goal", type=int, default=DEFAULT_BATCH_CHUNK_GOAL)
    parser.add_argument("--wait-ms", type=int, default=7000)
    parser.add_argument("--min-inter-keyword-wait-ms", type=int, default=DEFAULT_MIN_INTER_KEYWORD_WAIT_MS)
    parser.add_argument("--max-inter-keyword-wait-ms", type=int, default=DEFAULT_MAX_INTER_KEYWORD_WAIT_MS)
    parser.add_argument("--max-attempts", type=int, default=500)
    parser.add_argument("--doctor-interval-sec", type=int, default=180)
    parser.add_argument("--stall-timeout-sec", type=int, default=900)
    parser.add_argument("--cdp-unready-grace-sec", type=int, default=DEFAULT_CDP_UNREADY_GRACE_SEC)
    parser.add_argument("--browser-startup-settle-sec", type=int, default=DEFAULT_BROWSER_STARTUP_SETTLE_SEC)
    parser.add_argument("--batch-cooldown-min-sec", type=int, default=DEFAULT_BATCH_COOLDOWN_MIN_SEC)
    parser.add_argument("--batch-cooldown-max-sec", type=int, default=DEFAULT_BATCH_COOLDOWN_MAX_SEC)
    parser.add_argument("--failure-cooldown-min-sec", type=int, default=DEFAULT_FAILURE_COOLDOWN_MIN_SEC)
    parser.add_argument("--failure-cooldown-max-sec", type=int, default=DEFAULT_FAILURE_COOLDOWN_MAX_SEC)
    parser.add_argument("--worker-dir", type=Path, default=DEFAULT_WORKER_DIR)
    parser.add_argument("--runtime-state", type=Path, default=DEFAULT_RUNTIME_STATE)
    parser.add_argument("--report-dir", type=Path, default=DEFAULT_REPORT_DIR)
    parser.add_argument("--log-dir", type=Path, default=DEFAULT_LOG_DIR)
    parser.add_argument("--max-page-tabs", type=int, default=DEFAULT_MAX_PAGE_TABS)
    parser.add_argument("--preferred-working-pages", type=int, default=DEFAULT_ACTIVE_WORKING_PAGES)
    args = parser.parse_args()
    if args.worker_count < 1 or args.worker_count > args.max_page_tabs:
        raise SystemExit("worker-count must be between 1 and the configured max-page-tabs budget")
    if args.worker_count > args.preferred_working_pages:
        raise SystemExit("worker-count must not exceed preferred-working-pages in stability-first mode")
    if args.min_inter_keyword_wait_ms < 0 or args.max_inter_keyword_wait_ms < args.min_inter_keyword_wait_ms:
        raise SystemExit("invalid inter-keyword wait range")
    if args.batch_cooldown_max_sec < args.batch_cooldown_min_sec:
        raise SystemExit("invalid batch cooldown range")
    if args.failure_cooldown_max_sec < args.failure_cooldown_min_sec:
        raise SystemExit("invalid failure cooldown range")
    return args


def main() -> int:
    args = parse_args()
    total_expected_chunks = load_total_expected_chunks(args.input.expanduser().resolve(), args.chunk_size)
    if total_expected_chunks <= 0:
        raise SystemExit("no unique alternate keywords found to process")

    ensure_clone_browser(args.cdp_url)
    ensure_browser_profile(args.browser_profile, args.cdp_url)

    for attempt in range(1, args.max_attempts + 1):
        current_completed = completed_chunk_count(args.worker_dir)
        if current_completed >= total_expected_chunks:
            success_doctor = doctor_snapshot(args.report_dir, f"attempt-{attempt}-already-complete")
            write_monitor_state(
                args.runtime_state,
                {
                    "status": "completed",
                    "attempt": attempt,
                    "doctor_snapshot": str(success_doctor),
                    "completed_chunk_count": current_completed,
                    "total_expected_chunks": total_expected_chunks,
                },
            )
            return 0

        ensure_clone_browser(args.cdp_url)
        time.sleep(args.browser_startup_settle_sec)
        ensure_browser_profile(args.browser_profile, args.cdp_url)
        doctor_path = doctor_snapshot(args.report_dir, f"attempt-{attempt}-preflight")
        prune_result = prune_visible_page_tabs(args.browser_profile, max_page_tabs=0)
        write_monitor_state(
            args.runtime_state,
            {
                "status": "preflight",
                "attempt": attempt,
                "browser_profile": args.browser_profile,
                "cdp_url": args.cdp_url,
                "doctor_snapshot": str(doctor_path),
                "prune_result": prune_result,
                "worker_count": args.worker_count,
                "chunk_size": args.chunk_size,
                "batch_chunk_goal": args.batch_chunk_goal,
                "total_expected_chunks": total_expected_chunks,
                "completed_chunk_count": current_completed,
                "stability_first": True,
            },
        )

        try:
            attempt_result = run_attempt(args, attempt, current_completed, total_expected_chunks)
        except Exception as exc:
            failure_doctor = doctor_snapshot(args.report_dir, f"attempt-{attempt}-failure")
            stop_clone_browser(args.cdp_url)
            cooldown(
                "failure_recovery",
                args.failure_cooldown_min_sec,
                args.failure_cooldown_max_sec,
                args.runtime_state,
            )
            write_monitor_state(
                args.runtime_state,
                {
                    "status": "retrying",
                    "attempt": attempt,
                    "last_error": str(exc),
                    "doctor_snapshot": str(failure_doctor),
                    "completed_chunk_count": completed_chunk_count(args.worker_dir),
                    "total_expected_chunks": total_expected_chunks,
                },
            )
            continue

        partial_workers = partial_worker_names(args.worker_dir)
        bad_workers = worker_names_with_non_ok_metrics(args.worker_dir)
        removed_workers = remove_worker_dirs(args.worker_dir, sorted(set(partial_workers + bad_workers)))
        current_completed = completed_chunk_count(args.worker_dir)

        if attempt_result["outcome"] == "batch_complete":
            batch_doctor = doctor_snapshot(args.report_dir, f"attempt-{attempt}-batch-complete")
            stop_clone_browser(args.cdp_url)
            cooldown(
                "batch_cooldown",
                args.batch_cooldown_min_sec,
                args.batch_cooldown_max_sec,
                args.runtime_state,
            )
            write_monitor_state(
                args.runtime_state,
                {
                    "status": "running",
                    "attempt": attempt,
                    "doctor_snapshot": str(batch_doctor),
                    "completed_chunk_count": current_completed,
                    "total_expected_chunks": total_expected_chunks,
                    "removed_worker_dirs": removed_workers,
                    "stdout_log": str(attempt_result["stdout_log"]),
                    "stderr_log": str(attempt_result["stderr_log"]),
                },
            )
            continue

        returncode = int(attempt_result.get("returncode", 1) or 0)
        if returncode == 0 and current_completed >= total_expected_chunks and not removed_workers:
            success_doctor = doctor_snapshot(args.report_dir, f"attempt-{attempt}-success")
            write_monitor_state(
                args.runtime_state,
                {
                    "status": "completed",
                    "attempt": attempt,
                    "doctor_snapshot": str(success_doctor),
                    "completed_chunk_count": current_completed,
                    "total_expected_chunks": total_expected_chunks,
                    "stdout_log": str(attempt_result["stdout_log"]),
                    "stderr_log": str(attempt_result["stderr_log"]),
                },
            )
            return 0

        failure_doctor = doctor_snapshot(args.report_dir, f"attempt-{attempt}-nonzero-exit")
        stop_clone_browser(args.cdp_url)
        cooldown(
            "retry_after_nonzero_exit",
            args.failure_cooldown_min_sec,
            args.failure_cooldown_max_sec,
            args.runtime_state,
        )
        write_monitor_state(
            args.runtime_state,
            {
                "status": "retrying",
                "attempt": attempt,
                "last_error": f"stage3 runner exited with code {returncode}",
                "doctor_snapshot": str(failure_doctor),
                "completed_chunk_count": current_completed,
                "total_expected_chunks": total_expected_chunks,
                "removed_worker_dirs": removed_workers,
                "stdout_log": str(attempt_result["stdout_log"]),
                "stderr_log": str(attempt_result["stderr_log"]),
            },
        )

    write_monitor_state(
        args.runtime_state,
        {
            "status": "failed",
            "last_error": f"exhausted max attempts ({args.max_attempts})",
            "completed_chunk_count": completed_chunk_count(args.worker_dir),
            "total_expected_chunks": total_expected_chunks,
        },
    )
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
