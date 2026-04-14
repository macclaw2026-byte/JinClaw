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

from control_center_schemas import build_acquisition_objective_completion_schema
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


def _tool_names(items: List[Any]) -> List[str]:
    names: List[str] = []
    for item in items:
        if isinstance(item, dict):
            value = str(item.get("tool", "")).strip()
        else:
            value = str(item).strip()
        if value and value not in names:
            names.append(value)
    return names


def _nonempty_field_names(fields: Dict[str, Any]) -> List[str]:
    return [name for name, value in (fields or {}).items() if name != "evidence_excerpt" and str(value or "").strip()]


def _derive_execution_truth(
    profile: Dict[str, Any],
    latest_run: Dict[str, Any],
    contract: Dict[str, Any],
) -> Dict[str, Any]:
    """
    中文注解：
    - 功能：统一整理 site-profile、latest-run、contract 三层证据，生成单一可消费的执行真值。
    - 输入角色：profile 更像站点摘要缓存，latest-run 是运行摘要，contract 是带字段门禁的执行裁决。
    - 输出角色：供 capability profile、router、doctor 使用，避免每层各自挑一个 best tool 造成漂移。
    """
    comparison_summary = contract.get("comparison_summary", {}) or {}
    profile_selected_tool = str(profile.get("selected_tool") or "").strip()
    latest_selected_tool = str(latest_run.get("bestTool") or "").strip()
    contract_selected_tool = str(comparison_summary.get("best_tool") or "").strip()
    latest_best_status = str(latest_run.get("bestStatus", "")).strip().lower()
    contract_best_status = str(comparison_summary.get("best_status", "")).strip().lower()
    profile_usable_tools = _tool_names(profile.get("usable_tools", []) or [])
    contract_usable_tools = _tool_names(comparison_summary.get("usable_tools", []) or [])
    latest_usable_tools = [latest_selected_tool] if latest_selected_tool and latest_best_status == "usable" else []
    task_output_fields = (contract.get("task_ready_fields", {}) or {}) or (profile.get("task_output_fields", {}) or {})
    execution_selected_tool = ""
    execution_truth_source = "profile"
    execution_usable_tools = profile_usable_tools
    execution_best_status = str(profile.get("taskReadiness", "") or "").strip().lower()
    if contract_selected_tool or contract_usable_tools:
        execution_selected_tool = contract_selected_tool
        execution_truth_source = "contract"
        execution_usable_tools = contract_usable_tools
        execution_best_status = contract_best_status or execution_best_status
    elif latest_selected_tool or latest_usable_tools:
        execution_selected_tool = latest_selected_tool
        execution_truth_source = "latest_run"
        execution_usable_tools = latest_usable_tools
        execution_best_status = latest_best_status or execution_best_status
    elif profile_selected_tool or profile_usable_tools:
        execution_selected_tool = profile_selected_tool
        execution_truth_source = "profile"
        execution_usable_tools = profile_usable_tools

    profile_has_selection = bool(profile_selected_tool or profile_usable_tools)
    execution_has_selection = bool(execution_selected_tool or execution_usable_tools)
    execution_conflict = bool(contract_selected_tool and latest_selected_tool and contract_selected_tool != latest_selected_tool)
    profile_stale = execution_has_selection and (
        not profile_has_selection
        or profile_selected_tool != execution_selected_tool
        or set(profile_usable_tools) != set(execution_usable_tools)
    )
    if execution_conflict and profile_stale:
        alignment_status = "execution_conflict_and_profile_stale"
    elif execution_conflict:
        alignment_status = "execution_conflict"
    elif profile_stale:
        alignment_status = "profile_stale"
    elif execution_has_selection:
        alignment_status = "aligned"
    elif latest_best_status == "blocked" or contract_best_status == "blocked":
        alignment_status = "blocked_consensus"
    else:
        alignment_status = "no_execution_evidence"
    has_drift = alignment_status in {"profile_stale", "execution_conflict", "execution_conflict_and_profile_stale"}
    route_preference_strength = "none"
    if alignment_status in {"aligned", "profile_stale"} and execution_selected_tool:
        route_preference_strength = "strong"
    elif alignment_status in {"execution_conflict", "execution_conflict_and_profile_stale"} and execution_selected_tool:
        route_preference_strength = "guarded"
    return {
        "selected_tool": execution_selected_tool,
        "best_status": execution_best_status or latest_best_status or contract_best_status,
        "usable_tools": execution_usable_tools,
        "task_output_fields": task_output_fields,
        "execution_truth_source": execution_truth_source,
        "route_preference_strength": route_preference_strength,
        "evidence_alignment": {
            "status": alignment_status,
            "has_drift": has_drift,
            "profile_selected_tool": profile_selected_tool,
            "latest_run_selected_tool": latest_selected_tool,
            "contract_selected_tool": contract_selected_tool,
        },
    }


