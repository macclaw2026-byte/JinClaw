#!/usr/bin/env python3

"""
中文说明：
- 文件路径：`tools/openmoss/control_center/adoption_flow.py`
- 文件作用：负责控制中心中与 `adoption_flow` 相关的编排、分析或决策逻辑。
- 顶层函数：_write_json、build_adoption_flow、main。
- 顶层类：无顶层类。
- 阅读建议：先看模块说明，再按函数/类 docstring 顺着主流程理解调用关系。
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Dict, List

from paths import ADOPTIONS_ROOT


def _write_json(path: Path, payload: object) -> None:
    """
    中文注解：
    - 功能：实现 `_write_json` 对应的处理逻辑。
    - 角色：属于本模块中的内部辅助逻辑；私有函数通常服务同文件主流程，公共函数通常作为跨模块入口或能力接口。
    - 调用关系：建议结合本文件的模块说明、调用方以及同名相关辅助函数一起阅读。
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def build_adoption_flow(task_id: str, selected_plan: Dict[str, object], approval: Dict[str, object], tool_score: Dict[str, object]) -> Dict[str, object]:
    """
    中文注解：
    - 功能：实现 `build_adoption_flow` 对应的处理逻辑。
    - 角色：属于本模块中的对外可见逻辑；私有函数通常服务同文件主流程，公共函数通常作为跨模块入口或能力接口。
    - 调用关系：建议结合本文件的模块说明、调用方以及同名相关辅助函数一起阅读。
    """
    plan_id = str(selected_plan.get("plan_id", ""))
    pending = list(approval.get("pending", []))
    if plan_id == "audited_external_extension":
        phases: List[Dict[str, object]] = [
            {"name": "research", "goal": "find the most efficient trusted candidate from official or source-level material"},
            {"name": "audit", "goal": "run approval and security review before any download or install"},
            {"name": "trial", "goal": "test the approved artifact in a tightly scoped, reversible way"},
            {"name": "verify", "goal": "confirm the tool improves efficiency without violating security boundaries"},
            {"name": "rollback", "goal": "document and test a clean rollback path before broad adoption"},
            {"name": "adopt", "goal": "adopt the approved external tool only after the prior phases are evidenced"},
        ]
    elif plan_id == "in_house_capability_rebuild":
        phases = [
            {"name": "research", "goal": "study trusted external material for useful ideas only"},
            {"name": "distill", "goal": "extract the valuable patterns without inheriting unsafe execution paths"},
            {"name": "rebuild", "goal": "implement a local equivalent inside the approved workspace"},
            {"name": "verify", "goal": "prove that the rebuilt local capability reaches the same verified outcome"},
            {"name": "rollback", "goal": "keep local changes reversible and documented"},
            {"name": "adopt", "goal": "register the rebuilt capability as an in-house option for future tasks"},
        ]
    else:
        phases = [
            {"name": "execute", "goal": "continue with the selected low-risk local path"},
            {"name": "verify", "goal": "verify the local path remains sufficient"},
        ]

    payload = {
        "task_id": task_id,
        "plan_id": plan_id,
        "adoption_mode": tool_score.get("adoption_mode", "local_or_read_only"),
        "safe_enough": bool(tool_score.get("safe_enough", False)),
        "rollback_ready": bool(tool_score.get("rollback_ready", False)),
        "pending_approvals": pending,
        "phases": phases,
        "entry_gate": "approval_clear" if pending else "ready",
    }
    _write_json(ADOPTIONS_ROOT / f"{task_id}.json", payload)
    return payload


def main() -> int:
    """
    中文注解：
    - 功能：实现 `main` 对应的处理逻辑。
    - 角色：属于本模块中的对外可见逻辑；私有函数通常服务同文件主流程，公共函数通常作为跨模块入口或能力接口。
    - 调用关系：建议结合本文件的模块说明、调用方以及同名相关辅助函数一起阅读。
    """
    import argparse

    parser = argparse.ArgumentParser(description="Build a rollback-aware audited adoption flow")
    parser.add_argument("--task-id", required=True)
    parser.add_argument("--plan-json", required=True)
    parser.add_argument("--approval-json", required=True)
    parser.add_argument("--tool-score-json", required=True)
    args = parser.parse_args()
    print(
        json.dumps(
            build_adoption_flow(
                args.task_id,
                json.loads(args.plan_json),
                json.loads(args.approval_json),
                json.loads(args.tool_score_json),
            ),
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
