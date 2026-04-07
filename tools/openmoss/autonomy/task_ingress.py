#!/usr/bin/env python3

"""
中文说明：
- 文件路径：`tools/openmoss/autonomy/task_ingress.py`
- 文件作用：负责显式任务创建入口与 root mission 启动器。
- 顶层函数：slugify、main。
- 顶层类：无顶层类。
- 阅读建议：先看模块说明，再按函数/类 docstring 顺着主流程理解调用关系。
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

from manager import create_task

CONTROL_CENTER_DIR = Path("/Users/mac_claw/.openclaw/workspace/tools/openmoss/control_center")
if str(CONTROL_CENTER_DIR) not in sys.path:
    sys.path.insert(0, str(CONTROL_CENTER_DIR))

from orchestrator import build_control_center_package
from mission_profiles import detect_root_mission_profile


def slugify(value: str) -> str:
    """
    中文注解：
    - 功能：实现 `slugify` 对应的处理逻辑。
    - 角色：属于本模块中的对外可见逻辑；私有函数通常服务同文件主流程，公共函数通常作为跨模块入口或能力接口。
    - 调用关系：建议结合本文件的模块说明、调用方以及同名相关辅助函数一起阅读。
    """
    slug = re.sub(r"[^a-zA-Z0-9]+", "-", value.strip().lower()).strip("-")
    return slug[:48] or "autonomy-task"


def main() -> int:
    """
    中文注解：
    - 功能：实现 `main` 对应的处理逻辑。
    - 角色：属于本模块中的对外可见逻辑；私有函数通常服务同文件主流程，公共函数通常作为跨模块入口或能力接口。
    - 调用关系：建议结合本文件的模块说明、调用方以及同名相关辅助函数一起阅读。
    """
    parser = argparse.ArgumentParser(description="Create a generic autonomy task from a plain-language goal")
    parser.add_argument("--goal", required=True)
    parser.add_argument("--task-id", default="")
    parser.add_argument("--done-definition", default="")
    args = parser.parse_args()

    inferred_intent = None
    mission_profile = detect_root_mission_profile(args.goal, task_id=args.task_id or "")
    task_id = args.task_id or str(mission_profile.get("root_task_id", "")).strip() or slugify(args.goal)
    goal = str(mission_profile.get("canonical_goal", "")).strip() or args.goal
    package = build_control_center_package(task_id, goal, source="task_ingress")
    done_definition = args.done_definition or str(package["done_definition"])
    create_args = argparse.Namespace(
        task_id=task_id,
        goal=goal,
        done_definition=done_definition,
        stage=[],
        stage_json=json.dumps(package["stages"], ensure_ascii=False),
        hard_constraint=package["hard_constraints"],
        soft_preference=[],
        allowed_tool=package["allowed_tools"],
        forbidden_action=[],
        metadata_json=json.dumps(package["metadata"], ensure_ascii=False),
    )
    return create_task(create_args)


if __name__ == "__main__":
    raise SystemExit(main())
