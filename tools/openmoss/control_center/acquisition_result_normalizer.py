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
- 文件路径：`tools/openmoss/control_center/acquisition_result_normalizer.py`
- 文件作用：把 crawler probe 的真实执行结果归一化成 acquisition execution summary。
- 顶层函数：build_acquisition_execution_summary、render_acquisition_execution_summary_markdown、main。
- 顶层类：无顶层类。
"""
from __future__ import annotations

import json
from collections import defaultdict
from typing import Any, Dict, List

from control_center_schemas import (
    build_acquisition_execution_summary_schema,
    build_acquisition_field_provenance_schema,
    build_acquisition_release_disclosure_schema,
    build_acquisition_route_result_schema,
    build_acquisition_site_synthesis_schema,
)


STATUS_RANK = {
    "usable": 4,
    "partial": 3,
    "blocked": 1,
    "failed": 0,
}

ROUTE_TRUST_RANK = {
    "official_api": 5,
    "structured_public_endpoint": 4,
    "static_fetch": 3,
    "crawl4ai": 3,
    "browser_render": 2,
    "authorized_session": 2,
}

SOURCE_TRUST_RANK = {
    "official_source": 5,
    "reviewed_session": 5,
    "structured_public": 4,
    "public_fetch": 3,
    "content_extraction": 3,
    "browser_observation": 1,
}

FRESHNESS_ALIGNMENT_RANK = {
    "fresh_ready": 3,
    "session_snapshot": 2,
    "snapshot_only": 1,
    "adequate": 2,
}

RISK_PENALTY = {
    "low": 0,
    "medium": 4,
    "high": 8,
}

SITE_EXPECTED_FIELDS = {
    "amazon": ["title", "price", "rating", "reviews", "link"],
    "walmart": ["title", "price", "rating", "link"],
    "temu": ["title", "price", "link", "promo"],
    "1688": ["title", "price", "moq", "supplier", "link"],
}


def _normalized(value: str) -> str:
    return str(value or "").strip().lower().replace("_", "-")


def _unique_preserve(values: List[str]) -> List[str]:
    seen: set[str] = set()
    ordered: List[str] = []
    for value in values:
        text = str(value).strip()
        if not text or text in seen:
            continue
        seen.add(text)
        ordered.append(text)
    return ordered


def _planned_route_ids(acquisition_hand: Dict[str, Any]) -> List[str]:
    strategy = acquisition_hand.get("execution_strategy", {}) or {}
    return _unique_preserve(
        [
            str(strategy.get("primary_route_id", "")).strip(),
            *[str(item).strip() for item in strategy.get("validation_route_ids", []) or []],
            *[str(item).strip() for item in strategy.get("escalation_route_ids", []) or []],
        ]
    )


def _adapter_maps(acquisition_hand: Dict[str, Any]) -> Dict[str, Any]:
    registry = acquisition_hand.get("adapter_registry", {}) or {}
    adapters = registry.get("adapters", []) or []
    adapters_by_id = {
        str(item.get("adapter_id", "")).strip(): item
        for item in adapters
        if str(item.get("adapter_id", "")).strip()
    }
    tool_to_adapters: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    for adapter in adapters:
        for label in adapter.get("tool_labels", []) or []:
            normalized = _normalized(str(label))
            if normalized:
                tool_to_adapters[normalized].append(adapter)
    route_candidates = acquisition_hand.get("route_candidates", []) or []
    candidates_by_adapter: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    for candidate in route_candidates:
        adapter_id = str(candidate.get("adapter_id", "")).strip()
        if adapter_id:
            candidates_by_adapter[adapter_id].append(candidate)
    return {
        "adapters_by_id": adapters_by_id,
        "tool_to_adapters": tool_to_adapters,
        "candidates_by_adapter": candidates_by_adapter,
    }


def _report_execution_plan(report_payload: Dict[str, Any]) -> Dict[str, Any]:
    """
    中文注解：
    - 功能：读取 crawler probe 回传的局部执行计划。
    - 设计意图：当 probe 已明确记录“这次按哪些 route/tool 执行”时，summary 应优先消费这份一手证据。
    """
    planned_execution = report_payload.get("planned_execution", {}) or {}
    route_plan = [item for item in (planned_execution.get("route_plan", []) or []) if isinstance(item, dict)]
    return {
        "source": str(planned_execution.get("source", "")).strip(),
        "global_planned_route_ids": _unique_preserve(
            [str(item).strip() for item in planned_execution.get("global_planned_route_ids", []) or [] if str(item).strip()]
        ),
        "active_route_ids": _unique_preserve(
            [str(item).strip() for item in planned_execution.get("active_route_ids", []) or [] if str(item).strip()]
        ),
        "skipped_route_ids": _unique_preserve(
            [str(item).strip() for item in planned_execution.get("skipped_route_ids", []) or [] if str(item).strip()]
        ),
        "route_plan": route_plan,
    }


def _planned_route_binding(tool_label: str, execution_plan: Dict[str, Any]) -> Dict[str, Any]:
    normalized_tool = _normalized(tool_label)
    for item in execution_plan.get("route_plan", []) or []:
        if _normalized(str(item.get("tool_label", "")).strip()) == normalized_tool:
            return item
    return {}


def _pick_adapter(tool_label: str, acquisition_hand: Dict[str, Any], maps: Dict[str, Any]) -> Dict[str, Any]:
    normalized_label = _normalized(tool_label)
    matches = list((maps.get("tool_to_adapters", {}) or {}).get(normalized_label, []))
    if not matches:
        return {}
    candidates_by_adapter = maps.get("candidates_by_adapter", {}) or {}
    for adapter in matches:
        adapter_id = str(adapter.get("adapter_id", "")).strip()
        if candidates_by_adapter.get(adapter_id):
            return adapter
    for adapter in matches:
        if bool(adapter.get("enabled")) and str(adapter.get("auth_requirement", "none")).strip() == "none":
            return adapter
    return matches[0]


def _pick_route_candidate(adapter: Dict[str, Any], acquisition_hand: Dict[str, Any], maps: Dict[str, Any]) -> Dict[str, Any]:
    adapter_id = str(adapter.get("adapter_id", "")).strip()
    route_type = str(adapter.get("route_type", "")).strip()
    strategy = acquisition_hand.get("execution_strategy", {}) or {}
    prioritized_ids = _planned_route_ids(acquisition_hand)
    candidates = list((maps.get("candidates_by_adapter", {}) or {}).get(adapter_id, []))
    if not candidates:
        candidates = [
            item
            for item in acquisition_hand.get("route_candidates", []) or []
            if str(item.get("route_type", "")).strip() == route_type
        ]
    for route_id in prioritized_ids:
        for candidate in candidates:
            if str(candidate.get("route_id", "")).strip() == route_id:
                return candidate
    primary_route_id = str(strategy.get("primary_route_id", "")).strip()
    for candidate in candidates:
        if str(candidate.get("route_id", "")).strip() == primary_route_id:
            return candidate
    return candidates[0] if candidates else {}


def _route_quality_score(route_run: Dict[str, Any], acquisition_hand: Dict[str, Any]) -> float:
    strategy = acquisition_hand.get("execution_strategy", {}) or {}
    primary_route_id = str(strategy.get("primary_route_id", "")).strip()
    status_rank = STATUS_RANK.get(str(route_run.get("status", "")).strip(), 0)
    trust_rank = SOURCE_TRUST_RANK.get(_route_source_trust_tier(route_run), 0)
    risk_penalty = RISK_PENALTY.get(str(route_run.get("route_risk", "medium")).strip(), 4)
    preferred_site_bonus = 6 if route_run.get("preferred_site_match") else 0
    primary_bonus = 4 if str(route_run.get("route_id", "")).strip() == primary_route_id else 0
    required_field_bonus = float(route_run.get("required_field_coverage", 0.0) or 0.0) * 75
    freshness_bonus = FRESHNESS_ALIGNMENT_RANK.get(_route_freshness_alignment(route_run, acquisition_hand), 1) * 5
    return round(
        status_rank * 100
        + float(route_run.get("field_coverage", 0.0) or 0.0) * 60
        + required_field_bonus
        + int(route_run.get("arbitration_score", 0) or 0)
        + trust_rank * 12
        + freshness_bonus
        + preferred_site_bonus
        + primary_bonus
        - risk_penalty,
        3,
    )


def _route_validation_family(route_run: Dict[str, Any]) -> str:
    return str(route_run.get("validation_family", "")).strip() or str(route_run.get("route_type", "")).strip() or "unknown"


def _route_source_trust_tier(route_run: Dict[str, Any]) -> str:
    route_type = str(route_run.get("route_type", "")).strip()
    return (
        str(route_run.get("source_trust_tier", "")).strip()
        or {
            "official_api": "official_source",
            "structured_public_endpoint": "structured_public",
            "static_fetch": "public_fetch",
            "crawl4ai": "content_extraction",
            "browser_render": "browser_observation",
            "authorized_session": "reviewed_session",
        }.get(route_type, "")
        or "unknown"
    )


def _goal_time_sensitivity(acquisition_hand: Dict[str, Any]) -> str:
    return str(((acquisition_hand.get("target_profile", {}) or {}).get("time_sensitivity", "normal"))).strip() or "normal"


def _route_freshness_alignment(route_run: Dict[str, Any], acquisition_hand: Dict[str, Any]) -> str:
    if _goal_time_sensitivity(acquisition_hand) != "fresh":
        return str(route_run.get("freshness_alignment", "")).strip() or "adequate"
    route_type = str(route_run.get("route_type", "")).strip()
    return (
        str(route_run.get("freshness_alignment", "")).strip()
        or {
            "official_api": "fresh_ready",
            "structured_public_endpoint": "fresh_ready",
            "authorized_session": "session_snapshot",
            "static_fetch": "snapshot_only",
            "crawl4ai": "snapshot_only",
            "browser_render": "snapshot_only",
        }.get(route_type, "snapshot_only")
    )


def _route_families_for_ids(route_runs: List[Dict[str, Any]], route_ids: List[str]) -> List[str]:
    route_id_set = {str(item).strip() for item in route_ids if str(item).strip()}
    return _unique_preserve(
        [
            _route_validation_family(route_run)
            for route_run in route_runs
            if str(route_run.get("route_id", "")).strip() in route_id_set and _route_validation_family(route_run) != "unknown"
        ]
    )


def _delivery_requirements(acquisition_hand: Dict[str, Any]) -> Dict[str, Any]:
    return acquisition_hand.get("delivery_requirements", {}) or {}


def _release_governance(acquisition_hand: Dict[str, Any]) -> Dict[str, Any]:
    return acquisition_hand.get("release_governance", {}) or {}


def _site_field_requirements(
    site: str,
    acquisition_hand: Dict[str, Any],
    route_runs: List[Dict[str, Any]],
) -> Dict[str, List[str]]:
    """
    中文注解：
    - 功能：解析当前站点的 required/stretch 字段要求。
    - 设计意图：字段级合成应优先服从本次任务的交付要求，而不是只使用站点默认模板。
    """
    requirements = _delivery_requirements(acquisition_hand)
    required_by_site = requirements.get("required_fields_by_site", {}) or {}
    stretch_by_site = requirements.get("stretch_fields_by_site", {}) or {}
    default_required = required_by_site.get("default", []) or SITE_EXPECTED_FIELDS.get(site, [])[:3] or ["title", "link"]
    default_stretch = stretch_by_site.get("default", []) or []
    required_fields = _unique_preserve(
        [
            str(item).strip()
            for item in (required_by_site.get(site, []) or default_required)
            if str(item).strip()
        ]
    )
    stretch_fields = _unique_preserve(
        [
            str(item).strip()
            for item in (stretch_by_site.get(site, []) or default_stretch)
            if str(item).strip() and str(item).strip() not in set(required_fields)
        ]
    )
    discovered = _unique_preserve(
        [
            *[
                str(key).strip()
                for row in route_runs
                for key in (row.get("task_fields", {}) or {}).keys()
                if str(key).strip()
            ],
            *[
                str(item).strip()
                for row in route_runs
                for item in (row.get("populated_fields", []) or [])
                if str(item).strip()
            ],
        ]
    )
    stretch_fields = _unique_preserve([*stretch_fields, *[field for field in discovered if field not in required_fields]])
    return {
        "required_fields": required_fields,
        "stretch_fields": stretch_fields,
    }


def _required_field_metrics(task_fields: Dict[str, Any], required_fields: List[str]) -> Dict[str, Any]:
    present = [field for field in required_fields if _value_present((task_fields or {}).get(field))]
    missing = [field for field in required_fields if field not in set(present)]
    return {
        "required_fields_present": present,
        "missing_required_fields": missing,
        "required_field_coverage": round(len(present) / max(1, len(required_fields)), 3) if required_fields else 1.0,
    }


def _field_agreement(winner_fields: Dict[str, Any], other_fields: Dict[str, Any]) -> Dict[str, int]:
    shared_keys = [
        key
        for key in winner_fields.keys()
        if str(winner_fields.get(key, "")).strip() and str(other_fields.get(key, "")).strip()
    ]
    equal_count = sum(
        1
        for key in shared_keys
        if str(winner_fields.get(key, "")).strip() == str(other_fields.get(key, "")).strip()
    )
    diff_count = len(shared_keys) - equal_count
    return {
        "shared_fields": len(shared_keys),
        "equal_fields": equal_count,
        "different_fields": diff_count,
    }


def _value_present(value: Any) -> bool:
    if value is None:
        return False
    if isinstance(value, str):
        return bool(value.strip())
    if isinstance(value, (list, dict, tuple, set)):
        return bool(value)
    return True


def _value_key(value: Any) -> str:
    if isinstance(value, str):
        return str(value).strip().lower()
    return json.dumps(value, ensure_ascii=False, sort_keys=True)


def _field_group_score(best_quality_score: float, support_count: int) -> float:
    return round(float(best_quality_score or 0.0) + support_count * 35.0, 3)


def _derive_expected_fields(site: str, route_runs: List[Dict[str, Any]], acquisition_hand: Dict[str, Any]) -> List[str]:
    site_requirements = _site_field_requirements(site, acquisition_hand, route_runs)
    expected = [
        *site_requirements.get("required_fields", []),
        *site_requirements.get("stretch_fields", []),
        *SITE_EXPECTED_FIELDS.get(site, []),
    ]
    discovered = _unique_preserve(
        [
            *[
                str(key).strip()
                for row in route_runs
                for key in (row.get("task_fields", {}) or {}).keys()
                if str(key).strip()
            ],
            *[
                str(item).strip()
                for row in route_runs
                for item in (row.get("populated_fields", []) or [])
                if str(item).strip()
            ],
        ]
    )
    return _unique_preserve([*expected, *discovered])


def _required_field_freshness_posture(
    required_fields: List[str],
    field_provenance: Dict[str, Dict[str, Any]],
) -> str:
    alignments = _unique_preserve(
        [
            str((field_provenance.get(field_name, {}) or {}).get("selected_freshness_alignment", "")).strip()
            for field_name in required_fields
            if str((field_provenance.get(field_name, {}) or {}).get("selected_freshness_alignment", "")).strip()
        ]
    )
    if not alignments:
        return "not_ready"
    if any(item == "snapshot_only" for item in alignments):
        return "snapshot_only"
    if any(item == "session_snapshot" for item in alignments):
        return "session_snapshot"
    if any(item == "fresh_ready" for item in alignments):
        return "fresh_ready"
    if any(item == "adequate" for item in alignments):
        return "adequate"
    return alignments[0]


def _site_governed_release(
    *,
    release_ready: bool,
    trust_posture: str,
    freshness_posture: str,
    acquisition_hand: Dict[str, Any],
) -> Dict[str, Any]:
    """
    中文注解：
    - 功能：把结构性 readiness、来源信任和新鲜度姿态汇总成真正可执行的 release 治理结论。
    - 设计意图：系统不仅要知道“现在像不像能交付”，还要知道“此刻是否允许自动交付、是否只能 guarded 交付、是否必须先补抓”。
    """
    rules = _release_governance(acquisition_hand)
    preferred_actions = dict(rules.get("preferred_blocking_actions", {}) or {})
    fresh_task = _goal_time_sensitivity(acquisition_hand) == "fresh"
    blockers: List[str] = []
    actions: List[str] = []
    notes: List[str] = []
    governed_release_status = "blocked_release_readiness"
    governed_release_ready = False

    freshness_blocked = False
    if fresh_task and freshness_posture == "snapshot_only" and not bool(rules.get("allow_snapshot_only_for_fresh", False)):
        freshness_blocked = True
        blockers.append("snapshot_only_freshness_blocker")
        actions.append(preferred_actions.get("freshness_gap", "rerun_fresher_route_before_release"))
        notes.append("当前任务要求新鲜数据，但核心字段仍主要来自 snapshot-only 证据。")
    if fresh_task and freshness_posture == "session_snapshot" and not bool(rules.get("allow_session_snapshot_for_fresh", True)):
        freshness_blocked = True
        blockers.append("session_snapshot_freshness_blocker")
        actions.append(preferred_actions.get("freshness_gap", "rerun_fresher_route_before_release"))
        notes.append("当前任务要求新鲜数据，但 reviewed session 快照仍不满足 release 规则。")

    if not release_ready:
        blockers.append("release_readiness_blocked")
        notes.append("结构性 release readiness 尚未满足，当前结果不能进入交付路径。")
    elif trust_posture == "guarded_low_trust_sources":
        blockers.append("guarded_low_trust_blocker")
        actions.append(preferred_actions.get("guarded_low_trust", "seek_higher_trust_source_before_release"))
        governed_release_status = "needs_higher_trust_source"
        notes.append("核心字段仍主要依赖低信任浏览器观察证据，不能自动交付。")
    elif trust_posture == "guarded_medium_trust_sources":
        if bool(rules.get("auto_release_requires_trusted_ready", False)):
            if bool(rules.get("requires_human_confirmation_for_guarded", False)):
                blockers.append("guarded_medium_trust_requires_confirmation")
                actions.append(preferred_actions.get("human_confirmation", "ask_user_to_confirm_guarded_release"))
                governed_release_status = "guarded_requires_human_confirmation"
                notes.append("当前结果结构上可交付，但治理规则要求 guarded medium-trust 结果先获用户确认。")
            else:
                blockers.append("guarded_medium_trust_blocker")
                actions.append(preferred_actions.get("guarded_medium_trust", "capture_higher_trust_source_before_release"))
                governed_release_status = "needs_higher_trust_source"
                notes.append("当前任务要求 trusted-ready 级别结果，medium-trust 证据仍需升级。")
        elif bool(rules.get("allow_guarded_medium_trust_with_disclosure", True)):
            governed_release_status = "guarded_release_with_disclosure"
            governed_release_ready = True
            actions.append("include_guarded_release_disclosure")
            notes.append("当前结果允许 guarded 交付，但必须明确披露其主要来自 medium-trust 证据。")
        else:
            blockers.append("guarded_medium_trust_blocker")
            actions.append(preferred_actions.get("guarded_medium_trust", "capture_higher_trust_source_before_release"))
            governed_release_status = "needs_higher_trust_source"
            notes.append("medium-trust guarded release 当前不被允许。")
    elif freshness_blocked:
        blockers.append("freshness_blocker")
        governed_release_status = "needs_fresher_capture"
    else:
        governed_release_status = "auto_release_allowed"
        governed_release_ready = True
        notes.append("当前结果满足自动交付规则。")

    if freshness_blocked and governed_release_status in {"needs_higher_trust_source", "guarded_requires_human_confirmation"}:
        actions.append(preferred_actions.get("freshness_gap", "rerun_fresher_route_before_release"))
    return {
        "freshness_posture": freshness_posture,
        "governed_release_status": governed_release_status,
        "governed_release_ready": governed_release_ready,
        "governance_blockers": _unique_preserve(blockers),
        "governance_actions": _unique_preserve(actions),
        "governance_notes": notes,
    }


def _build_release_disclosure(
    *,
    site: str,
    governed_release_status: str,
    trust_posture: str,
    freshness_posture: str,
    governance_blockers: List[str],
    governance_actions: List[str],
    acquisition_hand: Dict[str, Any],
) -> Dict[str, Any]:
    """
    中文注解：
    - 功能：把 guarded/blocked release 的说明整理成结构化 disclosure。
    - 设计意图：release governance 不能只给内部状态名，还要能直接转成用户可见的披露与操作提示。
    """
    fresh_task = _goal_time_sensitivity(acquisition_hand) == "fresh"
    site_label = str(site or "current target").strip()
    status = str(governed_release_status or "").strip()
    blocker_reasons = _unique_preserve([str(item).strip() for item in governance_blockers if str(item).strip()])
    actions = _unique_preserve([str(item).strip() for item in governance_actions if str(item).strip()])
    user_lines: List[str] = []
    headline = ""
    summary = ""
    level = "none"
    requires_confirmation = False
    required = False

    if status == "guarded_release_with_disclosure":
        required = True
        level = "guarded"
        headline = f"{site_label} currently qualifies for a guarded release"
        summary = "结果可交付，但必须明确说明其关键字段仍主要来自 medium-trust 证据。"
        user_lines.append(f"{site_label} 的关键字段目前主要来自公开抓取或内容提取证据，而不是更高信任层级来源。")
        user_lines.append("这份结果适合作为 guarded answer 使用，并应保留来源与局限说明。")
    elif status == "guarded_requires_human_confirmation":
        required = True
        level = "confirmation_required"
        requires_confirmation = True
        headline = f"{site_label} requires user confirmation before guarded release"
        summary = "结果结构上可用，但治理规则要求先由用户确认，再以 guarded 方式交付。"
        user_lines.append(f"{site_label} 的关键字段当前没有达到 trusted-ready 水平。")
        user_lines.append("如果要继续使用当前结果，需要用户明确确认接受 guarded release。")
    elif status == "needs_higher_trust_source":
        required = True
        level = "blocked"
        headline = f"{site_label} needs a higher-trust source before release"
        summary = "当前结果还不能按现有治理规则交付，需要更高信任层级的来源补强。"
        user_lines.append(f"{site_label} 的当前证据层级不足以满足 release 规则。")
        user_lines.append("建议继续补抓更高信任来源，而不是直接把当前值当成最终答案。")
    elif status == "needs_fresher_capture":
        required = True
        level = "blocked"
        headline = f"{site_label} needs a fresher capture before release"
        summary = "当前结果的时效性不足，不能满足 fresh 任务的交付规则。"
        user_lines.append(f"{site_label} 当前依赖的证据时间姿态是 `{freshness_posture}`，还不够新。")
        user_lines.append("在 fresh 任务里，应先重新获取更新的数据后再交付。")
    elif status == "blocked_release_readiness":
        required = True
        level = "blocked"
        headline = f"{site_label} is not release-ready yet"
        summary = "当前结果还没有满足结构性 release readiness。"
        user_lines.append(f"{site_label} 仍存在缺失字段、未解决冲突或其他 release blocker。")
    else:
        return build_acquisition_release_disclosure_schema(
            required=False,
            level="none",
            headline="",
            summary="",
            user_visible_lines=[],
            blocker_reasons=[],
            recommended_actions=[],
            requires_user_confirmation=False,
        )

    if trust_posture == "guarded_low_trust_sources":
        user_lines.append("核心字段主要来自低信任浏览器观察证据。")
    elif trust_posture == "guarded_medium_trust_sources":
        user_lines.append("核心字段主要来自 medium-trust 的公开抓取/内容提取证据。")
    if fresh_task:
        user_lines.append(f"这次任务是 fresh-sensitive 任务，当前 freshness posture 为 `{freshness_posture}`。")
    return build_acquisition_release_disclosure_schema(
        required=required,
        level=level,
        headline=headline,
        summary=summary,
        user_visible_lines=_unique_preserve(user_lines),
        blocker_reasons=blocker_reasons,
        recommended_actions=actions,
        requires_user_confirmation=requires_confirmation,
    )


def _aggregate_release_disclosure(site_outputs: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    中文注解：
    - 功能：把站点级 disclosure 聚合成任务级 release disclosure。
    - 设计意图：doctor、snapshot、用户回复通常消费任务级摘要，因此需要一份总披露说明。
    """
    disclosures = [item.get("release_disclosure", {}) or {} for item in site_outputs if (item.get("release_disclosure", {}) or {})]
    required_disclosures = [item for item in disclosures if bool(item.get("required"))]
    if not required_disclosures:
        return build_acquisition_release_disclosure_schema(
            required=False,
            level="none",
            headline="",
            summary="",
            user_visible_lines=[],
            blocker_reasons=[],
            recommended_actions=[],
            requires_user_confirmation=False,
        )
    levels = [str(item.get("level", "")).strip() for item in required_disclosures if str(item.get("level", "")).strip()]
    if "confirmation_required" in levels:
        level = "confirmation_required"
    elif "blocked" in levels:
        level = "blocked"
    else:
        level = "guarded"
    headline = str(required_disclosures[0].get("headline", "")).strip()
    summary = " | ".join(
        [str(item.get("summary", "")).strip() for item in required_disclosures if str(item.get("summary", "")).strip()]
    )[:600]
    return build_acquisition_release_disclosure_schema(
        required=True,
        level=level,
        headline=headline,
        summary=summary,
        user_visible_lines=_unique_preserve(
            [str(line).strip() for item in required_disclosures for line in (item.get("user_visible_lines", []) or []) if str(line).strip()]
        ),
        blocker_reasons=_unique_preserve(
            [str(line).strip() for item in required_disclosures for line in (item.get("blocker_reasons", []) or []) if str(line).strip()]
        ),
        recommended_actions=_unique_preserve(
            [str(line).strip() for item in required_disclosures for line in (item.get("recommended_actions", []) or []) if str(line).strip()]
        ),
        requires_user_confirmation=any(bool(item.get("requires_user_confirmation")) for item in required_disclosures),
    )


