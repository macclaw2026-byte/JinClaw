#!/usr/bin/env python3

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _blocked_count(system_summary: Dict[str, Any], category: str) -> int:
    return int(((system_summary.get("blocked_categories", {}) or {}).get(category, 0) or 0))


def _derive_repair_focus(system_summary: Dict[str, Any]) -> str:
    top_blocked_category = str(system_summary.get("top_blocked_category", "")).strip()
    if top_blocked_category in {"project_crawler_remediation", "approval_or_contract", "authorized_session", "human_checkpoint"}:
        return "governance_blockers"
    if top_blocked_category in {"targeted_fix", "runtime_failure", "runtime_or_contract_fix"}:
        return "repair_blockers"
    if top_blocked_category in {"session_binding", "relay_attach"}:
        return "linkage_blockers"
    return "general"


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
    repair_focus = _derive_repair_focus(system_summary)
    repair_mode = "steady_balance"
    blocked_project_crawler = _blocked_count(system_summary, "project_crawler_remediation")
    blocked_authorized_session = _blocked_count(system_summary, "authorized_session")
    blocked_human_checkpoint = _blocked_count(system_summary, "human_checkpoint")
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
    if blocked_project_crawler > 0:
        recommended_mode = "aggressive"
        suggested_interval_seconds = min(suggested_interval_seconds, 900)
        start_tasks = True
        repair_mode = "project_crawler_unblock"
        reasons.append("project_tasks_blocked_by_crawler_remediation")
    if blocked_authorized_session > 0 or blocked_human_checkpoint > 0:
        recommended_mode = "aggressive"
        suggested_interval_seconds = min(suggested_interval_seconds, 1200)
        if repair_mode == "steady_balance":
            repair_mode = "route_gate_unblock"
        reasons.append("crawler_routes_waiting_on_authorized_or_human_gate")
    if repair_focus == "governance_blockers":
        suggested_interval_seconds = min(suggested_interval_seconds, 1200)
        repair_mode = "governance_first"
        reasons.append("doctor_focus_governance_blockers")
    elif repair_focus == "linkage_blockers":
        suggested_interval_seconds = min(suggested_interval_seconds, 1500)
        if repair_mode == "steady_balance":
            repair_mode = "linkage_first"
        reasons.append("doctor_focus_linkage_blockers")
    if active_items and str(feedback.get("coverage_status", "")).strip().lower() == "strong":
        start_tasks = False
        suggested_interval_seconds = max(suggested_interval_seconds, 7200)
        reasons.append("active_remediation_tasks_already_running")
    if blocked_project_crawler > 0:
        start_tasks = True
        reasons = [reason for reason in reasons if reason != "active_remediation_tasks_already_running"]
    return {
        "recommended_mode": recommended_mode,
        "repair_focus": repair_focus,
        "repair_mode": repair_mode,
        "suggested_interval_seconds": suggested_interval_seconds,
        "start_tasks": start_tasks,
        "active_execution_total": len(active_items),
        "reasons": reasons,
        "summary": {
            "feedback_coverage_status": feedback.get("coverage_status", "unknown"),
            "trend_direction": trend.get("direction", "unknown"),
            "attention_sites": attention_sites,
            "memory_writeback_tasks_total": system_summary.get("memory_writeback_tasks_total", 0),
            "blocked_project_crawler_remediation_total": blocked_project_crawler,
            "blocked_authorized_session_total": blocked_authorized_session,
            "blocked_human_checkpoint_total": blocked_human_checkpoint,
        },
    }


def _seller_bulk_policy(system_summary: Dict[str, Any]) -> Dict[str, Any]:
    blocked_approval = _blocked_count(system_summary, "approval_or_contract")
    blocked_targeted_fix = _blocked_count(system_summary, "targeted_fix")
    repair_focus = _derive_repair_focus(system_summary)
    reasons = ["seller_bulk_is_time_window_gated_in_script"]
    recommended_mode = "nightly_window"
    suggested_interval_seconds = 900
    repair_mode = "steady_balance"
    if blocked_approval > 0:
        recommended_mode = "approval_sensitive_nightly"
        suggested_interval_seconds = 1800
        repair_mode = "approval_guarded"
        reasons.append("project_approval_pressure_detected")
    if blocked_targeted_fix >= 3:
        recommended_mode = "repair_sensitive_nightly"
        suggested_interval_seconds = max(suggested_interval_seconds, 1800)
        repair_mode = "targeted_fix_bias"
        reasons.append("multiple_targeted_fix_blockers_detected")
    if repair_focus == "governance_blockers" and repair_mode == "steady_balance":
        repair_mode = "governance_watch"
        reasons.append("doctor_focus_governance_blockers")
    elif repair_focus == "repair_blockers":
        repair_mode = "targeted_fix_bias"
        reasons.append("doctor_focus_repair_blockers")
    return {
        "recommended_mode": recommended_mode,
        "repair_focus": repair_focus,
        "repair_mode": repair_mode,
        "suggested_interval_seconds": suggested_interval_seconds,
        "start_tasks": True,
        "reasons": reasons,
        "window_hour_new_york": 23,
        "skip_outside_window": True,
        "summary": {
            "memory_writeback_tasks_total": system_summary.get("memory_writeback_tasks_total", 0),
            "blocked_approval_or_contract_total": blocked_approval,
            "blocked_targeted_fix_total": blocked_targeted_fix,
        },
    }


