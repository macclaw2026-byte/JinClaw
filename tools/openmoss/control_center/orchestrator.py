#!/usr/bin/env python3

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List

from approval_gate import review_plan
from adoption_flow import build_adoption_flow
from adaptive_fetch_router import build_fetch_route
from bdi_state import build_bdi_state
from capability_registry import build_capability_registry
from challenge_classifier import classify_challenge
from authorized_session_manager import build_authorized_session_plan
from domain_profile_store import build_domain_profile
from event_bus import publish_event
from external_tool_scorer import score_external_options
from fractal_decomposer import build_fractal_loops
from htn_planner import build_htn_tree, select_htn_focus
from intent_analyzer import analyze_intent
from paths import MISSIONS_ROOT
from plan_reselector import reselect_plan
from proposal_judge import judge_proposals
from human_checkpoint import build_human_checkpoint
from resource_scout import build_resource_scout_brief
from solution_arbitrator import arbitrate_solution_path
from stpa_auditor import audit_mission
from topology_mapper import build_topology
from workflow_planner import build_workflow_blueprint


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _write_json(path: Path, payload) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _derive_allowed_tools(blueprint: Dict[str, object]) -> List[str]:
    tools = ["rg"]
    intent = blueprint.get("intent", {})
    if intent.get("needs_browser"):
        tools.extend(["browser", "agent-browser"])
    if intent.get("requires_external_information"):
        tools.extend(["web", "search", "crawl4ai"])
    if "web" in intent.get("task_types", []) or "data" in intent.get("task_types", []):
        tools.append("crawl4ai")
    return sorted(dict.fromkeys(tools))


def _merge_inherited_intent(intent: Dict[str, object], inherited_intent: Dict[str, object] | None) -> Dict[str, object]:
    if not inherited_intent:
        return intent
    merged = dict(intent)
    inherited_task_types = [str(item) for item in inherited_intent.get("task_types", []) if str(item)]
    current_task_types = [str(item) for item in intent.get("task_types", []) if str(item)]
    if current_task_types == ["general"] and inherited_task_types and inherited_task_types != ["general"]:
        merged["task_types"] = inherited_task_types
    for key in ("keywords", "domains", "likely_platforms"):
        merged[key] = sorted(
            dict.fromkeys(
                [str(item) for item in intent.get(key, []) if str(item)]
                + [str(item) for item in inherited_intent.get(key, []) if str(item)]
            )
        )
    for key in ("requires_external_information", "may_download_artifacts", "may_execute_external_code", "needs_browser", "needs_verification"):
        merged[key] = bool(intent.get(key) or inherited_intent.get(key))
    if str(intent.get("risk_level", "low")).lower() == "low":
        merged["risk_level"] = inherited_intent.get("risk_level", intent.get("risk_level", "low"))
    inherited_constraints = [str(item) for item in inherited_intent.get("hard_constraints", []) if str(item)]
    current_constraints = [str(item) for item in intent.get("hard_constraints", []) if str(item)]
    merged["hard_constraints"] = sorted(dict.fromkeys(current_constraints + inherited_constraints))
    return merged


def _requires_explicit_business_proof(intent: Dict[str, object], selected_plan: Dict[str, object]) -> bool:
    task_types = {str(item).strip().lower() for item in intent.get("task_types", []) if str(item).strip()}
    goal = str(intent.get("goal", "")).lower()
    return bool(
        intent.get("needs_browser")
        and (
            "marketplace" in task_types
            or "image" in task_types
            or any(token in goal for token in ["upload", "上传", "product", "详情页", "detail page", "image area", "图片区"])
            or str(selected_plan.get("plan_id", "")) == "local_image_pipeline"
        )
    )


def _business_outcome_verifier(task_id: str) -> Dict[str, object]:
    return {
        "type": "all",
        "checks": [
            {"type": "task_state_metadata_equals", "task_id": task_id, "field": "business_outcome.goal_satisfied", "equals": True},
            {"type": "task_state_metadata_equals", "task_id": task_id, "field": "business_outcome.user_visible_result_confirmed", "equals": True},
            {"type": "task_state_metadata_nonempty", "task_id": task_id, "field": "business_outcome.proof_summary"},
        ],
    }


