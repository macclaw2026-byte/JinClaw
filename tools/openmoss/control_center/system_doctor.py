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
import re
import shutil
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
from research_loop import prepare_research_package
from route_guardrails import persist_route, reroot_route_if_needed
from problem_solver import solve_problem
from task_receipt_engine import emit_route_receipt
from task_status_snapshot import build_task_status_snapshot
from memory_writeback_runtime import record_memory_writeback
from governance_runtime import _build_doctor_coverage_bundle

AUTONOMY_DIR = Path("/Users/mac_claw/.openclaw/workspace/tools/openmoss/autonomy")
if str(AUTONOMY_DIR) not in sys.path:
    sys.path.insert(0, str(AUTONOMY_DIR))

from manager import LINKS_ROOT, TASKS_ROOT, load_contract, load_state, log_event, save_state, create_task_from_contract, task_dir
from learning_engine import load_task_summary
from promotion_engine import promote_doctor_strategy, resolve_doctor_strategy

DOCTOR_ROOT = CONTROL_CENTER_RUNTIME_ROOT / "doctor"
DOCTOR_HEARTBEATS_ROOT = DOCTOR_ROOT / "heartbeats"
WORKSPACE_ROOT = Path("/Users/mac_claw/.openclaw/workspace")
CONTROL_CENTER_ROOT = WORKSPACE_ROOT / "tools/openmoss/control_center"
GSTACK_REQUIRED_FILES = [
    WORKSPACE_ROOT / 'compat/gstack/README.md',
    WORKSPACE_ROOT / 'compat/gstack/intake-assessment.md',
    WORKSPACE_ROOT / 'compat/gstack/capability-map.md',
    WORKSPACE_ROOT / 'compat/gstack/routing-policy.md',
    WORKSPACE_ROOT / 'compat/gstack/prompts/jinclaw-gstack-lite.md',
    WORKSPACE_ROOT / 'compat/gstack/prompts/jinclaw-gstack-plan.md',
    WORKSPACE_ROOT / 'compat/gstack/adapters/planning.md',
    WORKSPACE_ROOT / 'compat/gstack/adapters/review.md',
    WORKSPACE_ROOT / 'compat/gstack/adapters/verification.md',
    WORKSPACE_ROOT / 'compat/gstack/adapters/security-audit.md',
    WORKSPACE_ROOT / 'compat/gstack/adapters/acp-coding-session.md',
    WORKSPACE_ROOT / 'compat/gstack/adapters/acp-dispatch-request.md',
    WORKSPACE_ROOT / 'tools/bin/jinclaw-skill-factory',
    WORKSPACE_ROOT / 'tools/bin/jinclaw-skill-doctor',
    WORKSPACE_ROOT / 'tools/openmoss/control_center/coding_session_adapter.py',
    WORKSPACE_ROOT / 'tools/openmoss/control_center/acp_dispatch_builder.py',
]
GSTACK_LIFECYCLE = ['think', 'plan', 'build', 'review', 'test', 'ship', 'reflect']

# Single-doctor architecture rule:
# JinClaw must have exactly one canonical whole-system doctor.
# Extend this file's coverage for new subsystems instead of introducing peer doctors.
# New files, features, skills, modules, bridges, schedulers, and verification paths
# should surface their health/evidence into this canonical doctor path.


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


def _semantic_tokens(text: str) -> set[str]:
    return {
        token.lower()
        for token in re.findall(r"[A-Za-z][A-Za-z0-9_-]{2,}|[\u4e00-\u9fff]{2,}", str(text or ""))
        if token.strip()
    }


