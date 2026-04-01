#!/usr/bin/env python3

"""
中文说明：
- 文件路径：`tools/openmoss/control_center/system_doctor.py`
- 文件作用：系统任务级“医生”。当任务没有按预期推进时，这里负责诊断卡点、尝试修复，并在必要时向聊天窗口升级告警。
- 顶层函数：_utc_now_iso、_write_json、_seconds_since、_progress_age_seconds、diagnose_task、repair_task_if_possible、run_system_doctor。
- 顶层类：无顶层类。
- 主流程定位：
  1. 读取 control plane 和 task state；
  2. 判断任务是否真的 stuck；
  3. 如果能修，就直接把 state 拉回 planning/start_stage；
  4. 如果超过升级阈值，就通过 receipt engine 把真实诊断回给用户。
"""
from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict

from control_plane_builder import build_control_plane
from paths import CONTROL_CENTER_RUNTIME_ROOT
from mission_supervisor import run_mission_supervisor
from progress_evidence import build_progress_evidence
from brain_router import route_instruction
from response_policy_engine import build_supervisor_status_text
from route_guardrails import persist_route, reroot_route_if_needed
from task_receipt_engine import emit_route_receipt
from task_status_snapshot import build_task_status_snapshot
from memory_writeback_runtime import record_memory_writeback

AUTONOMY_DIR = Path("/Users/mac_claw/.openclaw/workspace/tools/openmoss/autonomy")
if str(AUTONOMY_DIR) not in sys.path:
    sys.path.insert(0, str(AUTONOMY_DIR))

from manager import LINKS_ROOT, TASKS_ROOT, load_state, log_event, save_state

DOCTOR_ROOT = CONTROL_CENTER_RUNTIME_ROOT / "doctor"


def _utc_now_iso() -> str:
    """
    中文注解：
    - 功能：实现 `_utc_now_iso` 对应的处理逻辑。
    - 角色：属于本模块中的内部辅助逻辑；私有函数通常服务同文件主流程，公共函数通常作为跨模块入口或能力接口。
    - 调用关系：建议结合本文件的模块说明、调用方以及同名相关辅助函数一起阅读。
    """
    return datetime.now(timezone.utc).isoformat()


