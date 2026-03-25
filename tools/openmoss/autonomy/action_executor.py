#!/usr/bin/env python3

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import uuid
from pathlib import Path
from typing import Dict

from manager import complete_stage_internal, find_link_by_task_id, load_contract, load_state, log_event, save_state, task_dir, utc_now_iso, verify_task, build_args
from preflight_engine import run_stage_preflight
from verifier_registry import run_verifier

CONTROL_CENTER_DIR = Path("/Users/mac_claw/.openclaw/workspace/tools/openmoss/control_center")
if str(CONTROL_CENTER_DIR) not in sys.path:
    sys.path.insert(0, str(CONTROL_CENTER_DIR))

from context_builder import build_stage_context


def _resolve_openclaw_bin() -> str:
    candidates = []
    env_value = (os.environ.get("OPENCLAW_BIN") or "").strip()
    if env_value:
        candidates.append(env_value)
        if "/" not in env_value:
            resolved_env = shutil.which(env_value)
            if resolved_env:
                candidates.append(resolved_env)
    discovered = shutil.which("openclaw")
    if discovered:
        candidates.append(discovered)
    candidates.extend(
        [
            "/opt/homebrew/bin/openclaw",
            "/usr/local/bin/openclaw",
        ]
    )
    for candidate in candidates:
        if candidate and Path(candidate).exists():
            return candidate
    return env_value or "openclaw"


def _execution_records_dir(task_id: str) -> Path:
    return task_dir(task_id) / "executions"


