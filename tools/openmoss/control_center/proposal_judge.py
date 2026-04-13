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
- 文件路径：`tools/openmoss/control_center/proposal_judge.py`
- 文件作用：负责给候选方案打分并选定执行方案。
- 顶层函数：_estimate_plan_risk、_estimate_plan_efficiency、_score_plan、judge_proposals、main。
- 顶层类：无顶层类。
- 阅读建议：先看模块说明，再按函数/类 docstring 顺着主流程理解调用关系。
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Dict, List

from necessity_prover import prove_plan_necessity
from plan_history import load_history_profile

AUTONOMY_DIR = Path("/Users/mac_claw/.openclaw/workspace/tools/openmoss/autonomy")
if str(AUTONOMY_DIR) not in sys.path:
    sys.path.insert(0, str(AUTONOMY_DIR))

from promotion_engine import doctor_strategy_bias


def _estimate_plan_risk(plan: Dict[str, object]) -> float:
    """
    中文注解：
    - 功能：实现 `_estimate_plan_risk` 对应的处理逻辑。
    - 角色：属于本模块中的内部辅助逻辑；私有函数通常服务同文件主流程，公共函数通常作为跨模块入口或能力接口。
    - 调用关系：建议结合本文件的模块说明、调用方以及同名相关辅助函数一起阅读。
    """
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
    """
    中文注解：
    - 功能：实现 `_estimate_plan_efficiency` 对应的处理逻辑。
    - 角色：属于本模块中的内部辅助逻辑；私有函数通常服务同文件主流程，公共函数通常作为跨模块入口或能力接口。
    - 调用关系：建议结合本文件的模块说明、调用方以及同名相关辅助函数一起阅读。
    """
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
    elif plan_id == "local_image_pipeline":
        efficiency += 3.0
        if {"image", "marketplace"}.issubset(task_types):
            efficiency += 3.0
        if intent.get("needs_browser"):
            efficiency += 1.0
    elif plan_id == "browser_evidence":
        efficiency += 2.0 if intent.get("needs_browser") else 0.5
    else:
        efficiency += 1.0
    if capabilities.get("script_count", 0):
        efficiency += 0.5
    return efficiency


def _score_plan(
    plan: Dict[str, object],
    intent: Dict[str, object],
    capabilities: Dict[str, object],
    knowledge_basis: Dict[str, object] | None = None,
) -> Dict[str, object]:
    """
    中文注解：
    - 功能：实现 `_score_plan` 对应的处理逻辑。
    - 角色：属于本模块中的内部辅助逻辑；私有函数通常服务同文件主流程，公共函数通常作为跨模块入口或能力接口。
    - 调用关系：建议结合本文件的模块说明、调用方以及同名相关辅助函数一起阅读。
    """
    external_actions = plan.get("external_actions", [])
    knowledge_basis = knowledge_basis or {}
    task_types = [str(item) for item in intent.get("task_types", [])]
    risk_level = str(intent.get("risk_level", ""))
    local_skill_matches = len(plan.get("skills", []))
    confidence = str(plan.get("confidence", "medium"))
    confidence_bonus = {"high": 3, "medium": 2, "low": 1}.get(confidence, 1)
    browser_bonus = 2 if intent.get("needs_browser") and plan.get("plan_id") == "browser_evidence" else 0
    image_pipeline_bonus = 0
    local_first_penalty = 0
    if "image" in task_types and "marketplace" in task_types and plan.get("plan_id") == "local_image_pipeline":
        image_pipeline_bonus = 4
    if "image" in task_types and plan.get("plan_id") == "local_first":
        local_first_penalty = 3
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
    strategy_bias = doctor_strategy_bias(intent, plan)
    strategy_bonus = float(strategy_bias.get("score_adjustment", 0.0) or 0.0)
    recommended_basis = str(knowledge_basis.get("recommended_basis", "")).strip()
    layer1_count = len([item for item in knowledge_basis.get("layer1_candidates", []) if str(item).strip()])
    layer3_count = len([item for item in knowledge_basis.get("layer3_observations", []) if str(item).strip()])
    uncertainty_count = len([item for item in knowledge_basis.get("known_uncertainties", []) if str(item).strip()])
    knowledge_bonus = 0.0
    knowledge_penalty = 0.0
    if layer1_count:
        knowledge_bonus += min(layer1_count, 3) * 0.6
    if layer3_count:
        knowledge_bonus += min(layer3_count, 2) * 0.5
    if recommended_basis == "layer1+layer3":
        knowledge_bonus += 0.8
    if recommended_basis == "layer1+layer2+layer3" and external_actions:
        knowledge_bonus += 0.6
    if uncertainty_count and external_actions:
        knowledge_penalty += min(uncertainty_count, 3) * 0.5
    if external_actions and not layer1_count:
        knowledge_penalty += 1.0
    score = (
        10
        + local_skill_matches
        + confidence_bonus
        + browser_bonus
        + image_pipeline_bonus
        - local_first_penalty
        - external_penalty
        - install_penalty
        + history_bonus
        + necessity_bonus
        - necessity_penalty
        - confidence_gate_penalty
        + efficiency_bonus
        - safety_penalty
        + strategy_bonus
        + knowledge_bonus
        - knowledge_penalty
    )
    rationale = []
    if local_skill_matches:
        rationale.append("matches existing local skills")
    if browser_bonus:
        rationale.append("fits browser-heavy task")
    if image_pipeline_bonus:
        rationale.append("fits image-generation plus marketplace upload closure")
    if local_first_penalty:
        rationale.append("generic local path is too coarse for image-generation closure")
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
    if recommended_basis:
        rationale.append(f"knowledge basis recommends {recommended_basis}")
    if layer1_count:
        rationale.append("has layer1 tried-and-true support")
    if layer3_count:
        rationale.append("includes first-principles observations for this task")
    if uncertainty_count and external_actions:
        rationale.append("still carries knowledge uncertainty for external actions")
    rationale.extend([str(item) for item in strategy_bias.get("rationale", []) if str(item).strip()])
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
        "doctor_strategy_bias": strategy_bias,
        "knowledge_basis_summary": {
            "recommended_basis": recommended_basis,
            "layer1_count": layer1_count,
            "layer3_count": layer3_count,
            "uncertainty_count": uncertainty_count,
            "knowledge_bonus": round(knowledge_bonus, 2),
            "knowledge_penalty": round(knowledge_penalty, 2),
        },
    }


