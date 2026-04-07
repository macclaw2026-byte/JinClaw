#!/usr/bin/env python3

"""
中文说明：
- 文件路径：`tools/openmoss/control_center/fractal_decomposer.py`
- 文件作用：负责控制中心中与 `fractal_decomposer` 相关的编排、分析或决策逻辑。
- 顶层函数：build_fractal_loops、select_loop_focus、main。
- 顶层类：无顶层类。
- 阅读建议：先看模块说明，再按函数/类 docstring 顺着主流程理解调用关系。
"""
from __future__ import annotations

import json
from typing import Dict, List


def build_fractal_loops(intent: Dict[str, object], selected_plan: Dict[str, object], topology: Dict[str, object]) -> Dict[str, object]:
    """
    中文注解：
    - 功能：实现 `build_fractal_loops` 对应的处理逻辑。
    - 角色：属于本模块中的对外可见逻辑；私有函数通常服务同文件主流程，公共函数通常作为跨模块入口或能力接口。
    - 调用关系：建议结合本文件的模块说明、调用方以及同名相关辅助函数一起阅读。
    """
    steps = [str(item) for item in selected_plan.get("steps", [])]
    loops: List[Dict[str, object]] = []
    for index, step in enumerate(steps, start=1):
        loops.append(
            {
                "loop_id": f"loop-{index}",
                "goal": step,
                "verify_with": topology.get("verification_nodes", [])[:2],
                "dependencies": topology.get("dependency_nodes", []),
                "risk_checks": topology.get("risk_nodes", []),
            }
        )
    return {
        "mode": "recursive_verifiable_subloops",
        "loop_count": len(loops),
        "loops": loops,
        "decomposition_rule": "each plan step becomes a verifiable sub-loop with explicit dependencies and risk checks",
    }


def select_loop_focus(fractal: Dict[str, object], stage_name: str, stage_attempts: int = 0) -> Dict[str, object]:
    """
    中文注解：
    - 功能：实现 `select_loop_focus` 对应的处理逻辑。
    - 角色：属于本模块中的对外可见逻辑；私有函数通常服务同文件主流程，公共函数通常作为跨模块入口或能力接口。
    - 调用关系：建议结合本文件的模块说明、调用方以及同名相关辅助函数一起阅读。
    """
    loops = fractal.get("loops", [])
    if not loops:
        return {
            "stage_name": stage_name,
            "loop_count": 0,
            "focus": {},
            "focus_reason": "no_fractal_loops_available",
        }
    if stage_name == "execute":
        index = min(max(stage_attempts - 1, 0), len(loops) - 1)
    elif stage_name == "verify":
        index = len(loops) - 1
    else:
        index = 0
    return {
        "stage_name": stage_name,
        "loop_count": len(loops),
        "focus": loops[index],
        "focus_reason": "stage-aligned_fractal_focus",
    }


def main() -> int:
    """
    中文注解：
    - 功能：实现 `main` 对应的处理逻辑。
    - 角色：属于本模块中的对外可见逻辑；私有函数通常服务同文件主流程，公共函数通常作为跨模块入口或能力接口。
    - 调用关系：建议结合本文件的模块说明、调用方以及同名相关辅助函数一起阅读。
    """
    import argparse

    parser = argparse.ArgumentParser(description="Build fractal sub-loops for a selected plan")
    parser.add_argument("--intent-json", required=True)
    parser.add_argument("--plan-json", required=True)
    parser.add_argument("--topology-json", required=True)
    parser.add_argument("--stage-name", default="")
    parser.add_argument("--stage-attempts", type=int, default=0)
    args = parser.parse_args()
    fractal = build_fractal_loops(json.loads(args.intent_json), json.loads(args.plan_json), json.loads(args.topology_json))
    payload = {"fractal": fractal}
    if args.stage_name:
        payload["focus"] = select_loop_focus(fractal, args.stage_name, args.stage_attempts)
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