def _drift_and_consistency_status(task_id: str) -> Dict[str, object]:
    """
    中文注解：
    - 功能：检查任务是否出现目标漂移或前后不一致。
    - 设计意图：
      1. 不只在“彻底卡死”时才介入；
      2. 一旦任务开始偏题、自相矛盾，就让医生提前纠偏。
    """
    contract = load_contract(task_id)
    state = load_state(task_id)
    task_summary = load_task_summary(task_id)
    goal_tokens = _semantic_tokens(contract.user_goal)
    signal_parts = [state.next_action, " ".join(state.blockers or [])]
    for stage_name in state.stage_order:
        stage = state.stages.get(stage_name)
        if not stage:
            continue
        signal_parts.append(stage.summary or "")
        signal_parts.append(stage.blocker or "")
    signal_parts.extend([str(item) for item in task_summary.get("notes", []) or [] if str(item).strip()])
    signal_text = " ".join(part for part in signal_parts if str(part).strip())
    signal_tokens = _semantic_tokens(signal_text)
    overlap = goal_tokens & signal_tokens

    inconsistency_reasons = []
    incomplete = [name for name in state.stage_order if state.stages.get(name) and state.stages[name].status != "completed"]
    milestone_stats = state.metadata.get("milestone_stats", {}) or {}
    if state.status == "completed" and incomplete:
        inconsistency_reasons.append(f"completed_with_incomplete_stages:{','.join(incomplete)}")
    if state.status == "completed" and milestone_stats and milestone_stats.get("all_required_completed") is False:
        inconsistency_reasons.append("completed_with_incomplete_required_milestones")
    if state.current_stage and state.current_stage not in state.stage_order and state.status not in {"completed", "failed"}:
        inconsistency_reasons.append("current_stage_not_in_stage_order")
    if (
        state.current_stage == "verify"
        and state.stages.get("verify")
        and state.stages["verify"].status == "completed"
        and str(state.stages["verify"].verification_status).strip() not in {"passed", "verified", "ok"}
    ):
        inconsistency_reasons.append("verify_completed_without_passed_verification_status")

    drift_detected = False
    drift_reason = ""
    if (
        len(goal_tokens) >= 2
        and len(signal_tokens) >= 4
        and not overlap
        and state.status in {"planning", "running", "recovering", "blocked"}
        and state.current_stage in {"plan", "execute", "verify"}
    ):
        drift_detected = True
        drift_reason = "goal_tokens_have_no_overlap_with_current_execution_signals"

    return {
        "goal_tokens": sorted(goal_tokens),
        "signal_tokens": sorted(signal_tokens),
        "overlap": sorted(overlap),
        "drift_detected": drift_detected,
        "drift_reason": drift_reason,
        "inconsistency_detected": bool(inconsistency_reasons),
        "inconsistency_reasons": inconsistency_reasons,
    }


def _goal_guardian_status(task_id: str, diagnosis: Dict[str, object]) -> Dict[str, object]:
    """
    中文注解：
    - 功能：汇总任务的目标守护状态。
    - 设计意图：让医生能明确知道“任务是否还在目标约束下继续推进，以及复盘是否已经落盘”。
    """
    contract = load_contract(task_id)
    control_center = (contract.metadata.get("control_center", {}) or {})
    guardian = control_center.get("goal_guardian", {}) or {}
    task_summary = load_task_summary(task_id)
    state = load_state(task_id)
    postmortem = state.metadata.get("postmortem", {}) or {}
    postmortem_written = bool(
        postmortem.get("written")
        or task_summary.get("postmortem_written")
        or str(task_summary.get("postmortem_path", "")).strip()
    )
    goal_conformance = diagnosis.get("goal_conformance", {}) or {}
    return {
        "enabled": bool(guardian.get("enabled")),
        "guardian_process": str(guardian.get("guardian_process", "system_doctor")).strip() or "system_doctor",
        "strict_continuation_required": bool(guardian.get("strict_continuation_required")),
        "require_postmortem_before_completion": bool(guardian.get("require_postmortem_before_completion")),
        "postmortem_written": postmortem_written,
        "postmortem_path": str(postmortem.get("path") or task_summary.get("postmortem_path", "") or "").strip(),
        "latest_user_goal": str(goal_conformance.get("latest_user_goal", "")).strip(),
        "bound_goal": str(goal_conformance.get("bound_goal", "")).strip(),
        "matches_latest_goal": goal_conformance.get("matches_latest_goal"),
    }


def _stuck_escalation_plan(task_id: str, diagnosis: Dict[str, object]) -> Dict[str, object]:
    """
    中文注解：
    - 功能：在任务卡壳时，为医生生成“继续研究还是请求人工”的升级方案。
    """
    contract = load_contract(task_id)
    state = load_state(task_id)
    control_center = (contract.metadata.get("control_center", {}) or {})
    intent = control_center.get("intent", {}) or {}
    approval = contract.metadata.get("approval", {}) or {}
    arbitration = control_center.get("arbitration", {}) or {}
    scout = control_center.get("resource_scout", {}) or {}
    blocker_list = list(state.blockers or [])
    problem = solve_problem(task_id, blocker_list, arbitration, approval)
    research_package = prepare_research_package(task_id, scout, intent)
    recommended_action = str(problem.get("recommended_action", "")).strip()
    learned_rule = resolve_doctor_strategy(str(diagnosis.get("reason", "")).strip())
    ask_user_actions = {
        "wait_for_or_request_approval",
        "await_human_verification_checkpoint",
        "request_authorized_configuration",
        "request_authorized_session",
    }
    deep_research_actions = {
        "research_alternative_solution",
        "needs_network_request_level_debugging",
        "investigate_frontend_binding_and_network_request_chain",
        "repair_and_retry",
        "browser_render",
        "official_source_or_authorized_session",
        "slow_down_and_switch_to_structured_source",
    }
    if learned_rule:
        mode = str(learned_rule.get("preferred_escalation_mode", "")).strip() or "continue"
    elif recommended_action in ask_user_actions:
        mode = "ask_user"
    elif (
        recommended_action in deep_research_actions
        or bool(research_package.get("enabled"))
        or bool(intent.get("requires_external_information"))
    ):
        mode = "deep_research"
    else:
        mode = "continue"
    return {
        "mode": mode,
        "recommended_action": recommended_action or "continue_current_plan",
        "learned_rule": learned_rule or {},
        "problem_analysis": problem,
        "research_package": research_package,
    }


