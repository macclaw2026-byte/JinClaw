#!/usr/bin/env python3

from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict

from paths import CONTROL_CENTER_RUNTIME_ROOT
from mission_supervisor import run_mission_supervisor
from response_policy_engine import build_supervisor_status_text
from task_receipt_engine import emit_route_receipt

AUTONOMY_DIR = Path("/Users/mac_claw/.openclaw/workspace/tools/openmoss/autonomy")
if str(AUTONOMY_DIR) not in sys.path:
    sys.path.insert(0, str(AUTONOMY_DIR))

from manager import LINKS_ROOT, TASKS_ROOT, load_state, log_event, save_state

DOCTOR_ROOT = CONTROL_CENTER_RUNTIME_ROOT / "doctor"


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _write_json(path: Path, payload: Dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _seconds_since(iso_text: str) -> float:
    if not iso_text:
        return 10**9
    try:
        dt = datetime.fromisoformat(str(iso_text).replace("Z", "+00:00"))
    except ValueError:
        return 10**9
    return max(0.0, (datetime.now(timezone.utc) - dt).total_seconds())


def _progress_age_seconds(*, status: str, next_action: str, last_progress_at: str, last_update_at: str) -> float:
    progress_age = _seconds_since(last_progress_at)
    update_age = _seconds_since(last_update_at)
    if status == "waiting_external" and next_action.startswith("poll_run:"):
        return progress_age
    return min(progress_age, update_age)


def diagnose_task(task_id: str, *, idle_after_seconds: int = 180) -> Dict[str, object]:
    state = load_state(task_id)
    age = _progress_age_seconds(
        status=state.status,
        next_action=state.next_action,
        last_progress_at=state.last_progress_at,
        last_update_at=state.last_update_at,
    )
    active_execution = state.metadata.get("active_execution", {}) or {}
    has_active_execution = bool(active_execution.get("run_id"))
    diagnosis = {
        "task_id": task_id,
        "status": state.status,
        "current_stage": state.current_stage,
        "next_action": state.next_action,
        "idle_seconds": age,
        "has_active_execution": has_active_execution,
        "stuck": False,
        "reason": "healthy_or_recently_updated",
    }
    if state.status in {"completed", "failed"}:
        diagnosis["reason"] = "terminal"
        return diagnosis
    if age < idle_after_seconds:
        return diagnosis
    if not has_active_execution and state.status in {"planning", "running", "recovering"}:
        diagnosis["stuck"] = True
        diagnosis["reason"] = "idle_without_active_execution"
    elif state.status == "blocked":
        diagnosis["stuck"] = True
        diagnosis["reason"] = f"blocked:{state.next_action or 'unknown'}"
    elif state.next_action.startswith("poll_run:") and age >= idle_after_seconds:
        diagnosis["stuck"] = True
        diagnosis["reason"] = "stale_waiting_external"
    return diagnosis


def repair_task_if_possible(task_id: str, diagnosis: Dict[str, object]) -> Dict[str, object]:
    if not diagnosis.get("stuck"):
        return {"task_id": task_id, "repaired": False, "reason": "not_stuck"}
    state = load_state(task_id)
    if diagnosis.get("reason") == "idle_without_active_execution":
        state.status = "planning"
        state.blockers = []
        state.metadata.pop("active_execution", None)
        state.metadata.pop("last_dispatched_marker", None)
        state.metadata.pop("last_dispatch_at", None)
        state.next_action = f"start_stage:{state.current_stage}" if state.current_stage else "initialize"
        state.last_update_at = _utc_now_iso()
        save_state(state)
        log_event(task_id, "system_doctor_repaired_idle_execution_gap", diagnosis=diagnosis)
        return {"task_id": task_id, "repaired": True, "reason": "restarted_stage_execution"}
    if diagnosis.get("reason") == "stale_waiting_external":
        state.status = "planning"
        state.blockers = []
        state.metadata.pop("active_execution", None)
        state.metadata.pop("last_dispatched_marker", None)
        state.metadata.pop("last_dispatch_at", None)
        state.next_action = f"start_stage:{state.current_stage}" if state.current_stage else "initialize"
        state.last_update_at = _utc_now_iso()
        save_state(state)
        log_event(task_id, "system_doctor_repaired_stale_waiting_external", diagnosis=diagnosis)
        return {"task_id": task_id, "repaired": True, "reason": "restarted_after_stale_waiting_external"}
    return {"task_id": task_id, "repaired": False, "reason": diagnosis.get("reason", "unhandled")}


def run_system_doctor(*, idle_after_seconds: int = 180, escalation_after_seconds: int = 600) -> Dict[str, object]:
    reports = []
    if not TASKS_ROOT.exists():
        return {"checked_at": _utc_now_iso(), "reports": reports}
    for task_root in sorted(TASKS_ROOT.iterdir()):
        if not task_root.is_dir():
            continue
        task_id = task_root.name
        diagnosis = diagnose_task(task_id, idle_after_seconds=idle_after_seconds)
        repair = repair_task_if_possible(task_id, diagnosis)
        report = {"diagnosis": diagnosis, "repair": repair}
        if diagnosis.get("stuck") and diagnosis.get("idle_seconds", 0) >= escalation_after_seconds:
            for link_path in LINKS_ROOT.glob("*.json"):
                try:
                    payload = json.loads(link_path.read_text(encoding="utf-8"))
                except (OSError, json.JSONDecodeError):
                    continue
                if payload.get("task_id") != task_id:
                    continue
                route = {
                    "mode": "doctor_diagnostic",
                    "task_id": task_id,
                    "goal": payload.get("goal", ""),
                    "authoritative_task_status": {
                        "authoritative_summary": build_supervisor_status_text(task_id, diagnosis, repair),
                    },
                }
                receipt = emit_route_receipt(
                    route,
                    provider=str(payload.get("provider", "openclaw-main")),
                    conversation_id=str(payload.get("conversation_id", "")),
                    session_key=str(payload.get("session_key", "")),
                )
                report["receipt"] = receipt
                log_event(task_id, "system_doctor_escalated_to_user", diagnosis=diagnosis, repair=repair)
                break
        reports.append(report)
    supervisor = run_mission_supervisor(
        stale_after_seconds=max(120, idle_after_seconds),
        escalation_after_seconds=max(300, escalation_after_seconds),
    )
    result = {"checked_at": _utc_now_iso(), "reports": reports, "mission_supervisor": supervisor}
    _write_json(DOCTOR_ROOT / "last_run.json", result)
    return result