def _field_provenance_for_site(
    site: str,
    route_runs: List[Dict[str, Any]],
    acquisition_hand: Dict[str, Any],
) -> Dict[str, Any]:
    """
    中文注解：
    - 功能：对单个站点做字段级融合与 provenance 说明。
    - 设计意图：站点级 winner 只能回答“谁赢了”，字段级 provenance 才能回答“最终每个字段为何选它”。
    """
    surviving = [item for item in route_runs if str(item.get("status", "")).strip() in {"usable", "partial"}]
    site_requirements = _site_field_requirements(site, acquisition_hand, surviving or route_runs)
    required_fields = site_requirements.get("required_fields", [])
    stretch_fields = site_requirements.get("stretch_fields", [])
    expected_fields = _derive_expected_fields(site, surviving or route_runs, acquisition_hand)
    if not surviving:
        return build_acquisition_site_synthesis_schema(
            site=site,
            synthesis_status="blocked",
            required_fields=required_fields,
            stretch_fields=stretch_fields,
            missing_fields=expected_fields,
            missing_required_fields=required_fields,
            missing_stretch_fields=stretch_fields,
            required_field_coverage_ratio=0.0,
            release_ready=False,
            recommended_next_actions=["switch_route_or_pause_for_human_checkpoint"],
            notes=["当前站点没有 surviving route，无法进行字段级融合。"],
        )

    final_fields: Dict[str, Any] = {}
    field_provenance: Dict[str, Dict[str, Any]] = {}
    cross_validated_fields: List[str] = []
    conflicted_fields: List[str] = []
    missing_fields: List[str] = []

    for field_name in expected_fields:
        observations = []
        for route_run in surviving:
            value = (route_run.get("task_fields", {}) or {}).get(field_name)
            if not _value_present(value):
                continue
            observations.append(
                {
                    "value": value,
                    "route_run": route_run,
                    "quality_score": _route_quality_score(route_run, acquisition_hand),
                }
            )
        if not observations:
            missing_fields.append(field_name)
            continue

        grouped: Dict[str, Dict[str, Any]] = {}
        for obs in observations:
            key = _value_key(obs.get("value"))
            bucket = grouped.setdefault(
                key,
                {
                    "value": obs.get("value"),
                    "supporting_route_ids": [],
                    "supporting_values": [],
                    "best_observation": obs,
                    "best_quality_score": float(obs.get("quality_score", 0.0) or 0.0),
                },
            )
            route_run = obs.get("route_run", {}) or {}
            route_id = str(route_run.get("route_id", "")).strip()
            if route_id:
                bucket["supporting_route_ids"].append(route_id)
            bucket["supporting_values"].append(obs.get("value"))
            if float(obs.get("quality_score", 0.0) or 0.0) > float(bucket.get("best_quality_score", 0.0) or 0.0):
                bucket["best_quality_score"] = float(obs.get("quality_score", 0.0) or 0.0)
                bucket["best_observation"] = obs

        grouped_rows = []
        for bucket in grouped.values():
            support_count = len(_unique_preserve(bucket.get("supporting_route_ids", []) or []))
            grouped_rows.append(
                {
                    **bucket,
                    "supporting_route_ids": _unique_preserve(bucket.get("supporting_route_ids", []) or []),
                    "group_score": _field_group_score(float(bucket.get("best_quality_score", 0.0) or 0.0), support_count),
                }
            )
        grouped_rows.sort(
            key=lambda item: (
                -float(item.get("group_score", 0.0) or 0.0),
                -len(item.get("supporting_route_ids", []) or []),
            )
        )
        selected = grouped_rows[0]
        selected_obs = selected.get("best_observation", {}) or {}
        selected_route = selected_obs.get("route_run", {}) or {}
        selected_source_trust_tier = _route_source_trust_tier(selected_route)
        selected_freshness_alignment = _route_freshness_alignment(selected_route, acquisition_hand)
        disagreeing_route_ids = _unique_preserve(
            [
                route_id
                for bucket in grouped_rows[1:]
                for route_id in (bucket.get("supporting_route_ids", []) or [])
                if str(route_id).strip()
            ]
        )
        supporting_families = _route_families_for_ids(surviving, selected.get("supporting_route_ids", []) or [])
        disagreeing_families = _route_families_for_ids(surviving, disagreeing_route_ids)

        confidence = "single_route"
        resolution_basis = "single_route_observation"
        notes: List[str] = []
        if len(grouped_rows) == 1:
            if len(selected.get("supporting_route_ids", []) or []) >= 2:
                confidence = "cross_validated_independent" if len(supporting_families) >= 2 else "cross_validated_same_family"
                resolution_basis = "cross_route_agreement"
                cross_validated_fields.append(field_name)
                if len(supporting_families) >= 2:
                    notes.append("至少两条不同验证家族的路线对该字段给出了相同值。")
                else:
                    notes.append("至少两条路线对该字段给出了相同值，但仍属于同一验证家族。")
            else:
                notes.append("当前字段只有单路线证据。")
        else:
            lead = float(selected.get("group_score", 0.0) or 0.0) - float(grouped_rows[1].get("group_score", 0.0) or 0.0)
            runner_up_route = (((grouped_rows[1] or {}).get("best_observation", {}) or {}).get("route_run", {}) or {})
            source_trust_gap = SOURCE_TRUST_RANK.get(selected_source_trust_tier, 0) - SOURCE_TRUST_RANK.get(_route_source_trust_tier(runner_up_route), 0)
            freshness_gap = FRESHNESS_ALIGNMENT_RANK.get(selected_freshness_alignment, 0) - FRESHNESS_ALIGNMENT_RANK.get(
                _route_freshness_alignment(runner_up_route, acquisition_hand),
                0,
            )
            if len(selected.get("supporting_route_ids", []) or []) >= 2 and lead >= 15:
                confidence = (
                    "resolved_multi_route_majority_independent"
                    if len(supporting_families) >= 2
                    else "resolved_multi_route_majority_same_family"
                )
                resolution_basis = "multi_route_majority"
                cross_validated_fields.append(field_name)
                if len(supporting_families) >= 2:
                    notes.append("存在冲突，但不同验证家族的多数路线支持当前值。")
                else:
                    notes.append("存在冲突，但多数支持仍来自同一验证家族。")
            elif source_trust_gap >= 2:
                confidence = "resolved_by_source_trust"
                resolution_basis = "source_trust_priority"
                notes.append("存在冲突，当前值优先采用来源信任层级更高的路线。")
            elif _goal_time_sensitivity(acquisition_hand) == "fresh" and source_trust_gap == 0 and freshness_gap >= 1:
                confidence = "resolved_by_freshness"
                resolution_basis = "freshness_priority"
                notes.append("存在冲突，当前值优先采用更新鲜的路线证据。")
            elif lead >= 40:
                confidence = "resolved_by_best_evidence"
                resolution_basis = "best_evidence_score"
                conflicted_fields.append(field_name)
                notes.append("存在冲突，当前值由最佳证据路线胜出。")
            else:
                confidence = "conflict_unresolved"
                resolution_basis = "unresolved_conflict"
                conflicted_fields.append(field_name)
                notes.append("字段冲突未完全消解，需要人工复核。")

        final_fields[field_name] = selected.get("value")
        field_provenance[field_name] = build_acquisition_field_provenance_schema(
            field_name=field_name,
            selected_value=selected.get("value"),
            selected_route_id=str(selected_route.get("route_id", "")).strip(),
            selected_adapter_id=str(selected_route.get("adapter_id", "")).strip(),
            selected_tool_label=str(selected_route.get("tool_label", "")).strip(),
            selected_source_trust_tier=selected_source_trust_tier,
            selected_freshness_alignment=selected_freshness_alignment,
            resolution_basis=resolution_basis,
            confidence=confidence,
            supporting_route_ids=selected.get("supporting_route_ids", []) or [],
            supporting_validation_families=supporting_families,
            disagreeing_route_ids=disagreeing_route_ids,
            disagreeing_validation_families=disagreeing_families,
            supporting_values=selected.get("supporting_values", []) or [],
            notes=notes,
        )

    missing_required_fields = [field for field in required_fields if field not in final_fields]
    missing_stretch_fields = [field for field in stretch_fields if field not in final_fields]
    required_field_coverage_ratio = round(
        (len(required_fields) - len(missing_required_fields)) / max(1, len(required_fields)),
        3,
    ) if required_fields else 1.0
    synthesis_status = "blocked"
    site_notes: List[str] = []
    recommended_next_actions: List[str] = []
    release_ready = False
    if final_fields:
        synthesis_status = "ready"
        if conflicted_fields:
            synthesis_status = "needs_review"
            site_notes.append("部分字段存在冲突，当前结果是保守择优后的合成视图。")
            recommended_next_actions.append("review_field_level_conflicts_before_release")
        elif missing_required_fields:
            synthesis_status = "partial"
            site_notes.append("核心 required 字段仍有缺口，当前结果可参考但不应直接 release。")
            recommended_next_actions.append("capture_missing_required_fields_before_release")
        elif missing_fields:
            synthesis_status = "partial"
            site_notes.append("已满足核心 required 字段，但仍缺少扩展字段。")
            recommended_next_actions.append("capture_missing_fields_via_backup_route")
        else:
            site_notes.append("当前站点已形成完整字段级合成结果。")
        release_ready = not conflicted_fields and not missing_required_fields
    else:
        recommended_next_actions.append("switch_route_or_pause_for_human_checkpoint")

    required_trust_tiers = _unique_preserve(
        [
            str((field_provenance.get(field_name, {}) or {}).get("selected_source_trust_tier", "")).strip()
            for field_name in required_fields
            if (field_provenance.get(field_name, {}) or {}).get("selected_source_trust_tier")
        ]
    )
    trust_posture = "not_ready"
    trusted_release_ready = False
    if release_ready:
        if required_trust_tiers and any(tier == "browser_observation" for tier in required_trust_tiers):
            trust_posture = "guarded_low_trust_sources"
            recommended_next_actions.append("seek_higher_trust_source_before_release")
            site_notes.append("核心字段当前主要来自浏览器观察类证据，建议继续寻找更高信任来源。")
        elif required_trust_tiers and any(tier in {"public_fetch", "content_extraction"} for tier in required_trust_tiers):
            trust_posture = "guarded_medium_trust_sources"
            recommended_next_actions.append("capture_higher_trust_source_before_release")
            site_notes.append("核心字段已经可交付，但主要来自公共抓取/内容提取证据。")
        else:
            trust_posture = "trusted_sources"
            trusted_release_ready = True
            site_notes.append("核心字段主要来自较高信任层级的来源。")

    freshness_posture = _required_field_freshness_posture(required_fields, field_provenance)
    release_governance = _site_governed_release(
        release_ready=release_ready,
        trust_posture=trust_posture,
        freshness_posture=freshness_posture,
        acquisition_hand=acquisition_hand,
    )
    release_disclosure = _build_release_disclosure(
        site=site,
        governed_release_status=str(release_governance.get("governed_release_status", "")).strip(),
        trust_posture=trust_posture,
        freshness_posture=freshness_posture,
        governance_blockers=list(release_governance.get("governance_blockers", []) or []),
        governance_actions=list(release_governance.get("governance_actions", []) or []),
        acquisition_hand=acquisition_hand,
    )
    site_notes.extend(list(release_governance.get("governance_notes", []) or []))
    recommended_next_actions.extend(list(release_governance.get("governance_actions", []) or []))

    return build_acquisition_site_synthesis_schema(
        site=site,
        synthesis_status=synthesis_status,
        final_fields=final_fields,
        field_provenance=field_provenance,
        required_fields=required_fields,
        stretch_fields=stretch_fields,
        missing_fields=missing_fields,
        missing_required_fields=missing_required_fields,
        missing_stretch_fields=missing_stretch_fields,
        required_field_coverage_ratio=required_field_coverage_ratio,
        release_ready=release_ready,
        trust_posture=trust_posture,
        trusted_release_ready=trusted_release_ready,
        freshness_posture=str(release_governance.get("freshness_posture", "")).strip(),
        governed_release_status=str(release_governance.get("governed_release_status", "")).strip(),
        governed_release_ready=bool(release_governance.get("governed_release_ready")),
        governance_blockers=list(release_governance.get("governance_blockers", []) or []),
        release_disclosure=release_disclosure,
        cross_validated_fields=_unique_preserve(cross_validated_fields),
        conflicted_fields=_unique_preserve(conflicted_fields),
        supporting_route_ids=_unique_preserve(
            [str(item.get("route_id", "")).strip() for item in surviving if str(item.get("route_id", "")).strip()]
        ),
        recommended_next_actions=_unique_preserve(recommended_next_actions),
        notes=site_notes,
    )


