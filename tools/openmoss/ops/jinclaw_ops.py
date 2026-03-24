#!/usr/bin/env python3

from __future__ import annotations

import argparse
import json
import subprocess
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List


WORKSPACE_ROOT = Path("/Users/mac_claw/.openclaw/workspace")
OPENMOSS_ROOT = WORKSPACE_ROOT / "tools/openmoss"
AUTONOMY_ROOT = OPENMOSS_ROOT / "autonomy"
CONTROL_CENTER_ROOT = OPENMOSS_ROOT / "control_center"
RUNTIME_ROOT = OPENMOSS_ROOT / "runtime"
SELFHEAL_STATE_PATH = RUNTIME_ROOT / "selfheal/state.json"
UPSTREAM_WATCH_STATE_PATH = RUNTIME_ROOT / "upstream_watch/state.json"
UPSTREAM_WATCH_REPORT_PATH = RUNTIME_ROOT / "upstream_watch/reports/latest-report.md"
BRAIN_ROUTES_ROOT = RUNTIME_ROOT / "control_center/brain_routes"
MAIN_LINK_PATH = RUNTIME_ROOT / "autonomy/links/openclaw-main__main.json"
UPSTREAM_WATCH_SCRIPT = OPENMOSS_ROOT / "upstream_watch/watch_updates.py"
LAUNCH_AGENTS = {
    "selfheal": "ai.openclaw.selfheal",
    "brain_enforcer": "ai.openclaw.brain-enforcer",
    "autonomy_runtime": "ai.jinclaw.autonomy-runtime",
    "upstream_watch": "ai.jinclaw.upstream-watch",
}


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def utc_now_iso() -> str:
    return utc_now().isoformat()


def run_cmd(command: List[str], timeout: int = 20) -> Dict[str, Any]:
    try:
        proc = subprocess.run(command, capture_output=True, text=True, check=False, timeout=timeout)
    except subprocess.TimeoutExpired as exc:
        return {
            "ok": False,
            "returncode": None,
            "stdout": (exc.stdout or "")[-4000:],
            "stderr": f"timeout after {timeout}s",
        }
    return {
        "ok": proc.returncode == 0,
        "returncode": proc.returncode,
        "stdout": (proc.stdout or "")[-12000:],
        "stderr": (proc.stderr or "")[-4000:],
    }


def parse_json_output(result: Dict[str, Any]) -> Dict[str, Any]:
    if not result.get("ok"):
        return {}
    try:
        return json.loads(result.get("stdout") or "{}")
    except json.JSONDecodeError:
        return {}


def read_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    return json.loads(path.read_text(encoding="utf-8"))


def parse_iso(value: str) -> datetime | None:
    if not value:
        return None
    normalized = value.replace("Z", "+00:00")
    try:
        dt = datetime.fromisoformat(normalized)
    except ValueError:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def is_recent(value: str, max_age_minutes: int) -> bool:
    dt = parse_iso(value)
    if not dt:
        return False
    return utc_now() - dt <= timedelta(minutes=max_age_minutes)


def git_summary() -> Dict[str, Any]:
    branch = run_cmd(["git", "-C", str(WORKSPACE_ROOT), "branch", "--show-current"])
    head = run_cmd(["git", "-C", str(WORKSPACE_ROOT), "rev-parse", "HEAD"])
    remote = run_cmd(["git", "-C", str(WORKSPACE_ROOT), "remote", "-v"])
    status = run_cmd(["git", "-C", str(WORKSPACE_ROOT), "status", "--short"])
    return {
        "branch": (branch.get("stdout") or "").strip(),
        "head": (head.get("stdout") or "").strip(),
        "remote": (remote.get("stdout") or "").strip(),
        "dirty": bool((status.get("stdout") or "").strip()),
        "status_lines": [line for line in (status.get("stdout") or "").splitlines() if line.strip()],
    }


def gateway_summary() -> Dict[str, Any]:
    status_result = run_cmd(["openclaw", "gateway", "status", "--json"])
    health_result = run_cmd(["openclaw", "gateway", "health", "--json"])
    status = parse_json_output(status_result)
    health = parse_json_output(health_result)
    service_runtime = status.get("service", {}).get("runtime", {})
    rpc = status.get("rpc", {})
    telegram = health.get("channels", {}).get("telegram", {})
    return {
        "service_running": service_runtime.get("status") == "running",
        "rpc_ok": bool(rpc.get("ok")),
        "pid": service_runtime.get("pid"),
        "telegram_configured": bool(telegram.get("configured")),
        "telegram_running": bool(telegram.get("running")),
        "status_result": status_result,
        "health_result": health_result,
    }


def launch_agent_summary() -> Dict[str, Any]:
    agents: Dict[str, Any] = {}
    for key, label in LAUNCH_AGENTS.items():
        result = run_cmd(["launchctl", "print", f"gui/{os_uid()}/{label}"], timeout=20)
        agents[key] = {
            "label": label,
            "loaded": result.get("ok", False),
            "returncode": result.get("returncode"),
        }
    return agents