def derive_business_verification_requirements(intent: Dict[str, object]) -> Dict[str, object]:
    goal = str(intent.get("goal", "") or "")
    goal_lower = goal.lower()
    requirements: Dict[str, object] = {}
    normalized_goal = goal.replace(" ", "")
    batch_draft_listings_goal = (
        ("draft" in goal_lower or "草稿" in goal or "listing页面所有draft" in normalized_goal or "所有draft状态" in normalized_goal)
        and ("listing" in goal_lower or "listing页面" in normalized_goal or "seller" in goal_lower or "seller中心" in normalized_goal)
    )

    if batch_draft_listings_goal:
        return {
            "draft_visible_count_at_most": 0,
            "batch_listings_mode": True,
        }

    if any(token in goal for token in ["至少3张场景图", "至少 3 张场景图", "至少三张场景图", "至少 3 张"]):
        requirements["scene_image_count_at_least"] = 3
    if any(token in goal for token in ["排到前面", "排到最前", "第8张"]):
        requirements["scene_image_position_max"] = 3
    if "packing unit" in goal_lower or "补齐缺失参数" in goal:
        requirements["packing_units_at_least"] = 1
        requirements["form_must_be_valid"] = True
    if any(token in goal for token in ["提交审核", "提审", "submit for review"]):
        requirements["review_status_not_in"] = ["DRAFT"]
        requirements["form_must_be_valid"] = True

    return requirements


def _derive_stage_contracts(task_id: str, blueprint: Dict[str, object]) -> List[Dict[str, object]]:
    intent = blueprint["intent"]
    selected_plan = blueprint["selected_plan"]
    approval = blueprint["approval"]
    pending_approvals = approval.get("pending", [])
    require_business_proof = _requires_explicit_business_proof(intent, selected_plan)
    execute_policy = {
        "approval_requirements": list(approval.get("decisions", {}).keys()),
        "approval_pending_ids": pending_approvals,
        "auto_complete_on_wait_ok": True,
    }
    verify_verifier = {
        "type": "all",
        "checks": [
            {"type": "command_exit_zero", "command": ["/bin/zsh", "-lc", "test -d /Users/mac_claw/.openclaw/workspace"]},
        ],
    }
    execute_verifier: Dict[str, object] = {}
    if require_business_proof:
        execute_policy["require_verifier_before_complete"] = True
        execute_verifier = _business_outcome_verifier(task_id)
        verify_verifier = _business_outcome_verifier(task_id)
    return [
        {
            "name": "understand",
            "goal": "Analyze the instruction, constraints, desired outcome, and security posture",
            "expected_output": "structured mission brief",
            "acceptance_check": "mission brief written into task metadata",
            "execution_policy": {"auto_complete_on_wait_ok": True},
        },
        {
            "name": "plan",
            "goal": "Compare multiple safe execution plans and select the best approved path",
            "expected_output": "candidate plan set and chosen plan",
            "acceptance_check": "selected plan recorded with alternatives",
            "execution_policy": {"auto_complete_on_wait_ok": True},
        },
        {
            "name": "execute",
            "goal": f"Execute the selected plan safely: {selected_plan.get('summary', '')}",
            "expected_output": "real progress toward the user goal with evidence",
            "acceptance_check": "execution evidence recorded without violating security boundaries and business completion proof captured when required",
            "verifier": execute_verifier,
            "execution_policy": execute_policy,
        },
        {
            "name": "verify",
            "goal": "Verify the goal is actually satisfied and the path stayed within security policy",
            "expected_output": "verification decision and evidence",
            "acceptance_check": "verifier passes with business-level proof when required and no unresolved approval or security blockers remain",
            "verifier": verify_verifier,
            "execution_policy": {"auto_complete_on_wait_ok": False},
        },
        {
            "name": "learn",
            "goal": "Persist lessons, promoted rules, and reusable guidance",
            "expected_output": "updated learning artifacts and task summary",
            "acceptance_check": "learning artifacts written successfully",
            "execution_policy": {"auto_complete_on_wait_ok": True},
        },
    ]


