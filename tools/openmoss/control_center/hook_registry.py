#!/usr/bin/env python3

"""
中文说明：
- 文件路径：`tools/openmoss/control_center/hook_registry.py`
- 文件作用：负责控制中心中与 `hook_registry` 相关的编排、分析或决策逻辑。
- 顶层函数：_write_json、get_registered_hooks、main。
- 顶层类：无顶层类。
- 阅读建议：先看模块说明，再按函数/类 docstring 顺着主流程理解调用关系。
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Dict, List

from paths import HOOKS_ROOT


DEFAULT_HOOKS: Dict[str, List[str]] = {
    "mission.built": ["evaluate_clone_need"],
    "plan.reselected": ["audit_plan_switch"],
    "challenge.detected": ["route_challenge_response"],
    "capability.clone_requested": ["run_capability_clone_pipeline"],
    "capability.clone_verified": ["promote_cloned_capability"],
    "stage.understand.entered": ["refresh_task_memory_snapshot"],
    "stage.plan.entered": ["refresh_task_memory_snapshot", "audit_plan_switch"],
    "stage.execute.entered": ["refresh_task_memory_snapshot", "verify_execution_policy_handoff"],
    "stage.verify.entered": ["refresh_task_memory_snapshot", "verify_execution_policy_handoff"],
    "stage.learn.entered": ["refresh_task_memory_snapshot"],
    "stage.execute.waiting": ["monitor_liveness_and_retry_path"],
}


def _write_json(path: Path, payload: object) -> None:
    """
    中文注解：
    - 功能：实现 `_write_json` 对应的处理逻辑。
    - 角色：属于本模块中的内部辅助逻辑；私有函数通常服务同文件主流程，公共函数通常作为跨模块入口或能力接口。
    - 调用关系：建议结合本文件的模块说明、调用方以及同名相关辅助函数一起阅读。
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def get_registered_hooks(event_type: str) -> Dict[str, object]:
    """
    中文注解：
    - 功能：实现 `get_registered_hooks` 对应的处理逻辑。
    - 角色：属于本模块中的对外可见逻辑；私有函数通常服务同文件主流程，公共函数通常作为跨模块入口或能力接口。
    - 调用关系：建议结合本文件的模块说明、调用方以及同名相关辅助函数一起阅读。
    """
    hooks = DEFAULT_HOOKS.get(event_type, [])
    payload = {"event_type": event_type, "hooks": hooks}
    _write_json(HOOKS_ROOT / f"{event_type.replace('.', '_')}.json", payload)
    return payload


def main() -> int:
    """
    中文注解：
    - 功能：实现 `main` 对应的处理逻辑。
    - 角色：属于本模块中的对外可见逻辑；私有函数通常服务同文件主流程，公共函数通常作为跨模块入口或能力接口。
    - 调用关系：建议结合本文件的模块说明、调用方以及同名相关辅助函数一起阅读。
    """
    import argparse

    parser = argparse.ArgumentParser(description="Inspect registered control-center hooks for an event")
    parser.add_argument("--event-type", required=True)
    args = parser.parse_args()
    print(json.dumps(get_registered_hooks(args.event_type), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
