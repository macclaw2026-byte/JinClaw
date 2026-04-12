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
- 文件路径：`tools/openmoss/control_center/canonical_active_task.py`
- 文件作用：负责解析会话当前唯一权威活跃任务。
- 顶层函数：_read_json、_successor_from_state、resolve_canonical_active_task。
- 顶层类：无顶层类。
- 阅读建议：先看模块说明，再按函数/类 docstring 顺着主流程理解调用关系。
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List

from paths import OPENMOSS_ROOT


AUTONOMY_TASKS_ROOT = OPENMOSS_ROOT / "runtime/autonomy/tasks"


def _read_json(path: Path) -> Dict[str, Any]:
    """
    中文注解：
    - 功能：实现 `_read_json` 对应的处理逻辑。
    - 角色：属于本模块中的内部辅助逻辑；私有函数通常服务同文件主流程，公共函数通常作为跨模块入口或能力接口。
    - 调用关系：建议结合本文件的模块说明、调用方以及同名相关辅助函数一起阅读。
    """
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def _successor_from_state(task_id: str) -> str:
    """
    中文注解：
    - 功能：实现 `_successor_from_state` 对应的处理逻辑。
    - 角色：属于本模块中的内部辅助逻辑；私有函数通常服务同文件主流程，公共函数通常作为跨模块入口或能力接口。
    - 调用关系：建议结合本文件的模块说明、调用方以及同名相关辅助函数一起阅读。
    """
    state = _read_json(AUTONOMY_TASKS_ROOT / task_id / "state.json")
    next_action = str(state.get("next_action", "")).strip()
    if next_action.startswith("superseded_by:"):
        return next_action.split(":", 1)[1].strip()
    metadata = state.get("metadata", {}) or {}
    return str(metadata.get("superseded_by_task_id", "")).strip()


def _contract_metadata(task_id: str) -> Dict[str, Any]:
    contract = _read_json(AUTONOMY_TASKS_ROOT / task_id / "contract.json")
    metadata = contract.get("metadata", {}) or {}
    return metadata if isinstance(metadata, dict) else {}


def _lineage_root_task_id(task_id: str) -> str:
    metadata = _contract_metadata(task_id)
    lineage_root = str(metadata.get("lineage_root_task_id", "")).strip()
    return lineage_root or str(task_id or "").strip()


def _predecessor_task_id(task_id: str) -> str:
    metadata = _contract_metadata(task_id)
    return str(metadata.get("predecessor_task_id", "")).strip()


def _is_same_lineage_successor(current_task_id: str, successor_task_id: str) -> bool:
    current = str(current_task_id or "").strip()
    successor = str(successor_task_id or "").strip()
    if not current or not successor:
        return False
    if current == successor:
        return True
    if not (AUTONOMY_TASKS_ROOT / successor).exists():
        return False
    if _predecessor_task_id(successor) == current:
        return True
    return _lineage_root_task_id(successor) == _lineage_root_task_id(current)


def resolve_canonical_active_task(task_id: str) -> Dict[str, Any]:
    """
    中文注解：
    - 功能：实现 `resolve_canonical_active_task` 对应的处理逻辑。
    - 角色：属于本模块中的对外可见逻辑；私有函数通常服务同文件主流程，公共函数通常作为跨模块入口或能力接口。
    - 调用关系：建议结合本文件的模块说明、调用方以及同名相关辅助函数一起阅读。
    """
    current = str(task_id or "").strip()
    visited: List[str] = []
    while current and current not in visited:
        visited.append(current)
        successor = _successor_from_state(current)
        if not successor:
            break
        if not _is_same_lineage_successor(current, successor):
            break
        current = successor
    return {
        "requested_task_id": str(task_id or "").strip(),
        "canonical_task_id": current or str(task_id or "").strip(),
        "lineage": visited,
        "rerooted": bool(visited and current and visited[0] != current),
    }
