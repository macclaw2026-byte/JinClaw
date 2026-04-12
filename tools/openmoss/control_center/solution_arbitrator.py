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


def arbitrate_solution_path(intent: Dict[str, object], selected_plan: Dict[str, object], approval: Dict[str, object], capabilities: Dict[str, object] | None = None) -> Dict[str, object]:
    """
    中文注解：
    - 功能：实现 `arbitrate_solution_path` 对应的处理逻辑。
    - 角色：属于本模块中的对外可见逻辑；私有函数通常服务同文件主流程，公共函数通常作为跨模块入口或能力接口。
    - 调用关系：建议结合本文件的模块说明、调用方以及同名相关辅助函数一起阅读。
    """
    pending = approval.get("pending", [])
    necessity = prove_plan_necessity(intent, selected_plan, capabilities or {})
    plan_id = str(selected_plan.get("plan_id", ""))
    actions: List[str] = []
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
    if not actions:
        actions.append("execute_local_plan")
    return {
        "selected_plan_id": selected_plan.get("plan_id", ""),
        "pending_approval_count": len(pending),
        "next_best_actions": actions,
        "necessity_proof": necessity,
        "switch_threshold": necessity.get("threshold", {}),
        "stall_policy": "diagnose_then_switch_path_not_skip_goal",
        "security_override": "never",
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
    args = parser.parse_args()
    print(
        json.dumps(
            arbitrate_solution_path(
                json.loads(args.intent_json),
                json.loads(args.plan_json),
                json.loads(args.approval_json),
                json.loads(args.capabilities_json),
            ),
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
