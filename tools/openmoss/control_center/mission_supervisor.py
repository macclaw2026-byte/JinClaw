#!/usr/bin/env python3

from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

from paths import CONTROL_CENTER_RUNTIME_ROOT
from progress_evidence import build_progress_evidence
from response_policy_engine import build_supervisor_status_text
from task_receipt_engine import emit_route_receipt

AUTONOMY_DIR = Path("/Users/mac_claw/.openclaw/workspace/tools/openmoss/autonomy")
if str(AUTONOMY_DIR) not in sys.path:
    sys.path.insert(0, str(AUTONOMY_DIR))

from manager import LINKS_ROOT, TASKS_ROOT, load_state, log_event, save_state


SUPERVISOR_ROOT = CONTROL_CENTER_RUNTIME_ROOT / "supervisor"


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _write_json(path: Path, payload: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _apply_repair(task_id: str, evidence: Dict[str, Any]) -> Dict[str, Any]:
    state = load_state(task_id)
    reason = str(evidence.get("reason", "unknown"))
    repaired = False
    new_next_action = str(state.next_action)
    if evidence.get("progress_state") in {"idle_without_execution", "stalled_waiting_external", "stalled_verification"}:
        state.status = "planning"
        state.blockers = []
        state.metadata.pop("active_execution", None)
        state.metadata.pop("last_dispatched_marker", None)
        state.metadata.pop("last_dispatch_at", None)
        if state.current_stage:
            state.next_action = f"start_stage:{state.current_stage}"
        else:
            state.next_action = "initialize"
        state.last_update_at = _utc_now_iso()
        save_state(state)
        log_event(task_id, "mission_supervisor_restarted_execution", reason=reason)
        repaired = True
        new_next_action = state.next_action
    return {
        "task_id": task_id,
        "repaired": repaired,
        "reason": reason,
        "next_action": new_next_action,
    }


def supervise_task(task_id: str, *, stale_after_seconds: int = 300, escalation_after_seconds: int = 900) -> Dict[str, Any]:
    evidence = build_progress_evidence(task_id, stale_after_seconds=stale_after_seconds)
    repair = _apply_repair(task_id, evidence) if evidence.get("needs_intervention") else {"task_id": task_id, "repaired": False, "reason": "healthy"}
    report: Dict[str, Any] = {"evidence": evidence, "repair": repair}
    if evidence.get("needs_intervention") and float(evidence.get("idle_seconds", 0)) >= float(escalation_after_seconds):
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
                    "authoritative_summary": build_supervisor_status_text(task_id, evidence, repair),
                },
            }
            receipt = emit_route_receipt(
                route,
                provider=str(payload.get("provider", "openclaw-main")),
                conversation_id=str(payload.get("conversation_id", "")),
                session_key=str(payload.get("session_key", "")),
            )
            report["receipt"] = receipt
            log_event(task_id, "mission_supervisor_escalated_to_user", evidence=evidence, repair=repair)
            break
    return report


def run_mission_supervisor(*, stale_after_seconds: int = 300, escalation_after_seconds: int = 900) -> Dict[str, Any]:
    reports: List[Dict[str, Any]] = []
    if not TASKS_ROOT.exists():
        return {"checked_at": _utc_now_iso(), "reports": reports}
    for task_root in sorted(TASKS_ROOT.iterdir()):
        if not task_root.is_dir():
            continue
        task_id = task_root.name
        reports.append(
            supervise_task(
                task_id,
                stale_after_seconds=stale_after_seconds,
                escalation_after_seconds=escalation_after_seconds,
            )
        )
    result = {"checked_at": _utc_now_iso(), "reports": reports}
    _write_json(SUPERVISOR_ROOT / "last_run.json", result)
    return result
