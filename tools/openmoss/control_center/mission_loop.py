#!/usr/bin/env python3
# RULES-FIRST NOTICE:
# Before modifying this file, first read:
# - `JINCLAW_CONSTITUTION.md`
# - `AI_OPTIMIZATION_FRAMEWORK.md`
# Follow the constitution and framework:
# brain-first, one-doctor, fail-closed, evidence-over-narration,
# validate locally, then use the required PR workflow.
"""
中文说明：
- 文件路径：`tools/openmoss/control_center/mission_loop.py`
- 文件作用：负责控制中心的“每轮巡航决策”，把静态 contract 和动态 state 重新拼成下一步行动建议。
- 顶层函数：_load_json、_write_json、_load_live_approval、_ensure_cognitive_maps、_force_browser_batch_plan、run_mission_cycle、main。
- 顶层类：无顶层类。
- 主流程定位：
  1. 读取当前 mission 快照与实时审批信息。
  2. 补齐拓扑、分形循环、HTN、风险、授权会话、browser signals 等认知图谱。
  3. 综合当前 stage、challenge、approval、business signals 生成 `next_decision`。
  4. runtime_service 再把这个决策翻译成真正的状态迁移或执行动作。
"""
from __future__ import annotations

import json
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict

from adoption_flow import build_adoption_flow
from adaptive_fetch_router import build_fetch_route
from advisory_engine import build_advisory
from authorized_session_manager import build_authorized_session_plan
from bdi_state import build_bdi_state
from browser_task_signals import collect_browser_task_signals
from challenge_classifier import classify_challenge
from context_builder import build_stage_context
from crawler_layer import build_crawler_plan
from domain_profile_store import build_domain_profile
from execution_governor import build_project_crawler_gate, summarize_governance_attention
from event_bus import publish_event
from external_tool_scorer import score_external_options
from forensic_simulator import reconstruct_trace
from htn_planner import build_htn_tree, select_htn_focus_by_cursor
from paths import APPROVALS_ROOT, MISSIONS_ROOT
from plan_reselector import reselect_plan
from problem_solver import solve_problem
from research_loop import prepare_research_package
from resource_scout import build_resource_scout_brief
from summary_compressor import compress_mission
from stpa_auditor import audit_mission
from solution_arbitrator import arbitrate_solution_path
from topology_mapper import build_topology
from fractal_decomposer import build_fractal_loops
from human_checkpoint import build_human_checkpoint
from orchestrator import _derive_knowledge_basis, _derive_plan_reviews

AUTONOMY_DIR = Path("/Users/mac_claw/.openclaw/workspace/tools/openmoss/autonomy")
if str(AUTONOMY_DIR) not in __import__("sys").path:
    __import__("sys").path.insert(0, str(AUTONOMY_DIR))

from manager import apply_hook_effects


