#!/usr/bin/env python3

"""
中文说明：
- 文件路径：`tools/openmoss/control_center/behavior_extractor.py`
- 文件作用：负责控制中心中与 `behavior_extractor` 相关的编排、分析或决策逻辑。
- 顶层函数：extract_behavior_model、main。
- 顶层类：无顶层类。
- 阅读建议：先看模块说明，再按函数/类 docstring 顺着主流程理解调用关系。
"""
from __future__ import annotations

import json
from typing import Dict, List


def extract_behavior_model(task_id: str, mission: Dict[str, object]) -> Dict[str, object]:
    """
    中文注解：
    - 功能：实现 `extract_behavior_model` 对应的处理逻辑。
    - 角色：属于本模块中的对外可见逻辑；私有函数通常服务同文件主流程，公共函数通常作为跨模块入口或能力接口。
    - 调用关系：建议结合本文件的模块说明、调用方以及同名相关辅助函数一起阅读。
    """
    selected_plan = mission.get("selected_plan", {})
    adoption_flow = mission.get("adoption_flow", {})
    resource_scout = mission.get("resource_scout", {})
    challenge = mission.get("challenge", {})
    return {
        "task_id": task_id,
        "source_plan_id": selected_plan.get("plan_id", ""),
        "behavior_goals": selected_plan.get("steps", []),
        "useful_external_behaviors": [
            "structured acquisition ladder",
            "verified evidence collection",
            "safe fallback routing",
        ],
        "external_touchpoints": selected_plan.get("external_actions", []),
        "challenge_model": {
            "type": challenge.get("challenge_type", "none"),
            "route": challenge.get("recommended_route", "continue"),
        },
        "trust_model": {
            "trusted_sources": resource_scout.get("trusted_source_types", []),
            "adoption_mode": adoption_flow.get("adoption_mode", "local_or_read_only"),
        },
    }


def main() -> int:
    """
    中文注解：
    - 功能：实现 `main` 对应的处理逻辑。
    - 角色：属于本模块中的对外可见逻辑；私有函数通常服务同文件主流程，公共函数通常作为跨模块入口或能力接口。
    - 调用关系：建议结合本文件的模块说明、调用方以及同名相关辅助函数一起阅读。
    """
    import argparse

    parser = argparse.ArgumentParser(description="Extract a behavior model from a mission for local capability cloning")
    parser.add_argument("--task-id", required=True)
    parser.add_argument("--mission-json", required=True)
    args = parser.parse_args()
    print(json.dumps(extract_behavior_model(args.task_id, json.loads(args.mission_json)), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
