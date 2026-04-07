#!/usr/bin/env python3

"""
中文说明：
- 文件路径：`tools/openmoss/autonomy/learning_engine.py`
- 文件作用：负责错误、学习与任务摘要的结构化沉淀。
- 顶层函数：_append、_read_json、_write_json、_utc_now_iso、_normalize_error、_recurrence_path、_promotion_report_path、_task_summary_path、record_learning、record_error、note_error_occurrence、get_error_recurrence、update_task_summary、load_task_summary。
- 顶层类：无顶层类。
- 阅读建议：先看模块说明，再按函数/类 docstring 顺着主流程理解调用关系。
"""
from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List


LEARNINGS_ROOT = Path("/Users/mac_claw/.openclaw/workspace/.learnings")
STRUCTURED_ROOT = Path("/Users/mac_claw/.openclaw/workspace/tools/openmoss/runtime/autonomy/learning")


def _append(path: Path, lines: List[str]) -> None:
    """
    中文注解：
    - 功能：实现 `_append` 对应的处理逻辑。
    - 角色：属于本模块中的内部辅助逻辑；私有函数通常服务同文件主流程，公共函数通常作为跨模块入口或能力接口。
    - 调用关系：建议结合本文件的模块说明、调用方以及同名相关辅助函数一起阅读。
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as fh:
        for line in lines:
            fh.write(line.rstrip() + "\n")


def _read_json(path: Path, default):
    """
    中文注解：
    - 功能：实现 `_read_json` 对应的处理逻辑。
    - 角色：属于本模块中的内部辅助逻辑；私有函数通常服务同文件主流程，公共函数通常作为跨模块入口或能力接口。
    - 调用关系：建议结合本文件的模块说明、调用方以及同名相关辅助函数一起阅读。
    """
    if not path.exists():
        return default
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, payload) -> None:
    """
    中文注解：
    - 功能：实现 `_write_json` 对应的处理逻辑。
    - 角色：属于本模块中的内部辅助逻辑；私有函数通常服务同文件主流程，公共函数通常作为跨模块入口或能力接口。
    - 调用关系：建议结合本文件的模块说明、调用方以及同名相关辅助函数一起阅读。
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _utc_now_iso() -> str:
    """
    中文注解：
    - 功能：实现 `_utc_now_iso` 对应的处理逻辑。
    - 角色：属于本模块中的内部辅助逻辑；私有函数通常服务同文件主流程，公共函数通常作为跨模块入口或能力接口。
    - 调用关系：建议结合本文件的模块说明、调用方以及同名相关辅助函数一起阅读。
    """
    return datetime.now(timezone.utc).isoformat()


def _normalize_error(error_text: str) -> str:
    """
    中文注解：
    - 功能：实现 `_normalize_error` 对应的处理逻辑。
    - 角色：属于本模块中的内部辅助逻辑；私有函数通常服务同文件主流程，公共函数通常作为跨模块入口或能力接口。
    - 调用关系：建议结合本文件的模块说明、调用方以及同名相关辅助函数一起阅读。
    """
    lowered = error_text.lower().strip()
    lowered = re.sub(r"^(understand|plan|execute|verify|learn)\s*:\s*", "", lowered)
    lowered = re.sub(r"^(auto-recovery failed for [^:]+:\s*)", "", lowered)
    lowered = re.sub(r"/users/[^\s]+", "/users/<path>", lowered)
    lowered = re.sub(r"/tmp/[^\s]+", "/tmp/<path>", lowered)
    lowered = re.sub(r"\b[0-9a-f]{8,}\b", "<id>", lowered)
    return lowered


def _recurrence_path() -> Path:
    """
    中文注解：
    - 功能：实现 `_recurrence_path` 对应的处理逻辑。
    - 角色：属于本模块中的内部辅助逻辑；私有函数通常服务同文件主流程，公共函数通常作为跨模块入口或能力接口。
    - 调用关系：建议结合本文件的模块说明、调用方以及同名相关辅助函数一起阅读。
    """
    return STRUCTURED_ROOT / "error_recurrence.json"


def _promotion_report_path(key: str) -> Path:
    """
    中文注解：
    - 功能：实现 `_promotion_report_path` 对应的处理逻辑。
    - 角色：属于本模块中的内部辅助逻辑；私有函数通常服务同文件主流程，公共函数通常作为跨模块入口或能力接口。
    - 调用关系：建议结合本文件的模块说明、调用方以及同名相关辅助函数一起阅读。
    """
    safe = re.sub(r"[^a-zA-Z0-9]+", "-", key).strip("-")[:80] or "recurring-error"
    return STRUCTURED_ROOT / "reports" / f"{safe}.json"