def _write_json(path: Path, payload: Dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _record_execution(task_id: str, payload: Dict) -> str:
    record_path = _execution_records_dir(task_id) / f"{uuid.uuid4().hex}.json"
    _write_json(record_path, payload)
    return str(record_path)


def _summarize_preflight_block(preflight: Dict) -> list[str]:
    result = preflight.get("result", {}) or {}
    entries = list(result.get("results", []) or [])
    blockers: list[str] = []
    for entry in entries:
        status = str(entry.get("status", "")).strip()
        if status == "required_commands_missing":
            missing = ", ".join(entry.get("missing_commands", []) or [])
            blockers.append(f"preflight_missing_commands:{missing or 'unknown'}")
        elif status == "required_paths_missing":
            missing = ", ".join(entry.get("missing_paths", []) or [])
            blockers.append(f"preflight_missing_paths:{missing or 'unknown'}")
        elif status == "writable_paths_blocked":
            blocked = ", ".join(entry.get("blocked_paths", []) or [])
            blockers.append(f"preflight_unwritable_paths:{blocked or 'unknown'}")
        elif status in {"approval_required", "approval_pending"}:
            pending = ", ".join(entry.get("pending_ids", []) or entry.get("declared_pending_ids", []) or [])
            blockers.append(f"preflight_approval_pending:{pending or 'unknown'}")
        elif status:
            blockers.append(f"preflight_{status}")
    if not blockers:
        blockers.append(f"preflight_blocked:{preflight.get('guard_type', 'unknown')}")
    return blockers


def _gateway_call(method: str, params: Dict, timeout_seconds: int = 15) -> Dict:
    openclaw_bin = _resolve_openclaw_bin()
    try:
        proc = subprocess.run(
            [
                openclaw_bin,
                "gateway",
                "call",
                method,
                "--params",
                json.dumps(params, ensure_ascii=False),
                "--json",
            ],
            capture_output=True,
            text=True,
            check=False,
            timeout=timeout_seconds,
        )
    except subprocess.TimeoutExpired as exc:
        return {
            "ok": False,
            "method": method,
            "openclaw_bin": openclaw_bin,
            "stderr": f"subprocess timeout after {timeout_seconds}s",
            "stdout": (exc.stdout or "")[-1000:],
        }
    if proc.returncode != 0:
        return {
            "ok": False,
            "method": method,
            "openclaw_bin": openclaw_bin,
            "stderr": proc.stderr[-1000:],
            "stdout": proc.stdout[-1000:],
        }
    return {
        "ok": True,
        "method": method,
        "openclaw_bin": openclaw_bin,
        "response": json.loads(proc.stdout.strip() or "{}"),
    }


def _dispatch_prompt(task_id: str, stage_name: str) -> str:
    contract = load_contract(task_id)
    state = load_state(task_id)
    stage_context = build_stage_context(task_id, stage_name, contract.to_dict(), state.to_dict())
    stage_contract = next((stage for stage in contract.stages if stage.name == stage_name), None)
    verifier_requirements = stage_contract.verifier if stage_contract and stage_contract.verifier else {}
    return "\n".join(
        [
            "[Autonomy runtime execution request]",
            f"task_id: {stage_context.get('task_id', task_id)}",
            f"stage: {stage_context.get('stage_name', stage_name)}",
            f"user_goal: {stage_context.get('goal', contract.user_goal)}",
            f"done_definition: {stage_context.get('done_definition', contract.done_definition)}",
            f"stage_goal: {stage_context.get('stage_goal', '')}",
            f"selected_plan: {json.dumps(stage_context.get('selected_plan', {}), ensure_ascii=False)}",
            f"topology_focus: {json.dumps(stage_context.get('topology_focus', {}), ensure_ascii=False)}",
            f"fractal_focus: {json.dumps(stage_context.get('fractal_focus', {}), ensure_ascii=False)}",
            f"htn_focus: {json.dumps(stage_context.get('htn_focus', {}), ensure_ascii=False)}",
            f"subtask_progress: {json.dumps(stage_context.get('subtask_progress', {}), ensure_ascii=False)}",
            f"execution_summary: {json.dumps(stage_context.get('summary', {}), ensure_ascii=False)}",
            f"allowed_tools: {json.dumps(stage_context.get('allowed_tools', []), ensure_ascii=False)}",
            f"business_verification_requirements: {json.dumps(verifier_requirements, ensure_ascii=False)}",
            "Instruction: execute only the minimum necessary work for this stage, use only approved actions, preserve security boundaries, and report concise evidence for verification.",
        ]
    )


def _finalize_stage_wait_result(task_id: str, stage_name: str, result: Dict, record_path: str) -> Dict:
    state = load_state(task_id)
    stage = state.stages.get(stage_name)
    if stage:
        stage.last_execution_status = result["status"]
    state.metadata.pop("active_execution", None)
    save_state(state)

    contract = load_contract(task_id)
    stage_contract = next((stage for stage in contract.stages if stage.name == stage_name), None)
    if (
        result.get("ok")
        and result.get("status") == "completed"
        and stage_contract
    ):
        if bool(stage_contract.execution_policy.get("require_verifier_before_complete", False)) and stage_contract.verifier:
            verification = run_verifier(stage_contract.verifier)
            result["completion_verifier"] = verification
            if not verification.get("ok"):
                stage.verification_status = verification["status"]
                stage.status = "failed"
                stage.blocker = f"business verification failed: {verification['status']}"
                stage.updated_at = utc_now_iso()
                state.status = "recovering"
                state.current_stage = stage_name
                state.next_action = "repair_verification_failure"
                state.blockers = [f"business_verification_failed:{verification['status']}"]
                state.last_update_at = utc_now_iso()
                save_state(state)
                log_event(task_id, "stage_completion_blocked_by_verifier", stage=stage_name, verifier=verification, record_path=record_path)
                return result
        if bool(stage_contract.execution_policy.get("auto_complete_on_wait_ok", False)):
            completion = complete_stage_internal(
                task_id=task_id,
                stage_name=stage_name,
                summary=f"OpenClaw run completed successfully for stage {stage_name}",
                evidence_ref=record_path,
            )
            result["auto_completed"] = completion
            refreshed_contract = load_contract(task_id)
            next_stage_name = completion.get("next_action", "").replace("start_stage:", "")
            next_stage = next((stage for stage in refreshed_contract.stages if stage.name == next_stage_name), None)
            if next_stage and next_stage.name == "verify" and next_stage.verifier:
                verify_result = verify_task(build_args(task_id=task_id))
                result["post_completion_verify"] = {"exit_code": verify_result}
            return result

        state.status = "running"
        state.current_stage = stage_name
        state.next_action = f"execute_stage:{stage_name}"
        state.last_update_at = utc_now_iso()
        save_state(state)
        return result
    return result


def dispatch_stage(task_id: str) -> Dict:
    state = load_state(task_id)
    stage_name = state.current_stage
    if not stage_name:
        return {"ok": False, "status": "no_current_stage"}

    link = find_link_by_task_id(task_id)
    session_key = link.get("session_key", "")
    if not session_key:
        return {"ok": False, "status": "no_bound_session"}

    active = state.metadata.get("active_execution", {})
    if active.get("stage_name") == stage_name and active.get("run_id"):
        return {"ok": True, "status": "already_waiting", "session_key": session_key, "run_id": active.get("run_id")}

    dispatch_marker = f"{task_id}:{stage_name}"
    if state.metadata.get("last_dispatched_marker") == dispatch_marker and not active:
        return {"ok": True, "status": "already_dispatched", "session_key": session_key}

    preflight = run_stage_preflight(task_id, stage_name)
    if preflight.get("status") != "no_preflight_needed" and preflight.get("status") != "no_promoted_rule":
        state.metadata["last_preflight"] = {
            "stage_name": stage_name,
            "ran_at": utc_now_iso(),
            "status": preflight.get("status"),
            "action": preflight.get("action", ""),
            "result": preflight.get("result", {}),
        }
        stage = state.stages.get(stage_name)
        if stage:
            stage.updated_at = utc_now_iso()
        state.last_update_at = utc_now_iso()
        save_state(state)
        log_event(task_id, "stage_preflight_ran", stage=stage_name, preflight=preflight)
    if not preflight.get("ok", True):
        state.status = "recovering"
        state.next_action = str(preflight.get("action") or "run_root_cause_review_before_retry")
        state.blockers = _summarize_preflight_block(preflight)
        state.last_update_at = utc_now_iso()
        current_stage = state.stages.get(stage_name)
        if current_stage:
            current_stage.blocker = "; ".join(state.blockers)
            current_stage.updated_at = utc_now_iso()
        save_state(state)
        result = {
            "ok": False,
            "status": "preflight_blocked",
            "session_key": session_key,
            "preflight": preflight,
        }
        record_path = _record_execution(task_id, result)
        result["record_path"] = record_path
        log_event(task_id, "stage_dispatch_blocked_by_preflight", stage=stage_name, result=result, link_path=link.get("_path"))
        return result

    send_result = _gateway_call(
        "chat.send",
        {
            "idempotencyKey": uuid.uuid4().hex,
            "sessionKey": session_key,
            "message": _dispatch_prompt(task_id, stage_name),
            "timeoutMs": 30000,
        },
    )
    if not send_result.get("ok"):
        result = {
            "ok": False,
            "status": "dispatch_failed",
            "session_key": session_key,
            "stderr": send_result.get("stderr", ""),
            "stdout": send_result.get("stdout", ""),
        }
        record_path = _record_execution(task_id, result)
        result["record_path"] = record_path
        log_event(task_id, "stage_dispatch_attempted", stage=stage_name, result=result, link_path=link.get("_path"))
        return result

    response = send_result.get("response", {})
    run_id = response.get("runId", "")
    result = {
        "ok": True,
        "status": "dispatched",
        "session_key": session_key,
        "response": response,
        "preflight": preflight,
    }

    state.metadata["last_dispatched_marker"] = dispatch_marker
    state.metadata["last_dispatch_at"] = utc_now_iso()
    state.metadata["active_execution"] = {
        "run_id": run_id,
        "stage_name": stage_name,
        "session_key": session_key,
        "dispatched_at": utc_now_iso(),
    }
    state.status = "waiting_external"
    state.next_action = f"poll_run:{run_id}" if run_id else f"poll_stage:{stage_name}"
    state.last_update_at = utc_now_iso()
    stage = state.stages.get(stage_name)
    if stage:
        stage.last_execution_status = "dispatched"
        stage.updated_at = utc_now_iso()
    save_state(state)

    wait_result = _gateway_call("agent.wait", {"runId": run_id, "timeoutMs": 1000}, timeout_seconds=8) if run_id else {"ok": False}
    if wait_result.get("ok"):
        wait_response = wait_result.get("response", {})
        result["wait"] = wait_response
        if wait_response.get("status") == "ok":
            result["status"] = "completed"
        else:
            result["status"] = "waiting_external"
    else:
        result["wait_error"] = wait_result.get("stderr", "") or wait_result.get("stdout", "")
        result["status"] = "waiting_external"

    record_path = _record_execution(task_id, result)
    result["record_path"] = record_path
    log_event(task_id, "stage_dispatch_attempted", stage=stage_name, result=result, link_path=link.get("_path"))
    if result.get("status") == "completed":
        return _finalize_stage_wait_result(task_id, stage_name, result, record_path)
    return result


def poll_active_execution(task_id: str) -> Dict:
    state = load_state(task_id)
    active = state.metadata.get("active_execution", {})
    run_id = active.get("run_id", "")
    stage_name = active.get("stage_name", state.current_stage)
    if not run_id or not stage_name:
        return {"ok": False, "status": "no_active_execution"}

    contract = load_contract(task_id)
    current_stage_contract = next((stage for stage in contract.stages if stage.name == stage_name), None)
    if stage_name == "verify" and current_stage_contract and current_stage_contract.verifier:
        state.metadata.pop("active_execution", None)
        state.status = "running"
        state.next_action = f"execute_stage:{stage_name}"
        state.last_update_at = utc_now_iso()
        save_state(state)
        result = {
            "ok": True,
            "status": "verify_handoff_to_structured_verifier",
            "run_id": run_id,
            "stage": stage_name,
        }
        record_path = _record_execution(task_id, result)
        result["record_path"] = record_path
        log_event(task_id, "verify_handoff_to_structured_verifier", stage=stage_name, result=result)
        return result

    tracked_stage = state.stages.get(stage_name)
    if tracked_stage and tracked_stage.status == "completed" and state.current_stage != stage_name:
        state.metadata.pop("active_execution", None)
        if state.current_stage:
            state.status = "running"
            state.next_action = f"execute_stage:{state.current_stage}"
        else:
            state.status = "verifying"
            state.next_action = "verify_done_definition"
        state.last_update_at = utc_now_iso()
        save_state(state)
        result = {
            "ok": True,
            "status": "stale_execution_cleared",
            "run_id": run_id,
            "stage": stage_name,
            "advanced_to": state.current_stage,
        }
        record_path = _record_execution(task_id, result)
        result["record_path"] = record_path
        log_event(task_id, "stale_execution_cleared", stage=stage_name, result=result)
        return result

    wait_result = _gateway_call("agent.wait", {"runId": run_id, "timeoutMs": 1000}, timeout_seconds=8)
    if not wait_result.get("ok"):
        result = {
            "ok": True,
            "status": "waiting_external",
            "run_id": run_id,
            "stage": stage_name,
            "wait_error": wait_result.get("stderr", "") or wait_result.get("stdout", ""),
        }
    else:
        wait_response = wait_result.get("response", {})
        if wait_response.get("status") == "ok":
            result = {
                "ok": True,
                "status": "completed",
                "run_id": run_id,
                "stage": stage_name,
                "wait": wait_response,
            }
        else:
            result = {
                "ok": True,
                "status": "waiting_external",
                "run_id": run_id,
                "stage": stage_name,
                "wait": wait_response,
            }

    stage = state.stages.get(stage_name)
    if stage:
        stage.last_execution_status = result["status"]
        stage.updated_at = utc_now_iso()
    if result["status"] == "waiting_external":
        state.status = "waiting_external"
        state.next_action = f"poll_run:{run_id}"
        state.last_update_at = utc_now_iso()
        save_state(state)
        record_path = _record_execution(task_id, result)
        result["record_path"] = record_path
        log_event(task_id, "stage_execution_polled", stage=stage_name, result=result)
        return result

    record_path = _record_execution(task_id, result)
    result["record_path"] = record_path
    log_event(task_id, "stage_execution_polled", stage=stage_name, result=result)
    return _finalize_stage_wait_result(task_id, stage_name, result, record_path)
