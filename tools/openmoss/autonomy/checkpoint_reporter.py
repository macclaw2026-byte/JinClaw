#!/usr/bin/env python3

"""
中文说明：
- 文件路径：`tools/openmoss/autonomy/checkpoint_reporter.py`
- 文件作用：负责自治运行时中与 `checkpoint_reporter` 相关的执行或状态管理逻辑。
- 顶层函数：render_checkpoint、write_checkpoint。
- 顶层类：无顶层类。
- 阅读建议：先看模块说明，再按函数/类 docstring 顺着主流程理解调用关系。
"""
from __future__ import annotations

from pathlib import Path

from task_state import TaskState


def render_checkpoint(state: TaskState) -> str:
    """
    中文注解：
    - 功能：实现 `render_checkpoint` 对应的处理逻辑。
    - 角色：属于本模块中的对外可见逻辑；私有函数通常服务同文件主流程，公共函数通常作为跨模块入口或能力接口。
    - 调用关系：建议结合本文件的模块说明、调用方以及同名相关辅助函数一起阅读。
    """
    completed = [name for name in state.stage_order if state.stages[name].status == "completed"]
    not_completed = [name for name in state.stage_order if state.stages[name].status != "completed"]
    risks = state.blockers or ["none"]
    return "\n".join(
        [
            f"Current stage: {state.current_stage or 'n/a'}",
            f"Completed: {', '.join(completed) if completed else 'none'}",
            f"Not completed: {', '.join(not_completed) if not_completed else 'none'}",
            f"Risks / issues: {', '.join(risks)}",
            f"Suggested next step: {state.next_action}",
            "Continuation mode: auto-continue",
        ]
    )


def write_checkpoint(path: Path, state: TaskState) -> str:
    """
    中文注解：
    - 功能：实现 `write_checkpoint` 对应的处理逻辑。
    - 角色：属于本模块中的对外可见逻辑；私有函数通常服务同文件主流程，公共函数通常作为跨模块入口或能力接口。
    - 调用关系：建议结合本文件的模块说明、调用方以及同名相关辅助函数一起阅读。
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    text = render_checkpoint(state)
    path.write_text(text + "\n", encoding="utf-8")
    return text