def _record_doctor_rule(task_id: str, diagnosis: Dict[str, object], repair_reason: str, escalation_mode: str) -> Dict[str, object] | None:
    """
    中文注解：
    - 功能：把本次医生诊断与成功修复沉淀成 durable doctor rule。
    """
    doctor_reason = str(diagnosis.get("reason", "")).strip()
    if not doctor_reason or not repair_reason:
        return None
    consistency = diagnosis.get("consistency", {}) or {}
    prevention_hint = "keep goal anchor, verify every stage, and reopen the right phase instead of silently terminating"
    if doctor_reason == "goal_tokens_have_no_overlap_with_current_execution_signals":
        prevention_hint = "when execution signals no longer overlap the goal anchor, force a re-plan before continuing"
    elif doctor_reason == "completed_without_postmortem":
        prevention_hint = "do not allow completed status before learn/reflect artifacts and postmortem are written"
    elif consistency.get("inconsistency_detected"):
        prevention_hint = "when task state becomes self-contradictory, reopen verification or learning instead of trusting terminal status"
    return promote_doctor_strategy(
        doctor_reason=doctor_reason,
        preferred_repair=repair_reason,
        preferred_escalation_mode=escalation_mode,
        prevention_hint=prevention_hint,
        task_id=task_id,
        evidence={
            "idle_seconds": diagnosis.get("idle_seconds", 0),
            "current_stage": diagnosis.get("current_stage", ""),
            "status": diagnosis.get("status", ""),
        },
    )


def _goal_alignment_status(task_id: str, evidence: Dict[str, object], consistency: Dict[str, object]) -> Dict[str, object]:
    goal_conformance = evidence.get("goal_conformance", {}) or {}
    latest_user_goal = str(goal_conformance.get("latest_user_goal", "")).strip()
    bound_goal = str(goal_conformance.get("bound_goal", "")).strip()
    matched = goal_conformance.get("matches_latest_goal")
    overlap_count = len(consistency.get("overlap", []) or [])
    goal_count = len(consistency.get("goal_tokens", []) or [])
    signal_count = len(consistency.get("signal_tokens", []) or [])
    ratio = round((overlap_count / max(goal_count, 1)), 3) if goal_count else 1.0
    if goal_conformance.get("ok") is False:
        status = "mismatch"
    elif consistency.get("drift_detected"):
        status = "drifting"
    elif overlap_count:
        status = "aligned"
    elif signal_count >= 4 and goal_count >= 2:
        status = "weak_alignment"
    else:
        status = "insufficient_signal"
    return {
        "status": status,
        "matches_latest_goal": matched,
        "bound_goal": bound_goal,
        "latest_user_goal": latest_user_goal,
        "semantic_overlap_tokens": consistency.get("overlap", []),
        "semantic_overlap_ratio": ratio,
        "evidence_reason": str(goal_conformance.get("reason", "")).strip() or "goal_conformance_ok",
    }


def _stage_consistency_status(state, consistency: Dict[str, object]) -> Dict[str, object]:
    current_stage = str(state.current_stage or "").strip()
    stage_order = list(state.stage_order or [])
    pending = [name for name in stage_order if state.stages.get(name) and state.stages[name].status != "completed"]
    consistency_reasons = list(consistency.get("inconsistency_reasons", []) or [])
    if consistency_reasons:
        status = "inconsistent"
    elif current_stage and current_stage not in stage_order and state.status not in {"completed", "failed"}:
        status = "unknown_stage"
    elif pending:
        status = "active"
    else:
        status = "complete_or_ready_for_completion"
    return {
        "status": status,
        "current_stage": current_stage,
        "stage_order": stage_order,
        "pending_stages": pending,
        "inconsistency_reasons": consistency_reasons,
    }


def _completion_gate_status(task_id: str, state, diagnosis: Dict[str, object]) -> Dict[str, object]:
    guardian = diagnosis.get("goal_guardian", {}) or {}
    milestone_stats = state.metadata.get("milestone_stats", {}) or {}
    all_required_completed = milestone_stats.get("all_required_completed")
    if not guardian.get("enabled"):
        gate_status = "not_applicable"
    elif state.status != "completed":
        gate_status = "open"
    elif guardian.get("require_postmortem_before_completion") and not guardian.get("postmortem_written"):
        gate_status = "blocked_by_missing_postmortem"
    elif all_required_completed is False:
        gate_status = "blocked_by_required_milestones"
    else:
        gate_status = "satisfied"
    return {
        "status": gate_status,
        "goal_guardian_enabled": bool(guardian.get("enabled")),
        "postmortem_required": bool(guardian.get("require_postmortem_before_completion")),
        "postmortem_written": bool(guardian.get("postmortem_written")),
        "all_required_milestones_completed": all_required_completed,
        "task_status": state.status,
    }


