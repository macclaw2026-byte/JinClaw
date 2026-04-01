#!/usr/bin/env python3

"""
中文说明：
- 文件路径：`tools/openmoss/control_center/crawler_capability_profile.py`
- 文件作用：汇总 JinClaw 项目的 crawler 站点画像、工具可用性、抓取宽度/广度/深度/稳定性，并生成项目级抓取能力快照。
- 顶层函数：build_crawler_capability_profile、main。
- 顶层类：无顶层类。
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

from memory_writeback_runtime import summarize_project_memory_writebacks
from paths import CRAWLER_CAPABILITY_HISTORY_PATH, CRAWLER_CAPABILITY_PROFILE_PATH


CRAWLER_ROOT = Path("/Users/mac_claw/.openclaw/workspace/crawler")
SITE_PROFILES_ROOT = CRAWLER_ROOT / "site-profiles"
REPORTS_ROOT = CRAWLER_ROOT / "reports"


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _read_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return default


def _read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except OSError:
        return ""


def _write_json(path: Path, payload: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _score_site(profile: Dict[str, Any], latest_run: Dict[str, Any], auth_policy_exists: bool) -> Dict[str, Any]:
    tested_tools = [str(item).strip() for item in profile.get("tested_tools", []) if str(item).strip()]
    usable_tools = [str(item).strip() for item in profile.get("usable_tools", []) if str(item).strip()]
    blocked_tools = [str(item).strip() for item in profile.get("blocked_tools", []) if str(item).strip()]
    task_output_fields = profile.get("task_output_fields", {}) or {}
    populated_fields = [name for name, value in task_output_fields.items() if str(value or "").strip()]
    field_count = len(task_output_fields) or 1
    field_coverage_ratio = len(populated_fields) / field_count
    best_status = str(latest_run.get("bestStatus", "") or "").strip().lower()
    confidence = str(profile.get("confidence", "") or "").strip().lower()
    authenticated_supported = bool((profile.get("authenticated_mode", {}) or {}).get("supported")) or auth_policy_exists
    blocked_ratio = min(1.0, len(blocked_tools) / max(1, len(tested_tools)))

    breadth_score = min(100.0, round(35 + len(tested_tools) * 4 + len(usable_tools) * 6 - len(blocked_tools) * 2, 2))
    depth_score = min(
        100.0,
        round(
            25
            + field_coverage_ratio * 35
            + (15 if best_status == "usable" else 0)
            + (10 if authenticated_supported else 0)
            + (10 if len(usable_tools) >= 2 else 0),
            2,
        ),
    )
    stability_score = min(
        100.0,
        round(
            40
            + (20 if best_status == "usable" else 0)
            + (10 if confidence == "high" else 5 if confidence == "medium" else 0)
            + (10 if usable_tools else 0)
            - blocked_ratio * 25,
            2,
        ),
    )
    readiness = (
        "production_ready"
        if best_status == "usable" and usable_tools
        else "attention_required"
        if tested_tools
        else "unknown"
    )
    primary_limitations = []
    if blocked_tools:
        primary_limitations.append(f"blocked_tools:{', '.join(blocked_tools[:4])}")
    if not populated_fields:
        primary_limitations.append("missing_structured_fields")
    if not usable_tools:
        primary_limitations.append("no_usable_tool")
    if best_status and best_status != "usable":
        primary_limitations.append(f"best_status:{best_status}")

    return {
        "site": profile.get("site") or latest_run.get("site") or "",
        "mode": profile.get("mode", ""),
        "confidence": profile.get("confidence", ""),
        "preferred_tool_order": profile.get("preferred_tool_order", []),
        "selected_tool": profile.get("selected_tool", "") or latest_run.get("bestTool", ""),
        "best_status": latest_run.get("bestStatus", "") or profile.get("taskReadiness", ""),
        "tested_tools_count": len(tested_tools),
        "usable_tools_count": len(usable_tools),
        "blocked_tools_count": len(blocked_tools),
        "task_output_field_count": len(task_output_fields),
        "populated_output_field_count": len(populated_fields),
        "field_coverage_ratio": round(field_coverage_ratio, 2),
        "authenticated_supported": authenticated_supported,
        "breadth_score": breadth_score,
        "depth_score": depth_score,
        "stability_score": stability_score,
        "readiness": readiness,
        "primary_limitations": primary_limitations,
        "latest_notes": ((latest_run.get("taskReadySummary", {}) or {}).get("notes", []) or [])[:5],
    }


def _append_history(summary: Dict[str, Any]) -> Dict[str, Any]:
    history = _read_json(CRAWLER_CAPABILITY_HISTORY_PATH, {"entries": []}) or {"entries": []}
    entries = list(history.get("entries", []) or [])
    entries.append(
        {
            "generated_at": _utc_now_iso(),
            "summary": summary,
        }
    )
    entries = entries[-30:]
    payload = {"entries": entries}
    _write_json(CRAWLER_CAPABILITY_HISTORY_PATH, payload)
    return payload


def _trend_delta(current: float, previous: float) -> float:
    return round(float(current or 0) - float(previous or 0), 2)


def _build_trend_summary(history_entries: List[Dict[str, Any]], summary: Dict[str, Any]) -> Dict[str, Any]:
    if len(history_entries) < 2:
        return {
            "sample_size": len(history_entries),
            "direction": "insufficient_history",
            "deltas": {},
        }
    previous = (history_entries[-2].get("summary", {}) or {})
    deltas = {
        "width_score": _trend_delta(summary.get("width_score", 0), previous.get("width_score", 0)),
        "breadth_score": _trend_delta(summary.get("breadth_score", 0), previous.get("breadth_score", 0)),
        "depth_score": _trend_delta(summary.get("depth_score", 0), previous.get("depth_score", 0)),
        "stability_score": _trend_delta(summary.get("stability_score", 0), previous.get("stability_score", 0)),
        "sites_production_ready": _trend_delta(summary.get("sites_production_ready", 0), previous.get("sites_production_ready", 0)),
        "sites_attention_required": _trend_delta(summary.get("sites_attention_required", 0), previous.get("sites_attention_required", 0)),
    }
    negative_axes = sum(1 for key, value in deltas.items() if key.endswith("_score") and value < 0)
    positive_axes = sum(1 for key, value in deltas.items() if key.endswith("_score") and value > 0)
    direction = "stable"
    if negative_axes >= 2:
        direction = "degrading"
    elif positive_axes >= 2:
        direction = "improving"
    return {
        "sample_size": len(history_entries),
        "direction": direction,
        "deltas": deltas,
    }


def _build_priority_actions(sites: List[Dict[str, Any]], summary: Dict[str, Any], trend: Dict[str, Any]) -> List[Dict[str, Any]]:
    actions: List[Dict[str, Any]] = []
    ranked_sites = sorted(
        [site for site in sites if site.get("readiness") != "production_ready"],
        key=lambda item: (
            len(item.get("primary_limitations", []) or []),
            -(item.get("depth_score", 0.0) or 0.0),
            -(item.get("stability_score", 0.0) or 0.0),
        ),
        reverse=True,
    )
    for site in ranked_sites[:5]:
        actions.append(
            {
                "site": site.get("site", ""),
                "priority": "high" if "no_usable_tool" in (site.get("primary_limitations", []) or []) else "medium",
                "action": "stabilize_site_profile",
                "reason": ", ".join((site.get("primary_limitations", []) or [])[:3]),
            }
        )
    if float(summary.get("depth_score", 0) or 0) < 50:
        actions.append(
            {
                "priority": "high",
                "action": "improve_structured_field_coverage",
                "reason": "project depth score remains below target",
            }
        )
    if trend.get("direction") == "degrading":
        actions.append(
            {
                "priority": "high",
                "action": "rerun_first_run_matrix",
                "reason": "crawler capability trend is degrading",
            }
        )
    return actions[:6]


def _build_feedback_summary(overview: Dict[str, Any]) -> Dict[str, Any]:
    target_counts = overview.get("target_counts", {}) or {}
    source_counts = overview.get("source_counts", {}) or {}
    recent_items = list(overview.get("recent_items", []) or [])
    recent_project_items = [
        item
        for item in recent_items
        if "project" in (((item.get("last_entry", {}) or {}).get("targets", []) or []))
    ]
    recent_project_sources: List[str] = []
    for item in recent_project_items:
        source = str(((item.get("last_entry", {}) or {}).get("source", ""))).strip()
        if source and source not in recent_project_sources:
            recent_project_sources.append(source)
    has_crawler_feedback = bool(source_counts.get("crawler_remediation_cycle"))
    has_seller_feedback = bool(source_counts.get("seller_bulk_cycle"))
    coverage_status = "strong"
    if not has_crawler_feedback and not has_seller_feedback:
        coverage_status = "thin"
    elif not has_crawler_feedback or not has_seller_feedback:
        coverage_status = "partial"
    return {
        "tasks_total": int(overview.get("tasks_total", 0) or 0),
        "project_target_total": int(target_counts.get("project", 0) or 0),
        "runtime_target_total": int(target_counts.get("runtime", 0) or 0),
        "recent_project_sources": recent_project_sources[:6],
        "has_crawler_feedback": has_crawler_feedback,
        "has_seller_feedback": has_seller_feedback,
        "coverage_status": coverage_status,
    }


def build_crawler_capability_profile() -> Dict[str, Any]:
    sites: List[Dict[str, Any]] = []
    for profile_path in sorted(SITE_PROFILES_ROOT.glob("*.json")):
        site_id = profile_path.stem
        profile = _read_json(profile_path, {})
        latest_run = _read_json(REPORTS_ROOT / f"{site_id}-latest-run.json", {})
        auth_policy_exists = (SITE_PROFILES_ROOT / f"{site_id}-auth-policy.md").exists()
        if not profile and not latest_run:
            continue
        sites.append(_score_site(profile, latest_run, auth_policy_exists))

    sites_total = len(sites)
    usable_sites = [site for site in sites if site.get("readiness") == "production_ready"]
    attention_sites = [site for site in sites if site.get("readiness") == "attention_required"]
    authenticated_sites = [site for site in sites if site.get("authenticated_supported")]
    width_score = round((len(usable_sites) / max(1, sites_total)) * 100, 2)
    breadth_score = round(sum(site.get("breadth_score", 0.0) for site in sites) / max(1, sites_total), 2)
    depth_score = round(sum(site.get("depth_score", 0.0) for site in sites) / max(1, sites_total), 2)
    stability_score = round(sum(site.get("stability_score", 0.0) for site in sites) / max(1, sites_total), 2)

    attention_reasons: Dict[str, int] = {}
    for site in attention_sites:
        for item in site.get("primary_limitations", []) or []:
            attention_reasons[item] = attention_reasons.get(item, 0) + 1

    summary = {
        "sites_total": sites_total,
        "sites_production_ready": len(usable_sites),
        "sites_attention_required": len(attention_sites),
        "authenticated_sites": len(authenticated_sites),
        "width_score": width_score,
        "breadth_score": breadth_score,
        "depth_score": depth_score,
        "stability_score": stability_score,
        "primary_attention_reasons": dict(sorted(attention_reasons.items(), key=lambda item: (-item[1], item[0]))),
    }
    memory_writeback_overview = summarize_project_memory_writebacks()
    feedback = _build_feedback_summary(memory_writeback_overview)
    history = _append_history(summary)
    trend = _build_trend_summary(history.get("entries", []) or [], summary)
    priority_actions = _build_priority_actions(sites, summary, trend)
    if not feedback.get("has_crawler_feedback"):
        priority_actions.append(
            {
                "priority": "high",
                "action": "restore_project_crawler_feedback_loop",
                "reason": "crawler remediation cycle has not written project feedback yet",
            }
        )
    if not feedback.get("has_seller_feedback"):
        priority_actions.append(
            {
                "priority": "medium",
                "action": "restore_project_seller_feedback_loop",
                "reason": "seller nightly has not written project feedback yet",
            }
        )
    if feedback.get("coverage_status") == "thin":
        priority_actions.append(
            {
                "priority": "high",
                "action": "increase_project_memory_feedback_coverage",
                "reason": "project-target memory writeback coverage is too thin",
            }
        )
    profile = {
        "generated_at": _utc_now_iso(),
        "version": "crawler-capability-profile-v1",
        "summary": summary,
        "trend": trend,
        "feedback": feedback,
        "memory_writeback_overview": {
            "tasks_total": memory_writeback_overview.get("tasks_total", 0),
            "target_counts": memory_writeback_overview.get("target_counts", {}) or {},
            "source_counts": memory_writeback_overview.get("source_counts", {}) or {},
        },
        "history_path": str(CRAWLER_CAPABILITY_HISTORY_PATH),
        "recommended_project_actions": [
            "stabilize_sites_marked_attention_required" if attention_sites else "keep_site_profiles_fresh",
            "promote_high_confidence_tool_orders",
            "refresh_first_run_matrix_when_best_status_degrades",
            "improve_project_feedback_loop" if feedback.get("coverage_status") != "strong" else "keep_project_feedback_loop_healthy",
        ],
        "priority_actions": priority_actions[:8],
        "sites": sites,
    }
    _write_json(CRAWLER_CAPABILITY_PROFILE_PATH, profile)
    return profile


def main() -> int:
    print(json.dumps(build_crawler_capability_profile(), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
