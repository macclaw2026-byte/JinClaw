#!/usr/bin/env python3

from __future__ import annotations

import re
from typing import Any, Dict

from task_status_snapshot import build_task_status_snapshot


def _normalize(text: str) -> str:
    return re.sub(r"\s+", "", str(text or "").strip().lower())


def _looks_like_status_query(goal: str) -> bool:
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
    task_id = str(route.get("task_id", "")).strip()
    if not task_id:
        return route
    snapshot = route.get("authoritative_task_status", {}) or build_task_status_snapshot(task_id)
    status = str(snapshot.get("status", "unknown"))
    goal = str(route.get("goal", ""))
    route = dict(route)
    route["authoritative_task_status"] = snapshot
    route["response_drift_checked"] = True

    if _looks_like_status_query(goal):
        route["mode"] = "authoritative_task_status"
        return route

    if status in {"blocked", "recovering", "waiting_external"} and route.get("mode") in {
        "append_to_existing_task",
        "create_successor_task",
        "append_to_active_successor_task",
    }:
        route["mode"] = "authoritative_task_status"
        return route

    business = snapshot.get("business_outcome", {}) or {}
    if business.get("goal_satisfied") is True and business.get("user_visible_result_confirmed") is True:
        route["mode"] = "authoritative_task_status"
    return route
