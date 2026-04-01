#!/usr/bin/env python3

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _crawler_remediation_policy(
    crawler_profile: Dict[str, Any],
    remediation_execution: Dict[str, Any],
    system_summary: Dict[str, Any],
) -> Dict[str, Any]:
    feedback = crawler_profile.get("feedback", {}) or {}
    trend = crawler_profile.get("trend", {}) or {}
    attention_sites = int((crawler_profile.get("summary", {}) or {}).get("sites_attention_required", 0) or 0)
    execution_items = list(remediation_execution.get("items", []) or [])
    active_items = [
        item
        for item in execution_items
        if str(((item.get("task_state", {}) or {}).get("status", ""))).strip().lower() in {"running", "planning", "recovering"}
    ]
    reasons: List[str] = []
    recommended_mode = "steady"
    suggested_interval_seconds = 3600
    start_tasks = True
    if str(feedback.get("coverage_status", "")).strip().lower() == "thin":
        recommended_mode = "aggressive"
        suggested_interval_seconds = 1800
        reasons.append("project_feedback_coverage_thin")
    elif str(feedback.get("coverage_status", "")).strip().lower() == "partial":
        recommended_mode = "steady"
        suggested_interval_seconds = 3600
        reasons.append("project_feedback_coverage_partial")
    else:
        recommended_mode = "light_touch"
        suggested_interval_seconds = 7200
        reasons.append("project_feedback_coverage_strong")
    if str(trend.get("direction", "")).strip().lower() == "degrading":
        recommended_mode = "aggressive"
        suggested_interval_seconds = min(suggested_interval_seconds, 1800)
        reasons.append("crawler_trend_degrading")
    if attention_sites >= 3:
        recommended_mode = "aggressive"
        suggested_interval_seconds = min(suggested_interval_seconds, 1800)
        reasons.append("multiple_attention_sites")
    if active_items and str(feedback.get("coverage_status", "")).strip().lower() == "strong":
        start_tasks = False
        suggested_interval_seconds = max(suggested_interval_seconds, 7200)
        reasons.append("active_remediation_tasks_already_running")
    return {
        "recommended_mode": recommended_mode,
        "suggested_interval_seconds": suggested_interval_seconds,
        "start_tasks": start_tasks,
        "active_execution_total": len(active_items),
        "reasons": reasons,
        "summary": {
            "feedback_coverage_status": feedback.get("coverage_status", "unknown"),
            "trend_direction": trend.get("direction", "unknown"),
            "attention_sites": attention_sites,
            "memory_writeback_tasks_total": system_summary.get("memory_writeback_tasks_total", 0),
        },
    }


def _seller_bulk_policy(system_summary: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "recommended_mode": "nightly_window",
        "suggested_interval_seconds": 900,
        "start_tasks": True,
        "reasons": ["seller_bulk_is_time_window_gated_in_script"],
        "summary": {
            "memory_writeback_tasks_total": system_summary.get("memory_writeback_tasks_total", 0),
        },
    }


def build_project_scheduler_policy(
    *,
    crawler_profile: Dict[str, Any],
    remediation_execution: Dict[str, Any],
    system_summary: Dict[str, Any],
) -> Dict[str, Any]:
    return {
        "generated_at": _utc_now_iso(),
        "crawler_remediation": _crawler_remediation_policy(crawler_profile, remediation_execution, system_summary),
        "seller_bulk": _seller_bulk_policy(system_summary),
    }