def _build_doctor_heartbeat(task_id: str, *, idle_after_seconds: int) -> Dict[str, object]:
    state = load_state(task_id)
    evidence = build_progress_evidence(task_id, stale_after_seconds=max(60, idle_after_seconds))
    diagnosis = {
        "goal_conformance": evidence.get("goal_conformance", {}),
    }
    diagnosis["goal_guardian"] = _goal_guardian_status(task_id, diagnosis)
    consistency = _drift_and_consistency_status(task_id)
    diagnosis["consistency"] = consistency
    goal_alignment = _goal_alignment_status(task_id, evidence, consistency)
    stage_consistency = _stage_consistency_status(state, consistency)
    drift_score = round(1.0 - float(goal_alignment.get("semantic_overlap_ratio", 0.0) or 0.0), 3)
    heartbeat = {
        "task_id": task_id,
        "written_at": _utc_now_iso(),
        "task_status": state.status,
        "current_stage": state.current_stage,
        "goal_alignment": goal_alignment,
        "stage_consistency": stage_consistency,
        "drift_score": drift_score,
        "drift_detected": bool(consistency.get("drift_detected")),
        "completion_gate_status": _completion_gate_status(task_id, state, diagnosis),
        "progress_evidence": {
            "progress_state": evidence.get("progress_state", ""),
            "needs_intervention": bool(evidence.get("needs_intervention")),
            "reason": evidence.get("reason", ""),
            "idle_seconds": float(evidence.get("idle_seconds", 0) or 0),
        },
    }
    _write_json(DOCTOR_HEARTBEATS_ROOT / f"{task_id}.json", heartbeat)
    state.metadata["doctor_heartbeat"] = {
        "written_at": heartbeat["written_at"],
        "goal_alignment_status": str((goal_alignment or {}).get("status", "")).strip(),
        "stage_consistency_status": str((stage_consistency or {}).get("status", "")).strip(),
        "drift_score": float(drift_score),
        "drift_detected": bool(consistency.get("drift_detected")),
        "completion_gate_status": str(((heartbeat.get("completion_gate_status", {}) or {}).get("status", ""))).strip(),
        "progress_state": str(((heartbeat.get("progress_evidence", {}) or {}).get("progress_state", ""))).strip(),
        "needs_intervention": bool((heartbeat.get("progress_evidence", {}) or {}).get("needs_intervention")),
        "heartbeat_path": str(DOCTOR_HEARTBEATS_ROOT / f"{task_id}.json"),
    }
    state.last_update_at = heartbeat["written_at"]
    save_state(state)
    return heartbeat


def _write_doctor_heartbeats(control_plane: Dict[str, object], *, idle_after_seconds: int) -> Dict[str, object]:
    eligible_statuses = {"running", "planning", "recovering", "blocked", "verifying"}
    registry_items = list(((control_plane.get("task_registry", {}) or {}).get("items", []) or []))
    heartbeats = []
    errors = []
    for item in registry_items:
        task_id = str(item.get("canonical_task_id") or item.get("task_id") or "").strip()
        status = str(item.get("status", "")).strip()
        if not task_id or status not in eligible_statuses:
            continue
        try:
            heartbeats.append(_build_doctor_heartbeat(task_id, idle_after_seconds=idle_after_seconds))
        except Exception as exc:
            errors.append({"task_id": task_id, "error": str(exc)})
    summary = {
        "written_at": _utc_now_iso(),
        "eligible_statuses": sorted(eligible_statuses),
        "count": len(heartbeats),
        "error_count": len(errors),
        "items": heartbeats,
        "errors": errors[:20],
    }
    _write_json(DOCTOR_HEARTBEATS_ROOT / "last_cycle.json", summary)
    return summary


def _heartbeat_stability_overview(heartbeat_summary: Dict[str, object]) -> Dict[str, object]:
    items = list(heartbeat_summary.get("items", []) or [])
    goal_alignment_counts: Dict[str, int] = {}
    stage_consistency_counts: Dict[str, int] = {}
    completion_gate_counts: Dict[str, int] = {}
    intervention_total = 0
    drift_detected_total = 0
    drift_scores = []
    for item in items:
        goal_status = str(((item.get("goal_alignment", {}) or {}).get("status", ""))).strip() or "unknown"
        stage_status = str(((item.get("stage_consistency", {}) or {}).get("status", ""))).strip() or "unknown"
        gate_status = str(((item.get("completion_gate_status", {}) or {}).get("status", ""))).strip() or "unknown"
        goal_alignment_counts[goal_status] = goal_alignment_counts.get(goal_status, 0) + 1
        stage_consistency_counts[stage_status] = stage_consistency_counts.get(stage_status, 0) + 1
        completion_gate_counts[gate_status] = completion_gate_counts.get(gate_status, 0) + 1
        if bool(((item.get("progress_evidence", {}) or {}).get("needs_intervention"))):
            intervention_total += 1
        if bool(item.get("drift_detected")):
            drift_detected_total += 1
        drift_scores.append(float(item.get("drift_score", 0.0) or 0.0))
    return {
        "heartbeat_total": len(items),
        "goal_alignment_counts": goal_alignment_counts,
        "stage_consistency_counts": stage_consistency_counts,
        "completion_gate_counts": completion_gate_counts,
        "needs_intervention_total": intervention_total,
        "drift_detected_total": drift_detected_total,
        "average_drift_score": round(sum(drift_scores) / max(1, len(drift_scores)), 3),
    }


