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
- 文件路径：`tools/openmoss/control_center/run_liveness_verifier.py`
- 文件作用：负责解释 waiting_external 所等待的 run 是否仍然存活。
- 顶层函数：_read_json、_seconds_since、_latest_execution_record、build_run_liveness。
- 顶层类：无顶层类。
- 阅读建议：先看模块说明，再按函数/类 docstring 顺着主流程理解调用关系。
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict

from paths import OPENMOSS_ROOT


AUTONOMY_TASKS_ROOT = OPENMOSS_ROOT / "runtime/autonomy/tasks"
WORKSPACE_ROOT = OPENMOSS_ROOT.parent.parent
OUTPUT_ROOT = WORKSPACE_ROOT / "data/output"


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


def _seconds_since(iso_text: str) -> float:
    """
    中文注解：
    - 功能：实现 `_seconds_since` 对应的处理逻辑。
    - 角色：属于本模块中的内部辅助逻辑；私有函数通常服务同文件主流程，公共函数通常作为跨模块入口或能力接口。
    - 调用关系：建议结合本文件的模块说明、调用方以及同名相关辅助函数一起阅读。
    """
    if not iso_text:
        return 10**9
    try:
        dt = datetime.fromisoformat(str(iso_text).replace("Z", "+00:00"))
    except ValueError:
        return 10**9
    return max(0.0, (datetime.now(timezone.utc) - dt).total_seconds())


def _latest_execution_record(task_id: str, run_id: str) -> Dict[str, Any]:
    """
    中文注解：
    - 功能：实现 `_latest_execution_record` 对应的处理逻辑。
    - 角色：属于本模块中的内部辅助逻辑；私有函数通常服务同文件主流程，公共函数通常作为跨模块入口或能力接口。
    - 调用关系：建议结合本文件的模块说明、调用方以及同名相关辅助函数一起阅读。
    """
    records_root = AUTONOMY_TASKS_ROOT / task_id / "executions"
    if not records_root.exists():
        return {}
    latest: Dict[str, Any] = {}
    latest_mtime = -1.0
    for record_path in records_root.glob("*.json"):
        payload = _read_json(record_path)
        if str(payload.get("run_id", "")).strip() != str(run_id).strip():
            continue
        try:
            mtime = record_path.stat().st_mtime
        except OSError:
            mtime = -1.0
        if mtime > latest_mtime:
            latest = payload
            latest_mtime = mtime
    return latest


def _completion_guard_paths(task_id: str) -> Dict[str, Path]:
    """
    中文注解：
    - 功能：给定 task_id，返回一组可作为“工作已完成/已交接”证据的本地 guard 文件路径。
    - 设计意图：当 autonomy runtime 目录已缺失，但 workspace 侧已经留下 final-state / verification / proof / handoff
      等产物时，下游不应继续把任务解释为活跃等待中。
    """
    return {
        "final_state": OUTPUT_ROOT / f"{task_id}-final-state.txt",
        "runtime_handoff": OUTPUT_ROOT / f"{task_id}-runtime-handoff.txt",
        "proof": OUTPUT_ROOT / f"{task_id}-proof.json",
        "verification": OUTPUT_ROOT / f"{task_id}-verification.txt",
    }


def _completion_guards(task_id: str) -> Dict[str, Any]:
    """
    中文注解：
    - 功能：汇总本地 completion guard 是否存在，并给出计数。
    """
    paths = _completion_guard_paths(task_id)
    present = {name: str(path) for name, path in paths.items() if path.exists()}
    return {
        "present": present,
        "present_count": len(present),
        "all_paths": {name: str(path) for name, path in paths.items()},
    }


def build_run_liveness(task_id: str) -> Dict[str, Any]:
    """
    中文注解：
    - 功能：实现 `build_run_liveness` 对应的处理逻辑。
    - 角色：属于本模块中的对外可见逻辑；私有函数通常服务同文件主流程，公共函数通常作为跨模块入口或能力接口。
    - 调用关系：建议结合本文件的模块说明、调用方以及同名相关辅助函数一起阅读。
    """
    task_root = AUTONOMY_TASKS_ROOT / task_id
    state_path = task_root / "state.json"
    contract_path = task_root / "contract.json"
    events_path = task_root / "events.jsonl"
    state = _read_json(state_path)
    metadata = state.get("metadata", {}) or {}
    active = metadata.get("active_execution", {}) or {}
    waiting = metadata.get("waiting_external", {}) or {}
    run_id = str(active.get("run_id", "")).strip()
    stage_name = str(active.get("stage_name", "")).strip() or str(state.get("current_stage", "")).strip()
    latest_record = _latest_execution_record(task_id, run_id) if run_id else {}
    wait_payload = latest_record.get("wait", {}) or {}
    wait_status = str(wait_payload.get("status", "")).strip()
    if not wait_status:
        wait_status = str(waiting.get("wait_status", "")).strip()
    wait_error = str(latest_record.get("wait_error", "")).strip() or str(waiting.get("wait_error", "")).strip()
    last_progress_at = str(state.get("last_progress_at", "")).strip()
    last_update_at = str(state.get("last_update_at", "")).strip()
    completion_guards = _completion_guards(task_id)
    runtime_files_missing = not state_path.exists() and not contract_path.exists() and not events_path.exists()
    orphaned_completed = runtime_files_missing and completion_guards.get("present_count", 0) > 0
    return {
        "task_id": task_id,
        "status": str(state.get("status", "")).strip(),
        "current_stage": str(state.get("current_stage", "")).strip(),
        "next_action": str(state.get("next_action", "")).strip(),
        "run_id": run_id,
        "stage_name": stage_name,
        "waiting_reason": str(waiting.get("reason", "")).strip() or ("agent_wait_timeout" if wait_status == "timeout" else "unknown"),
        "wait_status": wait_status or None,
        "wait_error": wait_error or None,
        "last_polled_at": str(waiting.get("last_polled_at", "")).strip() or None,
        "last_dispatched_at": str(active.get("dispatched_at", "")).strip() or None,
        "idle_seconds": _seconds_since(last_progress_at),
        "update_age_seconds": _seconds_since(last_update_at),
        "latest_execution_status": str(latest_record.get("status", "")).strip() or None,
        "latest_execution_record": latest_record,
        "has_active_execution": bool(run_id),
        "runtime_files_missing": runtime_files_missing,
        "missing_runtime_files": {
            "state": not state_path.exists(),
            "contract": not contract_path.exists(),
            "events": not events_path.exists(),
        },
        "completion_guards": completion_guards,
        "orphaned_completed": orphaned_completed,
        "orphaned_completed_reason": (
            "completed_workspace_guards_with_missing_runtime_state"
            if orphaned_completed
            else None
        ),
    }
