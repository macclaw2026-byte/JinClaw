#!/usr/bin/env python3

from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

from action_executor import dispatch_stage, poll_active_execution
from learning_engine import get_error_recurrence
from manager import TASKS_ROOT, advance_execute_subtask, apply_recovery, build_args, checkpoint_task, complete_stage_internal, load_contract, load_state, log_event, run_once, save_state, verify_task
from promotion_engine import promote_recurring_errors

CONTROL_CENTER_DIR = Path("/Users/mac_claw/.openclaw/workspace/tools/openmoss/control_center")
if str(CONTROL_CENTER_DIR) not in sys.path:
    sys.path.insert(0, str(CONTROL_CENTER_DIR))

from mission_loop import run_mission_cycle


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _mark_binding_required(task_id: str, reason: str) -> None:
    state = load_state(task_id)
    state.status = "blocked"
    state.blockers = [reason]
    state.next_action = "bind_session_link"
    state.last_update_at = utc_now_iso()
    save_state(state)
    log_event(task_id, "binding_required", reason=reason)


def _apply_control_center_decision(task_id: str, state, mission_cycle: dict) -> dict | None:
    decision = mission_cycle.get("next_decision", {})
    action = str(decision.get("action", ""))
    state.metadata["last_control_center_decision"] = decision
    if not decision.get("auto_safe", False):
        state.last_update_at = utc_now_iso()
        save_state(state)
        return None
    if action == "await_or_request_approval":
        state.status = "blocked"
        state.next_action = "await_approval_or_contract_fix"
        state.last_update_at = utc_now_iso()
        save_state(state)
        log_event(task_id, "control_center_waiting_for_approval", pending=decision.get("pending_approvals", []))
        return {
            "task_id": task_id,
            "status": state.status,
            "current_stage": state.current_stage,
            "next_action": state.next_action,
            "action": "awaiting_approval_by_control_center",
            "mission_cycle": mission_cycle,
        }
    if action == "bind_session_link":
        state.status = "blocked"
        state.next_action = "bind_session_link"
        state.last_update_at = utc_now_iso()
        save_state(state)
        log_event(task_id, "control_center_binding_required")
        return {
            "task_id": task_id,
            "status": state.status,
            "current_stage": state.current_stage,
            "next_action": state.next_action,
            "action": "awaiting_session_binding",
            "mission_cycle": mission_cycle,
        }
    if action == "prove_necessity_before_switching":
        state.status = "blocked"
        state.next_action = "prove_necessity_before_switching"
        state.blockers = ["higher-risk plan not yet justified"]
        state.last_update_at = utc_now_iso()
        save_state(state)
        log_event(task_id, "control_center_requires_necessity_proof", necessity=mission_cycle.get("necessity_proof", {}))
        return {
            "task_id": task_id,
            "status": state.status,
            "current_stage": state.current_stage,
            "next_action": state.next_action,
            "action": "awaiting_necessity_proof",
            "mission_cycle": mission_cycle,
        }
    if action == "request_authorized_session":
        state.status = "blocked"
        state.next_action = "request_authorized_session"
        state.blockers = ["authorized session is required before compliant continuation"]
        state.last_update_at = utc_now_iso()
        save_state(state)
        log_event(task_id, "control_center_requires_authorized_session", session_plan=mission_cycle.get("authorized_session", {}))
        return {
            "task_id": task_id,
            "status": state.status,
            "current_stage": state.current_stage,
            "next_action": state.next_action,
            "action": "awaiting_authorized_session",
            "mission_cycle": mission_cycle,
        }
    if action == "await_human_verification_checkpoint":
        state.status = "blocked"
        state.next_action = "await_human_verification_checkpoint"
        state.blockers = ["human verification checkpoint must be completed before continuation"]
        state.last_update_at = utc_now_iso()
        save_state(state)
        log_event(task_id, "control_center_requires_human_checkpoint", checkpoint=mission_cycle.get("human_checkpoint", {}))
        return {
            "task_id": task_id,
            "status": state.status,
            "current_stage": state.current_stage,
            "next_action": state.next_action,
            "action": "awaiting_human_checkpoint",
            "mission_cycle": mission_cycle,
        }
    if action.startswith("advance_subtask:"):
        subtask_id = action.split(":", 1)[1]
        result = advance_execute_subtask(task_id, subtask_id, summary=f"HTN subtask focus advanced to {subtask_id}")
        state = load_state(task_id)
        state.status = "planning"
        state.current_stage = "execute"
        state.next_action = "start_stage:execute"
        state.last_update_at = utc_now_iso()
        save_state(state)
        log_event(task_id, "control_center_auto_advance_subtask", subtask_id=subtask_id)
        return {
            "task_id": task_id,
            "status": state.status,
            "current_stage": state.current_stage,
            "next_action": state.next_action,
            "action": "advanced_execute_subtask",
            "subtask": result,
            "mission_cycle": mission_cycle,
        }
    if action.startswith("advance_stage:") and state.status in {"planning", "blocked"}:
        target_stage = action.split(":", 1)[1]
        state.status = "planning"
        state.current_stage = target_stage
        state.blockers = []
        state.next_action = f"start_stage:{target_stage}"
        state.last_update_at = utc_now_iso()
        save_state(state)
        log_event(task_id, "control_center_auto_advance_stage", stage=target_stage, reason=decision.get("reason", ""))
        return None
    state.last_update_at = utc_now_iso()
    save_state(state)
    return None