def _doctor_cycle_strategy(control_plane: Dict[str, object]) -> Dict[str, object]:
    summary = ((control_plane.get("system_snapshot", {}) or {}).get("summary", {}) or {}) if isinstance(control_plane, dict) else {}
    blocked_categories = summary.get("blocked_categories", {}) or {}
    top_blocked_category = str(summary.get("top_blocked_category", "")).strip()
    project_result_feedback_status = str(summary.get("project_result_feedback_status", "")).strip().lower()
    project_result_feedback_attention_total = int(summary.get("project_result_feedback_attention_total", 0) or 0)
    project_result_feedback_trend = str(summary.get("project_result_feedback_trend", "")).strip().lower()
    project_repair_value_status = str(summary.get("project_repair_value_status", "")).strip().lower()
    project_repair_value_trend = str(summary.get("project_repair_value_trend", "")).strip().lower()
    strategy = {
        "top_blocked_category": top_blocked_category,
        "blocked_categories": blocked_categories,
        "priority_focus": "general",
        "repair_mode": "balanced",
        "max_repairs_per_cycle": 12,
        "allowed_buckets": ["critical", "high", "medium", "low"],
    }
    if top_blocked_category in {"project_crawler_remediation", "approval_or_contract", "authorized_session", "human_checkpoint"}:
        strategy.update(
            {
                "priority_focus": "governance_blockers",
                "repair_mode": "governance_first",
                "max_repairs_per_cycle": 10,
                "allowed_buckets": ["critical", "high"],
            }
        )
    elif top_blocked_category in {"targeted_fix", "runtime_failure", "runtime_or_contract_fix"}:
        strategy.update(
            {
                "priority_focus": "repair_blockers",
                "repair_mode": "repair_first",
                "max_repairs_per_cycle": 16,
                "allowed_buckets": ["critical", "high", "medium"],
            }
        )
    elif top_blocked_category in {"session_binding", "relay_attach"}:
        strategy.update(
            {
                "priority_focus": "linkage_blockers",
                "repair_mode": "linkage_first",
                "max_repairs_per_cycle": 20,
                "allowed_buckets": ["critical", "high", "medium", "low"],
            }
        )
    if project_result_feedback_status in {"thin", "partial"} and strategy["priority_focus"] == "general":
        strategy.update(
            {
                "priority_focus": "feedback_rebuild",
                "repair_mode": "feedback_first",
                "max_repairs_per_cycle": 14,
                "allowed_buckets": ["critical", "high", "medium"],
            }
        )
    if project_result_feedback_attention_total > 0:
        strategy["repair_mode"] = "feedback_attention_first"
        strategy["max_repairs_per_cycle"] = min(int(strategy.get("max_repairs_per_cycle", 12) or 12), 10)
    elif project_result_feedback_trend == "degrading" and strategy["priority_focus"] == "general":
        strategy.update(
            {
                "priority_focus": "feedback_watch",
                "repair_mode": "feedback_trend_watch",
                "max_repairs_per_cycle": 12,
                "allowed_buckets": ["critical", "high", "medium"],
            }
        )
    if project_repair_value_status == "weak":
        strategy.update(
            {
                "priority_focus": "repair_value_rebuild",
                "repair_mode": "repair_value_first",
                "max_repairs_per_cycle": 10,
                "allowed_buckets": ["critical", "high", "medium"],
            }
        )
    elif project_repair_value_trend == "degrading" and strategy["priority_focus"] == "general":
        strategy.update(
            {
                "priority_focus": "repair_value_watch",
                "repair_mode": "repair_value_watch",
                "max_repairs_per_cycle": 12,
                "allowed_buckets": ["critical", "high", "medium"],
            }
        )
    return strategy


