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
- 文件路径：`tools/openmoss/control_center/crawler_remediation_planner.py`
- 文件作用：把 crawler remediation queue 转换成项目级可执行加固计划，供 control plane / doctor / supervisor 共享。
- 顶层函数：build_crawler_remediation_plan、main。
- 顶层类：无顶层类。
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

from paths import (
    CRAWLER_CAPABILITY_PROFILE_PATH,
    CRAWLER_REMEDIATION_EXECUTION_PATH,
    CRAWLER_REMEDIATION_PLAN_PATH,
    CRAWLER_REMEDIATION_QUEUE_PATH,
    CRAWLER_REMEDIATION_SCHEDULER_STATE_PATH,
)


REPORTS_ROOT = Path("/Users/mac_claw/.openclaw/workspace/crawler/reports")
SITE_PROFILES_ROOT = Path("/Users/mac_claw/.openclaw/workspace/crawler/site-profiles")


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _read_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return default


def _write_json(path: Path, payload: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _execution_feedback_map() -> Dict[str, Dict[str, Any]]:
    execution = _read_json(CRAWLER_REMEDIATION_EXECUTION_PATH, {"items": []}) or {"items": []}
    rows = execution.get("items", []) or []
    return {
        str(row.get("source_remediation_id", "")).strip(): row
        for row in rows
        if str(row.get("source_remediation_id", "")).strip()
    }


def _load_scheduler_state() -> Dict[str, Any]:
    return _read_json(CRAWLER_REMEDIATION_SCHEDULER_STATE_PATH, {}) or {}


def _derive_start_bias(scheduler_state: Dict[str, Any]) -> str:
    explicit = str(scheduler_state.get("last_effective_start_bias", "")).strip()
    if explicit:
        return explicit
    repair_mode = str(scheduler_state.get("last_repair_mode", "")).strip()
    if repair_mode == "project_crawler_unblock":
        return "site_revalidation_first"
    if repair_mode == "route_gate_unblock":
        return "route_unblock_first"
    if repair_mode == "repair_efficiency_watch":
        return "repair_hotspot_first"
    return "balanced"


def _plan_sort_key(item: Dict[str, Any], start_bias: str) -> tuple[int, int, str]:
    priority_rank = {"high": 0, "medium": 1, "low": 2}.get(str(item.get("priority", "medium")).strip().lower(), 9)
    execution_type = str(item.get("execution_type", "")).strip().lower()
    bias_rank = {
        "execution_truth_reconcile": 0,
        "site_revalidation": 1,
        "manual_triage": 2,
        "field_coverage_upgrade": 3,
    }
    if start_bias == "route_unblock_first":
        bias_rank = {
            "execution_truth_reconcile": 1,
            "manual_triage": 1,
            "site_revalidation": 2,
            "field_coverage_upgrade": 3,
        }
    elif start_bias == "repair_hotspot_first":
        bias_rank = {
            "execution_truth_reconcile": 0,
            "site_revalidation": 1,
            "field_coverage_upgrade": 2,
            "manual_triage": 3,
        }
    return (
        priority_rank,
        bias_rank.get(execution_type, 9),
        str(item.get("site", "")),
    )


def _priority_from_execution_feedback(priority: str, execution_feedback: Dict[str, Any]) -> tuple[str, str]:
    task_state = execution_feedback.get("task_state", {}) or {}
    status = str(task_state.get("status", "")).strip().lower()
    current_stage = str(task_state.get("current_stage", "")).strip().lower()
    if status in {"failed", "blocked"}:
        return "high", f"previous remediation task is {status}"
    if status == "recovering":
        return "high", "previous remediation task is recovering"
    if status == "completed":
        return "low", "previous remediation task already completed"
    if status in {"running", "planning"}:
        return "medium", f"previous remediation task active at {current_stage or status}"
    return priority, ""


def _priority_from_project_feedback(priority: str, profile_feedback: Dict[str, Any], action: str, site: str) -> tuple[str, str]:
    coverage_status = str((profile_feedback or {}).get("coverage_status", "")).strip().lower()
    has_crawler_feedback = bool((profile_feedback or {}).get("has_crawler_feedback"))
    has_seller_feedback = bool((profile_feedback or {}).get("has_seller_feedback"))
    recent_sources = {str(item).strip() for item in (profile_feedback or {}).get("recent_project_sources", []) if str(item).strip()}
    if action == "stabilize_site_profile" and not has_crawler_feedback:
        return "high", f"{site or 'project'} lacks recent crawler feedback"
    if action == "improve_structured_field_coverage" and coverage_status in {"thin", "partial"}:
        return "high", "project feedback coverage is not strong enough for field coverage confidence"
    if action == "improve_structured_field_coverage" and has_seller_feedback and "seller_bulk_cycle" in recent_sources:
        return "medium", "seller project feedback is active; keep field coverage upgrade warm"
    return priority, ""


def _plan_for_action(
    item: Dict[str, Any],
    site_map: Dict[str, Dict[str, Any]],
    execution_feedback: Dict[str, Any],
    profile_feedback: Dict[str, Any],
) -> Dict[str, Any]:
    site = str(item.get("site", "")).strip().lower()
    action = str(item.get("action", "")).strip()
    site_profile = site_map.get(site, {})
    preferred_tools = site_profile.get("preferred_tool_order", []) or []
    task_output_fields = list((site_profile.get("task_output_fields", {}) or {}).keys())
    effective_priority, priority_reason = _priority_from_execution_feedback(
        str(item.get("priority", "medium")),
        execution_feedback,
    )
    feedback_priority, feedback_reason = _priority_from_project_feedback(
        effective_priority,
        profile_feedback,
        action,
        site,
    )
    if feedback_priority != effective_priority or feedback_reason:
        effective_priority = feedback_priority
        priority_reason = "; ".join([part for part in [priority_reason, feedback_reason] if part]).strip()
    if action == "stabilize_site_profile":
        return {
            "id": item.get("id", ""),
            "priority": effective_priority,
            "execution_type": "site_revalidation",
            "site": site,
            "goal": f"重新验证 {site} 的抓取矩阵，优先补齐可用主栈与关键结构字段。",
            "suggested_route": "authorized_session" if site_profile.get("authenticated_supported") else "browser_render",
            "suggested_tools": preferred_tools[:4],
            "verification_targets": [
                "best_status becomes usable",
                "at least one usable tool is confirmed",
                "critical task_output_fields are populated",
            ],
            "evidence_inputs": [
                str(REPORTS_ROOT / f"{site}-latest-run.json"),
                str(SITE_PROFILES_ROOT / f"{site}.json"),
            ],
            "execution_feedback": execution_feedback,
            "priority_reason": priority_reason,
        }
    if action == "improve_structured_field_coverage":
        return {
            "id": item.get("id", ""),
            "priority": effective_priority,
            "execution_type": "field_coverage_upgrade",
            "site": site,
            "goal": "补齐项目级 crawler 关键结构字段覆盖率，优先修复当前为空或缺失的字段。",
            "suggested_route": "structured_public_endpoint",
            "suggested_tools": ["httpx", "selectolax", "crawl4ai", "playwright"],
            "verification_targets": [
                "project depth score improves",
                "missing structured fields are reduced",
                "site profiles expose usable task_output_fields",
            ],
            "evidence_inputs": [
                str(CRAWLER_CAPABILITY_PROFILE_PATH),
            ],
            "focus_fields": task_output_fields[:8],
            "execution_feedback": execution_feedback,
            "priority_reason": priority_reason,
        }
    if action == "reconcile_site_execution_truth":
        evidence_inputs = [str(CRAWLER_CAPABILITY_PROFILE_PATH)]
        if site:
            evidence_inputs.extend(
                [
                    str(REPORTS_ROOT / f"{site}-latest-run.json"),
                    str(REPORTS_ROOT / f"{site}-contract.json"),
                    str(SITE_PROFILES_ROOT / f"{site}.json"),
                ]
            )
        return {
            "id": item.get("id", ""),
            "priority": effective_priority,
            "execution_type": "execution_truth_reconcile",
            "site": site,
            "goal": (
                f"对账并修正 {site} 的 latest-run / contract / site-profile 执行真值漂移。"
                if site
                else "对账所有存在 execution-truth drift 的站点，并在安全可解释时自动修正。"
            ),
            "suggested_route": "local_reconciliation",
            "suggested_tools": ["crawler_execution_truth_reconciler", "crawler_contract", "crawler_capability_profile"],
            "verification_targets": [
                "fresh contract matches safe execution truth",
                "safe sites are reconciled without overriding weaker evidence",
                "unresolved sites are explicitly marked for revalidation",
            ],
            "evidence_inputs": evidence_inputs,
            "execution_feedback": execution_feedback,
            "priority_reason": priority_reason,
        }
    return {
        "id": item.get("id", ""),
        "priority": effective_priority,
        "execution_type": "manual_triage",
        "site": site,
        "goal": str(item.get("reason", "")).strip() or "人工检查 remediation action",
        "suggested_route": "human_checkpoint",
        "suggested_tools": [],
        "verification_targets": ["root cause is clarified"],
        "evidence_inputs": [],
        "execution_feedback": execution_feedback,
        "priority_reason": priority_reason,
    }


def build_crawler_remediation_plan() -> Dict[str, Any]:
    queue = _read_json(CRAWLER_REMEDIATION_QUEUE_PATH, {"items": []}) or {"items": []}
    profile = _read_json(CRAWLER_CAPABILITY_PROFILE_PATH, {}) or {}
    execution_feedback_map = _execution_feedback_map()
    scheduler_state = _load_scheduler_state()
    start_bias = _derive_start_bias(scheduler_state)
    sites = profile.get("sites", []) or []
    profile_feedback = profile.get("feedback", {}) or {}
    site_map = {
        str(site.get("site", "")).strip().lower(): site
        for site in sites
        if str(site.get("site", "")).strip()
    }
    plans = [
        _plan_for_action(
            item,
            site_map,
            execution_feedback_map.get(str(item.get("id", "")).strip(), {}),
            profile_feedback,
        )
        for item in (queue.get("items", []) or [])
    ]
    plans.sort(key=lambda item: _plan_sort_key(item, start_bias))
    payload = {
        "generated_at": _utc_now_iso(),
        "summary": {
            "items_total": len(plans),
            "high_priority_total": sum(1 for item in plans if item.get("priority") == "high"),
            "start_bias": start_bias,
            "sites_covered": sorted({item.get("site", "") for item in plans if item.get("site", "")}),
        },
        "items": plans,
    }
    _write_json(CRAWLER_REMEDIATION_PLAN_PATH, payload)
    return payload


def main() -> int:
    print(json.dumps(build_crawler_remediation_plan(), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