def _write_json(path: Path, payload: Dict[str, object]) -> None:
    """
    中文注解：
    - 功能：实现 `_write_json` 对应的处理逻辑。
    - 角色：属于本模块中的内部辅助逻辑；私有函数通常服务同文件主流程，公共函数通常作为跨模块入口或能力接口。
    - 调用关系：建议结合本文件的模块说明、调用方以及同名相关辅助函数一起阅读。
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _seconds_since(iso_text: str) -> float:
    """
    中文注解：
    - 功能：实现 `_seconds_since` 对应的处理逻辑。
    - 角色：属于本模块中的内部辅助逻辑；私有函数通常服务同文件主流程，公共函数通常作为跨模块入口或能力接口。
    - 调用关系：建议结合本文件的模块说明、调用方以及同名相关辅助函数一起阅读。
    """
    if not iso_text:
        return 10**9
    try:
        dt = datetime.fromisoformat(str(iso_text).replace("Z", "+00:00"))
    except ValueError:
        return 10**9
    return max(0.0, (datetime.now(timezone.utc) - dt).total_seconds())


def _progress_age_seconds(*, status: str, next_action: str, last_progress_at: str, last_update_at: str) -> float:
    """
    中文注解：
    - 功能：实现 `_progress_age_seconds` 对应的处理逻辑。
    - 角色：属于本模块中的内部辅助逻辑；私有函数通常服务同文件主流程，公共函数通常作为跨模块入口或能力接口。
    - 调用关系：建议结合本文件的模块说明、调用方以及同名相关辅助函数一起阅读。
    """
    progress_age = _seconds_since(last_progress_at)
    update_age = _seconds_since(last_update_at)
    if status == "waiting_external" and next_action.startswith("poll_run:"):
        return progress_age
    return min(progress_age, update_age)


def diagnose_task(task_id: str, *, idle_after_seconds: int = 180) -> Dict[str, object]:
    """
    中文注解：
    - 功能：对单个任务做“是不是卡住了”的诊断。
    - 判断依据：
      - status / next_action
      - active_execution 是否存在
      - last_progress_at 到现在的时间
    - 输出：一个 diagnosis dict，供 repair 和用户回执复用。
    """
    state = load_state(task_id)
    age = _progress_age_seconds(
        status=state.status,
        next_action=state.next_action,
        last_progress_at=state.last_progress_at,
        last_update_at=state.last_update_at,
    )
    active_execution = state.metadata.get("active_execution", {}) or {}
    has_active_execution = bool(active_execution.get("run_id"))
    milestone_stats = state.metadata.get("milestone_stats", {}) or {}
    blocked_runtime_state = state.metadata.get("blocked_runtime_state", {}) or {}
    diagnosis = {
        "task_id": task_id,
        "status": state.status,
        "current_stage": state.current_stage,
        "next_action": state.next_action,
        "blocked_runtime_state": blocked_runtime_state,
        "idle_seconds": age,
        "has_active_execution": has_active_execution,
        "milestone_stats": milestone_stats,
        "stuck": False,
        "reason": "healthy_or_recently_updated",
    }
    evidence = build_progress_evidence(task_id, stale_after_seconds=max(60, idle_after_seconds))
    diagnosis["goal_conformance"] = evidence.get("goal_conformance", {})
    # terminal completed 不需要医生继续介入；failed 则需要医生接管而不是直接放弃。
    if state.status == "completed":
        diagnosis["reason"] = "terminal"
        return diagnosis
    if state.status == "failed":
        diagnosis["stuck"] = True
        diagnosis["reason"] = "terminal_failure_requires_takeover"
        return diagnosis
    if evidence.get("reason") == "latest_user_goal_mismatch_with_bound_task":
        diagnosis["stuck"] = True
        diagnosis["reason"] = "latest_user_goal_mismatch_with_bound_task"
        return diagnosis
    if age < idle_after_seconds:
        return diagnosis
    if not has_active_execution and state.status in {"planning", "running", "recovering"}:
        diagnosis["stuck"] = True
        diagnosis["reason"] = "idle_without_active_execution"
    elif state.status == "waiting_external" and not has_active_execution:
        diagnosis["stuck"] = True
        diagnosis["reason"] = "waiting_external_without_active_execution"
    elif state.status == "blocked":
        diagnosis["stuck"] = True
        blocked_category = str(blocked_runtime_state.get("category", "")).strip()
        diagnosis["reason"] = f"blocked:{blocked_category or state.next_action or 'unknown'}"
    elif state.next_action.startswith("poll_run:") and age >= idle_after_seconds:
        diagnosis["stuck"] = True
        diagnosis["reason"] = "stale_waiting_external"
    return diagnosis


def repair_task_if_possible(task_id: str, diagnosis: Dict[str, object]) -> Dict[str, object]:
    """
    中文注解：
    - 功能：对已确认 stuck 的任务尝试做最小代价修复。
    - 典型修复动作：
      - 清理失效的 active_execution / waiting_external
      - 把状态重新拉回 planning
      - 在 failed 时切成 doctor takeover
    - 调用关系：run_system_doctor 先诊断，再调用这里决定是否真的“动刀”。
    """
    if not diagnosis.get("stuck"):
        return {"task_id": task_id, "repaired": False, "reason": "not_stuck"}
    state = load_state(task_id)
    # 这些修复策略的共同思路是：
    # 先清掉失真的运行态，再把任务送回一个 runtime 能重新推进的安全状态。
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
    if diagnosis.get("reason") == "waiting_external_without_active_execution":
        state.status = "planning"
        state.blockers = []
        state.metadata.pop("waiting_external", None)
        state.metadata.pop("active_execution", None)
        state.metadata.pop("last_dispatched_marker", None)
        state.metadata.pop("last_dispatch_at", None)
        state.next_action = f"start_stage:{state.current_stage}" if state.current_stage else "initialize"
        state.last_update_at = _utc_now_iso()
        save_state(state)
        log_event(task_id, "system_doctor_repaired_waiting_external_without_execution", diagnosis=diagnosis)
        return {"task_id": task_id, "repaired": True, "reason": "restarted_after_waiting_external_without_execution"}
    if diagnosis.get("reason") == "stale_waiting_external":
        state.status = "planning"
        state.blockers = []
        state.metadata.pop("waiting_external", None)
        state.metadata.pop("active_execution", None)
        state.metadata.pop("last_dispatched_marker", None)
        state.metadata.pop("last_dispatch_at", None)
        state.next_action = f"start_stage:{state.current_stage}" if state.current_stage else "initialize"
        state.last_update_at = _utc_now_iso()
        save_state(state)
        log_event(task_id, "system_doctor_repaired_stale_waiting_external", diagnosis=diagnosis)
        return {"task_id": task_id, "repaired": True, "reason": "restarted_after_stale_waiting_external"}
    if diagnosis.get("reason") == "terminal_failure_requires_takeover":
        state.status = "recovering"
        state.blockers = list(dict.fromkeys([*state.blockers, "terminal_failure_detected"]))
        state.metadata.pop("active_execution", None)
        state.metadata.pop("waiting_external", None)
        state.metadata["doctor_takeover"] = {
            "active": True,
            "reason": "terminal_failure_requires_takeover",
            "taken_over_at": _utc_now_iso(),
        }
        state.next_action = "doctor_investigating_failure"
        state.last_update_at = _utc_now_iso()
        save_state(state)
        log_event(task_id, "system_doctor_took_over_failed_task", diagnosis=diagnosis)
        return {"task_id": task_id, "repaired": True, "reason": "doctor_failure_takeover_started"}
    if diagnosis.get("reason") == "latest_user_goal_mismatch_with_bound_task":
        conformance = diagnosis.get("goal_conformance", {}) or {}
        provider = str(conformance.get("provider", "")).strip()
        conversation_id = str(conformance.get("conversation_id", "")).strip()
        conversation_type = str(conformance.get("conversation_type", "")).strip() or "direct"
        latest_goal = str(conformance.get("latest_user_goal", "")).strip()
        session_key = str(conformance.get("session_key", "")).strip()
        message_id = str(conformance.get("latest_user_message_id", "")).strip()
        if not provider or not conversation_id or not latest_goal:
            return {"task_id": task_id, "repaired": False, "reason": "goal_mismatch_missing_rebind_context"}
        route = route_instruction(
            provider=provider,
            conversation_id=conversation_id,
            conversation_type=conversation_type,
            text=latest_goal,
            source="system_doctor:goal_realign",
            sender_id="user",
            sender_name="doctor-goal-realign",
            message_id=message_id,
            session_key=session_key,
        )
        route = reroot_route_if_needed(
            route=route,
            provider=provider,
            conversation_id=conversation_id,
            conversation_type=conversation_type,
            goal=str(route.get("goal") or latest_goal),
            session_key=session_key,
        )
        persist_route(provider, conversation_id, route)
        new_task_id = str(route.get("task_id", "")).strip()
        if not new_task_id or new_task_id == task_id:
            return {
                "task_id": task_id,
                "repaired": False,
                "reason": "goal_mismatch_route_did_not_realign",
                "route_mode": route.get("mode", ""),
            }
        state.status = "blocked"
        state.blockers = [f"latest user goal was reassigned to {new_task_id}"]
        state.metadata.pop("active_execution", None)
        state.metadata.pop("waiting_external", None)
        state.metadata["superseded_by_task_id"] = new_task_id
        state.next_action = f"superseded_by:{new_task_id}"
        state.last_update_at = _utc_now_iso()
        save_state(state)
        log_event(
            task_id,
            "system_doctor_repaired_goal_execution_mismatch",
            diagnosis=diagnosis,
            new_task_id=new_task_id,
            route_mode=route.get("mode", ""),
        )
        return {
            "task_id": task_id,
            "repaired": True,
            "reason": "goal_mismatch_rebound_to_latest_goal",
            "new_task_id": new_task_id,
            "route_mode": route.get("mode", ""),
        }
    return {"task_id": task_id, "repaired": False, "reason": diagnosis.get("reason", "unhandled")}


def run_system_doctor(*, idle_after_seconds: int = 180, escalation_after_seconds: int = 600) -> Dict[str, object]:
    """
    中文注解：
    - 功能：执行一轮医生巡诊。
    - 主步骤：
      1. 先读取 control plane，拿到 doctor queue；
      2. 对每个待处理任务做 diagnose + repair；
      3. 超过升级阈值的任务，向聊天窗口发 doctor diagnostic receipt；
      4. 同时运行 mission_supervisor，补充更高层的监督结果。
    - 输出：会写 `doctor/last_run.json`，也会把结果返回给 runtime 或人工检查。
    """
    control_plane = build_control_plane(
        stale_after_seconds=max(120, idle_after_seconds),
        escalation_after_seconds=max(300, escalation_after_seconds),
    )
    reports = []
    doctor_items = control_plane.get("doctor_queue", {}).get("items", [])
    seen_task_ids = set()
    # doctor_queue 是 control plane 给医生的统一待办清单；
    # 医生不再自己到处翻日志，而是集中读这份汇总视图。
    for item in doctor_items:
        task_id = str(item.get("task_id", "")).strip()
        if not task_id or task_id in seen_task_ids:
            continue
        seen_task_ids.add(task_id)
        diagnosis = diagnose_task(task_id, idle_after_seconds=idle_after_seconds)
        repair = repair_task_if_possible(task_id, diagnosis)
        writeback_summary = {
            "attention_required": bool(diagnosis.get("stuck")),
            "state_patch": {},
            "governance_patch": {},
            "next_actions": [str(repair.get("reason", "")).strip()] if str(repair.get("reason", "")).strip() and repair.get("repaired") else [],
            "warnings": [str(diagnosis.get("reason", "")).strip()] if diagnosis.get("stuck") else [],
            "errors": [],
            "decisions": [
                "doctor_diagnosis_completed",
                "doctor_repair_applied" if repair.get("repaired") else "doctor_repair_not_applied",
            ],
            "memory_targets": ["runtime", "task"] if diagnosis.get("stuck") else ["runtime"],
            "memory_reasons": ["doctor_diagnosis", "doctor_repair"] if repair.get("repaired") else ["doctor_diagnosis"],
        }
        writeback = record_memory_writeback(task_id, source="doctor:diagnosis_cycle", summary=writeback_summary)
        state = load_state(task_id)
        state.metadata["memory_writeback"] = writeback
        state.last_update_at = _utc_now_iso()
        save_state(state)
        report = {"diagnosis": diagnosis, "repair": repair}
        report["memory_writeback"] = writeback
        if diagnosis.get("stuck"):
            report["governance"] = (build_task_status_snapshot(task_id).get("governance", {}) or {})
        if diagnosis.get("stuck") and diagnosis.get("idle_seconds", 0) >= escalation_after_seconds:
            for link_path in LINKS_ROOT.glob("*.json"):
                try:
                    payload = json.loads(link_path.read_text(encoding="utf-8"))
                except (OSError, json.JSONDecodeError):
                    continue
                if payload.get("task_id") != task_id:
                    continue
                snapshot = build_task_status_snapshot(task_id)
                snapshot["authoritative_summary"] = build_supervisor_status_text(task_id, diagnosis, repair, snapshot)
                route = {
                    "mode": "doctor_diagnostic",
                    "task_id": task_id,
                    "goal": payload.get("goal", ""),
                    "authoritative_task_status": snapshot,
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
    crawler_profile = control_plane.get("crawler_capability_profile", {}) or {}
    crawler_summary = crawler_profile.get("summary", {}) or {}
    crawler_attention_sites = [
        {
            "site": site.get("site", ""),
            "readiness": site.get("readiness", ""),
            "primary_limitations": site.get("primary_limitations", []),
        }
        for site in (crawler_profile.get("sites", []) or [])
        if site.get("readiness") != "production_ready"
    ][:5]
    result = {
        "checked_at": _utc_now_iso(),
        "control_plane": {
            "system_snapshot": control_plane.get("system_snapshot", {}),
            "doctor_queue_count": len(control_plane.get("doctor_queue", {}).get("items", [])),
            "alerts_count": len(control_plane.get("alerts", {}).get("items", [])),
            "crawler_remediation_queue_count": len(control_plane.get("crawler_remediation_queue", {}).get("items", [])),
            "crawler_remediation_plan_count": len(control_plane.get("crawler_remediation_plan", {}).get("items", [])),
            "crawler_remediation_execution_count": len(control_plane.get("crawler_remediation_execution", {}).get("items", [])),
        },
        "crawler_health": {
            "summary": crawler_summary,
            "trend": crawler_profile.get("trend", {}) or {},
            "feedback": crawler_profile.get("feedback", {}) or {},
            "memory_writeback_overview": crawler_profile.get("memory_writeback_overview", {}) or {},
            "attention_sites": crawler_attention_sites,
            "recommended_project_actions": (crawler_profile.get("recommended_project_actions", []) or [])[:5],
            "priority_actions": (crawler_profile.get("priority_actions", []) or [])[:6],
            "remediation_queue": (control_plane.get("crawler_remediation_queue", {}).get("items", []) or [])[:6],
            "remediation_plan": (control_plane.get("crawler_remediation_plan", {}).get("items", []) or [])[:6],
            "remediation_execution": (control_plane.get("crawler_remediation_execution", {}).get("items", []) or [])[:6],
        },
        "reports": reports,
        "mission_supervisor": supervisor,
    }
    _write_json(DOCTOR_ROOT / "last_run.json", result)
    return result