def build_control_center_package(task_id: str, goal: str, *, source: str = "manual", inherited_intent: Dict[str, object] | None = None) -> Dict[str, object]:
    raw_intent = analyze_intent(goal, source=source)
    intent = _merge_inherited_intent(raw_intent, inherited_intent)
    capabilities = build_capability_registry()
    blueprint = build_workflow_blueprint(intent, capabilities)
    judgment = judge_proposals(intent, capabilities, blueprint["candidate_plans"])
    tool_scores = score_external_options(task_id, intent, blueprint["candidate_plans"], capabilities)
    reselection = reselect_plan(task_id, intent, blueprint["candidate_plans"], judgment, tool_scores)
    selected_plan = reselection["final_selected_plan"]
    scored_by_id = {str(item.get("plan_id", "")): item for item in judgment.get("scores", [])}
    judgment["final_selected_plan"] = selected_plan
    judgment["final_selected_score"] = scored_by_id.get(str(selected_plan.get("plan_id", "")), judgment.get("selected_score", {}))
    approval = review_plan(task_id, selected_plan)
    tool_score_map = {str(item.get("plan_id", "")): item for item in tool_scores.get("scores", [])}
    adoption_flow = build_adoption_flow(task_id, selected_plan, approval, tool_score_map.get(str(selected_plan.get("plan_id", "")), {}))
    domain_profile = build_domain_profile(task_id, intent)
    challenge = classify_challenge(task_id, [], {"status": "planning", "current_stage": "understand"})
    authorized_session = build_authorized_session_plan(task_id, intent, challenge)
    human_checkpoint = build_human_checkpoint(task_id, challenge)
    fetch_route = build_fetch_route(task_id, intent, selected_plan, domain_profile, challenge)
    business_verification_requirements = derive_business_verification_requirements(intent)
    topology = build_topology(intent, selected_plan)
    fractal = build_fractal_loops(intent, selected_plan, topology)
    htn = build_htn_tree(intent, selected_plan, topology, fractal)
    initial_htn_focus = select_htn_focus(htn, "understand", 0)
    stpa = audit_mission(intent, selected_plan, topology, approval)
    scout = build_resource_scout_brief(intent, selected_plan, domain_profile, fetch_route)
    arbitration = arbitrate_solution_path(intent, selected_plan, approval, capabilities)
    initial_bdi = build_bdi_state(intent, selected_plan, approval, {"current_stage": "understand", "status": "planning", "blockers": []}, initial_htn_focus, arbitration)
    mission = {
        "task_id": task_id,
        "created_at": _utc_now_iso(),
        "intent": intent,
        "capabilities": capabilities,
        "candidate_plans": blueprint["candidate_plans"],
        "selected_plan": selected_plan,
        "proposal_judgment": judgment,
        "tool_scores": tool_scores,
        "reselection": reselection,
        "topology": topology,
        "fractal_loops": fractal,
        "htn": htn,
        "initial_bdi": initial_bdi,
        "stpa": stpa,
        "approval": approval,
        "domain_profile": domain_profile,
        "challenge": challenge,
        "authorized_session": authorized_session,
        "human_checkpoint": human_checkpoint,
        "fetch_route": fetch_route,
        "business_verification_requirements": business_verification_requirements,
        "resource_scout": scout,
        "arbitration": arbitration,
        "adoption_flow": adoption_flow,
    }
    should_clone_capability = selected_plan.get("plan_id") == "in_house_capability_rebuild"
    if should_clone_capability:
        clone_event = publish_event("capability.clone_requested", {"task_id": task_id, "mission": mission})
        mission["capability_clone"] = clone_event.get("emitted_hooks", [{}])[0].get("clone", {}) if clone_event.get("emitted_hooks") else {}
    _write_json(MISSIONS_ROOT / f"{task_id}.json", mission)
    publish_event("mission.built", {"task_id": task_id, "mission": mission})
    if reselection.get("switched"):
        publish_event("plan.reselected", {"task_id": task_id, "mission": mission, "reselection": reselection})
    metadata = {
        "control_center": {
            "mission_path": str(MISSIONS_ROOT / f"{task_id}.json"),
            "raw_intent": raw_intent,
            "inherited_intent": inherited_intent or {},
            "intent": intent,
            "candidate_plans": blueprint["candidate_plans"],
            "selected_plan": selected_plan,
            "proposal_judgment": judgment,
            "tool_scores": tool_scores,
            "reselection": reselection,
            "capabilities_snapshot": blueprint["capabilities_snapshot"],
            "topology": topology,
            "fractal_loops": fractal,
            "htn": htn,
            "initial_bdi": initial_bdi,
            "stpa": stpa,
            "domain_profile": domain_profile,
            "challenge": challenge,
            "authorized_session": authorized_session,
            "human_checkpoint": human_checkpoint,
            "fetch_route": fetch_route,
            "business_verification_requirements": business_verification_requirements,
            "resource_scout": scout,
            "arbitration": arbitration,
            "adoption_flow": adoption_flow,
            "capability_clone": mission.get("capability_clone", {}),
        },
        "approval": approval,
        "security": {
            "principle": "solve_by_all_reasonable_means_without_crossing_security_boundaries",
            "pending_approvals": approval.get("pending", []),
        },
        "created_by": source,
    }
    return {
        "task_id": task_id,
        "goal": goal,
        "done_definition": intent["done_definition"],
        "hard_constraints": intent["hard_constraints"],
        "allowed_tools": _derive_allowed_tools({**blueprint, "intent": intent, "selected_plan": selected_plan}),
        "stages": _derive_stage_contracts(task_id, {**blueprint, "approval": approval, "intent": intent, "selected_plan": selected_plan}),
        "metadata": metadata,
        "mission_path": str(MISSIONS_ROOT / f"{task_id}.json"),
    }


def main() -> int:
    import argparse

    parser = argparse.ArgumentParser(description="Build a single control-center task package from a goal")
    parser.add_argument("--task-id", required=True)
    parser.add_argument("--goal", required=True)
    parser.add_argument("--source", default="manual")
    args = parser.parse_args()
    print(json.dumps(build_control_center_package(args.task_id, args.goal, source=args.source), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
