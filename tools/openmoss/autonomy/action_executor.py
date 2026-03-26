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
from browser_task_signals import collect_browser_task_signals


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


def _derive_execution_session_key(session_key: str, task_id: str) -> str:
    normalized = str(session_key or "").strip()
    if not normalized:
        return normalized
    return f"{normalized}:autonomy:{task_id}"


def _write_json(path: Path, payload: Dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _record_execution(task_id: str, payload: Dict) -> str:
    record_path = _execution_records_dir(task_id) / f"{uuid.uuid4().hex}.json"
    _write_json(record_path, payload)
    return str(record_path)


def _set_waiting_external_metadata(state, *, run_id: str, stage_name: str, reason: str, wait_status: str = "", wait_error: str = "") -> None:
    state.metadata["waiting_external"] = {
        "run_id": str(run_id or "").strip(),
        "stage_name": str(stage_name or "").strip(),
        "reason": str(reason or "").strip(),
        "wait_status": str(wait_status or "").strip(),
        "wait_error": str(wait_error or "").strip(),
        "last_polled_at": utc_now_iso(),
    }


def _batch_execution_should_continue(task_id: str) -> Dict | None:
    contract = load_contract(task_id)
    requirements = contract.metadata.get("control_center", {}).get("business_verification_requirements", {}) or {}
    if requirements.get("batch_listings_mode") is not True:
        return None
    signals = collect_browser_task_signals(task_id)
    diagnosis = str(signals.get("diagnosis", "")).strip()
    recommended_action = str(signals.get("recommended_action", "")).strip()
    if diagnosis in {"draft_listings_remaining", "batch_not_on_listings_overview", "batch_listings_rows_unreadable"}:
        return {"signals": signals, "diagnosis": diagnosis, "recommended_action": recommended_action}
    if recommended_action in {"process_next_draft_listing", "return_to_listings_overview_and_retry_batch_probe"}:
        return {"signals": signals, "diagnosis": diagnosis or "batch_continuation_required", "recommended_action": recommended_action}
    return None


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
    prompt_lines = [
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
        f"batch_focus: {json.dumps(stage_context.get('batch_focus', {}), ensure_ascii=False)}",
        f"browser_target_hint: {json.dumps(stage_context.get('browser_target_hint', {}), ensure_ascii=False)}",
        f"execution_summary: {json.dumps(stage_context.get('summary', {}), ensure_ascii=False)}",
        f"allowed_tools: {json.dumps(stage_context.get('allowed_tools', []), ensure_ascii=False)}",
        f"business_verification_requirements: {json.dumps(verifier_requirements, ensure_ascii=False)}",
        "Instruction: this is a background runtime execution request, not a user-facing status conversation.",
        "Instruction: do not reply with a status-only summary before acting. Use approved tools, make the next concrete move, and then report concise verification evidence.",
    ]
    batch_focus = stage_context.get("batch_focus", {}) or {}
    normalized_goal = str(stage_context.get("goal", contract.user_goal) or "").lower()
    if "seller.neosgo" in normalized_goal or "neosgo" in normalized_goal or "seller" in normalized_goal:
        prompt_lines.extend(
            [
                "Browser execution rule: use the existing seller.neosgo host browser chain, not a fresh local browser profile.",
                "Browser execution rule: prefer browser tool calls with target=host and profile=chrome-relay for seller.neosgo work.",
                "Browser execution rule: if the previous target id is stale, reacquire a current chrome-relay tab for seller.neosgo before continuing.",
                "Do not switch to a generic local Chrome profile when the task depends on the already logged-in seller.neosgo session.",
            ]
        )
    if batch_focus.get("force_listings_overview"):
        prompt_lines.extend(
            [
                "Mandatory batch step: before any per-product work, return to the Listings overview page and confirm the page URL is the overview, not a single-product edit page.",
                f"Listings overview URL: {batch_focus.get('expected_listings_url', 'https://seller.neosgo.com/seller/products')}",
                "If you are still on a single-product page, navigate back to Listings overview first, re-read the visible Draft rows, and only then continue with the next Draft listing.",
                "Do not claim batch progress or completion from a single-product edit page.",
            ]
        )
    next_draft = batch_focus.get("next_draft", {}) or {}
    if next_draft:
        prompt_lines.extend(
            [
                f"Next draft listing sku: {next_draft.get('sku', '')}",
                f"Next draft listing edit URL: {next_draft.get('editHref', '')}",
                "After confirming you are on Listings overview, open exactly this next draft listing before doing any other seller action.",
            ]
        )
    if batch_focus and ("seller.neosgo" in normalized_goal or "neosgo" in normalized_goal):
        prompt_lines.extend(
            [
                "Single-tab execution rule: keep seller.neosgo work inside one chrome-relay tab whenever possible.",
                "Single-tab execution rule: do not intentionally open a new tab for each Draft listing edit page.",
                "Single-tab execution rule: prefer navigate(current tab, editHref) over clicking a link that may open target=_blank.",
                "Tab budget: at most 1 active seller.neosgo chrome-relay tab should remain attached after each listing is processed.",
                "If extra seller.neosgo tabs appear, close the older or duplicate ones and continue with the surviving working tab.",
                "After finishing a listing, return the same working tab to Listings overview before selecting the next Draft.",
            ]
        )
    browser_target_hint = stage_context.get("browser_target_hint", {}) or {}
    last_nav = browser_target_hint.get("last_listings_overview_navigation", {}) or {}
    last_nav_context = last_nav.get("context", {}) or {}
    hinted_target = str(last_nav_context.get("target_id", "") or browser_target_hint.get("last_browser_channel_recovery", {}).get("target_id", "") or "").strip()
    hinted_url = str(last_nav_context.get("page_url", "") or browser_target_hint.get("last_browser_channel_recovery", {}).get("page_url", "") or "").strip()
    if hinted_target or hinted_url:
        prompt_lines.extend(
            [
                f"Recovered browser target hint: {hinted_target or 'unknown'}",
                f"Recovered browser page hint: {hinted_url or 'unknown'}",
                "Prefer this recovered target/page hint first when reattaching browser control, instead of relying on stale prior tab focus.",
            ]
        )
    if batch_focus and ("seller.neosgo" in normalized_goal or "neosgo" in normalized_goal):
        prompt_lines.extend(
            [
                "Batch seller workflow for each Draft listing:",
                "1. Open the next Draft listing edit page.",
                "2. Ensure at least 3 scene images exist and the first 3 image positions are scene images.",
                "3. Ensure Packing Unit is valid and saved (at minimum one unit with valid numeric dimensions/quantity).",
                "4. Submit the listing for review and confirm the status is no longer DRAFT.",
                "5. Return to Listings overview and continue with the next visible Draft listing.",
                "Do not stop because 'previous task requirements are unclear' — use the workflow above as the authoritative per-listing checklist.",
                "If a browser act/evaluate/snapshot call returns 'tab not found', immediately reacquire the current seller.neosgo tab via tabs and retry the same step instead of replying with a blocker summary.",
                "Prefer DOM evaluate/act on the Listings page over aria snapshot when chrome-relay snapshot is unstable.",
            ]
        )
    return "\n".join(prompt_lines)


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
                continuation = _batch_execution_should_continue(task_id)
                if continuation:
                    stage.verification_status = verification["status"]
                    stage.status = "running"
                    stage.blocker = ""
                    stage.updated_at = utc_now_iso()
                    state.status = "planning"
                    state.current_stage = stage_name
                    state.next_action = f"start_stage:{stage_name}"
                    state.blockers = []
                    state.last_update_at = utc_now_iso()
                    save_state(state)
                    log_event(
                        task_id,
                        "batch_execution_continues_after_partial_progress",
                        stage=stage_name,
                        verifier=verification,
                        diagnosis=continuation["diagnosis"],
                        recommended_action=continuation["recommended_action"],
                        record_path=record_path,
                    )
                    result["continuation"] = continuation
                    return result
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
    linked_session_key = link.get("session_key", "")
    if not linked_session_key:
        return {"ok": False, "status": "no_bound_session"}
    session_key = _derive_execution_session_key(linked_session_key, task_id)

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
    state.metadata["last_execution_session_key"] = session_key
    state.metadata["active_execution"] = {
        "run_id": run_id,
        "stage_name": stage_name,
        "session_key": session_key,
        "linked_session_key": linked_session_key,
        "dispatched_at": utc_now_iso(),
    }
    state.status = "waiting_external"
    state.next_action = f"poll_run:{run_id}" if run_id else f"poll_stage:{stage_name}"
    _set_waiting_external_metadata(
        state,
        run_id=run_id,
        stage_name=stage_name,
        reason="dispatched_waiting_for_agent_completion",
    )
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
        _set_waiting_external_metadata(
            state,
            run_id=run_id,
            stage_name=stage_name,
            reason="agent_wait_timeout" if str((result.get("wait", {}) or {}).get("status", "")).strip() == "timeout" else "waiting_for_agent_completion",
            wait_status=str((result.get("wait", {}) or {}).get("status", "")).strip(),
            wait_error=str(result.get("wait_error", "")).strip(),
        )
        state.last_update_at = utc_now_iso()
        save_state(state)
        record_path = _record_execution(task_id, result)
        result["record_path"] = record_path
        log_event(task_id, "stage_execution_polled", stage=stage_name, result=result)
        return result

    record_path = _record_execution(task_id, result)
    result["record_path"] = record_path
    log_event(task_id, "stage_execution_polled", stage=stage_name, result=result)
    state.metadata.pop("waiting_external", None)
    save_state(state)
    return _finalize_stage_wait_result(task_id, stage_name, result, record_path)