def judge_proposals(
    intent: Dict[str, object],
    capabilities: Dict[str, object],
    candidate_plans: List[Dict[str, object]],
    knowledge_basis: Dict[str, object] | None = None,
) -> Dict[str, object]:
    """
    中文注解：
    - 功能：实现 `judge_proposals` 对应的处理逻辑。
    - 角色：属于本模块中的对外可见逻辑；私有函数通常服务同文件主流程，公共函数通常作为跨模块入口或能力接口。
    - 调用关系：建议结合本文件的模块说明、调用方以及同名相关辅助函数一起阅读。
    """
    scored = [_score_plan(plan, intent, capabilities, knowledge_basis=knowledge_basis) for plan in candidate_plans]
    scored_by_id = {item["plan_id"]: item for item in scored}
    selected_score = sorted(scored, key=lambda item: (-float(item["score"]), item["plan_id"]))[0]
    selected_plan = next(plan for plan in candidate_plans if plan.get("plan_id") == selected_score["plan_id"])
    return {
        "selected_plan": selected_plan,
        "selected_score": selected_score,
        "scores": scored,
        "why_selected": selected_score["rationale"],
        "knowledge_basis": knowledge_basis or {},
    }


def main() -> int:
    """
    中文注解：
    - 功能：实现 `main` 对应的处理逻辑。
    - 角色：属于本模块中的对外可见逻辑；私有函数通常服务同文件主流程，公共函数通常作为跨模块入口或能力接口。
    - 调用关系：建议结合本文件的模块说明、调用方以及同名相关辅助函数一起阅读。
    """
    import argparse

    parser = argparse.ArgumentParser(description="Judge candidate plans and choose the best option")
    parser.add_argument("--intent-json", required=True)
    parser.add_argument("--capabilities-json", required=True)
    parser.add_argument("--plans-json", required=True)
    parser.add_argument("--knowledge-basis-json", default="{}")
    args = parser.parse_args()
    print(
        json.dumps(
            judge_proposals(
                json.loads(args.intent_json),
                json.loads(args.capabilities_json),
                json.loads(args.plans_json),
                knowledge_basis=json.loads(args.knowledge_basis_json),
            ),
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
