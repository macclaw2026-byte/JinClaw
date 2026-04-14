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
- 文件路径：`tools/openmoss/control_center/plan_reselector.py`
- 文件作用：负责控制中心中与 `plan_reselector` 相关的编排、分析或决策逻辑。
- 顶层函数：_write_json、_intent_affinity、reselect_plan、main。
- 顶层类：无顶层类。
- 阅读建议：先看模块说明，再按函数/类 docstring 顺着主流程理解调用关系。
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Dict, List

from paths import RESELECTIONS_ROOT

AUTONOMY_DIR = Path("/Users/mac_claw/.openclaw/workspace/tools/openmoss/autonomy")
if str(AUTONOMY_DIR) not in sys.path:
    sys.path.insert(0, str(AUTONOMY_DIR))

from promotion_engine import doctor_strategy_bias


def _write_json(path: Path, payload: object) -> None:
    """
    中文注解：
    - 功能：实现 `_write_json` 对应的处理逻辑。
    - 角色：属于本模块中的内部辅助逻辑；私有函数通常服务同文件主流程，公共函数通常作为跨模块入口或能力接口。
    - 调用关系：建议结合本文件的模块说明、调用方以及同名相关辅助函数一起阅读。
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _intent_affinity(intent: Dict[str, object], plan_id: str) -> float:
    """
    中文注解：
    - 功能：实现 `_intent_affinity` 对应的处理逻辑。
    - 角色：属于本模块中的内部辅助逻辑；私有函数通常服务同文件主流程，公共函数通常作为跨模块入口或能力接口。
    - 调用关系：建议结合本文件的模块说明、调用方以及同名相关辅助函数一起阅读。
    """
    goal = str(intent.get("goal", "")).lower()
    ziniao_bridge_goal = any(
        token in goal
        for token in ["ziniao", "子鸟", "zclaw", "kuajingmaihuo", "temu", "对账中心", "账务明细", "店铺", "导出", "订单"]
    )
    if plan_id == "audited_external_extension":
        if all(token in goal for token in ["install", "approved", "official", "rollback"]):
            return 16.0
        if any(token in goal for token in ["install", "approved dependency", "package", "use the safest and most efficient way"]):
            return 6.0
    if plan_id == "ziniao_bridge_ops" and ziniao_bridge_goal:
        return 12.0
    if plan_id == "in_house_capability_rebuild":
        if ziniao_bridge_goal:
            return -8.0
        if any(token in goal for token in ["learn its strengths", "build a local replacement", "rebuild", "local equivalent"]):
            return 5.0
    return 0.0


def reselect_plan(
    task_id: str,
    intent: Dict[str, object],
    candidate_plans: List[Dict[str, object]],
    proposal_judgment: Dict[str, object],
    tool_scores: Dict[str, object],
) -> Dict[str, object]:
    """
    中文注解：
    - 功能：实现 `reselect_plan` 对应的处理逻辑。
    - 角色：属于本模块中的对外可见逻辑；私有函数通常服务同文件主流程，公共函数通常作为跨模块入口或能力接口。
    - 调用关系：建议结合本文件的模块说明、调用方以及同名相关辅助函数一起阅读。
    """
    by_plan = {str(plan.get("plan_id", "")): plan for plan in candidate_plans}
    proposal_scores = {str(item.get("plan_id", "")): item for item in proposal_judgment.get("scores", [])}
    tool_score_map = {str(item.get("plan_id", "")): item for item in tool_scores.get("scores", [])}

    ranked = []
    for plan_id, plan in by_plan.items():
        proposal = proposal_scores.get(plan_id, {})
        tool = tool_score_map.get(plan_id, {})
        strategy_bias = doctor_strategy_bias(intent, plan)
        objective = float(proposal.get("score", 0.0))
        objective += float(tool.get("efficiency_gain", 0.0)) * 1.5
        objective -= float(tool.get("risk_score", 0.0)) * 1.2
        if tool.get("rollback_ready"):
            objective += 1.5
        if tool.get("audit_ready"):
            objective += 1.5
        objective += _intent_affinity(intent, plan_id)
        objective += float(strategy_bias.get("score_adjustment", 0.0) or 0.0)
        if not tool.get("safe_enough", False):
            objective -= 100.0
        ranked.append(
            {
                "plan_id": plan_id,
                "objective_score": round(objective, 2),
                "proposal_score": proposal.get("score", 0.0),
                "efficiency_gain": tool.get("efficiency_gain", 0.0),
                "risk_score": tool.get("risk_score", 0.0),
                "safe_enough": bool(tool.get("safe_enough", False)),
                "doctor_strategy_bias": strategy_bias,
            }
        )

    ranked = sorted(ranked, key=lambda item: (-float(item["objective_score"]), item["plan_id"]))
    selected = ranked[0] if ranked else {"plan_id": proposal_judgment.get("selected_plan", {}).get("plan_id", "")}
    final_plan = by_plan.get(str(selected.get("plan_id", "")), proposal_judgment.get("selected_plan", {}))
    original_plan_id = str(proposal_judgment.get("selected_plan", {}).get("plan_id", ""))
    switched = bool(original_plan_id and original_plan_id != str(final_plan.get("plan_id", "")))
    selected_bias = next((item.get("doctor_strategy_bias", {}) for item in ranked if item.get("plan_id") == str(final_plan.get("plan_id", ""))), {})
    payload = {
        "task_id": task_id,
        "original_plan_id": original_plan_id,
        "final_plan_id": final_plan.get("plan_id", ""),
        "switched": switched,
        "switch_reason": "higher-efficiency safe option identified" if switched else "original plan remained the best safe option",
        "doctor_strategy_bias": selected_bias,
        "ranked_candidates": ranked,
        "final_selected_plan": final_plan,
    }
    _write_json(RESELECTIONS_ROOT / f"{task_id}.json", payload)
    return payload


def main() -> int:
    """
    中文注解：
    - 功能：实现 `main` 对应的处理逻辑。
    - 角色：属于本模块中的对外可见逻辑；私有函数通常服务同文件主流程，公共函数通常作为跨模块入口或能力接口。
    - 调用关系：建议结合本文件的模块说明、调用方以及同名相关辅助函数一起阅读。
    """
    import argparse

    parser = argparse.ArgumentParser(description="Reselect the final plan using safety-first efficiency scoring")
    parser.add_argument("--task-id", required=True)
    parser.add_argument("--plans-json", required=True)
    parser.add_argument("--judgment-json", required=True)
    parser.add_argument("--tool-scores-json", required=True)
    args = parser.parse_args()
    print(
        json.dumps(
            reselect_plan(
                args.task_id,
                {},
                json.loads(args.plans_json),
                json.loads(args.judgment_json),
                json.loads(args.tool_scores_json),
            ),
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
