#!/usr/bin/env python3

"""
中文说明：
- 文件路径：`tools/openmoss/autonomy/runtime_service.py`
- 文件作用：自治运行时主循环；它把 contract/state、mission_loop、executor、doctor、recovery 串成一个真正会“持续推进任务”的后台服务。
- 顶层函数：utc_now_iso、_preflight_block_details、_preferred_browser_url、_mark_binding_required、_recover_direct_session_link、_inherit_lineage_session_link、_purge_stale_successor_business_outcome、_invalidate_contradicted_business_outcome、_sync_business_outcome_from_live_probe、_upgrade_missing_business_requirements、_apply_control_center_decision、_auto_finalize_completed_business_task、process_task、_task_artifacts_complete、_write_contract_quarantine_record、_quarantine_invalid_runtime_artifacts、_validate_runtime_artifacts、_invalid_task_artifact_result、_repair_stale_waiting_external、_emit_terminal_receipt、_maybe_notify_completion、_maybe_take_over_failed_task、_post_process_terminal_transitions、main。
- 顶层类：无顶层类。
- 主流程定位：
  1. 遍历 task；
  2. 校验 contract/state 是否有效；
  3. 运行 mission_loop 获取控制中心建议；
  4. 根据当前 state 决定是 dispatch、poll、verify、recover 还是 doctor takeover；
  5. 在 terminal 时发送 completion / failed takeover 回执。
"""
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
from verifier_registry import run_verifier

CONTROL_CENTER_DIR = Path("/Users/mac_claw/.openclaw/workspace/tools/openmoss/control_center")
if str(CONTROL_CENTER_DIR) not in sys.path:
    sys.path.insert(0, str(CONTROL_CENTER_DIR))

from mission_loop import run_mission_cycle
from browser_channel_recovery import prune_relay_tabs, recover_browser_channel, navigate_relay_to_url
from browser_task_signals import collect_browser_task_signals
from mission_supervisor import supervise_task
from orchestrator import _derive_allowed_tools, _derive_stage_contracts, _derive_task_milestones, _goal_requires_strict_continuation, build_crawler_plan, derive_business_verification_requirements
from paths import CONTRACT_QUARANTINE_ROOT
from progress_evidence import build_progress_evidence
from system_doctor import run_system_doctor
from task_receipt_engine import emit_route_receipt
from task_status_snapshot import build_task_status_snapshot


def utc_now_iso() -> str:
    """
    中文注解：
    - 功能：实现 `utc_now_iso` 对应的处理逻辑。
    - 角色：属于本模块中的对外可见逻辑；私有函数通常服务同文件主流程，公共函数通常作为跨模块入口或能力接口。
    - 调用关系：建议结合本文件的模块说明、调用方以及同名相关辅助函数一起阅读。
    """
    return datetime.now(timezone.utc).isoformat()


def _preflight_block_details(state) -> dict:
    """
    中文注解：
    - 功能：实现 `_preflight_block_details` 对应的处理逻辑。
    - 角色：属于本模块中的内部辅助逻辑；私有函数通常服务同文件主流程，公共函数通常作为跨模块入口或能力接口。
    - 调用关系：建议结合本文件的模块说明、调用方以及同名相关辅助函数一起阅读。
    """
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
    """
    中文注解：
    - 功能：实现 `_preferred_browser_url` 对应的处理逻辑。
    - 角色：属于本模块中的内部辅助逻辑；私有函数通常服务同文件主流程，公共函数通常作为跨模块入口或能力接口。
    - 调用关系：建议结合本文件的模块说明、调用方以及同名相关辅助函数一起阅读。
    """
    metadata = getattr(state, "metadata", {}) or {}
    batch_focus = metadata.get("batch_focus", {}) or {}
    if isinstance(batch_focus, dict):
        return str(batch_focus.get("expected_listings_url", "")).strip()
    return ""


