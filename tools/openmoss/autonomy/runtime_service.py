#!/usr/bin/env python3

from __future__ import annotations

import argparse
import json
import sys
import time
import traceback
from datetime import datetime, timezone
from pathlib import Path

from action_executor import dispatch_stage, poll_active_execution
from learning_engine import get_error_recurrence
from manager import TASKS_ROOT, advance_execute_subtask, apply_recovery, build_args, checkpoint_task, complete_stage_internal, contract_path, find_link_by_task_id, infer_link_session_key, load_contract, load_state, log_event, run_once, save_contract, save_state, state_path, verify_task, write_business_outcome, write_link
from promotion_engine import promote_recurring_errors

CONTROL_CENTER_DIR = Path("/Users/mac_claw/.openclaw/workspace/tools/openmoss/control_center")
if str(CONTROL_CENTER_DIR) not in sys.path:
    sys.path.insert(0, str(CONTROL_CENTER_DIR))

from mission_loop import run_mission_cycle
from browser_channel_recovery import prune_relay_tabs, recover_browser_channel, navigate_relay_to_url
from browser_task_signals import collect_browser_task_signals
from mission_supervisor import supervise_task
from orchestrator import derive_business_verification_requirements
from paths import CONTRACT_QUARANTINE_ROOT
from progress_evidence import build_progress_evidence
from system_doctor import run_system_doctor
from task_receipt_engine import emit_route_receipt
from task_status_snapshot import build_task_status_snapshot


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _preflight_block_details(state) -> dict:
    last_preflight = state.metadata.get("last_preflight", {}) or {}
    result = last_preflight.get("result", {}) or {}
    entries = list(result.get("results", []) or [])
    statuses = [str(entry.get("status", "")).strip() for entry in entries if str(entry.get("status", "")).strip()]
    pending_ids: list[str] = []
    missing_commands: list[str] = []
    for entry in entries:
        pending_ids.extend([str(item) for item in entry.get("pending_ids", []) or [] if str(item).strip()])
        pending_ids.extend([str(item) for item in entry.get("declared_pending_ids", []) or [] if str(item).strip()])
        missing_commands.extend([str(item) for item in entry.get("missing_commands", []) or [] if str(item).strip()])
    return {
        "statuses": statuses,
        "pending_ids": sorted(set(pending_ids)),
        "missing_commands": sorted(set(missing_commands)),
        "entries": entries,
    }


def _preferred_browser_url(state) -> str:
    metadata = getattr(state, "metadata", {}) or {}
    batch_focus = metadata.get("batch_focus", {}) or {}
    if isinstance(batch_focus, dict):
        return str(batch_focus.get("expected_listings_url", "")).strip()
    return ""


def _mark_binding_required(task_id: str, reason: str) -> None:
    state = load_state(task_id)
    state.status = "blocked"
    state.blockers = [reason]
    state.next_action = "bind_session_link"
    state.last_update_at = utc_now_iso()
    save_state(state)
    log_event(task_id, "binding_required", reason=reason)


def _recover_direct_session_link(task_id: str) -> dict | None:
    link = find_link_by_task_id(task_id)
    if not link:
        return None
    session_key = infer_link_session_key(link)
    if session_key and not str(link.get("session_key", "")).strip():
        provider = str(link.get("provider", "")).strip()
        conversation_id = str(link.get("conversation_id", "")).strip()
        if provider and conversation_id:
            payload = {k: v for k, v in link.items() if not str(k).startswith("_")}
            payload["session_key"] = session_key
            payload["updated_at"] = utc_now_iso()
            write_link(provider, conversation_id, payload)
            link = find_link_by_task_id(task_id)
    state = load_state(task_id)
    state.status = "planning"
    state.blockers = []
    state.next_action = f"start_stage:{state.current_stage}" if state.current_stage else "initialize"
    state.metadata.pop("superseded_by_task_id", None)
    state.last_update_at = utc_now_iso()
    save_state(state)
    log_event(
        task_id,
        "session_link_recovered_from_direct_binding",
        provider=str(link.get("provider", "")).strip(),
        conversation_id=str(link.get("conversation_id", "")).strip(),
        session_key=str(link.get("session_key", "")).strip(),
    )
    return {
        "task_id": task_id,
        "provider": str(link.get("provider", "")).strip(),
        "conversation_id": str(link.get("conversation_id", "")).strip(),
        "session_key": str(link.get("session_key", "")).strip(),
    }


