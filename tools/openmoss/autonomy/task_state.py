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
- 文件路径：`tools/openmoss/autonomy/task_state.py`
- 文件作用：负责任务状态与阶段状态的数据结构定义。
- 顶层函数：无顶层函数。
- 顶层类：StageState、TaskState。
- 阅读建议：先看模块说明，再按函数/类 docstring 顺着主流程理解调用关系。
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional


TASK_STATUSES = {
    "created",
    "planning",
    "running",
    "waiting_external",
    "blocked",
    "recovering",
    "verifying",
    "learning",
    "completed",
    "failed",
}

STAGE_STATUSES = {
    "pending",
    "running",
    "completed",
    "blocked",
    "failed",
    "skipped",
}


@dataclass
class StageState:
    """
    中文注解：
    - 功能：封装 `StageState` 对应的数据结构或行为对象。
    - 角色：属于本模块中的对外可见逻辑，通常由上游流程实例化后参与状态流转或能力执行。
    - 调用关系：请结合模块级说明与类方法一起阅读，理解它在主链中的位置。
    """
    name: str
    status: str = "pending"
    attempts: int = 0
    summary: str = ""
    verification_status: str = "not-run"
    blocker: str = ""
    started_at: str = ""
    completed_at: str = ""
    updated_at: str = ""
    evidence_refs: List[str] = field(default_factory=list)
    last_execution_status: str = ""
    subtask_cursor: int = 0
    completed_subtasks: List[str] = field(default_factory=list)


@dataclass
class TaskState:
    """
    中文注解：
    - 功能：封装 `TaskState` 对应的数据结构或行为对象。
    - 角色：属于本模块中的对外可见逻辑，通常由上游流程实例化后参与状态流转或能力执行。
    - 调用关系：请结合模块级说明与类方法一起阅读，理解它在主链中的位置。
    """
    task_id: str
    status: str = "created"
    current_stage: str = ""
    attempts: int = 0
    next_action: str = "initialize"
    last_progress_at: str = ""
    last_success_at: str = ""
    last_update_at: str = ""
    blockers: List[str] = field(default_factory=list)
    learning_backlog: List[str] = field(default_factory=list)
    stage_order: List[str] = field(default_factory=list)
    stages: Dict[str, StageState] = field(default_factory=dict)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """
        中文注解：
        - 功能：实现 `to_dict` 对应的处理逻辑。
        - 角色：属于本模块中的对外可见逻辑；私有函数通常服务同文件主流程，公共函数通常作为跨模块入口或能力接口。
        - 调用关系：建议结合本文件的模块说明、调用方以及同名相关辅助函数一起阅读。
        """
        payload = asdict(self)
        payload["stages"] = {name: asdict(stage) for name, stage in self.stages.items()}
        return payload

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "TaskState":
        """
        中文注解：
        - 功能：实现 `from_dict` 对应的处理逻辑。
        - 角色：属于本模块中的对外可见逻辑；私有函数通常服务同文件主流程，公共函数通常作为跨模块入口或能力接口。
        - 调用关系：建议结合本文件的模块说明、调用方以及同名相关辅助函数一起阅读。
        """
        payload = dict(data)
        payload["stages"] = {
            name: StageState(**stage_data)
            for name, stage_data in payload.get("stages", {}).items()
        }
        return cls(**payload)

    def first_pending_stage(self) -> Optional[str]:
        """
        中文注解：
        - 功能：实现 `first_pending_stage` 对应的处理逻辑。
        - 角色：属于本模块中的对外可见逻辑；私有函数通常服务同文件主流程，公共函数通常作为跨模块入口或能力接口。
        - 调用关系：建议结合本文件的模块说明、调用方以及同名相关辅助函数一起阅读。
        """
        for name in self.stage_order:
            stage = self.stages.get(name)
            if stage and stage.status in {"pending", "failed", "blocked"}:
                return name
        return None