def _mark_binding_required(task_id: str, reason: str) -> None:
    """
    中文注解：
    - 功能：实现 `_mark_binding_required` 对应的处理逻辑。
    - 角色：属于本模块中的内部辅助逻辑；私有函数通常服务同文件主流程，公共函数通常作为跨模块入口或能力接口。
    - 调用关系：建议结合本文件的模块说明、调用方以及同名相关辅助函数一起阅读。
    """
    state = load_state(task_id)
    state.status = "blocked"
    state.blockers = [reason]
    state.next_action = "bind_session_link"
    state.last_update_at = utc_now_iso()
    save_state(state)
    log_event(task_id, "binding_required", reason=reason)


def _recover_direct_session_link(task_id: str) -> dict | None:
    """
    中文注解：
    - 功能：实现 `_recover_direct_session_link` 对应的处理逻辑。
    - 角色：属于本模块中的内部辅助逻辑；私有函数通常服务同文件主流程，公共函数通常作为跨模块入口或能力接口。
    - 调用关系：建议结合本文件的模块说明、调用方以及同名相关辅助函数一起阅读。
    """
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
    """
    中文注解：
    - 功能：实现 `_inherit_lineage_session_link` 对应的处理逻辑。
    - 角色：属于本模块中的内部辅助逻辑；私有函数通常服务同文件主流程，公共函数通常作为跨模块入口或能力接口。
    - 调用关系：建议结合本文件的模块说明、调用方以及同名相关辅助函数一起阅读。
    """
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
    """
    中文注解：
    - 功能：实现 `_purge_stale_successor_business_outcome` 对应的处理逻辑。
    - 角色：属于本模块中的内部辅助逻辑；私有函数通常服务同文件主流程，公共函数通常作为跨模块入口或能力接口。
    - 调用关系：建议结合本文件的模块说明、调用方以及同名相关辅助函数一起阅读。
    """
    contract = load_contract(task_id)
    if _is_crawler_contract(contract):
        return None
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
    """
    中文注解：
    - 功能：实现 `_invalidate_contradicted_business_outcome` 对应的处理逻辑。
    - 角色：属于本模块中的内部辅助逻辑；私有函数通常服务同文件主流程，公共函数通常作为跨模块入口或能力接口。
    - 调用关系：建议结合本文件的模块说明、调用方以及同名相关辅助函数一起阅读。
    """
    contract = load_contract(task_id)
    if _is_crawler_contract(contract):
        return None
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
    """
    中文注解：
    - 功能：实现 `_sync_business_outcome_from_live_probe` 对应的处理逻辑。
    - 角色：属于本模块中的内部辅助逻辑；私有函数通常服务同文件主流程，公共函数通常作为跨模块入口或能力接口。
    - 调用关系：建议结合本文件的模块说明、调用方以及同名相关辅助函数一起阅读。
    """
    contract = load_contract(task_id)
    if _is_crawler_contract(contract):
        return None
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


def _is_crawler_contract(contract) -> bool:
    """
    中文注解：
    - 功能：判断当前任务是否已经切换到 crawler 子系统。
    - 设计意图：crawler 任务的完成证据来自 crawler report / retro，而不是浏览器业务探针。
    """
    crawler = contract.metadata.get("control_center", {}).get("crawler", {}) or {}
    if bool(crawler.get("enabled")):
        return True
    for stage_contract in contract.stages:
        verifier = stage_contract.verifier or {}
        checks = verifier.get("checks", []) or []
        for item in checks:
            if isinstance(item, dict) and str(item.get("type", "")).strip() == "crawler_report_complete":
                return True
    return False


def _upgrade_missing_business_requirements(task_id: str) -> dict | None:
    """
    中文注解：
    - 功能：实现 `_upgrade_missing_business_requirements` 对应的处理逻辑。
    - 角色：属于本模块中的内部辅助逻辑；私有函数通常服务同文件主流程，公共函数通常作为跨模块入口或能力接口。
    - 调用关系：建议结合本文件的模块说明、调用方以及同名相关辅助函数一起阅读。
    """
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