def _load_json(path: Path) -> Dict[str, object]:
    """
    中文注解：
    - 功能：实现 `_load_json` 对应的处理逻辑。
    - 角色：属于本模块中的内部辅助逻辑；私有函数通常服务同文件主流程，公共函数通常作为跨模块入口或能力接口。
    - 调用关系：建议结合本文件的模块说明、调用方以及同名相关辅助函数一起阅读。
    """
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, payload: Dict[str, object]) -> None:
    """
    中文注解：
    - 功能：实现 `_write_json` 对应的处理逻辑。
    - 角色：属于本模块中的内部辅助逻辑；私有函数通常服务同文件主流程，公共函数通常作为跨模块入口或能力接口。
    - 调用关系：建议结合本文件的模块说明、调用方以及同名相关辅助函数一起阅读。
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _load_live_approval(task_id: str, mission: Dict[str, object]) -> Dict[str, object]:
    """
    中文注解：
    - 功能：实现 `_load_live_approval` 对应的处理逻辑。
    - 角色：属于本模块中的内部辅助逻辑；私有函数通常服务同文件主流程，公共函数通常作为跨模块入口或能力接口。
    - 调用关系：建议结合本文件的模块说明、调用方以及同名相关辅助函数一起阅读。
    """
    live = _load_json(APPROVALS_ROOT / f"{task_id}.json")
    return live or mission.get("approval", {})


def _doctor_heartbeat_guard(mission: Dict[str, object]) -> Dict[str, object]:
    runtime_state = mission.get("runtime_state", {}) or {}
    heartbeat = (runtime_state.get("doctor_heartbeat", {}) or {})
    goal_alignment_status = str(heartbeat.get("goal_alignment_status", "")).strip()
    stage_consistency_status = str(heartbeat.get("stage_consistency_status", "")).strip()
    completion_gate_status = str(heartbeat.get("completion_gate_status", "")).strip()
    drift_detected = bool(heartbeat.get("drift_detected"))
    drift_score = float(heartbeat.get("drift_score", 0.0) or 0.0)
    allowed = True
    blockers = []
    if not heartbeat:
        return {
            "heartbeat_present": False,
            "allow_dynamic_reselection": True,
            "reason": "no_heartbeat_available_yet",
        }
    if drift_detected or drift_score >= 0.95:
        allowed = False
        blockers.append("doctor heartbeat reports active or near-active drift")
    if stage_consistency_status in {"inconsistent", "unknown_stage"}:
        allowed = False
        blockers.append("doctor heartbeat reports stage inconsistency")
    if completion_gate_status in {"blocked_by_missing_postmortem", "blocked_by_required_milestones"}:
        allowed = False
        blockers.append("completion gate is not satisfied")
    if goal_alignment_status == "mismatch":
        allowed = False
        blockers.append("goal alignment is mismatched")
    return {
        "heartbeat_present": True,
        "allow_dynamic_reselection": allowed,
        "goal_alignment_status": goal_alignment_status,
        "stage_consistency_status": stage_consistency_status,
        "completion_gate_status": completion_gate_status,
        "drift_detected": drift_detected,
        "drift_score": drift_score,
        "blockers": blockers,
        "reason": "guard_passed" if allowed else "guard_blocked",
    }


def _seconds_until(iso_text: str) -> float:
    if not iso_text:
        return 0.0
    try:
        dt = datetime.fromisoformat(str(iso_text).replace("Z", "+00:00"))
    except ValueError:
        return 0.0
    return max(0.0, (dt - datetime.now(timezone.utc)).total_seconds())


def _plan_transition_cooldown_guard(mission: Dict[str, object]) -> Dict[str, object]:
    runtime_state = mission.get("runtime_state", {}) or {}
    cooldown = (runtime_state.get("plan_transition_cooldown", {}) or {})
    cooldown_until = str(cooldown.get("cooldown_until", "")).strip()
    remaining_seconds = round(_seconds_until(cooldown_until), 3)
    active = remaining_seconds > 0
    return {
        "cooldown_present": bool(cooldown),
        "active": active,
        "cooldown_until": cooldown_until,
        "remaining_seconds": remaining_seconds,
        "reason": "cooldown_active_after_rollback" if active else "cooldown_not_active",
        "restored_plan_id": str(cooldown.get("restored_plan_id", "")).strip(),
        "rollback_reasons": list(cooldown.get("rollback_reasons", []) or []),
    }


def _post_cooldown_stability_guard(heartbeat_guard: Dict[str, object], cooldown_guard: Dict[str, object]) -> Dict[str, object]:
    if cooldown_guard.get("active"):
        return {
            "required": True,
            "stable_enough": False,
            "reason": "cooldown_still_active",
        }
    if not cooldown_guard.get("cooldown_present"):
        return {
            "required": False,
            "stable_enough": True,
            "reason": "no_recent_rollback",
        }
    drift_score = float(heartbeat_guard.get("drift_score", 0.0) or 0.0)
    goal_alignment_status = str(heartbeat_guard.get("goal_alignment_status", "")).strip()
    stage_consistency_status = str(heartbeat_guard.get("stage_consistency_status", "")).strip()
    completion_gate_status = str(heartbeat_guard.get("completion_gate_status", "")).strip()
    stable_enough = (
        goal_alignment_status in {"aligned", "weak_alignment", "insufficient_signal"}
        and stage_consistency_status not in {"inconsistent", "unknown_stage"}
        and completion_gate_status not in {"blocked_by_missing_postmortem", "blocked_by_required_milestones"}
        and drift_score < 0.55
    )
    return {
        "required": True,
        "stable_enough": stable_enough,
        "drift_score_threshold": 0.55,
        "goal_alignment_status": goal_alignment_status,
        "stage_consistency_status": stage_consistency_status,
        "completion_gate_status": completion_gate_status,
        "drift_score": drift_score,
        "reason": "post_cooldown_stability_passed" if stable_enough else "post_cooldown_stability_not_ready",
    }


def _maybe_rollback_plan_transition(mission: Dict[str, object], candidate_plans: list[Dict[str, object]], selected_plan: Dict[str, object]) -> tuple[Dict[str, object], Dict[str, object]]:
    runtime_state = mission.get("runtime_state", {}) or {}
    snapshot = (runtime_state.get("last_plan_transition_snapshot", {}) or {})
    heartbeat = (runtime_state.get("doctor_heartbeat", {}) or {})
    previous_plan_id = str(snapshot.get("previous_plan_id", "")).strip()
    current_plan_id = str((selected_plan or {}).get("plan_id", "")).strip()
    heartbeat_status = {
        "goal_alignment_status": str(heartbeat.get("goal_alignment_status", "")).strip(),
        "stage_consistency_status": str(heartbeat.get("stage_consistency_status", "")).strip(),
        "completion_gate_status": str(heartbeat.get("completion_gate_status", "")).strip(),
        "drift_detected": bool(heartbeat.get("drift_detected")),
        "drift_score": float(heartbeat.get("drift_score", 0.0) or 0.0),
        "progress_state": str(heartbeat.get("progress_state", "")).strip(),
        "needs_intervention": bool(heartbeat.get("needs_intervention")),
    }
    should_rollback = False
    rollback_reasons = []
    if snapshot and previous_plan_id and current_plan_id and previous_plan_id != current_plan_id:
        if heartbeat_status["goal_alignment_status"] == "mismatch":
            should_rollback = True
            rollback_reasons.append("goal_alignment_degraded_after_plan_transition")
        if heartbeat_status["stage_consistency_status"] in {"inconsistent", "unknown_stage"}:
            should_rollback = True
            rollback_reasons.append("stage_consistency_degraded_after_plan_transition")
        if heartbeat_status["drift_detected"] or heartbeat_status["drift_score"] >= 0.95:
            should_rollback = True
            rollback_reasons.append("drift_detected_after_plan_transition")
    if not should_rollback:
        return selected_plan, {
            "performed": False,
            "reason": "no_safe_rollback_needed",
            "heartbeat_status": heartbeat_status,
            "previous_plan_id": previous_plan_id,
            "current_plan_id": current_plan_id,
        }
    by_plan = {str(plan.get("plan_id", "")).strip(): plan for plan in candidate_plans or [] if str(plan.get("plan_id", "")).strip()}
    rollback_plan = deepcopy(by_plan.get(previous_plan_id, {})) if previous_plan_id in by_plan else {}
    if not rollback_plan:
        return selected_plan, {
            "performed": False,
            "reason": "rollback_candidate_not_found",
            "heartbeat_status": heartbeat_status,
            "previous_plan_id": previous_plan_id,
            "current_plan_id": current_plan_id,
            "rollback_reasons": rollback_reasons,
        }
    return rollback_plan, {
        "performed": True,
        "reason": "rolled_back_to_previous_plan_after_degradation",
        "heartbeat_status": heartbeat_status,
        "previous_plan_id": previous_plan_id,
        "current_plan_id": current_plan_id,
        "rollback_reasons": rollback_reasons,
        "restored_plan_id": previous_plan_id,
    }


def _ensure_cognitive_maps(mission: Dict[str, object]) -> Dict[str, object]:
    """
    中文注解：
    - 功能：确保 mission 拥有后续决策所需的认知地图。
    - 这里会补齐或刷新：
      - tool_scores / reselection
      - topology / fractal_loops / htn
      - stpa / arbitration / adoption_flow
      - capability_clone / domain_profile
    - 调用关系：run_mission_cycle 进入主判断前一定先过这里，否则后面的 `next_decision` 只能基于残缺数据做判断。
    """
    intent = mission.get("intent", {})
    selected_plan = mission.get("selected_plan", {})
    candidate_plans = mission.get("candidate_plans", [])
    capabilities = mission.get("capabilities", {})
    live_status = str((mission.get("runtime_state", {}) or {}).get("status", "")).strip().lower()
    dynamic_reselection_statuses = {"planning", "running", "recovering", "blocked", "verifying"}
    refresh_dynamic_reselection = live_status in dynamic_reselection_statuses
    heartbeat_guard = _doctor_heartbeat_guard(mission)
    cooldown_guard = _plan_transition_cooldown_guard(mission)
    post_cooldown_stability = _post_cooldown_stability_guard(heartbeat_guard, cooldown_guard)
    previous_selected_plan_id = str((selected_plan or {}).get("plan_id", "")).strip()
    # 如果 mission 是从旧快照恢复出来的，这些图谱可能并不完整；
    # 这里的职责就是把“可推导但尚未落盘”的认知结构补全。
    if candidate_plans and (refresh_dynamic_reselection or not mission.get("tool_scores")):
        mission["tool_scores"] = score_external_options(str(mission.get("task_id", "mission")), intent, candidate_plans, capabilities)
    if (
        candidate_plans
        and mission.get("proposal_judgment")
        and (refresh_dynamic_reselection or not mission.get("reselection"))
        and heartbeat_guard.get("allow_dynamic_reselection", True)
        and not cooldown_guard.get("active")
        and post_cooldown_stability.get("stable_enough", True)
    ):
        mission["reselection"] = reselect_plan(
            str(mission.get("task_id", "mission")),
            intent,
            candidate_plans,
            mission.get("proposal_judgment", {}),
            mission.get("tool_scores", {"scores": []}),
        )
        mission["dynamic_reselection"] = {
            "refreshed": True,
            "refreshed_at": str((mission.get("runtime_state", {}) or {}).get("updated_at", "")).strip()
            or mission.get("generated_at", "")
            or mission.get("updated_at", ""),
            "runtime_status": live_status,
            "heartbeat_guard": heartbeat_guard,
            "cooldown_guard": cooldown_guard,
            "post_cooldown_stability": post_cooldown_stability,
        }
    elif refresh_dynamic_reselection:
        blocked_reason = str(heartbeat_guard.get("reason", "")).strip() or "dynamic_reselection_blocked"
        if cooldown_guard.get("active"):
            blocked_reason = str(cooldown_guard.get("reason", "")).strip() or "dynamic_reselection_cooldown_active"
        elif post_cooldown_stability.get("required") and not post_cooldown_stability.get("stable_enough", True):
            blocked_reason = str(post_cooldown_stability.get("reason", "")).strip() or "post_cooldown_stability_not_ready"
        mission["dynamic_reselection"] = {
            "refreshed": False,
            "refreshed_at": str((mission.get("runtime_state", {}) or {}).get("updated_at", "")).strip()
            or mission.get("generated_at", "")
            or mission.get("updated_at", ""),
            "runtime_status": live_status,
            "heartbeat_guard": heartbeat_guard,
            "cooldown_guard": cooldown_guard,
            "post_cooldown_stability": post_cooldown_stability,
            "blocked_reason": blocked_reason,
        }
    reselection = mission.get("reselection", {})
    final_selected_plan = reselection.get("final_selected_plan", {}) if reselection else {}
    selected_plan_changed = False
    if final_selected_plan and final_selected_plan.get("plan_id") and final_selected_plan.get("plan_id") != selected_plan.get("plan_id"):
        mission["selected_plan"] = deepcopy(final_selected_plan)
        selected_plan = mission["selected_plan"]
        selected_plan_changed = True
        mission["plan_transition_guard"] = {
            "allowed": True,
            "previous_plan_id": previous_selected_plan_id,
            "new_plan_id": str((selected_plan or {}).get("plan_id", "")).strip(),
            "heartbeat_guard": heartbeat_guard,
            "transition_reason": str((reselection.get("switch_reason", "") if isinstance(reselection, dict) else "")).strip(),
        }
    elif refresh_dynamic_reselection:
        mission["plan_transition_guard"] = {
            "allowed": False,
            "previous_plan_id": previous_selected_plan_id,
            "new_plan_id": previous_selected_plan_id,
            "heartbeat_guard": heartbeat_guard,
            "cooldown_guard": cooldown_guard,
            "post_cooldown_stability": post_cooldown_stability,
            "transition_reason": "no_safe_plan_transition",
        }
    rollback_plan, rollback_status = _maybe_rollback_plan_transition(mission, candidate_plans, selected_plan)
    if rollback_status.get("performed"):
        mission["selected_plan"] = deepcopy(rollback_plan)
        selected_plan = mission["selected_plan"]
        selected_plan_changed = True
    mission["plan_rollback_guard"] = rollback_status
    if selected_plan_changed or not mission.get("topology"):
        mission["topology"] = build_topology(intent, selected_plan)
    if selected_plan_changed or not mission.get("fractal_loops"):
        mission["fractal_loops"] = build_fractal_loops(intent, selected_plan, mission["topology"])
    if selected_plan_changed or not mission.get("htn"):
        mission["htn"] = build_htn_tree(intent, selected_plan, mission["topology"], mission["fractal_loops"])
    mission["stpa"] = audit_mission(intent, selected_plan, mission["topology"], mission.get("approval", {}))
    if selected_plan_changed or not mission.get("plan_reviews"):
        mission["plan_reviews"] = _derive_plan_reviews(
            intent,
            candidate_plans,
            selected_plan,
            mission.get("governance", {}) or {},
        )
    if selected_plan_changed or not mission.get("resource_scout"):
        mission["resource_scout"] = build_resource_scout_brief(
            intent,
            selected_plan,
            mission.get("domain_profile", {}) or {},
            mission.get("fetch_route", {}) or {},
        )
    if selected_plan_changed or not mission.get("knowledge_basis"):
        mission["knowledge_basis"] = _derive_knowledge_basis(
            intent,
            selected_plan,
            mission.get("resource_scout", {}) or {},
            mission.get("fetch_route", {}) or {},
        )
    arbitration = mission.get("arbitration", {})
    if selected_plan_changed or not arbitration or "necessity_proof" not in arbitration:
        mission["arbitration"] = arbitrate_solution_path(
            intent,
            selected_plan,
            mission.get("approval", {}),
            capabilities,
            knowledge_basis=mission.get("knowledge_basis", {}) or {},
            plan_reviews=mission.get("plan_reviews", {}) or {},
            governance=mission.get("governance", {}) or {},
        )
    if not mission.get("adoption_flow"):
        tool_score_map = {str(item.get("plan_id", "")): item for item in mission.get("tool_scores", {}).get("scores", [])}
        mission["adoption_flow"] = build_adoption_flow(
            str(mission.get("task_id", "mission")),
            selected_plan,
            mission.get("approval", {}),
            tool_score_map.get(str(selected_plan.get("plan_id", "")), {}),
        )
    if selected_plan.get("plan_id") == "in_house_capability_rebuild" and not mission.get("capability_clone"):
        clone_event = publish_event("capability.clone_requested", {"task_id": str(mission.get("task_id", "mission")), "mission": mission})
        mission["capability_clone"] = clone_event.get("emitted_hooks", [{}])[0].get("clone", {}) if clone_event.get("emitted_hooks") else {}
    if not mission.get("domain_profile"):
        mission["domain_profile"] = build_domain_profile(str(mission.get("task_id", "mission")), intent)
    return mission


def _force_browser_batch_plan(mission: Dict[str, object]) -> Dict[str, object]:
    """
    中文注解：
    - 功能：实现 `_force_browser_batch_plan` 对应的处理逻辑。
    - 角色：属于本模块中的内部辅助逻辑；私有函数通常服务同文件主流程，公共函数通常作为跨模块入口或能力接口。
    - 调用关系：建议结合本文件的模块说明、调用方以及同名相关辅助函数一起阅读。
    """
    intent = mission.get("intent", {}) or {}
    normalized_goal = str(intent.get("goal", "") or "").replace(" ", "")
    is_batch_marketplace_browser = (
        bool(intent.get("needs_browser"))
        and "marketplace" in {str(item) for item in intent.get("task_types", [])}
        and ("draft" in normalized_goal.lower() or "listing页面" in normalized_goal or "seller" in normalized_goal.lower())
    )
    if not is_batch_marketplace_browser:
        return mission
    candidate_plans = mission.get("candidate_plans", []) or []
    browser_plan = next((plan for plan in candidate_plans if plan.get("plan_id") == "browser_evidence"), None)
    if not browser_plan:
        return mission
    if mission.get("selected_plan", {}).get("plan_id") == "browser_evidence":
        return mission
    mission["selected_plan"] = browser_plan
    mission["topology"] = build_topology(intent, browser_plan)
    mission["fractal_loops"] = build_fractal_loops(intent, browser_plan, mission["topology"])
    mission["htn"] = build_htn_tree(intent, browser_plan, mission["topology"], mission["fractal_loops"])
    mission["stpa"] = audit_mission(intent, browser_plan, mission["topology"], mission.get("approval", {}))
    mission["plan_reviews"] = _derive_plan_reviews(
        intent,
        candidate_plans,
        browser_plan,
        mission.get("governance", {}) or {},
    )
    mission["resource_scout"] = build_resource_scout_brief(
        intent,
        browser_plan,
        mission.get("domain_profile", {}) or build_domain_profile(str(mission.get("task_id", "mission")), intent),
        mission.get("fetch_route", {}) or {},
    )
    mission["knowledge_basis"] = _derive_knowledge_basis(
        intent,
        browser_plan,
        mission.get("resource_scout", {}) or {},
        mission.get("fetch_route", {}) or {},
    )
    mission["arbitration"] = arbitrate_solution_path(
        intent,
        browser_plan,
        mission.get("approval", {}),
        mission.get("capabilities", {}),
        knowledge_basis=mission.get("knowledge_basis", {}) or {},
        plan_reviews=mission.get("plan_reviews", {}) or {},
        governance=mission.get("governance", {}) or {},
    )
    mission["adoption_flow"] = build_adoption_flow(
        str(mission.get("task_id", "mission")),
        browser_plan,
        mission.get("approval", {}),
        {},
    )
    mission["fetch_route"] = build_fetch_route(
        str(mission.get("task_id", "mission")),
        intent,
        browser_plan,
        mission.get("domain_profile", {}) or build_domain_profile(str(mission.get("task_id", "mission")), intent),
        mission.get("challenge", {}) or classify_challenge(str(mission.get("task_id", "mission")), [], {"status": "planning", "current_stage": "execute"}),
    )
    mission["capability_clone"] = {}
    return mission


def _hook_next_actions(event_result: Dict[str, object]) -> list[str]:
    control_center_dir = Path("/Users/mac_claw/.openclaw/workspace/tools/openmoss/control_center")
    if str(control_center_dir) not in __import__("sys").path:
        __import__("sys").path.insert(0, str(control_center_dir))
    from event_bus import summarize_hook_effects

    return list((summarize_hook_effects(event_result) or {}).get("next_actions", []) or [])


def run_mission_cycle(task_id: str, contract: Dict[str, object], state: Dict[str, object]) -> Dict[str, object]:
    """
    中文注解：
    - 功能：执行一轮 control center 决策循环，产出当前任务“下一步该怎么做”的判断结果。
    - 输入：task_id、contract、state。
    - 输出：包含 summary、challenge、browser_signals、next_decision 等信息的 mission_cycle 结果。
    - 调用关系：runtime_service.process_task 每轮都会调这里；可以把它看成 runtime 在正式改 state 之前的“参谋部”。
    """
    mission = _load_json(MISSIONS_ROOT / f"{task_id}.json")
    if not mission:
        return {"task_id": task_id, "status": "no_mission_package"}
    mission["runtime_state"] = {
        "status": state.get("status", ""),
        "current_stage": state.get("current_stage", ""),
        "next_action": state.get("next_action", ""),
        "updated_at": state.get("last_update_at", ""),
        "doctor_heartbeat": ((state.get("metadata", {}) or {}).get("doctor_heartbeat", {}) or {}),
        "plan_transition_cooldown": ((state.get("metadata", {}) or {}).get("plan_transition_cooldown", {}) or {}),
        "last_plan_rollback_snapshot": ((state.get("metadata", {}) or {}).get("last_plan_rollback_snapshot", {}) or {}),
    }
    mission["approval"] = _load_live_approval(task_id, mission)
    mission = _ensure_cognitive_maps(mission)
    mission = _force_browser_batch_plan(mission)
    # 先把 mission 和 state 压成一份短摘要，后面 AI 执行包、状态回复、医生回执都会复用这份摘要。
    summary = compress_mission(task_id, mission, state)
    current_stage = state.get("current_stage", "") or (state.get("stage_order", [""])[0] if state.get("stage_order") else "")
    # challenge 是运行态问题分类器的结果：
    # 它决定当前更像是业务推进、浏览器问题、审批阻塞还是需要更深的请求链调试。
    challenge = classify_challenge(task_id, state.get("blockers", []), state)
    challenge_event = {}
    if challenge.get("challenge_type") not in {"", "none"}:
        challenge_event = publish_event("challenge.detected", {"task_id": task_id, "mission": mission, "challenge": challenge})
        apply_hook_effects(task_id, challenge_event, source="mission:challenge")
    mission["challenge"] = challenge
    if challenge_event:
        mission["challenge_hook"] = challenge_event
    mission["authorized_session"] = build_authorized_session_plan(task_id, mission.get("intent", {}), challenge)
    mission["human_checkpoint"] = build_human_checkpoint(task_id, challenge)
    mission["fetch_route"] = build_fetch_route(task_id, mission.get("intent", {}), mission.get("selected_plan", {}), mission.get("domain_profile", {}), challenge)
    mission["crawler"] = build_crawler_plan(
        task_id,
        mission.get("intent", {}),
        mission.get("selected_plan", {}),
        mission.get("domain_profile", {}),
        mission.get("fetch_route", {}),
        challenge,
    )
    mission["resource_scout"] = prepare_research_package(task_id, build_resource_scout_brief(mission.get("intent", {}), mission.get("selected_plan", {}), mission.get("domain_profile", {}), mission.get("fetch_route", {})), mission.get("intent", {}))
    browser_signals = collect_browser_task_signals(task_id)
    _write_json(MISSIONS_ROOT / f"{task_id}.json", mission)
    context_packet = build_stage_context(task_id, current_stage, contract, state) if current_stage else {}
    stage_state = state.get("stages", {}).get(current_stage, {}) if current_stage else {}
    stage_attempts = int(stage_state.get("attempts", 0) or 0) if current_stage else 0
    subtask_cursor = int(stage_state.get("subtask_cursor", max(stage_attempts - 1, 0)) or 0) if current_stage else 0
    htn_focus = select_htn_focus_by_cursor(mission.get("htn", {}), current_stage, subtask_cursor) if current_stage else {}
    bdi = build_bdi_state(mission.get("intent", {}), mission.get("selected_plan", {}), mission.get("approval", {}), state, htn_focus, mission.get("arbitration", {}))
    research = mission.get("resource_scout", {})
    problem = solve_problem(task_id, state.get("blockers", []), mission.get("arbitration", {}), mission.get("approval", {}))
    advisory = build_advisory(task_id, mission, state)
    forensic = reconstruct_trace(task_id, state)
    pending_approvals = mission.get("approval", {}).get("pending", [])
    necessity_proof = mission.get("arbitration", {}).get("necessity_proof", {})
    governance_attention = summarize_governance_attention((context_packet.get("governance", {}) or {}))
    permission_status = str(governance_attention.get("permission_overall_status", "")).strip()
    project_crawler_gate = build_project_crawler_gate(mission, context_packet, governance_attention, current_stage)
    # 下面这段分支就是 mission loop 最关键的输出：`next_decision`。
    # 它并不直接改 state，而是先表达“控制中心建议接下来怎么做”，
    # 然后 runtime_service 再依据这个建议去改变状态或触发执行。
    if state.get("status") == "blocked" and state.get("next_action") == "bind_session_link":
        next_decision = {
            "action": "bind_session_link",
            "reason": "execution requires a bound session before autonomous continuation can proceed",
        }
    elif permission_status == "blocked":
        next_decision = {
            "action": "await_approval_or_contract_fix",
            "reason": "governance permission decision currently blocks execution until contract or policy issues are fixed",
            "auto_safe": True,
        }
    elif mission.get("human_checkpoint", {}).get("required"):
        next_decision = {
            "action": "await_human_verification_checkpoint",
            "reason": "the current web challenge requires human completion before safe continuation",
            "auto_safe": True,
        }
    elif mission.get("authorized_session", {}).get("needs_authorized_session"):
        next_decision = {
            "action": "request_authorized_session",
            "reason": "this task now requires an isolated approved authorized session",
            "auto_safe": True,
        }
    elif project_crawler_gate:
        next_decision = project_crawler_gate
    elif current_stage and state.get("status") == "blocked" and state.get("next_action") == "await_approval_or_contract_fix" and not pending_approvals:
        next_decision = {
            "action": f"advance_stage:{current_stage}",
            "reason": "required approvals are now satisfied, so the blocked stage can resume safely",
            "auto_safe": True,
        }
    elif pending_approvals:
        next_decision = {
            "action": "await_or_request_approval",
            "reason": "high-risk external actions remain gated by approval",
            "pending_approvals": pending_approvals,
            "auto_safe": True,
        }
    elif bdi.get("current_intention") == "prove_necessity_before_switching":
        next_decision = {
            "action": "prove_necessity_before_switching",
            "reason": "the current intention is to keep the safer route until the higher-risk path is justified",
            "auto_safe": True,
        }
    elif (
        browser_signals.get("requirements_evaluation", {}).get("ok") is True
        and browser_signals.get("requirements_evaluation", {}).get("status") != "no_explicit_requirements"
    ):
        learn_pending = bool(state.get("stages", {}).get("learn", {}).get("status") != "completed")
        next_decision = {
            "action": "advance_stage:learn" if learn_pending else "confirm_business_outcome_and_finalize",
            "reason": "browser-observed business requirements are fully satisfied, so the task should finalize and learn",
            "auto_safe": True,
        }
    elif browser_signals.get("diagnosis") not in {"", "none"}:
        recommended_action = (
            str(browser_signals.get("recommended_action", "")).strip()
            or problem.get("recommended_action", "needs_network_request_level_debugging")
        )
        next_decision = {
            "action": recommended_action,
            "reason": "browser-observed evidence produced a concrete recovery or continuation action",
            "auto_safe": recommended_action in {
                "reacquire_browser_channel",
                "needs_network_request_level_debugging",
                "investigate_frontend_binding_and_network_request_chain",
                "normalize_invalid_numeric_fields_then_resubmit",
                "repair_form_validation_then_retry_submit",
                "confirm_business_outcome_and_finalize",
                "continue_current_plan",
                "process_next_draft_listing",
                "return_to_listings_overview_and_retry_batch_probe",
                "await_relay_attach_checkpoint",
            },
        }
    elif current_stage == "execute" and htn_focus.get("focus_node", {}).get("node_id"):
        next_decision = {
            "action": f"advance_subtask:{htn_focus['focus_node']['node_id']}",
            "reason": "the HTN focus identifies the next execution subtask to advance",
            "auto_safe": True,
        }
    elif bdi.get("current_intention") == "complete_verification":
        next_decision = {
            "action": "advance_stage:verify",
            "reason": "the current cognitive intention is to complete verification",
            "auto_safe": True,
        }
    elif state.get("status") == "recovering":
        next_decision = {
            "action": problem.get("recommended_action", "diagnose_and_retry"),
            "reason": "task is recovering and should follow the problem solver recommendation",
            "auto_safe": problem.get("recommended_action") in {"repair_and_retry", "apply_permission_recovery", "reacquire_browser_channel"},
        }
    elif _hook_next_actions(challenge_event):
        next_decision = {
            "action": _hook_next_actions(challenge_event)[0],
            "reason": "challenge hook produced a concrete next action that should override generic monitoring",
            "auto_safe": True,
        }
    elif current_stage and state.get("status") in {"planning", "running"}:
        next_decision = {
            "action": f"advance_stage:{current_stage}",
            "reason": "current stage can continue using the minimal context packet",
            "auto_safe": True,
        }
    else:
        next_decision = {
            "action": "monitor",
            "reason": "no stronger automated action was inferred in this cycle",
            "auto_safe": True,
        }
    next_decision["governance_attention"] = governance_attention
    return {
        "task_id": task_id,
        "summary": summary,
        "context_packet": context_packet,
        "governance_attention": governance_attention,
        "research": research,
        "htn": mission.get("htn", {}),
        "htn_focus": htn_focus,
        "bdi": bdi,
        "stpa": mission.get("stpa", {}),
        "necessity_proof": necessity_proof,
        "reselection": mission.get("reselection", {}),
        "tool_scores": mission.get("tool_scores", {}),
        "dynamic_reselection": mission.get("dynamic_reselection", {}),
        "plan_transition_guard": mission.get("plan_transition_guard", {}),
        "plan_rollback_guard": mission.get("plan_rollback_guard", {}),
        "adoption_flow": mission.get("adoption_flow", {}),
        "capability_clone": mission.get("capability_clone", {}),
        "domain_profile": mission.get("domain_profile", {}),
        "challenge": mission.get("challenge", {}),
        "authorized_session": mission.get("authorized_session", {}),
        "human_checkpoint": mission.get("human_checkpoint", {}),
        "fetch_route": mission.get("fetch_route", {}),
        "crawler": mission.get("crawler", {}),
        "browser_signals": browser_signals,
        "problem_solver": problem,
        "advisory": advisory,
        "forensic": forensic,
        "next_decision": next_decision,
    }


def main() -> int:
    """
    中文注解：
    - 功能：实现 `main` 对应的处理逻辑。
    - 角色：属于本模块中的对外可见逻辑；私有函数通常服务同文件主流程，公共函数通常作为跨模块入口或能力接口。
    - 调用关系：建议结合本文件的模块说明、调用方以及同名相关辅助函数一起阅读。
    """
    import argparse

    parser = argparse.ArgumentParser(description="Run one control-center mission cycle")
    parser.add_argument("--task-id", required=True)
    parser.add_argument("--contract-json", required=True)
    parser.add_argument("--state-json", required=True)
    args = parser.parse_args()
    print(json.dumps(run_mission_cycle(args.task_id, json.loads(args.contract_json), json.loads(args.state_json)), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