def os_uid() -> str:
    result = run_cmd(["id", "-u"], timeout=5)
    return (result.get("stdout") or "").strip() or "0"


def runtime_summary() -> Dict[str, Any]:
    selfheal_state = read_json(SELFHEAL_STATE_PATH, {})
    upstream_watch_state = read_json(UPSTREAM_WATCH_STATE_PATH, {})
    brain_route_count = len(list(BRAIN_ROUTES_ROOT.rglob("*.json"))) if BRAIN_ROUTES_ROOT.exists() else 0
    main_link = read_json(MAIN_LINK_PATH, {})
    return {
        "selfheal_state_exists": SELFHEAL_STATE_PATH.exists(),
        "selfheal_recent": is_recent(selfheal_state.get("last_check_at", ""), 15),
        "selfheal_last_status": selfheal_state.get("last_status", ""),
        "upstream_watch_state_exists": UPSTREAM_WATCH_STATE_PATH.exists(),
        "upstream_watch_recent": is_recent(upstream_watch_state.get("checked_at", ""), 24 * 60 + 30),
        "upstream_watch_report_exists": UPSTREAM_WATCH_REPORT_PATH.exists(),
        "brain_route_count": brain_route_count,
        "main_link_exists": MAIN_LINK_PATH.exists(),
        "main_link_task": main_link.get("task_id", ""),
    }


def status_payload() -> Dict[str, Any]:
    return {
        "checked_at": utc_now_iso(),
        "workspace": str(WORKSPACE_ROOT),
        "git": git_summary(),
        "gateway": gateway_summary(),
        "launch_agents": launch_agent_summary(),
        "runtime": runtime_summary(),
    }


def doctor_payload() -> Dict[str, Any]:
    payload = status_payload()
    issues: List[str] = []
    warnings: List[str] = []

    if not payload["gateway"]["service_running"]:
        issues.append("openclaw_gateway_not_running")
    if not payload["gateway"]["rpc_ok"]:
        issues.append("openclaw_gateway_rpc_unhealthy")

    for key, agent in payload["launch_agents"].items():
        if not agent["loaded"]:
            issues.append(f"launch_agent_missing:{key}")

    runtime = payload["runtime"]
    if not runtime["selfheal_state_exists"]:
        issues.append("selfheal_state_missing")
    elif not runtime["selfheal_recent"]:
        warnings.append("selfheal_not_recent")

    if not runtime["upstream_watch_state_exists"]:
        issues.append("upstream_watch_state_missing")
    elif not runtime["upstream_watch_recent"]:
        warnings.append("upstream_watch_not_recent")

    if not runtime["main_link_exists"]:
        issues.append("main_session_link_missing")
    if runtime["brain_route_count"] == 0:
        warnings.append("no_brain_routes_recorded_yet")

    if not (CONTROL_CENTER_ROOT / "brain_router.py").exists():
        issues.append("brain_router_missing")
    if not (CONTROL_CENTER_ROOT / "brain_enforcer.py").exists():
        issues.append("brain_enforcer_missing")
    if not (AUTONOMY_ROOT / "runtime_service.py").exists():
        issues.append("autonomy_runtime_missing")

    payload["issues"] = issues
    payload["warnings"] = warnings
    payload["ok"] = not issues
    return payload


def upgrade_check_payload() -> Dict[str, Any]:
    watch_run = run_cmd(["python3", str(UPSTREAM_WATCH_SCRIPT), "--once"], timeout=60)
    doctor = doctor_payload()
    upstream_watch_state = read_json(UPSTREAM_WATCH_STATE_PATH, {})
    changed: List[Dict[str, Any]] = []
    for repo_id, snapshot in (upstream_watch_state.get("repos") or {}).items():
        changed.append(
            {
                "id": repo_id,
                "repo": snapshot.get("repo", ""),
                "latest_release": (snapshot.get("latest_release") or {}).get("tag_name", ""),
                "pushed_at": snapshot.get("pushed_at", ""),
            }
        )
    return {
        "checked_at": utc_now_iso(),
        "watch_run": {
            "ok": watch_run.get("ok"),
            "returncode": watch_run.get("returncode"),
            "stdout": watch_run.get("stdout"),
            "stderr": watch_run.get("stderr"),
        },
        "doctor": doctor,
        "git": git_summary(),
        "upstream_report_path": str(UPSTREAM_WATCH_REPORT_PATH),
        "tracked_upstreams": changed,
    }


def print_payload(payload: Dict[str, Any]) -> None:
    print(json.dumps(payload, ensure_ascii=False, indent=2))


def main() -> int:
    parser = argparse.ArgumentParser(description="JinClaw local ops commands")
    parser.add_argument("command", choices=["status", "doctor", "upgrade-check"])
    args = parser.parse_args()

    if args.command == "status":
        print_payload(status_payload())
        return 0
    if args.command == "doctor":
        payload = doctor_payload()
        print_payload(payload)
        return 0 if payload["ok"] else 1
    payload = upgrade_check_payload()
    print_payload(payload)
    return 0 if payload["doctor"]["ok"] and payload["watch_run"]["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
