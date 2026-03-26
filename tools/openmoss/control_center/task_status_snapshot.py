#!/usr/bin/env python3

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List

from canonical_active_task import resolve_canonical_active_task
from paths import BROWSER_SIGNALS_ROOT, OPENMOSS_ROOT, TASK_STATUS_ROOT
from run_liveness_verifier import build_run_liveness
from task_lifecycle import classify_task_lifecycle

AUTONOMY_DIR = OPENMOSS_ROOT / "autonomy"
if str(AUTONOMY_DIR) not in __import__("sys").path:
    __import__("sys").path.insert(0, str(AUTONOMY_DIR))

from learning_engine import get_error_recurrence, load_task_summary
from promotion_engine import resolve_rule_for_error


AUTONOMY_TASKS_ROOT = OPENMOSS_ROOT / "runtime/autonomy/tasks"


def _read_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return default


def _write_json(path: Path, payload: Dict[str, Any]) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return str(path)


def _load_task_state(task_id: str) -> Dict[str, Any]:
    return _read_json(AUTONOMY_TASKS_ROOT / task_id / "state.json", {})


def _load_task_contract(task_id: str) -> Dict[str, Any]:
    return _read_json(AUTONOMY_TASKS_ROOT / task_id / "contract.json", {})


def _load_browser_signals(task_id: str) -> Dict[str, Any]:
    return _read_json(BROWSER_SIGNALS_ROOT / f"{task_id}.json", {})


def _recent_events(task_id: str, limit: int = 8) -> List[Dict[str, Any]]:
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


def _build_authoritative_summary(task_id: str, state: Dict[str, Any], browser_signals: Dict[str, Any]) -> str:
    business = state.get("metadata", {}).get("business_outcome", {}) or {}
    status = str(state.get("status", ""))
    current_stage = str(state.get("current_stage", ""))
    next_action = str(state.get("next_action", ""))
    diagnosis = str(browser_signals.get("diagnosis", "none"))
    if business.get("goal_satisfied") is True and business.get("user_visible_result_confirmed") is True:
        return (
            f"Authoritative task state says {task_id} is completed. "
            f"Business outcome is confirmed: {business.get('proof_summary', '')}"
        ).strip()
    if diagnosis and diagnosis != "none":
        return (
            f"Authoritative task state says {task_id} is {status or 'unknown'} "
            f"at stage {current_stage or 'none'} with next action {next_action or 'none'}. "
            f"Latest browser diagnosis is {diagnosis}."
        ).strip()
    return (
        f"Authoritative task state says {task_id} is {status or 'unknown'} "
        f"at stage {current_stage or 'none'} with next action {next_action or 'none'}."
    ).strip()


def build_task_status_snapshot(task_id: str) -> Dict[str, Any]:
    canonical = resolve_canonical_active_task(task_id)
    canonical_task_id = str(canonical.get("canonical_task_id", task_id)).strip() or task_id
    state = _load_task_state(canonical_task_id)
    contract = _load_task_contract(canonical_task_id)
    browser_signals = _load_browser_signals(canonical_task_id)
    business = state.get("metadata", {}).get("business_outcome", {}) or {}
    summary = load_task_summary(canonical_task_id)
    last_failure = summary.get("last_failure", {}) or {}
    last_failure_error = str(last_failure.get("error", "")).strip()
    snapshot: Dict[str, Any] = {
        "requested_task_id": task_id,
        "task_id": canonical_task_id,
        "canonical_task": canonical,
        "goal": contract.get("user_goal", ""),
        "status": state.get("status", "unknown"),
        "current_stage": state.get("current_stage", ""),
        "next_action": state.get("next_action", ""),
        "blockers": state.get("blockers", []),
        "business_outcome": business,
        "lifecycle": classify_task_lifecycle(state),
        "memory": {
            "task_summary": summary,
            "last_failure": last_failure,
            "error_recurrence": get_error_recurrence(last_failure_error) if last_failure_error else {"count": 0, "tasks": []},
            "promoted_rule": resolve_rule_for_error(last_failure_error) if last_failure_error else None,
        },
        "run_liveness": build_run_liveness(canonical_task_id),
        "browser_signals": {
            "diagnosis": browser_signals.get("diagnosis", "none"),
            "recommended_action": browser_signals.get("recommended_action", "continue_current_plan"),
            "live_product_image_count": browser_signals.get("live_product_image_count"),
            "save_request_succeeded": browser_signals.get("save_request_succeeded"),
            "live_last_images": browser_signals.get("live_last_images", []),
        },
        "recent_events": _recent_events(canonical_task_id),
    }
    snapshot["authoritative_summary"] = _build_authoritative_summary(canonical_task_id, state, browser_signals)
    snapshot["reply_contract"] = {
        "must_use_authoritative_snapshot": True,
        "must_prefer_task_state_over_chat_memory": True,
        "forbid_outdated_failure_claims_when_business_outcome_confirmed": bool(
            business.get("goal_satisfied") and business.get("user_visible_result_confirmed")
        ),
    }
    snapshot["snapshot_path"] = _write_json(TASK_STATUS_ROOT / f"{canonical_task_id}.json", snapshot)
    return snapshot


def main() -> int:
    import argparse

    parser = argparse.ArgumentParser(description="Build an authoritative task status snapshot for response-time use")
    parser.add_argument("--task-id", required=True)
    args = parser.parse_args()
    print(json.dumps(build_task_status_snapshot(args.task_id), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