def _upgrade_missing_goal_decomposition(task_id: str) -> dict | None:
    """
    中文注解：
    - 功能：为旧 contract 回填 strict continuation 和 milestones。
    - 作用：让这次 milestone/verifier 修复对历史任务同样生效，而不是只覆盖新任务。
    """
    contract = load_contract(task_id)
    metadata = contract.metadata.get("control_center", {}) or {}
    intent = metadata.get("intent", {}) or {}
    mission_profile = metadata.get("mission_profile", {}) or {}
    strict = _goal_requires_strict_continuation(contract.user_goal, intent, mission_profile)
    stage_contracts = _derive_stage_contracts(
        task_id,
        {
            "goal": contract.user_goal,
            "done_definition": contract.done_definition,
            "intent": intent,
            "selected_plan": metadata.get("selected_plan", {}) or {},
            "mission_profile": mission_profile,
            "strict_continuation_required": strict,
            "approval": metadata.get("approval", {}) or {},
        },
    )
    milestones = _derive_task_milestones(task_id, contract.user_goal, intent, mission_profile)
    contract_changed = False
    if metadata.get("task_milestones") != milestones or metadata.get("strict_continuation_required") != strict:
        metadata["strict_continuation_required"] = strict
        metadata["task_milestones"] = milestones
        contract.metadata["control_center"] = metadata
        contract_changed = True
    if contract.stages != stage_contracts:
        contract.stages = stage_contracts
        contract_changed = True
    if contract_changed:
        save_contract(contract)

    state = load_state(task_id)
    progress = state.metadata.get("milestone_progress", {}) or {}
    now = utc_now_iso()
    changed = False
    for item in milestones:
        milestone_id = str(item.get("id", "")).strip()
        stage_name = str(item.get("stage", "")).strip()
        completion_mode = str(item.get("completion_mode", "stage_completion")).strip()
        if not milestone_id or milestone_id in progress:
            continue
        stage_state = state.stages.get(stage_name)
        completed = bool(stage_state and stage_state.status == "completed" and completion_mode == "stage_completion")
        progress[milestone_id] = {
            "id": milestone_id,
            "title": str(item.get("title", milestone_id)),
            "stage": stage_name,
            "required": bool(item.get("required", True)),
            "completion_mode": completion_mode,
            "status": "completed" if completed else "pending",
            "completed_at": now if completed else "",
            "summary": stage_state.summary if completed and stage_state else "",
        }
        changed = True
    if changed:
        state.metadata["milestone_progress"] = progress
        completed_required = sum(1 for item in milestones if item.get("required", True) and (progress.get(str(item.get("id", "")), {}) or {}).get("status") == "completed")
        required_total = sum(1 for item in milestones if item.get("required", True))
        state.metadata["milestone_stats"] = {
            "total": len(milestones),
            "required_total": required_total,
            "required_completed": completed_required,
            "all_required_completed": required_total == completed_required if required_total else True,
        }
        state.last_update_at = now
        save_state(state)
    elif "milestone_stats" not in state.metadata:
        completed_required = sum(1 for item in milestones if item.get("required", True) and (progress.get(str(item.get("id", "")), {}) or {}).get("status") == "completed")
        required_total = sum(1 for item in milestones if item.get("required", True))
        state.metadata["milestone_stats"] = {
            "total": len(milestones),
            "required_total": required_total,
            "required_completed": completed_required,
            "all_required_completed": required_total == completed_required if required_total else True,
        }
        state.last_update_at = now
        save_state(state)
    log_event(task_id, "goal_decomposition_upgraded", strict_continuation_required=strict, milestone_count=len(milestones))
    return {
        "task_id": task_id,
        "strict_continuation_required": strict,
        "milestone_count": len(milestones),
        "contract_changed": contract_changed,
        "state_changed": changed,
    }