def _inherit_lineage_session_link(task_id: str) -> dict | None:
    contract = load_contract(task_id)
    lineage_candidates = [
        str(contract.metadata.get("predecessor_task_id", "")).strip(),
        str(contract.metadata.get("lineage_root_task_id", "")).strip(),
    ]
    for candidate in lineage_candidates:
        if not candidate:
            continue
        link = find_link_by_task_id(candidate)
        if not link:
            continue
        provider = str(link.get("provider", "")).strip()
        conversation_id = str(link.get("conversation_id", "")).strip()
        if not provider or not conversation_id:
            continue
        payload = {k: v for k, v in link.items() if not str(k).startswith("_")}
        payload["task_id"] = task_id
        payload["goal"] = contract.user_goal
        payload["updated_at"] = utc_now_iso()
        write_link(provider, conversation_id, payload)
        state = load_state(task_id)
        state.status = "planning"
        state.blockers = []
        state.next_action = f"start_stage:{state.current_stage}" if state.current_stage else "initialize"
        state.metadata.pop("superseded_by_task_id", None)
        state.last_update_at = utc_now_iso()
        save_state(state)
        log_event(
            task_id,
            "session_link_inherited_from_lineage",
            inherited_from_task_id=candidate,
            provider=provider,
            conversation_id=conversation_id,
        )
        return {
            "task_id": task_id,
            "inherited_from_task_id": candidate,
            "provider": provider,
            "conversation_id": conversation_id,
        }
    return None


def _purge_stale_successor_business_outcome(task_id: str) -> dict | None:
    contract = load_contract(task_id)
    if not contract.metadata.get("predecessor_task_id"):
        return None
    state = load_state(task_id)
    existing = state.metadata.get("business_outcome", {}) or {}
    diagnosis = str(existing.get("evidence", {}).get("diagnosis", "")).strip()
    if diagnosis not in {"upload_saved_successfully", "upload_persisted_in_product_gallery"}:
        return None
    current_signals = collect_browser_task_signals(task_id)
    current_business_outcome = current_signals.get("business_outcome", {}) or {}
    if (
        current_business_outcome.get("goal_satisfied") is True
        and current_business_outcome.get("user_visible_result_confirmed") is True
        and str(current_business_outcome.get("proof_summary", "")).strip()
    ):
        return None
    state.metadata.pop("business_outcome", None)
    state.metadata.pop("active_execution", None)
    for stage_name in ("execute", "verify", "learn"):
        stage = state.stages.get(stage_name)
        if not stage:
            continue
        stage.status = "pending"
        stage.summary = ""
        stage.verification_status = "not-run"
        stage.blocker = ""
        stage.completed_at = ""
        stage.updated_at = utc_now_iso()
    state.status = "planning"
    state.current_stage = "execute" if "execute" in state.stages else state.first_pending_stage() or ""
    state.next_action = f"start_stage:{state.current_stage}" if state.current_stage else "initialize"
    state.blockers = []
    state.last_update_at = utc_now_iso()
    save_state(state)
    result = {"task_id": task_id, "diagnosis": diagnosis, "reopened_stage": state.current_stage}
    log_event(task_id, "stale_successor_business_outcome_purged", result=result)
    return result


def _invalidate_contradicted_business_outcome(task_id: str) -> dict | None:
    state = load_state(task_id)
    existing = state.metadata.get("business_outcome", {}) or {}
    if not existing:
        return None
    signals = collect_browser_task_signals(task_id)
    requirements = signals.get("requirements_evaluation", {}) or {}
    if requirements.get("ok") is True:
        return None

    state.metadata.pop("business_outcome", None)
    state.metadata.pop("active_execution", None)
    state.metadata.pop("last_dispatched_marker", None)
    state.metadata.pop("last_dispatch_at", None)
    last_decision = state.metadata.get("last_control_center_decision", {}) or {}
    if str(last_decision.get("action", "")).strip() == "confirm_business_outcome_and_finalize":
        state.metadata.pop("last_control_center_decision", None)

    execute_stage = state.stages.get("execute")
    verify_stage = state.stages.get("verify")
    learn_stage = state.stages.get("learn")
    for stage in (execute_stage, verify_stage, learn_stage):
        if not stage:
            continue
        stage.status = "pending"
        stage.summary = ""
        stage.verification_status = "not-run"
        stage.blocker = ""
        stage.completed_at = ""
        stage.updated_at = utc_now_iso()

    state.status = "planning"
    state.current_stage = "execute" if execute_stage else state.first_pending_stage() or ""
    state.next_action = f"start_stage:{state.current_stage}" if state.current_stage else "initialize"
    state.blockers = []
    state.last_update_at = utc_now_iso()
    save_state(state)
    result = {
        "task_id": task_id,
        "diagnosis": signals.get("diagnosis", ""),
        "requirement_status": requirements.get("status", ""),
        "reopened_stage": state.current_stage,
    }
    log_event(task_id, "contradicted_business_outcome_invalidated", result=result)
    return result