def process_task(task_id: str, stale_after_seconds: int) -> dict:
    contract = load_contract(task_id)
    state = load_state(task_id)
    mission_cycle = run_mission_cycle(task_id, contract.to_dict(), state.to_dict())
    control_center_result = _apply_control_center_decision(task_id, state, mission_cycle)
    state = load_state(task_id)
    if control_center_result and control_center_result.get("action") == "advanced_execute_subtask":
        return control_center_result
    if control_center_result and state.status not in {"planning", "running"}:
        return control_center_result
    if state.status in {"completed", "failed"}:
        return {"task_id": task_id, "status": state.status, "action": "skipped_terminal", "mission_cycle": mission_cycle}

    if state.last_update_at:
        updated_at = datetime.fromisoformat(state.last_update_at.replace("Z", "+00:00"))
        age = (datetime.now(timezone.utc) - updated_at).total_seconds()
    else:
        age = 0

    if age >= stale_after_seconds:
        checkpoint_task(build_args(task_id=task_id))
        log_event(task_id, "stale_task_detected", age_seconds=age, detected_at=utc_now_iso())

    if state.status == "recovering":
        if state.next_action == "satisfy_stage_contract_preflight":
            state.status = "blocked"
            state.next_action = "await_approval_or_contract_fix"
            state.last_update_at = utc_now_iso()
            save_state(state)
            log_event(task_id, "preflight_block_requires_review", next_action=state.next_action)
            return {
                "task_id": task_id,
                "status": state.status,
                "current_stage": state.current_stage,
                "next_action": state.next_action,
                "action": "awaiting_preflight_resolution",
                "mission_cycle": mission_cycle,
            }
        if state.next_action == "prove_necessity_before_switching":
            log_event(task_id, "recovery_waiting_for_necessity_proof")
            return {
                "task_id": task_id,
                "status": state.status,
                "current_stage": state.current_stage,
                "next_action": state.next_action,
                "action": "awaiting_necessity_proof",
                "mission_cycle": mission_cycle,
            }
        if state.next_action == "request_authorized_session":
            log_event(task_id, "recovery_waiting_for_authorized_session")
            return {
                "task_id": task_id,
                "status": state.status,
                "current_stage": state.current_stage,
                "next_action": state.next_action,
                "action": "awaiting_authorized_session",
                "mission_cycle": mission_cycle,
            }
        if state.next_action == "await_human_verification_checkpoint":
            log_event(task_id, "recovery_waiting_for_human_checkpoint")
            return {
                "task_id": task_id,
                "status": state.status,
                "current_stage": state.current_stage,
                "next_action": state.next_action,
                "action": "awaiting_human_checkpoint",
                "mission_cycle": mission_cycle,
            }
        blocker_text = " ".join(state.blockers)
        recurrence = get_error_recurrence(blocker_text) if blocker_text else {"count": 0}
        log_event(task_id, "recovery_watchdog_review", blocker=blocker_text, recurrence=recurrence)
        apply_recovery(build_args(task_id=task_id, stage="", action=""))
        state = load_state(task_id)
        return {
            "task_id": task_id,
            "status": state.status,
            "current_stage": state.current_stage,
            "next_action": state.next_action,
            "action": "auto_recovery_attempted",
            "recurrence_count": recurrence.get("count", 0),
            "mission_cycle": mission_cycle,
        }

    if state.status == "waiting_external" or state.next_action.startswith("poll_run:"):
        poll = poll_active_execution(task_id)
        state = load_state(task_id)
        return {
            "task_id": task_id,
            "status": state.status,
            "current_stage": state.current_stage,
            "next_action": state.next_action,
            "action": "execution_polled",
            "poll": poll,
            "mission_cycle": mission_cycle,
        }

    if state.status == "verifying" or state.next_action == "verify_done_definition":
        verify_task(build_args(task_id=task_id))
        state = load_state(task_id)
        return {
            "task_id": task_id,
            "status": state.status,
            "current_stage": state.current_stage,
            "next_action": state.next_action,
            "action": "verification_ran",
            "mission_cycle": mission_cycle,
        }

    run_once(build_args(task_id=task_id))
    state = load_state(task_id)
    contract = load_contract(task_id)
    current_stage_contract = next((stage for stage in contract.stages if stage.name == state.current_stage), None)
    if state.status == "running" and state.current_stage == "learn":
        checkpoint_task(build_args(task_id=task_id))
        promotions = promote_recurring_errors()
        completion = complete_stage_internal(
            task_id=task_id,
            stage_name="learn",
            summary=f"Learning artifacts refreshed and promotion scan completed ({len(promotions.get('added', []))} new rules)",
            evidence_ref=str((TASKS_ROOT / task_id / "runtime-evolution-proposal.json")),
        )
        state = load_state(task_id)
        return {
            "task_id": task_id,
            "status": state.status,
            "current_stage": state.current_stage,
            "next_action": state.next_action,
            "action": "learn_completed",
            "completion": completion,
            "promotions": promotions,
            "task_summary_path": str((TASKS_ROOT.parent / "learning" / "task_summaries" / f"{task_id}.json")),
            "mission_cycle": mission_cycle,
        }
    if state.status == "running" and state.current_stage == "verify" and current_stage_contract and current_stage_contract.verifier:
        verify_task(build_args(task_id=task_id))
        state = load_state(task_id)
        return {
            "task_id": task_id,
            "status": state.status,
            "current_stage": state.current_stage,
            "next_action": state.next_action,
            "action": "stage_verify_ran",
            "mission_cycle": mission_cycle,
        }
    if state.status == "running" and state.next_action.startswith("execute_stage:"):
        dispatch = dispatch_stage(task_id)
        if dispatch.get("status") == "no_bound_session":
            _mark_binding_required(task_id, "no session link is bound for this task")
            state = load_state(task_id)
            return {
                "task_id": task_id,
                "status": state.status,
                "current_stage": state.current_stage,
                "next_action": state.next_action,
                "dispatch": dispatch,
                "mission_cycle": mission_cycle,
            }
        if dispatch.get("status") == "preflight_blocked":
            preflight = dispatch.get("preflight", {})
            pending = preflight.get("result", {}).get("results", [{}])[0].get("pending_ids", [])
            if pending:
                state.status = "blocked"
                state.next_action = "await_approval_or_contract_fix"
                state.last_update_at = utc_now_iso()
                save_state(state)
                log_event(task_id, "awaiting_approval_after_preflight_block", pending_ids=pending)
        state = load_state(task_id)
        return {
            "task_id": task_id,
            "status": state.status,
            "current_stage": state.current_stage,
            "next_action": state.next_action,
            "dispatch": dispatch,
            "mission_cycle": mission_cycle,
        }
    return {
        "task_id": task_id,
        "status": state.status,
        "current_stage": state.current_stage,
        "next_action": state.next_action,
        "mission_cycle": mission_cycle,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Watchdog service for the general autonomy runtime")
    parser.add_argument("--once", action="store_true")
    parser.add_argument("--poll-seconds", type=int, default=30)
    parser.add_argument("--stale-after-seconds", type=int, default=600)
    args = parser.parse_args()

    while True:
        results = []
        if TASKS_ROOT.exists():
            for task_root in sorted(TASKS_ROOT.iterdir()):
                if task_root.is_dir():
                    results.append(process_task(task_root.name, args.stale_after_seconds))
        promotions = promote_recurring_errors()
        print(json.dumps({"processed_at": utc_now_iso(), "tasks": results, "promotions": promotions}, ensure_ascii=False, indent=2))
        if args.once:
            return 0
        time.sleep(args.poll_seconds)


if __name__ == "__main__":
    raise SystemExit(main())