def _goal_requires_crawler_system(contract, metadata: dict) -> bool:
    """
    中文注解：
    - 功能：判断旧任务是否属于“应该切换到 crawler 子系统”的抓取型任务。
    - 设计意图：不要求用户重建任务；只要旧 contract 明显在做多站点抓取/网页数据任务，就在 runtime 里自动补齐 crawler plan。
    """
    intent = metadata.get("intent", {}) or {}
    task_types = {str(item).strip().lower() for item in intent.get("task_types", []) if str(item).strip()}
    allowed_tools = {str(item).strip().lower() for item in contract.allowed_tools if str(item).strip()}
    goal = str(contract.user_goal or "").lower()
    if metadata.get("crawler", {}).get("enabled"):
        return True
    if task_types & {"web", "data", "marketplace"}:
        return True
    if any(tool in allowed_tools for tool in {"crawl4ai", "web", "search", "browser", "agent-browser", "playwright", "scrapy", "httpx", "curl_cffi", "selectolax"}):
        return True
    crawler_tokens = [
        "amazon",
        "walmart",
        "temu",
        "1688",
        "crawl",
        "scrape",
        "抓取",
        "网页",
        "website",
        "search",
        "research",
        "选品",
        "product selection",
    ]
    return any(token in goal for token in crawler_tokens)


def _upgrade_missing_crawler_system(task_id: str) -> dict | None:
    """
    中文注解：
    - 功能：为旧抓取任务补齐 crawler plan、allowed tools 和强 verifier。
    - 作用：让已经在跑、或历史上错误 completed 的抓取任务，都能切到新的 crawler 子系统，而不是只对新任务生效。
    """
    contract = load_contract(task_id)
    metadata = contract.metadata.get("control_center", {}) or {}
    if not _goal_requires_crawler_system(contract, metadata):
        return None

    intent = metadata.get("intent", {}) or {}
    mission_profile = metadata.get("mission_profile", {}) or {}
    selected_plan = metadata.get("selected_plan", {}) or {}
    approval = metadata.get("approval", {}) or {}
    domain_profile = metadata.get("domain_profile", {}) or {}
    fetch_route = metadata.get("fetch_route", {}) or {}
    challenge = metadata.get("challenge", {}) or {}
    strict = _goal_requires_strict_continuation(contract.user_goal, intent, mission_profile)
    crawler = build_crawler_plan(task_id, intent, selected_plan, domain_profile, fetch_route, challenge)
    crawler["enabled"] = True
    metadata["crawler"] = crawler
    metadata["strict_continuation_required"] = strict
    metadata["task_milestones"] = _derive_task_milestones(task_id, contract.user_goal, intent, mission_profile)
    metadata["business_verification_requirements"] = derive_business_verification_requirements(intent)
    contract.metadata["control_center"] = metadata

    derived_tools = _derive_allowed_tools(
        {
            "intent": intent,
            "selected_plan": selected_plan,
        }
    )
    crawler_tools = []
    crawler_tools.extend([str(item) for item in (crawler.get("selected_stack", {}) or {}).get("tools", []) if str(item).strip()])
    for row in crawler.get("scores", []) or []:
        crawler_tools.extend([str(item) for item in row.get("tools", []) if str(item).strip()])
    if "agent_browser" in {str(item) for item in crawler.get("requested_tools", [])}:
        crawler_tools.append("agent-browser")
    contract.allowed_tools = sorted(dict.fromkeys([*contract.allowed_tools, *derived_tools, *crawler_tools]))
    contract.stages = _derive_stage_contracts(
        task_id,
        {
            "goal": contract.user_goal,
            "done_definition": contract.done_definition,
            "intent": intent,
            "selected_plan": selected_plan,
            "mission_profile": mission_profile,
            "strict_continuation_required": strict,
            "approval": approval,
            "crawler": crawler,
        },
    )
    save_contract(contract)

    state = load_state(task_id)
    state.metadata["contract_metadata"] = contract.metadata
    state.last_update_at = utc_now_iso()
    save_state(state)
    log_event(
        task_id,
        "crawler_system_upgraded",
        selected_stack=(crawler.get("selected_stack", {}) or {}).get("stack_id", ""),
        fallback_stacks=crawler.get("fallback_stacks", []),
        allowed_tools=contract.allowed_tools,
    )
    return {
        "task_id": task_id,
        "selected_stack": (crawler.get("selected_stack", {}) or {}).get("stack_id", ""),
        "fallback_stacks": crawler.get("fallback_stacks", []),
        "allowed_tools": contract.allowed_tools,
    }