def _sync_business_outcome_from_live_probe(task_id: str) -> dict | None:
    contract = load_contract(task_id)
    signals = collect_browser_task_signals(task_id)
    business_outcome = signals.get("business_outcome", {}) or {}
    if not business_outcome:
        return None
    requirements = signals.get("requirements_evaluation", {}) or {}
    current_state = load_state(task_id)
    existing = current_state.metadata.get("business_outcome", {}) or {}
    proof_summary = str(business_outcome.get("proof_summary", "")).strip()
    existing_summary = str(existing.get("proof_summary", "")).strip()
    needs_write = (
        existing.get("goal_satisfied") is not True
        or existing.get("user_visible_result_confirmed") is not True
        or not existing_summary
        or existing_summary != proof_summary
    )
    written = None
    if needs_write:
        written = write_business_outcome(
            task_id,
            goal_satisfied=bool(business_outcome.get("goal_satisfied")),
            user_visible_result_confirmed=bool(business_outcome.get("user_visible_result_confirmed")),
            proof_summary=proof_summary,
            evidence=business_outcome.get("evidence", {}),
        )
    state = load_state(task_id)
    if requirements.get("ok"):
        for stage_name in state.stage_order:
            stage = state.stages.get(stage_name)
            if not stage:
                continue
            if stage_name in {"understand", "plan", "execute", "verify"}:
                if stage.status != "completed":
                    stage.status = "completed"
                    stage.verification_status = "ok" if stage_name in {"execute", "verify"} else stage.verification_status
                    if not stage.summary:
                        stage.summary = f"Live business outcome satisfied the {stage_name} stage requirements"
                    if not stage.completed_at:
                        stage.completed_at = utc_now_iso()
                    stage.blocker = ""
                    stage.updated_at = utc_now_iso()
            elif stage_name == "learn" and stage.status == "failed":
                stage.status = "pending"
                stage.blocker = ""
                stage.updated_at = utc_now_iso()
        state.metadata.pop("active_execution", None)
    state.blockers = []
    state.status = "verifying"
    state.current_stage = "verify"
    state.next_action = "verify_done_definition"
    state.last_update_at = utc_now_iso()
    save_state(state)
    log_event(
        task_id,
        "business_outcome_synced_from_live_probe",
        outcome=written or existing,
        diagnosis=signals.get("diagnosis", ""),
        refreshed=bool(needs_write),
    )
    return {"signals": signals, "written": bool(needs_write), "business_outcome": written or existing}