def _score_site(profile: Dict[str, Any], latest_run: Dict[str, Any], contract: Dict[str, Any], auth_policy_exists: bool) -> Dict[str, Any]:
    tested_tools = [str(item).strip() for item in (profile.get("tested_tools", []) or contract.get("tested_tools", [])) if str(item).strip()]
    execution_truth = _derive_execution_truth(profile, latest_run, contract)
    usable_tools = _tool_names(execution_truth.get("usable_tools", []) or [])
    blocked_tools = [str(item).strip() for item in (profile.get("blocked_tools", []) or contract.get("blocked_tools", [])) if str(item).strip()]
    task_output_fields = execution_truth.get("task_output_fields", {}) or {}
    populated_fields = _nonempty_field_names(task_output_fields)
    field_count = len([name for name in task_output_fields if name != "evidence_excerpt"]) or 1
    field_coverage_ratio = len(populated_fields) / field_count
    best_status = str(execution_truth.get("best_status", "") or latest_run.get("bestStatus", "")).strip().lower()
    confidence = str(profile.get("confidence", "") or "").strip().lower()
    authenticated_supported = bool((profile.get("authenticated_mode", {}) or {}).get("supported")) or auth_policy_exists
    mode = str(profile.get("mode", "") or "").strip()
    blocked_ratio = min(1.0, len(blocked_tools) / max(1, len(tested_tools)))

    readiness = "unknown"
    if best_status == "usable" and usable_tools:
        readiness = "production_ready"
    elif authenticated_supported and mode in {"anonymous_truth_check_only", "browser_first_anonymous"}:
        readiness = "governed_ready"
    elif tested_tools:
        readiness = "attention_required"
    access_posture = "unknown"
    access_route = "human_checkpoint"
    governed_ready = False
    if readiness == "production_ready":
        access_posture = "anonymous_ready"
        access_route = "anonymous_public"
        governed_ready = True
    elif readiness == "governed_ready":
        access_posture = "governed_authenticated_ready"
        access_route = "authorized_session"
        governed_ready = True
    elif tested_tools:
        access_posture = "blocked_or_partial"

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
    if readiness == "governed_ready":
        breadth_score = max(breadth_score, 55.0)
        depth_score = max(depth_score, 60.0)
        stability_score = max(stability_score, 60.0)

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
        "preferred_tool_order": (contract.get("preferred_tool_order", []) or profile.get("preferred_tool_order", [])),
        "selected_tool": execution_truth.get("selected_tool", ""),
        "best_status": best_status,
        "usable_tools": usable_tools,
        "execution_truth_source": execution_truth.get("execution_truth_source", ""),
        "route_preference_strength": execution_truth.get("route_preference_strength", "none"),
        "evidence_alignment": execution_truth.get("evidence_alignment", {}),
        "tested_tools_count": len(tested_tools),
        "usable_tools_count": len(usable_tools),
        "blocked_tools_count": len(blocked_tools),
        "task_output_field_count": len(task_output_fields),
        "populated_output_field_count": len(populated_fields),
        "field_coverage_ratio": round(field_coverage_ratio, 2),
        "authenticated_supported": authenticated_supported,
        "auth_policy_exists": auth_policy_exists,
        "breadth_score": breadth_score,
        "depth_score": depth_score,
        "stability_score": stability_score,
        "readiness": readiness,
        "governed_ready": governed_ready,
        "access_posture": access_posture,
        "preferred_access_route": access_route,
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
        [site for site in sites if site.get("readiness") not in {"production_ready", "governed_ready"}],
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
    if not recent_project_sources:
        if has_seller_feedback:
            recent_project_sources.append("seller_bulk_cycle")
        if has_crawler_feedback:
            recent_project_sources.append("crawler_remediation_cycle")
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