def _reopen_incomplete_terminal_crawler_task(task_id: str) -> dict | None:
    """
    中文注解：
    - 功能：如果旧抓取任务被过早标成 terminal，但缺少 crawler 报告/retro 证据，就把它拉回执行。
    - 设计意图：修掉“回答得很好但提前停下来了”的旧问题，让错误 completed 的抓取任务重新进入执行链。
    """
    contract = load_contract(task_id)
    crawler = contract.metadata.get("control_center", {}).get("crawler", {}) or {}
    if not bool(crawler.get("enabled")):
        return None
    state = load_state(task_id)
    if state.status not in {"completed", "failed"}:
        return None

    report_result = run_verifier({"type": "crawler_report_complete", "task_id": task_id})
    retro_required = bool((crawler.get("loop_contract", {}) or {}).get("retro_required"))
    retro_result = run_verifier({"type": "crawler_retro_complete", "task_id": task_id}) if retro_required else {"ok": True}

    target_stage = ""
    reason = ""
    if not report_result.get("ok"):
        target_stage = "execute"
        reason = "missing_crawler_report"
    elif retro_required and not retro_result.get("ok"):
        target_stage = "learn"
        reason = "missing_crawler_retro"
    if not target_stage:
        return None

    for stage_name in ("execute", "verify", "learn"):
        stage = state.stages.get(stage_name)
        if not stage:
            continue
        if stage_name == target_stage or (target_stage == "execute" and stage_name in {"verify", "learn"}):
            stage.status = "pending"
            stage.summary = ""
            stage.verification_status = "not-run"
            stage.blocker = ""
            stage.completed_at = ""
            stage.updated_at = utc_now_iso()
    if target_stage == "execute":
        state.metadata.pop("business_outcome", None)
        state.metadata.pop("crawler_execution", None)
        state.metadata.pop("output_artifacts", None)
        state.metadata.pop("delivery_artifacts", None)
    state.status = "planning"
    state.current_stage = target_stage
    state.next_action = f"start_stage:{target_stage}"
    state.blockers = []
    state.last_update_at = utc_now_iso()
    save_state(state)
    log_event(
        task_id,
        "terminal_crawler_task_reopened",
        reason=reason,
        target_stage=target_stage,
        report_status=report_result.get("status"),
        retro_status=retro_result.get("status"),
    )
    return {
        "task_id": task_id,
        "reason": reason,
        "target_stage": target_stage,
    }


