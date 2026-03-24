#!/usr/bin/env python3

from __future__ import annotations

import json
from typing import Dict, List

from necessity_prover import prove_plan_necessity
from plan_history import load_history_profile


def _estimate_plan_risk(plan: Dict[str, object]) -> float:
    risk = 0.0
    for action in plan.get("external_actions", []):
        action_type = str(action.get("type", ""))
        risk += {
            "public_read": 1.0,
            "public_download": 3.0,
            "dependency_install": 4.0,
            "external_code_execution": 5.0,
        }.get(action_type, 1.0)
    if plan.get("plan_id") == "in_house_capability_rebuild":
        risk -= 1.0
    return max(risk, 0.0)


def _estimate_plan_efficiency(plan: Dict[str, object], intent: Dict[str, object], capabilities: Dict[str, object]) -> float:
    task_types = set(str(item) for item in intent.get("task_types", []))
    plan_id = str(plan.get("plan_id", ""))
    capability_tags = set(str(item) for item in capabilities.get("capability_tags", []))
    efficiency = 1.0
    if plan_id == "audited_external_extension":
        efficiency += 3.5
        if "dependency" in task_types:
            efficiency += 2.5
        if intent.get("may_download_artifacts"):
            efficiency += 1.0
    elif plan_id == "in_house_capability_rebuild":
        efficiency += 2.5
        if "code" in task_types:
            efficiency += 1.5
        if "security" in capability_tags:
            efficiency += 1.0
    elif plan_id == "browser_evidence":
        efficiency += 2.0 if intent.get("needs_browser") else 0.5
    else:
        efficiency += 1.0
    if capabilities.get("script_count", 0):
        efficiency += 0.5
    return efficiency


def _score_plan(plan: Dict[str, object], intent: Dict[str, object], capabilities: Dict[str, object]) -> Dict[str, object]:
    external_actions = plan.get("external_actions", [])
    task_types = [str(item) for item in intent.get("task_types", [])]
    risk_level = str(intent.get("risk_level", ""))
    local_skill_matches = len(plan.get("skills", []))
    confidence = str(plan.get("confidence", "medium"))
    confidence_bonus = {"high": 3, "medium": 2, "low": 1}.get(confidence, 1)
    browser_bonus = 2 if intent.get("needs_browser") and plan.get("plan_id") == "browser_evidence" else 0
    external_penalty = len(external_actions) * 2
    install_penalty = sum(3 for item in external_actions if item.get("type") in {"public_download", "dependency_install", "external_code_execution"})
    history_profile = load_history_profile(str(plan.get("plan_id", "")), task_types=task_types, risk_level=risk_level)
    historical_success_rate = float(history_profile.get("blended_success_rate", 0.5))
    history_bonus = round((historical_success_rate - 0.5) * 6, 2)
    necessity = prove_plan_necessity(intent, plan, capabilities)
    plan_risk = _estimate_plan_risk(plan)
    plan_efficiency = _estimate_plan_efficiency(plan, intent, capabilities)
    necessity_bonus = 2 if necessity.get("required") else 0
    necessity_penalty = 4 if external_actions and not necessity.get("required") else 0
    confidence_gate_penalty = 2 if external_actions and necessity.get("confidence") == "low" else 0
    efficiency_bonus = round(plan_efficiency * 1.6, 2)
    safety_penalty = round(plan_risk * 1.8, 2)
    score = 10 + local_skill_matches + confidence_bonus + browser_bonus - external_penalty - install_penalty + history_bonus + necessity_bonus - necessity_penalty - confidence_gate_penalty + efficiency_bonus - safety_penalty
    rationale = []
    if local_skill_matches:
        rationale.append("matches existing local skills")
    if browser_bonus:
        rationale.append("fits browser-heavy task")
    if plan_efficiency >= 4:
        rationale.append("offers a strong efficiency advantage for this task shape")
    if external_penalty:
        rationale.append("requires external actions that increase review overhead")
    if install_penalty:
        rationale.append("requires installation/download approvals")
    if plan.get("plan_id") == "in_house_capability_rebuild":
        rationale.append("keeps the useful external ideas while rebuilding the capability locally")
    if history_profile.get("active_weight", 0):
        rationale.append(f"scene-aware historical success rate {historical_success_rate:.2f}")
    if external_actions:
        if necessity.get("required"):
            rationale.append("external extension necessity is justified for this task")
        else:
            rationale.append("higher-risk extension is not yet necessary")
    return {
        "plan_id": plan.get("plan_id", ""),
        "score": score,
        "token_cost_estimate": "low" if len(external_actions) <= 1 else "medium" if len(external_actions) <= 2 else "high",
        "rationale": rationale or ["balanced default plan"],
        "historical_success_rate": historical_success_rate,
        "history": history_profile,
        "necessity": necessity,
        "efficiency_score": plan_efficiency,
        "risk_score": plan_risk,
    }


def judge_proposals(intent: Dict[str, object], capabilities: Dict[str, object], candidate_plans: List[Dict[str, object]]) -> Dict[str, object]:
    scored = [_score_plan(plan, intent, capabilities) for plan in candidate_plans]
    scored_by_id = {item["plan_id"]: item for item in scored}
    selected_score = sorted(scored, key=lambda item: (-int(item["score"]), item["plan_id"]))[0]
    selected_plan = next(plan for plan in candidate_plans if plan.get("plan_id") == selected_score["plan_id"])
    return {
        "selected_plan": selected_plan,
        "selected_score": selected_score,
        "scores": scored,
        "why_selected": selected_score["rationale"],
    }


def main() -> int:
    import argparse

    parser = argparse.ArgumentParser(description="Judge candidate plans and choose the best option")
    parser.add_argument("--intent-json", required=True)
    parser.add_argument("--capabilities-json", required=True)
    parser.add_argument("--plans-json", required=True)
    args = parser.parse_args()
    print(
        json.dumps(
            judge_proposals(json.loads(args.intent_json), json.loads(args.capabilities_json), json.loads(args.plans_json)),
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