def _should_process_doctor_item(item: Dict[str, object], strategy: Dict[str, object], processed_total: int) -> tuple[bool, str]:
    if processed_total >= int(strategy.get("max_repairs_per_cycle", 0) or 0):
        return False, "cycle_capacity_reached"
    bucket = str(item.get("priority_bucket", "")).strip() or "low"
    allowed = {str(v).strip() for v in (strategy.get("allowed_buckets", []) or []) if str(v).strip()}
    if allowed and bucket not in allowed:
        return False, f"bucket_filtered:{bucket}"
    return True, "selected"


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
    diagnosis["goal_guardian"] = _goal_guardian_status(task_id, diagnosis)
    diagnosis["consistency"] = _drift_and_consistency_status(task_id)
    # terminal completed 不需要医生继续介入；failed 则需要医生接管而不是直接放弃。
    if state.status == "completed":
        guardian = diagnosis.get("goal_guardian", {}) or {}
        if guardian.get("enabled") and guardian.get("require_postmortem_before_completion") and not guardian.get("postmortem_written"):
            diagnosis["stuck"] = True
            diagnosis["reason"] = "completed_without_postmortem"
            diagnosis["stuck_escalation"] = _stuck_escalation_plan(task_id, diagnosis)
            return diagnosis
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
    consistency = diagnosis.get("consistency", {}) or {}
    if consistency.get("inconsistency_detected"):
        diagnosis["stuck"] = True
        diagnosis["reason"] = str((consistency.get("inconsistency_reasons") or ["state_inconsistency_detected"])[0])
        diagnosis["stuck_escalation"] = _stuck_escalation_plan(task_id, diagnosis)
        return diagnosis
    if consistency.get("drift_detected"):
        diagnosis["stuck"] = True
        diagnosis["reason"] = str(consistency.get("drift_reason") or "goal_drift_detected")
        diagnosis["stuck_escalation"] = _stuck_escalation_plan(task_id, diagnosis)
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
    if diagnosis.get("stuck"):
        diagnosis["stuck_escalation"] = _stuck_escalation_plan(task_id, diagnosis)
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
    if diagnosis.get("reason") == "completed_without_postmortem":
        learn_stage = state.stages.get("learn")
        if learn_stage:
            learn_stage.status = "pending"
            learn_stage.summary = ""
            learn_stage.verification_status = "not-run"
            learn_stage.blocker = ""
            learn_stage.completed_at = ""
            learn_stage.updated_at = _utc_now_iso()
        state.status = "planning"
        state.current_stage = "learn" if learn_stage else state.current_stage
        state.blockers = ["goal guardian requires written postmortem before completion"]
        state.next_action = f"start_stage:{state.current_stage}" if state.current_stage else "initialize"
        state.metadata.pop("completion_notice_sent", None)
        state.last_update_at = _utc_now_iso()
        save_state(state)
        log_event(task_id, "system_doctor_reopened_task_for_postmortem", diagnosis=diagnosis)
        promoted_rule = _record_doctor_rule(task_id, diagnosis, "reopened_for_postmortem", "continue")
        return {"task_id": task_id, "repaired": True, "reason": "reopened_for_postmortem", "promoted_rule": promoted_rule}
    if diagnosis.get("reason") == "goal_tokens_have_no_overlap_with_current_execution_signals":
        state.status = "planning"
        state.current_stage = "plan"
        state.blockers = ["doctor detected goal drift and forced a re-plan against the original goal anchor"]
        state.metadata["last_drift_repair"] = diagnosis.get("consistency", {})
        state.next_action = "start_stage:plan"
        state.last_update_at = _utc_now_iso()
        save_state(state)
        log_event(task_id, "system_doctor_repaired_goal_drift", diagnosis=diagnosis)
        promoted_rule = _record_doctor_rule(task_id, diagnosis, "replanned_after_goal_drift", "continue")
        return {"task_id": task_id, "repaired": True, "reason": "replanned_after_goal_drift", "promoted_rule": promoted_rule}
    if str(diagnosis.get("reason", "")).startswith("completed_with_") or str(diagnosis.get("reason", "")).startswith("verify_completed_") or diagnosis.get("reason") == "current_stage_not_in_stage_order":
        target_stage = "verify" if state.stages.get("verify") else state.first_pending_stage() or state.current_stage or "plan"
        state.status = "planning"
        state.current_stage = target_stage
        state.blockers = ["doctor detected state inconsistency and reopened the task for reconciliation"]
        state.metadata["last_consistency_repair"] = diagnosis.get("consistency", {})
        state.next_action = f"start_stage:{target_stage}"
        state.last_update_at = _utc_now_iso()
        save_state(state)
        log_event(task_id, "system_doctor_repaired_state_inconsistency", diagnosis=diagnosis)
        promoted_rule = _record_doctor_rule(task_id, diagnosis, "reopened_after_state_inconsistency", "continue")
        return {"task_id": task_id, "repaired": True, "reason": "reopened_after_state_inconsistency", "promoted_rule": promoted_rule}
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
    escalation = diagnosis.get("stuck_escalation", {}) or {}
    if escalation.get("mode") == "deep_research":
        state.status = "planning"
        state.blockers = []
        state.metadata["last_stuck_escalation"] = escalation
        state.next_action = f"start_stage:{state.current_stage}" if state.current_stage else "initialize"
        state.last_update_at = _utc_now_iso()
        save_state(state)
        log_event(task_id, "system_doctor_restarted_with_deep_research", diagnosis=diagnosis, escalation=escalation)
        promoted_rule = _record_doctor_rule(task_id, diagnosis, "restarted_with_deep_research", "deep_research")
        return {"task_id": task_id, "repaired": True, "reason": "restarted_with_deep_research", "promoted_rule": promoted_rule}
    if escalation.get("mode") == "ask_user":
        state.status = "blocked"
        state.metadata["last_stuck_escalation"] = escalation
        state.next_action = "doctor_request_human_guidance"
        state.last_update_at = _utc_now_iso()
        save_state(state)
        log_event(task_id, "system_doctor_marked_human_guidance_required", diagnosis=diagnosis, escalation=escalation)
        promoted_rule = _record_doctor_rule(task_id, diagnosis, "awaiting_human_guidance", "ask_user")
        return {"task_id": task_id, "repaired": True, "reason": "awaiting_human_guidance", "promoted_rule": promoted_rule}
    return {"task_id": task_id, "repaired": False, "reason": diagnosis.get("reason", "unhandled")}