def _task_summary_path(task_id: str) -> Path:
    """
    中文注解：
    - 功能：实现 `_task_summary_path` 对应的处理逻辑。
    - 角色：属于本模块中的内部辅助逻辑；私有函数通常服务同文件主流程，公共函数通常作为跨模块入口或能力接口。
    - 调用关系：建议结合本文件的模块说明、调用方以及同名相关辅助函数一起阅读。
    """
    return STRUCTURED_ROOT / "task_summaries" / f"{task_id}.json"


def record_learning(task_id: str, summary: str) -> str:
    """
    中文注解：
    - 功能：实现 `record_learning` 对应的处理逻辑。
    - 角色：属于本模块中的对外可见逻辑；私有函数通常服务同文件主流程，公共函数通常作为跨模块入口或能力接口。
    - 调用关系：建议结合本文件的模块说明、调用方以及同名相关辅助函数一起阅读。
    """
    path = LEARNINGS_ROOT / "LEARNINGS.md"
    _append(path, [f"- [{task_id}] {summary}"])
    return str(path)


def record_error(task_id: str, error_text: str) -> str:
    """
    中文注解：
    - 功能：实现 `record_error` 对应的处理逻辑。
    - 角色：属于本模块中的对外可见逻辑；私有函数通常服务同文件主流程，公共函数通常作为跨模块入口或能力接口。
    - 调用关系：建议结合本文件的模块说明、调用方以及同名相关辅助函数一起阅读。
    """
    path = LEARNINGS_ROOT / "ERRORS.md"
    _append(path, [f"- [{task_id}] {error_text}"])
    note_error_occurrence(task_id, error_text)
    return str(path)


def note_error_occurrence(task_id: str, error_text: str) -> Dict[str, object]:
    """
    中文注解：
    - 功能：实现 `note_error_occurrence` 对应的处理逻辑。
    - 角色：属于本模块中的对外可见逻辑；私有函数通常服务同文件主流程，公共函数通常作为跨模块入口或能力接口。
    - 调用关系：建议结合本文件的模块说明、调用方以及同名相关辅助函数一起阅读。
    """
    path = _recurrence_path()
    payload = _read_json(path, {"errors": {}})
    key = _normalize_error(error_text)
    item = payload["errors"].get(
        key,
        {
            "count": 0,
            "tasks": [],
            "first_seen_task": task_id,
            "last_seen_task": task_id,
            "sample_error": error_text,
        },
    )
    item["count"] += 1
    item["last_seen_task"] = task_id
    if task_id not in item["tasks"]:
        item["tasks"].append(task_id)
    payload["errors"][key] = item
    _write_json(path, payload)
    if item["count"] >= 2:
        _write_json(
            _promotion_report_path(key),
            {
                "error_key": key,
                "count": item["count"],
                "tasks": item["tasks"],
                "recommended_action": "promote recurring fix into runtime guidance",
                "sample_error": item["sample_error"],
            },
        )
    return {"key": key, "count": item["count"], "tasks": item["tasks"]}


def get_error_recurrence(error_text: str) -> Dict[str, object]:
    """
    中文注解：
    - 功能：实现 `get_error_recurrence` 对应的处理逻辑。
    - 角色：属于本模块中的对外可见逻辑；私有函数通常服务同文件主流程，公共函数通常作为跨模块入口或能力接口。
    - 调用关系：建议结合本文件的模块说明、调用方以及同名相关辅助函数一起阅读。
    """
    payload = _read_json(_recurrence_path(), {"errors": {}})
    key = _normalize_error(error_text)
    item = payload["errors"].get(key, {"count": 0, "tasks": []})
    return {"key": key, "count": item.get("count", 0), "tasks": item.get("tasks", [])}


def update_task_summary(task_id: str, update: Dict[str, object]) -> Dict[str, object]:
    """
    中文注解：
    - 功能：实现 `update_task_summary` 对应的处理逻辑。
    - 角色：属于本模块中的对外可见逻辑；私有函数通常服务同文件主流程，公共函数通常作为跨模块入口或能力接口。
    - 调用关系：建议结合本文件的模块说明、调用方以及同名相关辅助函数一起阅读。
    """
    path = _task_summary_path(task_id)
    current = _read_json(
        path,
        {
            "task_id": task_id,
            "updated_at": "",
            "status": "unknown",
            "current_stage": "",
            "last_completed_stage": "",
            "last_failure": {},
            "learning_backlog": [],
            "verified_stages": [],
            "completed_stages": [],
            "notes": [],
        },
    )
    current.update({k: v for k, v in update.items() if v is not None})
    current["updated_at"] = _utc_now_iso()
    _write_json(path, current)
    return current


def load_task_summary(task_id: str) -> Dict[str, object]:
    """
    中文注解：
    - 功能：实现 `load_task_summary` 对应的处理逻辑。
    - 角色：属于本模块中的对外可见逻辑；私有函数通常服务同文件主流程，公共函数通常作为跨模块入口或能力接口。
    - 调用关系：建议结合本文件的模块说明、调用方以及同名相关辅助函数一起阅读。
    """
    return _read_json(_task_summary_path(task_id), {})
