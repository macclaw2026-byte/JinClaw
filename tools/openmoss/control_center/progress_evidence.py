#!/usr/bin/env python3

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

from paths import OPENMOSS_ROOT
from run_liveness_verifier import build_run_liveness


AUTONOMY_TASKS_ROOT = OPENMOSS_ROOT / "runtime/autonomy/tasks"


def _read_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return default


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
    # For poll loops, last_update_at mostly reflects bookkeeping churn rather than
    # real forward motion. We should treat "time since last meaningful progress"
    # as authoritative so the supervisor/doctor can detect stale poll_run tasks.
    if status == "waiting_external" and next_action.startswith("poll_run:"):
        return progress_age
    # In normal states, any real stage progress or state update can count as
    # recent movement, so use the fresher of the two timestamps.
    return min(progress_age, update_age)


def _recent_events(task_id: str, limit: int = 12) -> List[Dict[str, Any]]:
    events_path = AUTONOMY_TASKS_ROOT / task_id / "events.jsonl"
    if not events_path.exists():
        return []
    rows: List[Dict[str, Any]] = []
    for line in events_path.read_text(encoding="utf-8", errors="ignore").splitlines()[-limit:]:
        try:
            rows.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return rows


def build_progress_evidence(task_id: str, *, stale_after_seconds: int = 300) -> Dict[str, Any]:
    state = _read_json(AUTONOMY_TASKS_ROOT / task_id / "state.json", {})
    contract = _read_json(AUTONOMY_TASKS_ROOT / task_id / "contract.json", {})
    status = str(state.get("status", "unknown"))
    current_stage = str(state.get("current_stage", ""))
    next_action = str(state.get("next_action", ""))
    metadata = state.get("metadata", {}) or {}
    active_execution = metadata.get("active_execution", {}) or {}
    has_active_execution = bool(active_execution.get("run_id"))
    last_progress_at = str(state.get("last_progress_at", ""))
    last_update_at = str(state.get("last_update_at", ""))
    idle_seconds = _progress_age_seconds(
        status=status,
        next_action=next_action,
        last_progress_at=last_progress_at,
        last_update_at=last_update_at,
    )
    business_outcome = metadata.get("business_outcome", {}) or {}
    events = _recent_events(task_id)
    event_types = [str(item.get("type", "")) for item in events if str(item.get("type", "")).strip()]
    run_liveness = build_run_liveness(task_id)

    evidence = {
        "task_id": task_id,
        "goal": contract.get("user_goal", ""),
        "status": status,
        "current_stage": current_stage,
        "next_action": next_action,
        "has_active_execution": has_active_execution,
        "active_execution_run_id": str(active_execution.get("run_id", "")),
        "active_execution_stage_name": str(active_execution.get("stage_name", "")),
        "idle_seconds": idle_seconds,
        "stale_after_seconds": stale_after_seconds,
        "recent_event_types": event_types,
        "business_goal_satisfied": business_outcome.get("goal_satisfied") is True,
        "user_visible_result_confirmed": business_outcome.get("user_visible_result_confirmed") is True,
        "run_liveness": run_liveness,
        "progress_state": "healthy",
        "needs_intervention": False,
        "reason": "healthy",
    }
    waiting_external = metadata.get("waiting_external", {}) or {}
    waiting_stage_name = str(waiting_external.get("stage_name", ""))
    waiting_run_id = str(waiting_external.get("run_id", ""))
    active_stage_name = str(active_execution.get("stage_name", ""))
    active_run_id = str(active_execution.get("run_id", ""))

    if status == "waiting_external" and (
        (waiting_stage_name and current_stage and waiting_stage_name != current_stage)
        or (waiting_stage_name and active_stage_name and waiting_stage_name != active_stage_name)
        or (waiting_run_id and active_run_id and waiting_run_id != active_run_id)
    ):
        evidence["progress_state"] = "waiting_external_state_mismatch"
        evidence["needs_intervention"] = True
        evidence["reason"] = "waiting_external_metadata_mismatch"
        return evidence

    if status in {"completed", "failed"}:
        evidence["progress_state"] = "terminal"
        evidence["reason"] = status
        return evidence

    if status == "waiting_external" and not has_active_execution:
        evidence["progress_state"] = "waiting_external_without_execution"
        evidence["needs_intervention"] = True
        evidence["reason"] = "waiting_external_without_active_execution"
        return evidence

    if status == "waiting_external" and next_action.startswith("poll_run:") and idle_seconds >= stale_after_seconds:
        evidence["progress_state"] = "stalled_waiting_external"
        evidence["needs_intervention"] = True
        evidence["reason"] = "stale_poll_run_without_recent_progress"
        return evidence

    if status in {"planning", "running", "recovering"} and not has_active_execution and idle_seconds >= stale_after_seconds:
        evidence["progress_state"] = "idle_without_execution"
        evidence["needs_intervention"] = True
        evidence["reason"] = "no_active_execution_and_no_recent_progress"
        return evidence

    if status == "blocked":
        evidence["progress_state"] = "blocked"
        evidence["needs_intervention"] = True
        evidence["reason"] = f"blocked:{next_action or 'unknown'}"
        return evidence

    if status == "verifying" and idle_seconds >= stale_after_seconds:
        evidence["progress_state"] = "stalled_verification"
        evidence["needs_intervention"] = True
        evidence["reason"] = "verification_not_advancing"
        return evidence

    return evidence