def _run_gstack_integration_checks() -> Dict[str, object]:
    errors = []
    for path in GSTACK_REQUIRED_FILES:
        if not path.exists():
            errors.append(f'missing_required_file:{path}')
    prompt_path = WORKSPACE_ROOT / 'compat/gstack/prompts/jinclaw-gstack-lite.md'
    if prompt_path.exists():
        prompt_text = prompt_path.read_text(encoding='utf-8')
        for stage in GSTACK_LIFECYCLE:
            if stage not in prompt_text:
                errors.append(f'prompt_missing_lifecycle_stage:{stage}')
        if '## Reporting contract' not in prompt_text:
            errors.append('prompt_missing_reporting_contract')
    else:
        errors.append(f'missing_required_file:{prompt_path}')

    if str(CONTROL_CENTER_ROOT) not in sys.path:
        sys.path.insert(0, str(CONTROL_CENTER_ROOT))
    from orchestrator import build_control_center_package
    from context_builder import build_stage_context
    from coding_session_adapter import build_coding_session_payload
    from acp_dispatch_builder import build_acp_dispatch_request
    from task_contract import TaskContract
    from action_executor import _dispatch_prompt

    def _run_case(task_id: str, goal: str, expect_coding: bool) -> None:
        task_path = task_dir(task_id)
        if task_path.exists():
            shutil.rmtree(task_path)
        try:
            package = build_control_center_package(task_id, goal, source='system-doctor')
            contract = TaskContract.from_dict({
                'task_id': task_id,
                'user_goal': package['goal'],
                'done_definition': package['done_definition'],
                'allowed_tools': package.get('allowed_tools', []),
                'forbidden_actions': package.get('forbidden_actions', []),
                'stages': package['stages'],
                'metadata': package['metadata'],
            })
            create_task_from_contract(contract)
            methodology = (package.get('metadata', {}) or {}).get('control_center', {}).get('coding_methodology', {}) or {}
            state = {
                'current_stage': 'execute',
                'status': 'running',
                'next_action': 'start_stage:execute',
                'blockers': [],
                'stages': {'execute': {'attempts': 1, 'completed_subtasks': []}},
                'metadata': {},
            }
            stage_context = build_stage_context(task_id, 'execute', contract.to_dict(), state)
            payload = build_coding_session_payload(contract.to_dict(), stage_context)
            request = build_acp_dispatch_request(contract.to_dict(), stage_context)
            runtime_prompt = _dispatch_prompt(task_id, 'execute')
            if expect_coding:
                if methodology.get('methodology') != 'jinclaw-gstack-lite':
                    errors.append('coding_chain_missing_methodology_in_package')
                if methodology.get('lifecycle') != GSTACK_LIFECYCLE:
                    errors.append('coding_chain_invalid_lifecycle_in_package')
                if not payload.get('requires_prompt_injection'):
                    errors.append('coding_chain_missing_prompt_injection_flag')
                if not request.get('prompt_components', {}).get('methodology_prompt_included'):
                    errors.append('coding_chain_dispatch_missing_methodology_marker')
                if '# JinClaw GStack-Lite Coding Discipline' not in runtime_prompt:
                    errors.append('coding_chain_runtime_prompt_missing_gstack_header')
            else:
                if methodology.get('enabled') is not False:
                    errors.append('noncoding_chain_should_not_enable_coding_methodology')
                if payload.get('requires_prompt_injection'):
                    errors.append('noncoding_chain_should_not_require_prompt_injection')
                if request.get('prompt_components', {}).get('methodology_prompt_included'):
                    errors.append('noncoding_chain_dispatch_should_not_include_methodology_marker')
                if '# JinClaw GStack-Lite Coding Discipline' in runtime_prompt:
                    errors.append('noncoding_chain_runtime_prompt_should_remain_native')
        finally:
            if task_path.exists():
                shutil.rmtree(task_path)

    _run_case('doctor-coding-chain', 'Implement a code fix and add regression tests for integration doctor coverage', True)
    _run_case('doctor-optimization-chain', '优化 JinClaw 的目标守护与测试闭环，确保复杂任务更稳定', True)
    _run_case('doctor-noncoding-chain', 'Research marketplace competitors and produce a structured report', False)
    return {
        'single_doctor_rule': True,
        'authoritative_doctor': 'tools/openmoss/control_center/system_doctor.py',
        'registered_integrations': _build_doctor_coverage_bundle().get('registered_integrations', []),
        'required_files_checked': len(GSTACK_REQUIRED_FILES),
        'lifecycle': GSTACK_LIFECYCLE,
        'coding_chain': 'ok' if not any(err.startswith('coding_chain_') for err in errors) else 'error',
        'noncoding_chain': 'ok' if not any(err.startswith('noncoding_chain_') for err in errors) else 'error',
        'errors': errors,
        'ok': not errors,
    }


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
    heartbeat_summary = _write_doctor_heartbeats(control_plane, idle_after_seconds=idle_after_seconds)
    heartbeat_overview = _heartbeat_stability_overview(heartbeat_summary)
    reports = []
    doctor_items = list(control_plane.get("doctor_queue", {}).get("items", []) or [])
    doctor_strategy = _doctor_cycle_strategy(control_plane)
    seen_task_ids = set()
    processed_total = 0
    skipped_reports = []
    # doctor_queue 是 control plane 给医生的统一待办清单；
    # 医生不再自己到处翻日志，而是集中读这份汇总视图。
    for item in doctor_items:
        task_id = str(item.get("task_id", "")).strip()
        if not task_id or task_id in seen_task_ids:
            continue
        seen_task_ids.add(task_id)
        try:
            should_process, decision_reason = _should_process_doctor_item(item, doctor_strategy, processed_total)
            if not should_process:
                skipped_reports.append(
                    {
                        "task_id": task_id,
                        "priority": {
                            "score": int(item.get("priority_score", 0) or 0),
                            "bucket": str(item.get("priority_bucket", "")).strip() or "unknown",
                            "reason": str(item.get("priority_reason", "")).strip() or "unknown",
                        },
                        "skip_reason": decision_reason,
                    }
                )
                continue
            diagnosis = diagnose_task(task_id, idle_after_seconds=idle_after_seconds)
            repair = repair_task_if_possible(task_id, diagnosis)
            processed_total += 1
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
            report["priority"] = {
                "score": int(item.get("priority_score", 0) or 0),
                "bucket": str(item.get("priority_bucket", "")).strip() or "unknown",
                "reason": str(item.get("priority_reason", "")).strip() or "unknown",
            }
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
        except Exception as exc:
            reports.append(
                {
                    "task_id": task_id,
                    "doctor_internal_error": True,
                    "error": str(exc),
                    "priority": {
                        "score": int(item.get("priority_score", 0) or 0),
                        "bucket": str(item.get("priority_bucket", "")).strip() or "unknown",
                        "reason": str(item.get("priority_reason", "")).strip() or "unknown",
                    },
                }
            )
    supervisor = run_mission_supervisor(
        stale_after_seconds=max(120, idle_after_seconds),
        escalation_after_seconds=max(300, escalation_after_seconds),
    )
    integration_health = _run_gstack_integration_checks()
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
        "project_repair_value": control_plane.get("project_repair_value", {}) or {},
        "project_repair_history": (control_plane.get("project_repair_value_history", {}) or {}).get("trend", {}) or {},
        "project_repair_recommendations": (control_plane.get("project_repair_recommendations", []) or [])[:6],
        "doctor_strategy": doctor_strategy,
        "doctor_heartbeat": {
            "count": int(heartbeat_summary.get("count", 0) or 0),
            "error_count": int(heartbeat_summary.get("error_count", 0) or 0),
            "eligible_statuses": heartbeat_summary.get("eligible_statuses", []),
            "last_cycle_path": str(DOCTOR_HEARTBEATS_ROOT / "last_cycle.json"),
        },
        "stability_overview": heartbeat_overview,
        "doctor_cycle_stats": {
            "processed_total": processed_total,
            "skipped_total": len(skipped_reports),
            "max_repairs_per_cycle": int(doctor_strategy.get("max_repairs_per_cycle", 0) or 0),
        },
        "integration_health": integration_health,
        "skipped_reports": skipped_reports[:20],
        "heartbeat_sample": (heartbeat_summary.get("items", []) or [])[:10],
        "reports": reports,
        "mission_supervisor": supervisor,
    }
    try:
        from generate_doctor_dashboard import build_dashboard

        dashboard_path = DOCTOR_ROOT / "dashboard.html"
        dashboard_path.write_text(build_dashboard(), encoding="utf-8")
        result["dashboard"] = {
            "generated": True,
            "path": str(dashboard_path),
        }
    except Exception as exc:
        result["dashboard"] = {
            "generated": False,
            "error": str(exc),
        }
    _write_json(DOCTOR_ROOT / "last_run.json", result)
    return result
