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
- 文件路径：`tools/openmoss/control_center/response_drift_detector.py`
- 文件作用：负责拦截回复与权威状态漂移。
- 顶层函数：_normalize、_looks_like_status_query、reconcile_route_with_authoritative_state。
- 顶层类：无顶层类。
- 阅读建议：先看模块说明，再按函数/类 docstring 顺着主流程理解调用关系。
"""
from __future__ import annotations

import re
from typing import Any, Dict

from execution_governor import governance_attention_flags
from task_status_snapshot import build_task_status_snapshot


def _normalize(text: str) -> str:
    """
    中文注解：
    - 功能：实现 `_normalize` 对应的处理逻辑。
    - 角色：属于本模块中的内部辅助逻辑；私有函数通常服务同文件主流程，公共函数通常作为跨模块入口或能力接口。
    - 调用关系：建议结合本文件的模块说明、调用方以及同名相关辅助函数一起阅读。
    """
    return re.sub(r"\s+", "", str(text or "").strip().lower())


def _looks_like_status_query(goal: str) -> bool:
    """
    中文注解：
    - 功能：实现 `_looks_like_status_query` 对应的处理逻辑。
    - 角色：属于本模块中的内部辅助逻辑；私有函数通常服务同文件主流程，公共函数通常作为跨模块入口或能力接口。
    - 调用关系：建议结合本文件的模块说明、调用方以及同名相关辅助函数一起阅读。
    """
    normalized = _normalize(goal)
    patterns = (
        "进展",
        "进度",
        "状态",
        "结果",
        "到什么阶段",
        "什么阶段",
        "搞定了吗",
        "完成了吗",
        "解决了吗",
        "跑通了吗",
        "情况",
    )
    return any(token in normalized for token in patterns)


def reconcile_route_with_authoritative_state(route: Dict[str, Any]) -> Dict[str, Any]:
    """
    中文注解：
    - 功能：实现 `reconcile_route_with_authoritative_state` 对应的处理逻辑。
    - 角色：属于本模块中的对外可见逻辑；私有函数通常服务同文件主流程，公共函数通常作为跨模块入口或能力接口。
    - 调用关系：建议结合本文件的模块说明、调用方以及同名相关辅助函数一起阅读。
    """
    task_id = str(route.get("task_id", "")).strip()
    if not task_id:
        return route
    snapshot = route.get("authoritative_task_status", {}) or build_task_status_snapshot(task_id)
    status = str(snapshot.get("status", "unknown"))
    goal = str(route.get("goal", ""))
    governance_flags = governance_attention_flags(snapshot)
    route = dict(route)
    route["authoritative_task_status"] = snapshot
    route["response_drift_checked"] = True
    route["governance_attention"] = governance_flags

    if _looks_like_status_query(goal):
        route["mode"] = "authoritative_task_status"
        return route

    # 这里不能再把“动作型新指令”简单改写成纯状态回复。
    # 之前只要当前任务正处于 waiting/recovering/blocked，新的动作型 follow-up
    # 就会被强制降级成 authoritative_task_status，于是用户看到的只是一句
    # “当前在 waiting_external...”，像是系统没真正接到新指令。
    #
    # 正确做法是：
    # - 保留动作型 route mode，让系统继续推进任务链；
    # - 同时把权威状态快照附着在 route 上，交给回复策略生成更诚实的确认文案。
    if status in {"blocked", "recovering", "waiting_external"} and route.get("mode") in {
        "append_to_existing_task",
        "create_successor_task",
        "append_to_active_successor_task",
        "append_to_root_mission_task",
        "branch_from_active_task",
        "reopen_from_archive_task",
    }:
        route["state_attention_required"] = True
    if any(governance_flags.values()) and route.get("mode") not in {"task_completed_notice", "milestone_progress_notice"}:
        route["state_attention_required"] = True

    business = snapshot.get("business_outcome", {}) or {}
    if business.get("goal_satisfied") is True and business.get("user_visible_result_confirmed") is True:
        route["mode"] = "authoritative_task_status"
    return route