def _upgrade_missing_business_requirements(task_id: str) -> dict | None:
    contract = load_contract(task_id)
    metadata = contract.metadata.get("control_center", {}) or {}
    current_requirements = metadata.get("business_verification_requirements", {}) or {}
    intent = metadata.get("intent", {}) or {}
    derived = derive_business_verification_requirements(intent)
    if not derived:
        return None
    should_update = not current_requirements
    if not should_update and derived.get("batch_listings_mode") is True:
        should_update = (
            current_requirements.get("draft_visible_count_at_most") != 0
            or current_requirements.get("batch_listings_mode") is not True
        )
    if not should_update:
        return None
    metadata["business_verification_requirements"] = derived
    contract.metadata["control_center"] = metadata
    save_contract(contract)
    mission_path = Path(str(metadata.get("mission_path", "")).strip())
    if mission_path.exists():
        try:
            mission_payload = json.loads(mission_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            mission_payload = {}
        if isinstance(mission_payload, dict):
            mission_payload["business_verification_requirements"] = derived
            mission_path.write_text(json.dumps(mission_payload, ensure_ascii=False, indent=2), encoding="utf-8")
    log_event(task_id, "business_requirements_upgraded", requirements=derived)
    return {"task_id": task_id, "requirements": derived}


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
    if action == "await_relay_attach_checkpoint":
        state.status = "blocked"
        state.next_action = "await_relay_attach_checkpoint"
        state.blockers = ["chrome-relay has no attached tabs; re-attach the relay badge on the target seller.neosgo tab before continuation"]
        state.last_update_at = utc_now_iso()
        save_state(state)
        log_event(task_id, "control_center_requires_relay_attach_checkpoint")
        return {
            "task_id": task_id,
            "status": state.status,
            "current_stage": state.current_stage,
            "next_action": state.next_action,
            "action": "awaiting_relay_attach_checkpoint",
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
    if action in {
        "reacquire_browser_channel",
        "needs_network_request_level_debugging",
        "investigate_frontend_binding_and_network_request_chain",
        "normalize_invalid_numeric_fields_then_resubmit",
        "repair_form_validation_then_retry_submit",
    }:
        if action == "reacquire_browser_channel":
            recovery = recover_browser_channel(
                task_id,
                expected_domains=["seller.neosgo.com"],
                preferred_url=_preferred_browser_url(state),
            )
            if recovery.get("ok"):
                state.status = "planning"
                state.blockers = []
                state.next_action = f"start_stage:{state.current_stage}" if state.current_stage else "initialize"
                state.metadata["last_browser_channel_recovery"] = recovery
                state.last_update_at = utc_now_iso()
                save_state(state)
                log_event(task_id, "control_center_browser_channel_recovered", recovery=recovery)
                return {
                    "task_id": task_id,
                    "status": state.status,
                    "current_stage": state.current_stage,
                    "next_action": state.next_action,
                    "action": "browser_channel_recovered",
                    "recovery": recovery,
                    "mission_cycle": mission_cycle,
                }
        state.status = "blocked"
        state.next_action = action
        blocker_map = {
            "reacquire_browser_channel": "the browser control channel must be reacquired before execution can continue",
            "needs_network_request_level_debugging": "the current browser path needs request-level debugging before retrying",
            "investigate_frontend_binding_and_network_request_chain": "the current upload control requires frontend-binding and request-chain inspection",
            "normalize_invalid_numeric_fields_then_resubmit": "form validation must be normalized before a reliable resubmit",
            "repair_form_validation_then_retry_submit": "invalid form fields must be repaired before submit can succeed",
        }
        state.blockers = [blocker_map[action]]
        state.last_update_at = utc_now_iso()
        save_state(state)
        log_event(task_id, "control_center_targeted_debug_required", action=action, diagnosis=mission_cycle.get("browser_signals", {}).get("diagnosis", ""))
        return {
            "task_id": task_id,
            "status": state.status,
            "current_stage": state.current_stage,
            "next_action": state.next_action,
            "action": "targeted_debug_required",
            "mission_cycle": mission_cycle,
        }
    if action == "confirm_business_outcome_and_finalize":
        state.status = "verifying"
        state.current_stage = "verify"
        state.next_action = "verify_done_definition"
        state.blockers = []
        state.last_update_at = utc_now_iso()
        save_state(state)
        log_event(task_id, "control_center_finalize_business_outcome")
        return {
            "task_id": task_id,
            "status": state.status,
            "current_stage": state.current_stage,
            "next_action": state.next_action,
            "action": "finalize_business_outcome",
            "mission_cycle": mission_cycle,
        }
    if action == "continue_current_plan":
        if state.status in {"recovering", "blocked"}:
            state.status = "planning"
            state.blockers = []
            state.next_action = f"start_stage:{state.current_stage}" if state.current_stage else "initialize"
            state.last_update_at = utc_now_iso()
            save_state(state)
            log_event(task_id, "control_center_continued_current_plan")
            return {
                "task_id": task_id,
                "status": state.status,
                "current_stage": state.current_stage,
                "next_action": state.next_action,
                "action": "continued_current_plan",
                "mission_cycle": mission_cycle,
            }
        state.last_update_at = utc_now_iso()
        save_state(state)
        return None
    if action == "process_next_draft_listing":
        browser_signals = mission_cycle.get("browser_signals", {}) or {}
        draft_rows = browser_signals.get("draft_rows", []) or []
        channel_recovery = browser_signals.get("channel_recovery", {}) or {}
        keep_target_id = str(channel_recovery.get("target_id", "")).strip()
        prune_result = prune_relay_tabs(
            task_id,
            keep_target_id=keep_target_id,
            preferred_url=_preferred_browser_url(state) or "https://seller.neosgo.com/seller/products",
            last_known_url=str(browser_signals.get("page_url", "")).strip(),
            expected_domains=["seller.neosgo.com"],
            max_tabs=1,
        )
        state.status = "planning"
        state.current_stage = "execute"
        state.blockers = []
        state.next_action = "start_stage:execute"
        if draft_rows:
            state.metadata["batch_focus"] = {
                "next_draft": draft_rows[0],
                "remaining_visible_drafts": browser_signals.get("draft_visible_count"),
                "listing_status_counts": browser_signals.get("listing_status_counts", {}),
                "single_tab_mode": True,
                "tab_budget": 1,
                "working_target_id": keep_target_id,
                "expected_listings_url": "https://seller.neosgo.com/seller/products",
            }
        state.metadata["last_tab_pruning"] = prune_result
        state.metadata.pop("active_execution", None)
        state.metadata.pop("last_dispatched_marker", None)
        state.metadata.pop("last_dispatch_at", None)
        state.last_update_at = utc_now_iso()
        save_state(state)
        log_event(
            task_id,
            "control_center_process_next_draft_listing",
            next_draft=draft_rows[0] if draft_rows else {},
            remaining_visible_drafts=browser_signals.get("draft_visible_count"),
            tab_pruning=prune_result,
        )
        return {
            "task_id": task_id,
            "status": state.status,
            "current_stage": state.current_stage,
            "next_action": state.next_action,
            "action": "processing_next_draft_listing",
            "mission_cycle": mission_cycle,
        }
    if action == "return_to_listings_overview_and_retry_batch_probe":
        browser_signals = mission_cycle.get("browser_signals", {}) or {}
        batch_focus = state.metadata.get("batch_focus", {}) or {}
        expected_listings_url = "https://seller.neosgo.com/seller/products"
        navigation = navigate_relay_to_url(
            task_id,
            expected_listings_url,
            expected_domains=["seller.neosgo.com"],
        )
        batch_focus["force_listings_overview"] = True
        batch_focus["expected_listings_url"] = expected_listings_url
        batch_focus["single_tab_mode"] = True
        batch_focus["tab_budget"] = 1
        batch_focus["last_probe_page_url"] = browser_signals.get("page_url", "")
        batch_focus["last_listings_page_url"] = browser_signals.get("listings_page_url", "")
        state.metadata["batch_focus"] = batch_focus
        state.metadata["last_listings_overview_navigation"] = navigation
        state.metadata["last_tab_pruning"] = navigation.get("tab_pruning", {})
        if not navigation.get("ok"):
            state.status = "recovering"
            state.current_stage = "execute"
            state.blockers = ["failed to navigate seller.neosgo back to listings overview"]
            state.next_action = "reacquire_browser_channel"
            state.metadata.pop("active_execution", None)
            state.metadata.pop("last_dispatched_marker", None)
            state.metadata.pop("last_dispatch_at", None)
            state.last_update_at = utc_now_iso()
            save_state(state)
            log_event(
                task_id,
                "control_center_return_to_listings_overview_failed",
                navigation=navigation,
                page_url=browser_signals.get("page_url", ""),
                listings_page_url=browser_signals.get("listings_page_url", ""),
            )
            return {
                "task_id": task_id,
                "status": state.status,
                "current_stage": state.current_stage,
                "next_action": state.next_action,
                "action": "return_to_listings_overview_failed",
                "navigation": navigation,
                "mission_cycle": mission_cycle,
            }
        state.status = "planning"
        state.current_stage = "execute"
        state.blockers = []
        state.next_action = "start_stage:execute"
        state.metadata.pop("active_execution", None)
        state.metadata.pop("last_dispatched_marker", None)
        state.metadata.pop("last_dispatch_at", None)
        state.last_update_at = utc_now_iso()
        save_state(state)
        log_event(
            task_id,
            "control_center_return_to_listings_overview",
            navigation=navigation,
            page_url=browser_signals.get("page_url", ""),
            listings_page_url=browser_signals.get("listings_page_url", ""),
        )
        return {
            "task_id": task_id,
            "status": state.status,
            "current_stage": state.current_stage,
            "next_action": state.next_action,
            "action": "returning_to_listings_overview",
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
    if action.startswith("advance_stage:") and state.status in {"planning", "blocked", "running"}:
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


def _auto_finalize_completed_business_task(task_id: str) -> dict | None:
    state = load_state(task_id)
    business = state.metadata.get("business_outcome", {}) or {}
    if not (
        business.get("goal_satisfied") is True
        and business.get("user_visible_result_confirmed") is True
        and str(business.get("proof_summary", "")).strip()
    ):
        return None
    incomplete = [name for name in state.stage_order if state.stages.get(name) and state.stages[name].status != "completed"]
    if incomplete != ["learn"]:
        return None
    completion = complete_stage_internal(
        task_id=task_id,
        stage_name="learn",
        summary="Business outcome already confirmed; runtime finalized learning and closure automatically.",
    )
    verify_task(build_args(task_id=task_id))
    state = load_state(task_id)
    log_event(task_id, "business_outcome_auto_finalized", completion=completion)
    return {
        "task_id": task_id,
        "status": state.status,
        "current_stage": state.current_stage,
        "next_action": state.next_action,
        "action": "business_outcome_auto_finalized",
        "completion": completion,
    }


def process_task(task_id: str, stale_after_seconds: int) -> dict:
    _upgrade_missing_business_requirements(task_id)
    contract = load_contract(task_id)
    state = load_state(task_id)
    purged_business_outcome = _purge_stale_successor_business_outcome(task_id)
    if purged_business_outcome:
        state = load_state(task_id)
    invalidated_business_outcome = _invalidate_contradicted_business_outcome(task_id)
    if invalidated_business_outcome:
        state = load_state(task_id)
    mission_cycle = run_mission_cycle(task_id, contract.to_dict(), state.to_dict())
    synced_business_outcome = _sync_business_outcome_from_live_probe(task_id)
    if synced_business_outcome:
        state = load_state(task_id)
        mission_cycle = run_mission_cycle(task_id, contract.to_dict(), state.to_dict())
    auto_finalized = _auto_finalize_completed_business_task(task_id)
    if auto_finalized:
        return auto_finalized
    control_center_result = _apply_control_center_decision(task_id, state, mission_cycle)
    state = load_state(task_id)
    if control_center_result and control_center_result.get("action") == "advanced_execute_subtask":
        return control_center_result
    if (
        control_center_result
        and control_center_result.get("action") != "finalize_business_outcome"
        and not (state.status == "blocked" and state.next_action == "bind_session_link")
        and state.status not in {"planning", "running"}
    ):
        return control_center_result
    if state.status in {"completed", "failed"}:
        return {"task_id": task_id, "status": state.status, "action": "skipped_terminal", "mission_cycle": mission_cycle}
    if state.status == "blocked" and state.next_action == "bind_session_link":
        direct_link = _recover_direct_session_link(task_id)
        inherited_link = None
        if direct_link:
            state = load_state(task_id)
            log_event(task_id, "binding_auto_recovered_from_direct_link", link=direct_link)
        else:
            inherited_link = _inherit_lineage_session_link(task_id)
        if direct_link or inherited_link:
            state = load_state(task_id)
            if inherited_link:
                log_event(task_id, "binding_auto_recovered_from_lineage", link=inherited_link)
        else:
            return {
                "task_id": task_id,
                "status": state.status,
                "current_stage": state.current_stage,
                "next_action": state.next_action,
                "action": "blocked_waiting_for_targeted_fix",
                "mission_cycle": mission_cycle,
            }

    if state.status == "blocked" and state.next_action == "repair_runtime_failure":
        if any("runtime isolated" in str(item).lower() for item in state.blockers or []):
            state.status = "planning"
            state.blockers = []
            state.next_action = f"start_stage:{state.current_stage}" if state.current_stage else "initialize"
            state.last_update_at = utc_now_iso()
            save_state(state)
            log_event(task_id, "runtime_failure_auto_recovered")
            return {
                "task_id": task_id,
                "status": state.status,
                "current_stage": state.current_stage,
                "next_action": state.next_action,
                "action": "runtime_failure_auto_recovered",
                "mission_cycle": mission_cycle,
            }

    if state.status == "blocked":
        return {
            "task_id": task_id,
            "status": state.status,
            "current_stage": state.current_stage,
            "next_action": state.next_action,
            "action": "blocked_waiting_for_targeted_fix",
            "mission_cycle": mission_cycle,
        }

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
            details = _preflight_block_details(state)
            statuses = set(details["statuses"])
            if statuses & {"approval_required", "approval_pending"}:
                state.status = "blocked"
                state.next_action = "await_approval_or_contract_fix"
                state.last_update_at = utc_now_iso()
                save_state(state)
                log_event(task_id, "preflight_block_requires_review", next_action=state.next_action, pending_ids=details["pending_ids"])
                return {
                    "task_id": task_id,
                    "status": state.status,
                    "current_stage": state.current_stage,
                    "next_action": state.next_action,
                    "action": "awaiting_preflight_resolution",
                    "mission_cycle": mission_cycle,
                }

            blocker_text = "; ".join(state.blockers or []) or "contract preflight blocked execution"
            state.status = "blocked"
            state.next_action = "inspect_runtime_contract_or_environment"
            state.learning_backlog = sorted(set([*state.learning_backlog, "convert_repeated_preflight_blocks_into_explicit_runtime_faults"]))
            state.last_update_at = utc_now_iso()
            save_state(state)
            log_event(
                task_id,
                "preflight_block_escalated_to_runtime_fault",
                next_action=state.next_action,
                blocker=blocker_text,
                details=details,
            )
            return {
                "task_id": task_id,
                "status": state.status,
                "current_stage": state.current_stage,
                "next_action": state.next_action,
                "action": "awaiting_runtime_or_contract_fix",
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
        if state.next_action == "reacquire_browser_channel":
            recovery = recover_browser_channel(
                task_id,
                expected_domains=["seller.neosgo.com"],
                preferred_url=_preferred_browser_url(state),
            )
            if recovery.get("ok"):
                state.status = "planning"
                state.blockers = []
                state.metadata["last_browser_channel_recovery"] = recovery
                state.next_action = f"start_stage:{state.current_stage}" if state.current_stage else "initialize"
                state.last_update_at = utc_now_iso()
                save_state(state)
                log_event(task_id, "recovery_browser_channel_recovered", recovery=recovery)
                return {
                    "task_id": task_id,
                    "status": state.status,
                    "current_stage": state.current_stage,
                    "next_action": state.next_action,
                    "action": "browser_channel_recovered",
                    "recovery": recovery,
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
        restarted = _repair_stale_waiting_external(task_id, stale_after_seconds=stale_after_seconds)
        if restarted:
            restarted["mission_cycle"] = mission_cycle
            return restarted
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


def _task_artifacts_complete(task_id: str) -> bool:
    if not (contract_path(task_id).exists() and state_path(task_id).exists()):
        return False
    try:
        payload = json.loads(contract_path(task_id).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return False
    return all(str(payload.get(field, "")).strip() for field in ("task_id", "user_goal", "done_definition"))


def _write_contract_quarantine_record(task_id: str, *, artifact: str, error: Exception | str) -> str:
    CONTRACT_QUARANTINE_ROOT.mkdir(parents=True, exist_ok=True)
    path = CONTRACT_QUARANTINE_ROOT / f"{task_id}.json"
    payload = {
        "task_id": task_id,
        "artifact": artifact,
        "quarantined_at": utc_now_iso(),
        "error_type": type(error).__name__ if not isinstance(error, str) else "RuntimeValidationError",
        "error": str(error),
        "contract_path": str(contract_path(task_id)),
        "state_path": str(state_path(task_id)),
    }
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return str(path)


def _quarantine_invalid_runtime_artifacts(task_id: str, *, artifact: str, error: Exception | str) -> dict:
    quarantine_path = _write_contract_quarantine_record(task_id, artifact=artifact, error=error)
    if state_path(task_id).exists():
        try:
            state = load_state(task_id)
            state.status = "blocked"
            state.next_action = "repair_invalid_contract"
            state.blockers = [f"{artifact} invalid: {str(error)}"]
            state.last_update_at = utc_now_iso()
            save_state(state)
            log_event(task_id, "invalid_task_artifact_quarantined", artifact=artifact, quarantine_path=quarantine_path, error=str(error))
        except Exception:
            pass
    return {
        "task_id": task_id,
        "status": "isolated_invalid_task_artifact",
        "action": "contract_quarantined",
        "artifact": artifact,
        "error": str(error),
        "quarantine_path": quarantine_path,
    }


def _validate_runtime_artifacts(task_id: str) -> dict | None:
    if not contract_path(task_id).exists():
        return _quarantine_invalid_runtime_artifacts(task_id, artifact="contract", error="contract.json is missing")
    if not state_path(task_id).exists():
        return _quarantine_invalid_runtime_artifacts(task_id, artifact="state", error="state.json is missing")
    try:
        load_contract(task_id)
    except Exception as exc:
        return _quarantine_invalid_runtime_artifacts(task_id, artifact="contract", error=exc)
    try:
        load_state(task_id)
    except Exception as exc:
        return _quarantine_invalid_runtime_artifacts(task_id, artifact="state", error=exc)
    return None


def _invalid_task_artifact_result(task_id: str) -> dict:
    state_file = state_path(task_id)
    if state_file.exists():
        try:
            state = load_state(task_id)
            state.status = "blocked"
            state.next_action = "repair_invalid_contract"
            state.blockers = ["task artifacts are incomplete or invalid"]
            state.last_update_at = utc_now_iso()
            save_state(state)
            log_event(task_id, "invalid_task_artifact_isolated")
        except Exception:
            pass
    return {
        "task_id": task_id,
        "status": "skipped_invalid_task_artifact",
        "action": "isolated_invalid_task_artifact",
        "contract_exists": contract_path(task_id).exists(),
        "state_exists": state_path(task_id).exists(),
    }


def _repair_stale_waiting_external(task_id: str, *, stale_after_seconds: int) -> dict | None:
    evidence = build_progress_evidence(task_id, stale_after_seconds=stale_after_seconds)
    if evidence.get("progress_state") not in {
        "stalled_waiting_external",
        "waiting_external_without_execution",
        "waiting_external_state_mismatch",
    }:
        return None
    state = load_state(task_id)
    state.status = "planning"
    state.blockers = []
    state.metadata.pop("waiting_external", None)
    state.metadata.pop("active_execution", None)
    state.metadata.pop("last_dispatched_marker", None)
    state.metadata.pop("last_dispatch_at", None)
    state.next_action = f"start_stage:{state.current_stage}" if state.current_stage else "initialize"
    state.last_update_at = utc_now_iso()
    save_state(state)
    log_event(task_id, "stale_waiting_external_restarted_before_poll", evidence=evidence)
    return {
        "task_id": task_id,
        "status": state.status,
        "current_stage": state.current_stage,
        "next_action": state.next_action,
        "action": "stale_waiting_external_restarted",
        "evidence": evidence,
    }


def _emit_terminal_receipt(task_id: str, *, mode: str) -> dict | None:
    link = find_link_by_task_id(task_id)
    if not link:
        return None
    provider = str(link.get("provider", "")).strip() or "openclaw-main"
    conversation_id = str(link.get("conversation_id", "")).strip()
    if not conversation_id:
        return None
    route = {
        "mode": mode,
        "task_id": task_id,
        "goal": str(link.get("goal", "")).strip(),
        "authoritative_task_status": build_task_status_snapshot(task_id),
    }
    return emit_route_receipt(
        route,
        provider=provider,
        conversation_id=conversation_id,
        session_key=str(link.get("session_key", "")).strip(),
    )


def _maybe_notify_completion(task_id: str) -> dict | None:
    state = load_state(task_id)
    if state.status != "completed" or state.metadata.get("completion_notice_sent") is True:
        return None
    receipt = _emit_terminal_receipt(task_id, mode="task_completed_notice")
    state = load_state(task_id)
    state.metadata["completion_notice_sent"] = True
    state.metadata["completion_notice_sent_at"] = utc_now_iso()
    state.last_update_at = utc_now_iso()
    save_state(state)
    log_event(task_id, "task_completed_notice_sent", delivered=bool(receipt))
    return receipt


def _maybe_take_over_failed_task(task_id: str) -> dict | None:
    state = load_state(task_id)
    takeover = state.metadata.get("doctor_takeover", {}) or {}
    if state.status != "failed" or takeover.get("active") is True:
        return None
    receipt = _emit_terminal_receipt(task_id, mode="failed_task_doctor_takeover")
    state = load_state(task_id)
    state.status = "recovering"
    state.blockers = list(dict.fromkeys([*state.blockers, "terminal_failure_detected"]))
    state.metadata.pop("active_execution", None)
    state.metadata.pop("waiting_external", None)
    state.metadata["doctor_takeover"] = {
        "active": True,
        "reason": "terminal_failure_requires_takeover",
        "taken_over_at": utc_now_iso(),
        "notified": bool(receipt),
    }
    state.next_action = "doctor_investigating_failure"
    state.last_update_at = utc_now_iso()
    save_state(state)
    log_event(task_id, "failed_task_escalated_to_doctor", delivered=bool(receipt))
    run_system_doctor(idle_after_seconds=1, escalation_after_seconds=1)
    return receipt


def _post_process_terminal_transitions(task_id: str) -> None:
    _maybe_notify_completion(task_id)
    _maybe_take_over_failed_task(task_id)


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
                    task_id = task_root.name
                    validation = _validate_runtime_artifacts(task_id)
                    if validation:
                        results.append(validation)
                        continue
                    supervision = supervise_task(
                        task_id,
                        stale_after_seconds=max(120, min(args.stale_after_seconds, 180)),
                        escalation_after_seconds=max(300, args.stale_after_seconds),
                    )
                    if supervision.get("repair", {}).get("repaired"):
                        results.append(
                            {
                                "task_id": task_id,
                                "status": "supervisor_repaired",
                                "action": "mission_supervisor_restarted_task",
                                "supervision": supervision,
                            }
                        )
                    if not _task_artifacts_complete(task_id):
                        results.append(_invalid_task_artifact_result(task_id))
                        continue
                    try:
                        result = process_task(task_id, args.stale_after_seconds)
                        _post_process_terminal_transitions(task_id)
                        results.append(result)
                    except Exception as exc:
                        if state_path(task_id).exists():
                            try:
                                state = load_state(task_id)
                                state.status = "blocked"
                                state.next_action = "repair_runtime_failure"
                                state.blockers = [f"runtime isolated {type(exc).__name__}: {str(exc)}"]
                                state.last_update_at = utc_now_iso()
                                save_state(state)
                                log_event(task_id, "runtime_failure_isolated", error=str(exc), error_type=type(exc).__name__)
                            except Exception:
                                pass
                        results.append(
                            {
                                "task_id": task_id,
                                "status": "runtime_error_isolated",
                                "action": "isolated_runtime_failure",
                                "error": str(exc),
                                "error_type": type(exc).__name__,
                                "traceback": traceback.format_exc(limit=8),
                            }
                        )
        doctor = run_system_doctor(
            idle_after_seconds=max(60, min(args.stale_after_seconds, 180)),
            escalation_after_seconds=max(180, args.stale_after_seconds),
        )
        promotions = promote_recurring_errors()
        print(json.dumps({"processed_at": utc_now_iso(), "tasks": results, "doctor": doctor, "promotions": promotions}, ensure_ascii=False, indent=2))
        if args.once:
            return 0
        time.sleep(args.poll_seconds)


if __name__ == "__main__":
    raise SystemExit(main())
