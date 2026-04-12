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
- 文件路径：`tools/openmoss/control_center/external_tool_scorer.py`
- 文件作用：负责控制中心中与 `external_tool_scorer` 相关的编排、分析或决策逻辑。
- 顶层函数：_write_json、_score_plan、score_external_options、main。
- 顶层类：无顶层类。
- 阅读建议：先看模块说明，再按函数/类 docstring 顺着主流程理解调用关系。
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Dict, List

from paths import TOOL_SCORES_ROOT
from security_policy import assess_plan_risk


def _write_json(path: Path, payload: object) -> None:
    """
    中文注解：
    - 功能：实现 `_write_json` 对应的处理逻辑。
    - 角色：属于本模块中的内部辅助逻辑；私有函数通常服务同文件主流程，公共函数通常作为跨模块入口或能力接口。
    - 调用关系：建议结合本文件的模块说明、调用方以及同名相关辅助函数一起阅读。
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _score_plan(plan: Dict[str, object], intent: Dict[str, object], capabilities: Dict[str, object]) -> Dict[str, object]:
    """
    中文注解：
    - 功能：实现 `_score_plan` 对应的处理逻辑。
    - 角色：属于本模块中的内部辅助逻辑；私有函数通常服务同文件主流程，公共函数通常作为跨模块入口或能力接口。
    - 调用关系：建议结合本文件的模块说明、调用方以及同名相关辅助函数一起阅读。
    """
    plan_id = str(plan.get("plan_id", ""))
    task_types = {str(item) for item in intent.get("task_types", [])}
    capability_tags = {str(item) for item in capabilities.get("capability_tags", [])}
    assessed = assess_plan_risk(plan)
    risk = str(assessed.get("risk", "low"))
    risk_score = {"low": 1.0, "medium": 2.0, "high": 3.0, "critical": 4.0}.get(risk, 3.0)
    rollback_ready = plan_id in {"audited_external_extension", "in_house_capability_rebuild", "local_first"}
    audit_ready = risk in {"low", "medium"} or plan_id in {"audited_external_extension", "in_house_capability_rebuild"}

    efficiency_gain = 1.0
    if plan_id == "audited_external_extension":
        efficiency_gain += 4.5
        if "dependency" in task_types:
            efficiency_gain += 2.0
        if intent.get("may_download_artifacts"):
            efficiency_gain += 1.5
        if intent.get("may_execute_external_code"):
            efficiency_gain += 1.0
    elif plan_id == "in_house_capability_rebuild":
        efficiency_gain += 3.5
        if "code" in task_types:
            efficiency_gain += 1.5
        if "security" in capability_tags:
            efficiency_gain += 1.0
    elif plan_id == "browser_evidence":
        efficiency_gain += 2.0 if intent.get("needs_browser") else 0.5
    else:
        efficiency_gain += 1.0

    if "research" in capability_tags:
        efficiency_gain += 0.5
    if "security" in capability_tags and plan_id == "in_house_capability_rebuild":
        efficiency_gain += 0.5

    safe_enough = audit_ready and risk != "critical"
    adoption_mode = {
        "audited_external_extension": "audited_external_adoption",
        "in_house_capability_rebuild": "learn_and_rebuild_locally",
    }.get(plan_id, "local_or_read_only")
    recommendation = "eligible_for_safe_high_efficiency_selection" if safe_enough else "keep_as_fallback_only"
    if plan_id == "in_house_capability_rebuild":
        recommendation = "prefer_when_external_method_is_useful_but_direct_adoption_is_risky"
    return {
        "plan_id": plan_id,
        "adoption_mode": adoption_mode,
        "risk_level": risk,
        "risk_score": risk_score,
        "efficiency_gain": round(efficiency_gain, 2),
        "rollback_ready": rollback_ready,
        "audit_ready": audit_ready,
        "safe_enough": safe_enough,
        "recommendation": recommendation,
    }


def score_external_options(task_id: str, intent: Dict[str, object], candidate_plans: List[Dict[str, object]], capabilities: Dict[str, object]) -> Dict[str, object]:
    """
    中文注解：
    - 功能：实现 `score_external_options` 对应的处理逻辑。
    - 角色：属于本模块中的对外可见逻辑；私有函数通常服务同文件主流程，公共函数通常作为跨模块入口或能力接口。
    - 调用关系：建议结合本文件的模块说明、调用方以及同名相关辅助函数一起阅读。
    """
    scores = [_score_plan(plan, intent, capabilities) for plan in candidate_plans]
    payload = {
        "task_id": task_id,
        "scores": scores,
    }
    _write_json(TOOL_SCORES_ROOT / f"{task_id}.json", payload)
    return payload


def main() -> int:
    """
    中文注解：
    - 功能：实现 `main` 对应的处理逻辑。
    - 角色：属于本模块中的对外可见逻辑；私有函数通常服务同文件主流程，公共函数通常作为跨模块入口或能力接口。
    - 调用关系：建议结合本文件的模块说明、调用方以及同名相关辅助函数一起阅读。
    """
    import argparse

    parser = argparse.ArgumentParser(description="Score external-tool adoption options under the control-center policy")
    parser.add_argument("--task-id", required=True)
    parser.add_argument("--intent-json", required=True)
    parser.add_argument("--plans-json", required=True)
    parser.add_argument("--capabilities-json", required=True)
    args = parser.parse_args()
    print(
        json.dumps(
            score_external_options(
                args.task_id,
                json.loads(args.intent_json),
                json.loads(args.plans_json),
                json.loads(args.capabilities_json),
            ),
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