def _cross_market_arbitrage_policy(
    crawler_profile: Dict[str, Any],
    system_summary: Dict[str, Any],
) -> Dict[str, Any]:
    feedback = crawler_profile.get("feedback", {}) or {}
    trend = crawler_profile.get("trend", {}) or {}
    attention_sites = int((crawler_profile.get("summary", {}) or {}).get("sites_attention_required", 0) or 0)
    reasons: List[str] = []
    coverage_status = str(feedback.get("coverage_status", "")).strip().lower()
    recommended_mode = "steady"
    loop_sleep_seconds = 300
    discovery_interval_seconds = 30 * 60
    matching_interval_seconds = 60 * 60
    start_tasks = True
    repair_focus = _derive_repair_focus(system_summary)
    repair_mode = "steady_balance"
    blocked_project_crawler = _blocked_count(system_summary, "project_crawler_remediation")
    blocked_authorized_session = _blocked_count(system_summary, "authorized_session")
    blocked_human_checkpoint = _blocked_count(system_summary, "human_checkpoint")
    if coverage_status == "thin":
        recommended_mode = "aggressive"
        loop_sleep_seconds = 180
        discovery_interval_seconds = 15 * 60
        matching_interval_seconds = 30 * 60
        reasons.append("project_feedback_coverage_thin")
    elif coverage_status == "partial":
        recommended_mode = "steady"
        loop_sleep_seconds = 300
        reasons.append("project_feedback_coverage_partial")
    else:
        recommended_mode = "light_touch"
        loop_sleep_seconds = 600
        reasons.append("project_feedback_coverage_strong")
    if str(trend.get("direction", "")).strip().lower() == "degrading":
        recommended_mode = "aggressive"
        loop_sleep_seconds = min(loop_sleep_seconds, 180)
        discovery_interval_seconds = min(discovery_interval_seconds, 15 * 60)
        matching_interval_seconds = min(matching_interval_seconds, 30 * 60)
        reasons.append("crawler_trend_degrading")
    if attention_sites >= 3:
        recommended_mode = "aggressive"
        loop_sleep_seconds = min(loop_sleep_seconds, 180)
        reasons.append("multiple_attention_sites")
    if blocked_project_crawler > 0:
        recommended_mode = "remediation_hold"
        loop_sleep_seconds = max(loop_sleep_seconds, 900)
        discovery_interval_seconds = max(discovery_interval_seconds, 60 * 60)
        matching_interval_seconds = max(matching_interval_seconds, 2 * 60 * 60)
        start_tasks = False
        repair_mode = "crawler_hold"
        reasons.append("project_tasks_blocked_by_crawler_remediation")
    elif blocked_authorized_session > 0 or blocked_human_checkpoint > 0:
        recommended_mode = "guarded"
        loop_sleep_seconds = max(loop_sleep_seconds, 600)
        discovery_interval_seconds = max(discovery_interval_seconds, 45 * 60)
        matching_interval_seconds = max(matching_interval_seconds, 90 * 60)
        repair_mode = "route_guarded"
        reasons.append("crawler_routes_waiting_on_authorized_or_human_gate")
    if repair_focus == "repair_blockers" and repair_mode == "steady_balance":
        recommended_mode = "light_touch"
        loop_sleep_seconds = max(loop_sleep_seconds, 900)
        discovery_interval_seconds = max(discovery_interval_seconds, 45 * 60)
        matching_interval_seconds = max(matching_interval_seconds, 90 * 60)
        repair_mode = "repair_observe"
        reasons.append("doctor_focus_repair_blockers")
    return {
        "recommended_mode": recommended_mode,
        "repair_focus": repair_focus,
        "repair_mode": repair_mode,
        "loop_sleep_seconds": loop_sleep_seconds,
        "discovery_interval_seconds": discovery_interval_seconds,
        "matching_interval_seconds": matching_interval_seconds,
        "report_hour_new_york": 18,
        "start_tasks": start_tasks,
        "reasons": reasons,
        "summary": {
            "feedback_coverage_status": feedback.get("coverage_status", "unknown"),
            "trend_direction": trend.get("direction", "unknown"),
            "attention_sites": attention_sites,
            "memory_writeback_tasks_total": system_summary.get("memory_writeback_tasks_total", 0),
            "blocked_project_crawler_remediation_total": blocked_project_crawler,
            "blocked_authorized_session_total": blocked_authorized_session,
            "blocked_human_checkpoint_total": blocked_human_checkpoint,
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
        "cross_market_arbitrage": _cross_market_arbitrage_policy(crawler_profile, system_summary),
    }