def _build_completion_contract(summary: Dict[str, Any], feedback: Dict[str, Any], sites: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    中文注解：
    - 功能：给 acquisition-hand 生成项目级 completion contract。
    - 输入角色：summary 代表项目聚合指标，feedback 代表项目反馈闭环，sites 用来定位具体 blocker。
    - 输出角色：供 doctor/status/runtime 明确判断“这只抓取的手是否已经达到当前项目目标”。
    """
    required_checks = [
        {
            "key": "all_sites_governed_ready",
            "ok": int(summary.get("sites_governed_ready", 0) or 0) >= int(summary.get("sites_total", 0) or 0) > 0,
            "why": "所有目标站点都必须至少进入 governed-ready，可走匿名或授权治理路径。",
        },
        {
            "key": "no_attention_required_sites",
            "ok": int(summary.get("sites_attention_required", 0) or 0) == 0,
            "why": "还存在 attention-required 站点时，取数之手仍有明显缺口。",
        },
        {
            "key": "execution_truth_aligned",
            "ok": int(summary.get("sites_with_evidence_drift", 0) or 0) == 0 and float(summary.get("evidence_alignment_score", 0.0) or 0.0) >= 100.0,
            "why": "site profile、latest run 与 contract 必须收敛成单一执行真值。",
        },
        {
            "key": "effective_width_full",
            "ok": float(summary.get("governed_width_score", 0.0) or 0.0) >= 100.0,
            "why": "项目目标看的是 effective governed width，不是匿名 production width。",
        },
        {
            "key": "feedback_loop_strong",
            "ok": str(feedback.get("coverage_status", "")).strip().lower() == "strong",
            "why": "没有强反馈闭环时，系统无法稳定学习和持续择优。",
        },
        {
            "key": "stability_floor_met",
            "ok": float(summary.get("stability_score", 0.0) or 0.0) >= 60.0,
            "why": "完成态至少要达到治理认可的稳定性下限。",
        },
    ]
    satisfied_checks = [item["key"] for item in required_checks if item.get("ok")]
    blockers: List[Dict[str, Any]] = []
    if int(summary.get("sites_governed_ready", 0) or 0) < int(summary.get("sites_total", 0) or 0):
        blockers.append(
            {
                "key": "missing_governed_ready_sites",
                "value": [site.get("site", "") for site in sites if not site.get("governed_ready")][:8],
                "reason": "仍有站点没有完成匿名或授权治理接入。",
            }
        )
    if int(summary.get("sites_attention_required", 0) or 0) > 0:
        blockers.append(
            {
                "key": "attention_required_sites",
                "value": [site.get("site", "") for site in sites if site.get("readiness") == "attention_required"][:8],
                "reason": "仍有 attention-required 站点需要继续修复。",
            }
        )
    if int(summary.get("sites_with_evidence_drift", 0) or 0) > 0:
        blockers.append(
            {
                "key": "execution_truth_drift",
                "value": [site.get("site", "") for site in sites if bool((site.get("evidence_alignment", {}) or {}).get("has_drift"))][:8],
                "reason": "仍有站点的 profile / latest-run / contract 没有对齐。",
            }
        )
    if float(summary.get("governed_width_score", 0.0) or 0.0) < 100.0:
        blockers.append(
            {
                "key": "effective_width_incomplete",
                "value": float(summary.get("governed_width_score", 0.0) or 0.0),
                "reason": "effective governed width 还没有覆盖全部目标站点。",
            }
        )
    if str(feedback.get("coverage_status", "")).strip().lower() != "strong":
        blockers.append(
            {
                "key": "feedback_loop_not_strong",
                "value": str(feedback.get("coverage_status", "")).strip().lower() or "unknown",
                "reason": "项目反馈闭环仍然不够强，后续自动择优与学习会偏弱。",
            }
        )
    if float(summary.get("stability_score", 0.0) or 0.0) < 60.0:
        blockers.append(
            {
                "key": "stability_floor_not_met",
                "value": float(summary.get("stability_score", 0.0) or 0.0),
                "reason": "稳定性还没有达到治理认可的收口阈值。",
            }
        )
    completion_score = 100.0 if not blockers else round((len(satisfied_checks) / max(1, len(required_checks))) * 100.0, 2)
    effective_width_score = max(
        float(summary.get("width_score", 0.0) or 0.0),
        float(summary.get("governed_width_score", 0.0) or 0.0),
    )
    return build_acquisition_objective_completion_schema(
        objective="build a fully governed, explainable, multi-route acquisition hand for JinClaw/OpenClaw",
        status="complete" if not blockers else "incomplete",
        goal_reached=not blockers,
        completion_score=completion_score,
        effective_width_score=effective_width_score,
        required_checks=required_checks,
        satisfied_checks=satisfied_checks,
        blockers=blockers,
        rationale=[
            "effective completion 以 governed-ready 覆盖为准，因此授权态可治理站点不会被匿名 production width 误伤。",
            "项目收口同时要求 execution truth 对齐、强反馈闭环和稳定性达标，避免只是‘看起来可用’。",
        ],
        terminal_boundaries=[
            "safety_boundary",
            "permission_boundary",
            "governance_boundary",
        ],
    )


def build_crawler_capability_profile() -> Dict[str, Any]:
    sites: List[Dict[str, Any]] = []
    for profile_path in sorted(SITE_PROFILES_ROOT.glob("*.json")):
        site_id = profile_path.stem
        profile = _read_json(profile_path, {})
        latest_run = _read_json(REPORTS_ROOT / f"{site_id}-latest-run.json", {})
        contract = _read_json(REPORTS_ROOT / f"{site_id}-contract.json", {})
        auth_policy_exists = (SITE_PROFILES_ROOT / f"{site_id}-auth-policy.md").exists()
        if not profile and not latest_run and not contract:
            continue
        sites.append(_score_site(profile, latest_run, contract, auth_policy_exists))

    sites_total = len(sites)
    usable_sites = [site for site in sites if site.get("readiness") == "production_ready"]
    attention_sites = [site for site in sites if site.get("readiness") == "attention_required"]
    authenticated_sites = [site for site in sites if site.get("authenticated_supported")]
    governed_ready_sites = [site for site in sites if site.get("governed_ready")]
    authorized_session_ready_sites = [site for site in sites if site.get("access_posture") == "governed_authenticated_ready"]
    drift_sites = [site for site in sites if bool((site.get("evidence_alignment", {}) or {}).get("has_drift"))]
    aligned_sites = [
        site for site in sites
        if str(((site.get("evidence_alignment", {}) or {}).get("status", ""))).strip() in {"aligned", "blocked_consensus"}
    ]
    width_score = round((len(usable_sites) / max(1, sites_total)) * 100, 2)
    governed_width_score = round((len(governed_ready_sites) / max(1, sites_total)) * 100, 2)
    evidence_alignment_score = round((len(aligned_sites) / max(1, sites_total)) * 100, 2)
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
        "sites_governed_ready": len(governed_ready_sites),
        "sites_authorized_session_ready": len(authorized_session_ready_sites),
        "sites_with_evidence_drift": len(drift_sites),
        "width_score": width_score,
        "governed_width_score": governed_width_score,
        "evidence_alignment_score": evidence_alignment_score,
        "breadth_score": breadth_score,
        "depth_score": depth_score,
        "stability_score": stability_score,
        "primary_attention_reasons": dict(sorted(attention_reasons.items(), key=lambda item: (-item[1], item[0]))),
    }
    memory_writeback_overview = summarize_project_memory_writebacks()
    feedback = _build_feedback_summary(memory_writeback_overview)
    completion_contract = _build_completion_contract(summary, feedback, sites)
    summary["completion_status"] = str(completion_contract.get("status", "")).strip() or "incomplete"
    summary["completion_score"] = float(completion_contract.get("completion_score", 0.0) or 0.0)
    summary["effective_width_score"] = float(completion_contract.get("effective_width_score", 0.0) or 0.0)
    summary["goal_reached"] = bool(completion_contract.get("goal_reached"))
    summary["completion_blocker_total"] = len(completion_contract.get("blockers", []) or [])
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
    if drift_sites:
        priority_actions.append(
            {
                "priority": "high",
                "action": "reconcile_site_execution_truth",
                "reason": f"{len(drift_sites)} site profiles drift from execution evidence",
            }
        )
    profile = {
        "generated_at": _utc_now_iso(),
        "version": "crawler-capability-profile-v1",
        "summary": summary,
        "trend": trend,
        "feedback": feedback,
        "completion_contract": completion_contract,
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