def _site_consensus(site: str, route_runs: List[Dict[str, Any]], acquisition_hand: Dict[str, Any]) -> Dict[str, Any]:
    surviving = [item for item in route_runs if str(item.get("status", "")).strip() in {"usable", "partial"}]
    if not surviving:
        return {
            "site": site,
            "decision": "insufficient_evidence",
            "validation_status": "blocked_or_empty",
            "winner": {},
            "compared_route_ids": [str(item.get("route_id", "")).strip() for item in route_runs if str(item.get("route_id", "")).strip()],
            "requires_review": True,
            "recommended_next_actions": ["switch_route_or_pause_for_human_checkpoint"],
            "notes": ["当前站点没有可用于任务交付的 surviving routes。"],
        }

    ranked = sorted(
        surviving,
        key=lambda item: (
            -_route_quality_score(item, acquisition_hand),
            str(item.get("route_risk", "medium")).strip(),
            str(item.get("route_id", "")).strip(),
        ),
    )
    winner = ranked[0]
    compared_families = _unique_preserve([_route_validation_family(item) for item in ranked if _route_validation_family(item) != "unknown"])
    validation_status = "single_route_only"
    requires_review = False
    notes: List[str] = []
    recommended_next_actions: List[str] = []

    if len(ranked) >= 2:
        agreements = [
            _field_agreement(dict(winner.get("task_fields", {}) or {}), dict(item.get("task_fields", {}) or {}))
            for item in ranked[1:]
        ]
        if any(item.get("different_fields", 0) > 0 for item in agreements):
            validation_status = "conflict_detected"
            requires_review = True
            notes.append("多路线在共享字段上出现冲突。")
            recommended_next_actions.append("review_conflicting_route_outputs_before_release")
        elif any(item.get("equal_fields", 0) > 0 for item in agreements):
            if len(compared_families) >= 2:
                validation_status = "cross_validated_independent"
                notes.append("至少存在一条不同验证家族的路线与赢家在共享字段上达成一致。")
            else:
                validation_status = "cross_validated_same_family"
                notes.append("存在路线与赢家达成一致，但仍属于同一验证家族。")
        else:
            validation_status = "weak_validation"
            notes.append("存在多路线，但共享字段不足，验证强度有限。")
            recommended_next_actions.append("capture_additional_validation_route_if_needed")

    if str(winner.get("status", "")).strip() != "usable":
        requires_review = True
        notes.append("赢家路线只有 partial 质量，建议保守处理。")
        recommended_next_actions.append("improve_field_coverage_before_release")
    if (winner.get("missing_required_fields", []) or []):
        notes.append("赢家路线仍缺少 required 字段，需要继续补齐后再 release。")
        recommended_next_actions.append("capture_missing_required_fields_before_release")
    if len(ranked) >= 2 and len(compared_families) < 2:
        recommended_next_actions.append("capture_independent_validation_family_before_release")

    return {
        "site": site,
        "decision": "clear_winner" if not requires_review else "needs_review",
        "validation_status": validation_status,
        "validation_families": compared_families,
        "winner": {
            "route_id": str(winner.get("route_id", "")).strip(),
            "adapter_id": str(winner.get("adapter_id", "")).strip(),
            "validation_family": _route_validation_family(winner),
            "source_trust_tier": _route_source_trust_tier(winner),
            "freshness_alignment": _route_freshness_alignment(winner, acquisition_hand),
            "tool_label": str(winner.get("tool_label", "")).strip(),
            "status": str(winner.get("status", "")).strip(),
            "field_coverage": float(winner.get("field_coverage", 0.0) or 0.0),
            "required_field_coverage": float(winner.get("required_field_coverage", 0.0) or 0.0),
        },
        "compared_route_ids": [str(item.get("route_id", "")).strip() for item in ranked if str(item.get("route_id", "")).strip()],
        "requires_review": requires_review,
        "recommended_next_actions": _unique_preserve(recommended_next_actions),
        "notes": notes,
    }


