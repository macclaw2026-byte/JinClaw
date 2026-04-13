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
- 文件路径：`tools/openmoss/control_center/solution_arbitrator.py`
- 文件作用：负责控制中心中与 `solution_arbitrator` 相关的编排、分析或决策逻辑。
- 顶层函数：arbitrate_solution_path、main。
- 顶层类：无顶层类。
- 阅读建议：先看模块说明，再按函数/类 docstring 顺着主流程理解调用关系。
"""
from __future__ import annotations

import json
from typing import Dict, List

from necessity_prover import prove_plan_necessity


def arbitrate_solution_path(
    intent: Dict[str, object],
    selected_plan: Dict[str, object],
    approval: Dict[str, object],
    capabilities: Dict[str, object] | None = None,
    *,
    knowledge_basis: Dict[str, object] | None = None,
    plan_reviews: Dict[str, object] | None = None,
    governance: Dict[str, object] | None = None,
) -> Dict[str, object]:
    """
    中文注解：
    - 功能：实现 `arbitrate_solution_path` 对应的处理逻辑。
    - 角色：属于本模块中的对外可见逻辑；私有函数通常服务同文件主流程，公共函数通常作为跨模块入口或能力接口。
    - 调用关系：建议结合本文件的模块说明、调用方以及同名相关辅助函数一起阅读。
    """
    pending = approval.get("pending", [])
    knowledge_basis = knowledge_basis or {}
    plan_reviews = plan_reviews or {}
    governance = governance or {}
    necessity = prove_plan_necessity(intent, selected_plan, capabilities or {})
    plan_id = str(selected_plan.get("plan_id", ""))
    actions: List[str] = []
    known_uncertainties = [str(item).strip() for item in knowledge_basis.get("known_uncertainties", []) if str(item).strip()]
    recommended_basis = str(knowledge_basis.get("recommended_basis", "")).strip()
    tier = str(governance.get("tier", "standard")).strip() or "standard"
    pending_direction_confirmations = list(plan_reviews.get("pending_direction_confirmations", []) or [])
    if pending:
        actions.append("hold_high_risk_execution_until_approval")
    if intent.get("requires_external_information"):
        actions.append("use_public_research_with_audit_logging")
    if intent.get("may_download_artifacts"):
        actions.append("search_candidates_but_do_not_download_before_approval")
    if intent.get("may_execute_external_code"):
        actions.append("prefer_local_or_in_house_safe_replacement_before_external_execution")
    if plan_id == "in_house_capability_rebuild":
        actions.append("extract_useful_external_patterns_then_build_local_equivalent")
    if plan_id == "audited_external_extension":
        actions.append("prefer_the_most_efficient_safe_option_regardless_of_origin")
    if plan_id == "audited_external_extension" and not necessity.get("required", False):
        actions.append("stay_on_local_plan_until_necessity_is_proven")
    if recommended_basis:
        actions.append(f"use_{recommended_basis}_as_primary_knowledge_basis")
    if known_uncertainties:
        actions.append("treat_known_uncertainties_as_open_risks_not_silent_assumptions")
    if pending_direction_confirmations:
        actions.append("pause_direction_changes_until_user_confirms_recommendation")
    if tier in {"reviewed", "mission"}:
        actions.append("preserve_role_review_must_fix_items_during_execution")
    if not actions:
        actions.append("execute_local_plan")
    direction_change_recommendation = bool(
        pending_direction_confirmations
        or approval.get("direction_change_recommendation")
        or selected_plan.get("plan_id") == "audited_external_extension"
    )
    requires_user_confirmation = bool(
        pending_direction_confirmations
        or approval.get("requires_user_confirmation")
    )
    pending_user_confirmations = []
    for item in pending_direction_confirmations:
        pending_user_confirmations.append(
            {
                "reviewer": item.get("reviewer", ""),
                "recommendation": item.get("recommendation", []),
                "why": item.get("why", ""),
                "requires_user_confirmation": True,
            }
        )
    for item in approval.get("pending_direction_confirmations", []) or []:
        if not isinstance(item, dict):
            continue
        pending_user_confirmations.append(
            {
                "reviewer": item.get("reviewer", ""),
                "recommendation": item.get("recommendation", []),
                "why": item.get("reason", ""),
                "requires_user_confirmation": bool(item.get("requires_user_confirmation", True)),
                "approval_id": item.get("id", ""),
            }
        )
    must_fix_before_execute = [str(item).strip() for item in plan_reviews.get("must_fix_before_execute", []) if str(item).strip()]
    return {
        "selected_plan_id": selected_plan.get("plan_id", ""),
        "pending_approval_count": len(pending),
        "next_best_actions": actions,
        "necessity_proof": necessity,
        "switch_threshold": necessity.get("threshold", {}),
        "stall_policy": "diagnose_then_switch_path_not_skip_goal",
        "security_override": "never",
        "knowledge_basis_recommendation": {
            "recommended_basis": recommended_basis,
            "known_uncertainties": known_uncertainties,
        },
        "must_fix_before_execute": must_fix_before_execute,
        "direction_change_recommendation": direction_change_recommendation,
        "requires_user_confirmation": requires_user_confirmation,
        "pending_user_confirmations": pending_user_confirmations,
        "governance_tier": tier,
    }


def main() -> int:
    """
    中文注解：
    - 功能：实现 `main` 对应的处理逻辑。
    - 角色：属于本模块中的对外可见逻辑；私有函数通常服务同文件主流程，公共函数通常作为跨模块入口或能力接口。
    - 调用关系：建议结合本文件的模块说明、调用方以及同名相关辅助函数一起阅读。
    """
    import argparse

    parser = argparse.ArgumentParser(description="Arbitrate next actions for the control-center mission")
    parser.add_argument("--intent-json", required=True)
    parser.add_argument("--plan-json", required=True)
    parser.add_argument("--approval-json", required=True)
    parser.add_argument("--capabilities-json", default="{}")
    parser.add_argument("--knowledge-basis-json", default="{}")
    parser.add_argument("--plan-reviews-json", default="{}")
    parser.add_argument("--governance-json", default="{}")
    args = parser.parse_args()
    print(
        json.dumps(
            arbitrate_solution_path(
                json.loads(args.intent_json),
                json.loads(args.plan_json),
                json.loads(args.approval_json),
                json.loads(args.capabilities_json),
                knowledge_basis=json.loads(args.knowledge_basis_json),
                plan_reviews=json.loads(args.plan_reviews_json),
                governance=json.loads(args.governance_json),
            ),
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
