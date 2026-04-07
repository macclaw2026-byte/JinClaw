#!/usr/bin/env python3

"""
中文说明：
- 文件路径：`tools/openmoss/control_center/necessity_prover.py`
- 文件作用：负责控制中心中与 `necessity_prover` 相关的编排、分析或决策逻辑。
- 顶层函数：prove_plan_necessity、main。
- 顶层类：无顶层类。
- 阅读建议：先看模块说明，再按函数/类 docstring 顺着主流程理解调用关系。
"""
from __future__ import annotations

import json
from typing import Dict, List


def prove_plan_necessity(intent: Dict[str, object], selected_plan: Dict[str, object], capabilities: Dict[str, object]) -> Dict[str, object]:
    """
    中文注解：
    - 功能：实现 `prove_plan_necessity` 对应的处理逻辑。
    - 角色：属于本模块中的对外可见逻辑；私有函数通常服务同文件主流程，公共函数通常作为跨模块入口或能力接口。
    - 调用关系：建议结合本文件的模块说明、调用方以及同名相关辅助函数一起阅读。
    """
    external_actions = selected_plan.get("external_actions", [])
    plan_id = str(selected_plan.get("plan_id", ""))
    capability_tags = set(str(item) for item in capabilities.get("capability_tags", []))
    reasons: List[str] = []
    threshold = {
        "switch_only_if_all_true": [],
        "minimum_confidence": "medium",
    }
    required = False

    if not external_actions:
        reasons.append("The selected plan can proceed with local capabilities and public read-only evidence.")
        threshold["switch_only_if_all_true"] = [
            "local capabilities proved insufficient",
            "verification would otherwise remain impossible",
        ]
        return {
            "required": False,
            "reason_code": "local_plan_sufficient",
            "justification": reasons,
            "threshold": threshold,
        }

    if plan_id == "in_house_capability_rebuild":
        reasons.append("The task benefits from learning useful external patterns while keeping execution local and auditable.")
        threshold["switch_only_if_all_true"].append("public research provides enough implementation evidence")
        threshold["switch_only_if_all_true"].append("the rebuilt local substitute can be verified against the target outcome")
        required = True
    if intent.get("may_download_artifacts"):
        reasons.append("The mission text explicitly allows external artifacts, but only after approval.")
        threshold["switch_only_if_all_true"].append("all approval gates are satisfied")
        required = True
    if intent.get("may_execute_external_code"):
        reasons.append("The mission may require code execution, so local-only fallback must be disproved before switching.")
        threshold["switch_only_if_all_true"].append("local or in-house replacement was exhausted")
        required = True
    if "dependency" in intent.get("task_types", []):
        reasons.append("This task includes a dependency dimension, so a candidate tool may be necessary if no safe local substitute exists.")
        threshold["switch_only_if_all_true"].append("no safe local substitute is available")
        required = True
    if "browser" not in capability_tags and intent.get("needs_browser"):
        reasons.append("Browser evidence is needed and local browser capability is limited.")
        threshold["switch_only_if_all_true"].append("browser evidence is required for verification")
        required = True
    if plan_id == "audited_external_extension":
        threshold["switch_only_if_all_true"].append("external option is measurably more efficient than safe local alternatives")
        threshold["switch_only_if_all_true"].append("rollback path is documented and tested")

    if not reasons:
        reasons.append("No hard necessity signal was found; stay on the safer local route.")
    return {
        "required": required,
        "reason_code": "external_extension_necessary" if required else "external_extension_not_yet_necessary",
        "justification": reasons,
        "confidence": "high" if len(reasons) >= 3 else "medium" if len(reasons) >= 2 else "low",
        "threshold": threshold,
    }


def main() -> int:
    """
    中文注解：
    - 功能：实现 `main` 对应的处理逻辑。
    - 角色：属于本模块中的对外可见逻辑；私有函数通常服务同文件主流程，公共函数通常作为跨模块入口或能力接口。
    - 调用关系：建议结合本文件的模块说明、调用方以及同名相关辅助函数一起阅读。
    """
    import argparse

    parser = argparse.ArgumentParser(description="Prove whether a higher-risk plan is actually necessary")
    parser.add_argument("--intent-json", required=True)
    parser.add_argument("--plan-json", required=True)
    parser.add_argument("--capabilities-json", required=True)
    args = parser.parse_args()
    print(
        json.dumps(
            prove_plan_necessity(
                json.loads(args.intent_json),
                json.loads(args.plan_json),
                json.loads(args.capabilities_json),
            ),
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