def build_acquisition_execution_summary(
    task_id: str,
    goal: str,
    report_payload: Dict[str, Any],
    acquisition_hand: Dict[str, Any],
    *,
    report_path: str = "",
) -> Dict[str, Any]:
    """
    中文注解：
    - 功能：把 crawler probe 的真实执行结果归一化为 acquisition execution summary。
    - 输入角色：消费 report payload 与 acquisition_hand。
    - 输出角色：给 runtime、verifier、doctor 提供统一的执行后证据。
    """
    if not acquisition_hand:
        return build_acquisition_execution_summary_schema(task_id=task_id, goal=goal)

    maps = _adapter_maps(acquisition_hand)
    execution_plan = _report_execution_plan(report_payload)
    route_runs: List[Dict[str, Any]] = []
    site_consensus_rows: List[Dict[str, Any]] = []
    site_synthesized_outputs: List[Dict[str, Any]] = []
    route_runs_by_site: Dict[str, List[Dict[str, Any]]] = defaultdict(list)

    for site in report_payload.get("sites", []) or []:
        site_id = str(site.get("site", "")).strip()
        source_url = str(site.get("url", "")).strip()
        site_requirements = _site_field_requirements(site_id, acquisition_hand, [])
        for row in site.get("tool_results", []) or []:
            tool_label = str(row.get("tool", "")).strip()
            if not tool_label:
                continue
            planned_binding = _planned_route_binding(tool_label, execution_plan)
            adapter = {}
            candidate = {}
            if planned_binding:
                adapter = (maps.get("adapters_by_id", {}) or {}).get(str(planned_binding.get("adapter_id", "")).strip(), {}) or {}
                candidate = {
                    "route_id": str(planned_binding.get("route_id", "")).strip(),
                    "adapter_id": str(planned_binding.get("adapter_id", "")).strip(),
                    "route_type": str(planned_binding.get("route_type", "")).strip(),
                    "validation_family": str(planned_binding.get("validation_family", "")).strip()
                    or str((adapter or {}).get("validation_family", "")).strip(),
                    "source_trust_tier": str(planned_binding.get("source_trust_tier", "")).strip()
                    or str((adapter or {}).get("source_trust_tier", "")).strip(),
                    "risk_level": str((adapter or {}).get("risk_level", "medium")).strip() or "medium",
                    "parallel_role": str(planned_binding.get("parallel_role", "")).strip(),
                }
            else:
                adapter = _pick_adapter(tool_label, acquisition_hand, maps)
                candidate = _pick_route_candidate(adapter, acquisition_hand, maps) if adapter else {}
            normalized_output = row.get("normalized_task_output", {}) or {}
            required_metrics = _required_field_metrics(
                dict(normalized_output.get("fields", {}) or {}),
                site_requirements.get("required_fields", []),
            )
            notes = [str(item) for item in ((row.get("false_positive", {}) or {}).get("reasons", []) or []) if str(item).strip()]
            if planned_binding:
                if str(planned_binding.get("parallel_role", "")).strip():
                    notes.append(f"planned_role:{str(planned_binding.get('parallel_role', '')).strip()}")
                if str(execution_plan.get("source", "")).strip():
                    notes.append(f"execution_plan_source:{str(execution_plan.get('source', '')).strip()}")
                if str(planned_binding.get("execution_profile", "")).strip():
                    notes.append(f"execution_profile:{str(planned_binding.get('execution_profile', '')).strip()}")
            route_run = build_acquisition_route_result_schema(
                site=site_id,
                route_id=str(candidate.get("route_id", "")).strip() or f"executed:{_normalized(tool_label)}",
                adapter_id=str((adapter or {}).get("adapter_id", "")).strip(),
                route_type=str((candidate or {}).get("route_type", "")).strip() or str((adapter or {}).get("route_type", "")).strip(),
                validation_family=str((candidate or {}).get("validation_family", "")).strip()
                or str((adapter or {}).get("validation_family", "")).strip(),
                source_trust_tier=str((candidate or {}).get("source_trust_tier", "")).strip()
                or str((adapter or {}).get("source_trust_tier", "")).strip(),
                freshness_alignment=_route_freshness_alignment(
                    {
                        **dict(candidate or {}),
                        "route_type": str((candidate or {}).get("route_type", "")).strip() or str((adapter or {}).get("route_type", "")).strip(),
                        "source_trust_tier": str((candidate or {}).get("source_trust_tier", "")).strip()
                        or str((adapter or {}).get("source_trust_tier", "")).strip(),
                    },
                    acquisition_hand,
                ),
                tool_label=tool_label,
                status=str(row.get("status", "")).strip() or "failed",
                source_url=source_url,
                retrieved_at=str(report_payload.get("generated_at", "")).strip(),
                field_coverage=float(normalized_output.get("field_completeness", 0.0) or 0.0),
                required_field_coverage=float(required_metrics.get("required_field_coverage", 0.0) or 0.0),
                populated_fields=[str(item) for item in normalized_output.get("populated_fields", []) or [] if str(item).strip()],
                required_fields_present=required_metrics.get("required_fields_present", []) or [],
                missing_required_fields=required_metrics.get("missing_required_fields", []) or [],
                arbitration_score=int(row.get("arbitration_score", row.get("score", 0)) or 0),
                evidence_ref=report_path,
                route_risk=str((candidate or {}).get("risk_level", (adapter or {}).get("risk_level", "medium"))).strip() or "medium",
                preferred_site_match=site_id in ((adapter or {}).get("preferred_sites", []) or []),
                task_fields=dict(normalized_output.get("fields", {}) or {}),
                notes=notes,
            )
            route_runs.append(route_run)
            route_runs_by_site[site_id].append(route_run)

    for site_id, site_route_runs in route_runs_by_site.items():
        synthesis = _field_provenance_for_site(site_id, site_route_runs, acquisition_hand)
        site_synthesized_outputs.append(synthesis)
        consensus_row = _site_consensus(site_id, site_route_runs, acquisition_hand)
        if (
            str(consensus_row.get("validation_status", "")).strip() == "conflict_detected"
            and not (synthesis.get("conflicted_fields", []) or [])
            and bool(synthesis.get("release_ready"))
        ):
            consensus_row["validation_status"] = "trust_resolved_conflict"
            consensus_row["requires_review"] = False
            consensus_row["decision"] = "clear_winner"
            consensus_row["recommended_next_actions"] = [
                action
                for action in (consensus_row.get("recommended_next_actions", []) or [])
                if str(action).strip() != "review_conflicting_route_outputs_before_release"
            ]
            consensus_row.setdefault("notes", []).append("原始路线存在冲突，但字段级合成已通过来源信任规则完成保守解冲突。")
        consensus_row["synthesis_status"] = str(synthesis.get("synthesis_status", "")).strip()
        consensus_row["release_ready"] = bool(synthesis.get("release_ready"))
        consensus_row["trust_posture"] = str(synthesis.get("trust_posture", "")).strip()
        consensus_row["trusted_release_ready"] = bool(synthesis.get("trusted_release_ready"))
        consensus_row["final_field_count"] = len((synthesis.get("final_fields", {}) or {}).keys())
        consensus_row["cross_validated_field_count"] = len(synthesis.get("cross_validated_fields", []) or [])
        consensus_row["conflicted_field_count"] = len(synthesis.get("conflicted_fields", []) or [])
        consensus_row["missing_required_field_count"] = len(synthesis.get("missing_required_fields", []) or [])
        site_consensus_rows.append(consensus_row)

    planned_route_ids = execution_plan.get("active_route_ids") or _planned_route_ids(acquisition_hand)
    executed_route_ids = _unique_preserve([str(item.get("route_id", "")).strip() for item in route_runs if str(item.get("route_id", "")).strip()])
    planned_but_not_executed = [route_id for route_id in planned_route_ids if route_id not in set(executed_route_ids)]
    global_skipped_route_ids = execution_plan.get("skipped_route_ids", []) or []

    sites_total = len(site_consensus_rows)
    sites_clear_winner = sum(1 for item in site_consensus_rows if item.get("decision") == "clear_winner")
    sites_needs_review = sum(1 for item in site_consensus_rows if bool(item.get("requires_review")))
    sites_cross_validated = sum(
        1
        for item in site_consensus_rows
        if str(item.get("validation_status", "")).strip() in {"cross_validated_independent", "cross_validated_same_family"}
    )
    independent_validation_sites_total = sum(
        1 for item in site_consensus_rows if str(item.get("validation_status", "")).strip() == "cross_validated_independent"
    )
    same_family_validation_sites_total = sum(
        1 for item in site_consensus_rows if str(item.get("validation_status", "")).strip() == "cross_validated_same_family"
    )
    sites_blocked = sum(1 for item in site_consensus_rows if item.get("decision") == "insufficient_evidence")
    synthesized_sites_total = sum(1 for item in site_synthesized_outputs if (item.get("final_fields", {}) or {}))
    sites_release_ready = sum(1 for item in site_synthesized_outputs if bool(item.get("release_ready")))
    trusted_ready_sites_total = sum(1 for item in site_synthesized_outputs if bool(item.get("trusted_release_ready")))
    guarded_low_trust_sites_total = sum(1 for item in site_synthesized_outputs if str(item.get("trust_posture", "")).strip() == "guarded_low_trust_sources")
    guarded_medium_trust_sites_total = sum(1 for item in site_synthesized_outputs if str(item.get("trust_posture", "")).strip() == "guarded_medium_trust_sources")
    fresh_ready_sites_total = sum(1 for item in site_synthesized_outputs if str(item.get("freshness_posture", "")).strip() == "fresh_ready")
    snapshot_only_sites_total = sum(1 for item in site_synthesized_outputs if str(item.get("freshness_posture", "")).strip() == "snapshot_only")
    session_snapshot_sites_total = sum(1 for item in site_synthesized_outputs if str(item.get("freshness_posture", "")).strip() == "session_snapshot")
    governed_release_ready_sites_total = sum(1 for item in site_synthesized_outputs if bool(item.get("governed_release_ready")))
    guarded_release_sites_total = sum(1 for item in site_synthesized_outputs if str(item.get("governed_release_status", "")).strip() == "guarded_release_with_disclosure")
    needs_higher_trust_sites_total = sum(1 for item in site_synthesized_outputs if str(item.get("governed_release_status", "")).strip() == "needs_higher_trust_source")
    needs_fresher_capture_sites_total = sum(1 for item in site_synthesized_outputs if str(item.get("governed_release_status", "")).strip() == "needs_fresher_capture")
    human_confirmation_sites_total = sum(1 for item in site_synthesized_outputs if str(item.get("governed_release_status", "")).strip() == "guarded_requires_human_confirmation")
    disclosure_required_sites_total = sum(1 for item in site_synthesized_outputs if bool((item.get("release_disclosure", {}) or {}).get("required")))
    cross_validated_field_total = sum(len(item.get("cross_validated_fields", []) or []) for item in site_synthesized_outputs)
    conflicted_field_total = sum(len(item.get("conflicted_fields", []) or []) for item in site_synthesized_outputs)
    missing_field_total = sum(len(item.get("missing_fields", []) or []) for item in site_synthesized_outputs)
    required_field_gap_total = sum(len(item.get("missing_required_fields", []) or []) for item in site_synthesized_outputs)
    stretch_field_gap_total = sum(len(item.get("missing_stretch_fields", []) or []) for item in site_synthesized_outputs)
    validation_family_count = len(
        _unique_preserve(
            [
                _route_validation_family(item)
                for item in route_runs
                if _route_validation_family(item) != "unknown"
            ]
        )
    )
    validation_diversity_status = "no_validation"
    if independent_validation_sites_total:
        validation_diversity_status = "independent_family_validation"
    elif same_family_validation_sites_total:
        validation_diversity_status = "same_family_validation_only"
    elif sites_cross_validated:
        validation_diversity_status = "mixed_validation_strength"

    consensus_status = "insufficient_evidence"
    if sites_needs_review:
        consensus_status = "needs_review"
    elif sites_total and sites_clear_winner == sites_total and independent_validation_sites_total:
        consensus_status = "cross_route_validated"
    elif sites_total and sites_clear_winner == sites_total:
        consensus_status = "clear_winner"

    synthesis_status = "blocked"
    if any(str(item.get("synthesis_status", "")).strip() == "needs_review" for item in site_synthesized_outputs):
        synthesis_status = "needs_review"
    elif any(str(item.get("synthesis_status", "")).strip() == "partial" for item in site_synthesized_outputs):
        synthesis_status = "partial"
    elif sites_total and all(str(item.get("synthesis_status", "")).strip() == "ready" for item in site_synthesized_outputs):
        synthesis_status = "ready"

    release_readiness_status = "blocked"
    if sites_total and sites_release_ready == sites_total and not sites_needs_review:
        release_readiness_status = "ready"
    elif required_field_gap_total:
        release_readiness_status = "missing_required_fields"
    elif sites_needs_review or conflicted_field_total:
        release_readiness_status = "needs_review"
    elif missing_field_total:
        release_readiness_status = "stretch_fields_missing"

    trusted_release_status = "not_ready"
    if release_readiness_status == "ready" and sites_total and trusted_ready_sites_total == sites_total:
        trusted_release_status = "trusted_ready"
    elif release_readiness_status == "ready" and guarded_low_trust_sites_total:
        trusted_release_status = "guarded_low_trust"
    elif release_readiness_status == "ready" and guarded_medium_trust_sites_total:
        trusted_release_status = "guarded_medium_trust"

    governed_release_status = "blocked_release_readiness"
    if any(str(item.get("governed_release_status", "")).strip() == "needs_higher_trust_source" for item in site_synthesized_outputs):
        governed_release_status = "needs_higher_trust_source"
    elif any(str(item.get("governed_release_status", "")).strip() == "needs_fresher_capture" for item in site_synthesized_outputs):
        governed_release_status = "needs_fresher_capture"
    elif any(str(item.get("governed_release_status", "")).strip() == "guarded_requires_human_confirmation" for item in site_synthesized_outputs):
        governed_release_status = "guarded_requires_human_confirmation"
    elif any(str(item.get("governed_release_status", "")).strip() == "guarded_release_with_disclosure" for item in site_synthesized_outputs):
        governed_release_status = "guarded_release_with_disclosure"
    elif sites_total and governed_release_ready_sites_total == sites_total:
        governed_release_status = "auto_release_allowed"

    release_blockers = _unique_preserve(
        [
            str(blocker).strip()
            for item in site_synthesized_outputs
            for blocker in (item.get("governance_blockers", []) or [])
            if str(blocker).strip()
        ]
    )
    release_disclosure = _aggregate_release_disclosure(site_synthesized_outputs)

    recommended_next_actions = _unique_preserve(
        [
            *(
                ["record_planned_vs_executed_route_gap"]
                if planned_but_not_executed
                else []
            ),
            *(
                ["review_global_routes_skipped_by_local_probe"]
                if global_skipped_route_ids
                else []
            ),
            *(
                ["persist_winning_route_into_learning"]
                if consensus_status in {"clear_winner", "cross_route_validated"}
                else []
            ),
            *(
                ["capture_independent_validation_family_before_release"]
                if validation_diversity_status == "same_family_validation_only"
                else []
            ),
            *(
                ["review_conflicting_route_outputs_before_release"]
                if consensus_status == "needs_review"
                else []
            ),
            *(
                ["switch_route_or_pause_for_human_checkpoint"]
                if sites_blocked
                else []
            ),
            *(
                ["review_field_level_conflicts_before_release"]
                if conflicted_field_total
                else []
            ),
            *(
                ["capture_missing_required_fields_before_release"]
                if required_field_gap_total
                else []
            ),
            *(
                ["seek_higher_trust_source_before_release"]
                if trusted_release_status == "guarded_low_trust"
                else []
            ),
            *(
                ["capture_higher_trust_source_before_release"]
                if trusted_release_status == "guarded_medium_trust"
                else []
            ),
            *(
                ["capture_missing_fields_via_backup_route"]
                if stretch_field_gap_total
                else []
            ),
            *(
                ["rerun_fresher_route_before_release"]
                if needs_fresher_capture_sites_total
                else []
            ),
            *(
                ["ask_user_to_confirm_guarded_release"]
                if human_confirmation_sites_total
                else []
            ),
            *(
                ["include_guarded_release_disclosure"]
                if guarded_release_sites_total
                else []
            ),
            *[
                str(action).strip()
                for item in site_consensus_rows
                for action in item.get("recommended_next_actions", []) or []
                if str(action).strip()
            ],
            *[
                str(action).strip()
                for item in site_synthesized_outputs
                for action in item.get("recommended_next_actions", []) or []
                if str(action).strip()
            ],
        ]
    )

    return build_acquisition_execution_summary_schema(
        task_id=task_id,
        goal=goal,
        generated_at=str(report_payload.get("generated_at", "")).strip(),
        report_path=report_path,
        planned_route_ids=planned_route_ids,
        executed_route_ids=executed_route_ids,
        planned_but_not_executed_route_ids=planned_but_not_executed,
        route_runs=route_runs,
        site_consensus=site_consensus_rows,
        site_synthesized_outputs=site_synthesized_outputs,
        overall_summary={
            "consensus_status": consensus_status,
            "synthesis_status": synthesis_status,
            "sites_total": sites_total,
            "sites_clear_winner": sites_clear_winner,
            "sites_cross_validated": sites_cross_validated,
            "independent_validation_sites_total": independent_validation_sites_total,
            "same_family_validation_sites_total": same_family_validation_sites_total,
            "sites_needs_review": sites_needs_review,
            "sites_blocked": sites_blocked,
            "validation_family_count": validation_family_count,
            "validation_diversity_status": validation_diversity_status,
            "synthesized_sites_total": synthesized_sites_total,
            "sites_release_ready": sites_release_ready,
            "trusted_ready_sites_total": trusted_ready_sites_total,
            "guarded_low_trust_sites_total": guarded_low_trust_sites_total,
            "guarded_medium_trust_sites_total": guarded_medium_trust_sites_total,
            "fresh_ready_sites_total": fresh_ready_sites_total,
            "snapshot_only_sites_total": snapshot_only_sites_total,
            "session_snapshot_sites_total": session_snapshot_sites_total,
            "governed_release_ready_sites_total": governed_release_ready_sites_total,
            "guarded_release_sites_total": guarded_release_sites_total,
            "needs_higher_trust_sites_total": needs_higher_trust_sites_total,
            "needs_fresher_capture_sites_total": needs_fresher_capture_sites_total,
            "human_confirmation_sites_total": human_confirmation_sites_total,
            "disclosure_required_sites_total": disclosure_required_sites_total,
            "cross_validated_field_total": cross_validated_field_total,
            "conflicted_field_total": conflicted_field_total,
            "missing_field_total": missing_field_total,
            "required_field_gap_total": required_field_gap_total,
            "stretch_field_gap_total": stretch_field_gap_total,
            "release_readiness_status": release_readiness_status,
            "trusted_release_status": trusted_release_status,
            "governed_release_status": governed_release_status,
            "requires_human_confirmation": bool(human_confirmation_sites_total),
            "release_blockers": release_blockers,
            "release_disclosure": release_disclosure,
            "route_gap_count": len(planned_but_not_executed),
            "global_planned_route_ids": execution_plan.get("global_planned_route_ids", []) or _planned_route_ids(acquisition_hand),
            "global_skipped_route_ids": global_skipped_route_ids,
            "execution_plan_source": str(execution_plan.get("source", "")).strip(),
            "planned_route_coverage_ratio": round(
                len(set(planned_route_ids).intersection(set(executed_route_ids))) / max(1, len(planned_route_ids)),
                3,
            ),
        },
        recommended_next_actions=recommended_next_actions,
    )