def _apply_control_center_decision(task_id: str, state, mission_cycle: dict) -> dict | None:
    """
    中文注解：
    - 功能：实现 `_apply_control_center_decision` 对应的处理逻辑。
    - 角色：属于本模块中的内部辅助逻辑；私有函数通常服务同文件主流程，公共函数通常作为跨模块入口或能力接口。
    - 调用关系：建议结合本文件的模块说明、调用方以及同名相关辅助函数一起阅读。
    """
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
    """
    中文注解：
    - 功能：实现 `_auto_finalize_completed_business_task` 对应的处理逻辑。
    - 角色：属于本模块中的内部辅助逻辑；私有函数通常服务同文件主流程，公共函数通常作为跨模块入口或能力接口。
    - 调用关系：建议结合本文件的模块说明、调用方以及同名相关辅助函数一起阅读。
    """
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
    """
    中文注解：
    - 功能：runtime 对单个任务执行一整轮状态推进。
    - 可以把它看成任务实例的主状态机：
      - 先做 contract/state 的收口和纠偏
      - 再跑 mission_loop 拿到 next_decision
      - 再根据当前 status 选择 dispatch / poll / verify / recovery / doctor takeover
    - 调用关系：main 循环遍历 tasks 时，真正推进每个任务的入口就是这里。
    """
    _upgrade_missing_business_requirements(task_id)
    _upgrade_missing_goal_decomposition(task_id)
    _upgrade_missing_crawler_system(task_id)
    contract = load_contract(task_id)
    state = load_state(task_id)
    reopened_terminal_crawler = _reopen_incomplete_terminal_crawler_task(task_id)
    if reopened_terminal_crawler:
        contract = load_contract(task_id)
        state = load_state(task_id)
    progress_evidence = build_progress_evidence(task_id, stale_after_seconds=stale_after_seconds)
    if progress_evidence.get("reason") == "latest_user_goal_mismatch_with_bound_task":
        state.status = "recovering"
        state.blockers = ["latest user goal no longer matches this executing task"]
        state.metadata["goal_conformance"] = progress_evidence.get("goal_conformance", {})
        state.metadata.pop("active_execution", None)
        state.metadata.pop("waiting_external", None)
        state.metadata.pop("last_dispatched_marker", None)
        state.metadata.pop("last_dispatch_at", None)
        state.next_action = "doctor_align_latest_user_goal"
        state.last_update_at = utc_now_iso()
        save_state(state)
        log_event(
            task_id,
            "goal_execution_mismatch_detected",
            goal_conformance=progress_evidence.get("goal_conformance", {}),
        )
        return {
            "task_id": task_id,
            "status": state.status,
            "current_stage": state.current_stage,
            "next_action": state.next_action,
            "action": "goal_execution_mismatch_detected",
            "goal_conformance": progress_evidence.get("goal_conformance", {}),
        }
    purged_business_outcome = _purge_stale_successor_business_outcome(task_id)
    if purged_business_outcome:
        state = load_state(task_id)
    invalidated_business_outcome = _invalidate_contradicted_business_outcome(task_id)
    if invalidated_business_outcome:
        state = load_state(task_id)
    # mission_loop 负责出“参谋意见”，但真正改 state 的人还是 runtime。
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
        and state.status not in {"planning", "running"}
    ):
        return control_center_result
    # terminal task 在这里先短路返回，后面的 terminal 回执由 post_process 阶段统一处理。
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

    # recovering 分支是 runtime 的自救通道：这里会根据 next_action 进入更细的恢复动作。
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

    # waiting_external / poll_run 是外部 run 仍在执行或看起来仍在执行的状态。
    # runtime 会先做 stale 判断，再决定继续 poll 还是直接重启该阶段。
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

    # verify 阶段使用结构化 verifier，不再继续沿普通 execute 链推进。
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
        if _is_crawler_contract(contract):
            dispatch = dispatch_stage(task_id)
            state = load_state(task_id)
            return {
                "task_id": task_id,
                "status": state.status,
                "current_stage": state.current_stage,
                "next_action": state.next_action,
                "action": "crawler_learn_dispatched",
                "dispatch": dispatch,
                "mission_cycle": mission_cycle,
            }
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
    # 真正把当前 stage 派发给 AI agent 的路径在这里：
    # runtime -> action_executor.dispatch_stage -> gateway.chat.send / agent.wait
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
    """
    中文注解：
    - 功能：实现 `_task_artifacts_complete` 对应的处理逻辑。
    - 角色：属于本模块中的内部辅助逻辑；私有函数通常服务同文件主流程，公共函数通常作为跨模块入口或能力接口。
    - 调用关系：建议结合本文件的模块说明、调用方以及同名相关辅助函数一起阅读。
    """
    if not (contract_path(task_id).exists() and state_path(task_id).exists()):
        return False
    try:
        payload = json.loads(contract_path(task_id).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return False
    return all(str(payload.get(field, "")).strip() for field in ("task_id", "user_goal", "done_definition"))


def _write_contract_quarantine_record(task_id: str, *, artifact: str, error: Exception | str) -> str:
    """
    中文注解：
    - 功能：实现 `_write_contract_quarantine_record` 对应的处理逻辑。
    - 角色：属于本模块中的内部辅助逻辑；私有函数通常服务同文件主流程，公共函数通常作为跨模块入口或能力接口。
    - 调用关系：建议结合本文件的模块说明、调用方以及同名相关辅助函数一起阅读。
    """
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
    """
    中文注解：
    - 功能：实现 `_quarantine_invalid_runtime_artifacts` 对应的处理逻辑。
    - 角色：属于本模块中的内部辅助逻辑；私有函数通常服务同文件主流程，公共函数通常作为跨模块入口或能力接口。
    - 调用关系：建议结合本文件的模块说明、调用方以及同名相关辅助函数一起阅读。
    """
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
    """
    中文注解：
    - 功能：实现 `_validate_runtime_artifacts` 对应的处理逻辑。
    - 角色：属于本模块中的内部辅助逻辑；私有函数通常服务同文件主流程，公共函数通常作为跨模块入口或能力接口。
    - 调用关系：建议结合本文件的模块说明、调用方以及同名相关辅助函数一起阅读。
    """
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
    """
    中文注解：
    - 功能：实现 `_invalid_task_artifact_result` 对应的处理逻辑。
    - 角色：属于本模块中的内部辅助逻辑；私有函数通常服务同文件主流程，公共函数通常作为跨模块入口或能力接口。
    - 调用关系：建议结合本文件的模块说明、调用方以及同名相关辅助函数一起阅读。
    """
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
    """
    中文注解：
    - 功能：实现 `_repair_stale_waiting_external` 对应的处理逻辑。
    - 角色：属于本模块中的内部辅助逻辑；私有函数通常服务同文件主流程，公共函数通常作为跨模块入口或能力接口。
    - 调用关系：建议结合本文件的模块说明、调用方以及同名相关辅助函数一起阅读。
    """
    evidence = build_progress_evidence(task_id, stale_after_seconds=stale_after_seconds)
    if evidence.get("progress_state") not in {"stalled_waiting_external", "waiting_external_without_execution"}:
        return None
    state = load_state(task_id)
    state.status = "planning"
    state.blockers = []
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
    """
    中文注解：
    - 功能：实现 `_emit_terminal_receipt` 对应的处理逻辑。
    - 角色：属于本模块中的内部辅助逻辑；私有函数通常服务同文件主流程，公共函数通常作为跨模块入口或能力接口。
    - 调用关系：建议结合本文件的模块说明、调用方以及同名相关辅助函数一起阅读。
    """
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
    """
    中文注解：
    - 功能：任务首次进入 completed 时，自动给当前绑定聊天渠道发完成通知。
    - 关键点：这里只在首次通知时写 `completion_notice_sent`，避免 completed 任务被 runtime 每轮重复提醒。
    """
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
    """
    中文注解：
    - 功能：实现 `_maybe_take_over_failed_task` 对应的处理逻辑。
    - 角色：属于本模块中的内部辅助逻辑；私有函数通常服务同文件主流程，公共函数通常作为跨模块入口或能力接口。
    - 调用关系：建议结合本文件的模块说明、调用方以及同名相关辅助函数一起阅读。
    """
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
    """
    中文注解：
    - 功能：统一处理 terminal 收尾逻辑。
    - 当前包含：
      - completed -> completion notice
      - failed -> doctor takeover
    - 调用关系：main 每轮推进完单个 task 后都会调用这里，确保 terminal 变化不会静默发生。
    """
    _maybe_notify_completion(task_id)
    _maybe_take_over_failed_task(task_id)


def main() -> int:
    """
    中文注解：
    - 功能：实现 `main` 对应的处理逻辑。
    - 角色：属于本模块中的对外可见逻辑；私有函数通常服务同文件主流程，公共函数通常作为跨模块入口或能力接口。
    - 调用关系：建议结合本文件的模块说明、调用方以及同名相关辅助函数一起阅读。
    """
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