def render_acquisition_execution_summary_markdown(summary: Dict[str, Any]) -> str:
    """
    中文注解：
    - 功能：把 acquisition execution summary 渲染成便于人工阅读的 Markdown。
    - 输出角色：供 output artifacts、doctor、operator 快速查看路线执行与共识结果。
    """
    overall = summary.get("overall_summary", {}) or {}
    lines = [
        "# Acquisition execution summary",
        "",
        f"- Task: `{summary.get('task_id', '')}`",
        f"- Consensus status: `{overall.get('consensus_status', '')}`",
        f"- Synthesis status: `{overall.get('synthesis_status', '')}`",
        f"- Release readiness: `{overall.get('release_readiness_status', '')}`",
        f"- Trusted release: `{overall.get('trusted_release_status', '')}`",
        f"- Governed release: `{overall.get('governed_release_status', '')}`",
        f"- Validation diversity: `{overall.get('validation_diversity_status', '')}`",
        f"- Planned routes: `{', '.join(summary.get('planned_route_ids', []) or [])}`",
        f"- Executed routes: `{', '.join(summary.get('executed_route_ids', []) or [])}`",
        f"- Planned but not executed: `{', '.join(summary.get('planned_but_not_executed_route_ids', []) or [])}`",
        "",
    ]
    release_disclosure = overall.get("release_disclosure", {}) or {}
    if release_disclosure.get("required"):
        lines.extend(
            [
                "## Release Disclosure",
                "",
                f"- Level: `{release_disclosure.get('level', '')}`",
                f"- Headline: {release_disclosure.get('headline', '')}",
                f"- Summary: {release_disclosure.get('summary', '')}",
            ]
        )
        for item in release_disclosure.get("user_visible_lines", []) or []:
            lines.append(f"- Disclosure: {item}")
        lines.append("")
    synthesis_by_site = {
        str(item.get("site", "")).strip(): item
        for item in summary.get("site_synthesized_outputs", []) or []
        if str(item.get("site", "")).strip()
    }
    for site in summary.get("site_consensus", []) or []:
        winner = site.get("winner", {}) or {}
        synthesized = synthesis_by_site.get(str(site.get("site", "")).strip(), {}) or {}
        lines.extend(
            [
                f"## {site.get('site', '')}",
                "",
                f"- Decision: `{site.get('decision', '')}`",
                f"- Validation: `{site.get('validation_status', '')}`",
                f"- Validation families: `{', '.join(site.get('validation_families', []) or [])}`",
                f"- Synthesis: `{site.get('synthesis_status', synthesized.get('synthesis_status', ''))}`",
                f"- Trust posture: `{site.get('trust_posture', synthesized.get('trust_posture', ''))}`",
                f"- Freshness posture: `{synthesized.get('freshness_posture', '')}`",
                f"- Governed release: `{synthesized.get('governed_release_status', '')}`",
                f"- Winner route: `{winner.get('route_id', '')}`",
                f"- Winner adapter: `{winner.get('adapter_id', '')}`",
                f"- Winner source trust: `{winner.get('source_trust_tier', '')}`",
                f"- Winner tool: `{winner.get('tool_label', '')}`",
                f"- Winner status: `{winner.get('status', '')}`",
                f"- Winner field coverage: `{winner.get('field_coverage', 0.0)}`",
                f"- Winner required field coverage: `{winner.get('required_field_coverage', 0.0)}`",
            ]
        )
        if synthesized.get("required_fields"):
            lines.append(f"- Required fields: `{', '.join(synthesized.get('required_fields', []) or [])}`")
        if synthesized.get("final_fields"):
            lines.append("- Final fields:")
            for key, value in (synthesized.get("final_fields", {}) or {}).items():
                lines.append(f"  - {key}: {value}")
        if synthesized.get("missing_required_fields"):
            lines.append(f"- Missing required fields: `{', '.join(synthesized.get('missing_required_fields', []) or [])}`")
        if synthesized.get("conflicted_fields"):
            lines.append(f"- Conflicted fields: `{', '.join(synthesized.get('conflicted_fields', []) or [])}`")
        if synthesized.get("missing_fields"):
            lines.append(f"- Missing fields: `{', '.join(synthesized.get('missing_fields', []) or [])}`")
        if site.get("notes"):
            lines.append("- Notes:")
            for note in site.get("notes", []) or []:
                lines.append(f"  - {note}")
        if synthesized.get("notes"):
            lines.append("- Synthesis notes:")
            for note in synthesized.get("notes", []) or []:
                lines.append(f"  - {note}")
        if (synthesized.get("release_disclosure", {}) or {}).get("required"):
            lines.append("- Release disclosure:")
            disclosure = synthesized.get("release_disclosure", {}) or {}
            lines.append(f"  - level: {disclosure.get('level', '')}")
            lines.append(f"  - headline: {disclosure.get('headline', '')}")
            for item in disclosure.get("user_visible_lines", []) or []:
                lines.append(f"  - {item}")
        if site.get("recommended_next_actions"):
            lines.append("- Recommended next actions:")
            for action in site.get("recommended_next_actions", []) or []:
                lines.append(f"  - {action}")
        if synthesized.get("recommended_next_actions"):
            lines.append("- Synthesis actions:")
            for action in synthesized.get("recommended_next_actions", []) or []:
                lines.append(f"  - {action}")
        lines.append("")
    if summary.get("recommended_next_actions"):
        lines.append("## Overall next actions")
        lines.append("")
        for action in summary.get("recommended_next_actions", []) or []:
            lines.append(f"- {action}")
        lines.append("")
    return "\n".join(lines)


def main() -> int:
    """
    中文注解：
    - 功能：为 acquisition summary normalizer 提供命令行调试入口。
    """
    import argparse

    parser = argparse.ArgumentParser(description="Normalize acquisition execution results")
    parser.add_argument("--task-id", required=True)
    parser.add_argument("--goal", required=True)
    parser.add_argument("--report-json", required=True)
    parser.add_argument("--acquisition-hand-json", required=True)
    args = parser.parse_args()
    payload = build_acquisition_execution_summary(
        args.task_id,
        args.goal,
        json.loads(args.report_json),
        json.loads(args.acquisition_hand_json),
    )
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
