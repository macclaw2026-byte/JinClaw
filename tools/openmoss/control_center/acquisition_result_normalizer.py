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
    route_type = str(route_run.get("route_type", "")).strip()
    trust_rank = ROUTE_TRUST_RANK.get(route_type, 1)
    risk_penalty = RISK_PENALTY.get(str(route_run.get("route_risk", "medium")).strip(), 4)
    preferred_site_bonus = 6 if route_run.get("preferred_site_match") else 0
    primary_bonus = 4 if str(route_run.get("route_id", "")).strip() == primary_route_id else 0
    return round(
        status_rank * 100
        + float(route_run.get("field_coverage", 0.0) or 0.0) * 60
        + int(route_run.get("arbitration_score", 0) or 0)
        + trust_rank * 10
        + preferred_site_bonus
        + primary_bonus
        - risk_penalty,
        3,
    )


def _route_validation_family(route_run: Dict[str, Any]) -> str:
    return str(route_run.get("validation_family", "")).strip() or str(route_run.get("route_type", "")).strip() or "unknown"


def _route_families_for_ids(route_runs: List[Dict[str, Any]], route_ids: List[str]) -> List[str]:
    route_id_set = {str(item).strip() for item in route_ids if str(item).strip()}
    return _unique_preserve(
        [
            _route_validation_family(route_run)
            for route_run in route_runs
            if str(route_run.get("route_id", "")).strip() in route_id_set and _route_validation_family(route_run) != "unknown"
        ]
    )


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


def _derive_expected_fields(site: str, route_runs: List[Dict[str, Any]]) -> List[str]:
    expected = list(SITE_EXPECTED_FIELDS.get(site, []))
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
    expected_fields = _derive_expected_fields(site, surviving or route_runs)
    if not surviving:
        return build_acquisition_site_synthesis_schema(
            site=site,
            synthesis_status="blocked",
            missing_fields=expected_fields,
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
        notes: List[str] = []
        if len(grouped_rows) == 1:
            if len(selected.get("supporting_route_ids", []) or []) >= 2:
                confidence = "cross_validated_independent" if len(supporting_families) >= 2 else "cross_validated_same_family"
                cross_validated_fields.append(field_name)
                if len(supporting_families) >= 2:
                    notes.append("至少两条不同验证家族的路线对该字段给出了相同值。")
                else:
                    notes.append("至少两条路线对该字段给出了相同值，但仍属于同一验证家族。")
            else:
                notes.append("当前字段只有单路线证据。")
        else:
            lead = float(selected.get("group_score", 0.0) or 0.0) - float(grouped_rows[1].get("group_score", 0.0) or 0.0)
            if len(selected.get("supporting_route_ids", []) or []) >= 2 and lead >= 15:
                confidence = (
                    "resolved_multi_route_majority_independent"
                    if len(supporting_families) >= 2
                    else "resolved_multi_route_majority_same_family"
                )
                cross_validated_fields.append(field_name)
                if len(supporting_families) >= 2:
                    notes.append("存在冲突，但不同验证家族的多数路线支持当前值。")
                else:
                    notes.append("存在冲突，但多数支持仍来自同一验证家族。")
            elif lead >= 40:
                confidence = "resolved_by_best_evidence"
                conflicted_fields.append(field_name)
                notes.append("存在冲突，当前值由最佳证据路线胜出。")
            else:
                confidence = "conflict_unresolved"
                conflicted_fields.append(field_name)
                notes.append("字段冲突未完全消解，需要人工复核。")

        final_fields[field_name] = selected.get("value")
        field_provenance[field_name] = build_acquisition_field_provenance_schema(
            field_name=field_name,
            selected_value=selected.get("value"),
            selected_route_id=str(selected_route.get("route_id", "")).strip(),
            selected_adapter_id=str(selected_route.get("adapter_id", "")).strip(),
            selected_tool_label=str(selected_route.get("tool_label", "")).strip(),
            confidence=confidence,
            supporting_route_ids=selected.get("supporting_route_ids", []) or [],
            supporting_validation_families=supporting_families,
            disagreeing_route_ids=disagreeing_route_ids,
            disagreeing_validation_families=disagreeing_families,
            supporting_values=selected.get("supporting_values", []) or [],
            notes=notes,
        )

    synthesis_status = "blocked"
    site_notes: List[str] = []
    recommended_next_actions: List[str] = []
    if final_fields:
        synthesis_status = "ready"
        if conflicted_fields:
            synthesis_status = "needs_review"
            site_notes.append("部分字段存在冲突，当前结果是保守择优后的合成视图。")
            recommended_next_actions.append("review_field_level_conflicts_before_release")
        elif missing_fields:
            synthesis_status = "partial"
            site_notes.append("已能输出结构化结果，但仍有缺失字段。")
            recommended_next_actions.append("capture_missing_fields_via_backup_route")
        else:
            site_notes.append("当前站点已形成完整字段级合成结果。")
    else:
        recommended_next_actions.append("switch_route_or_pause_for_human_checkpoint")

    return build_acquisition_site_synthesis_schema(
        site=site,
        synthesis_status=synthesis_status,
        final_fields=final_fields,
        field_provenance=field_provenance,
        missing_fields=missing_fields,
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
            "tool_label": str(winner.get("tool_label", "")).strip(),
            "status": str(winner.get("status", "")).strip(),
            "field_coverage": float(winner.get("field_coverage", 0.0) or 0.0),
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
                    "risk_level": str((adapter or {}).get("risk_level", "medium")).strip() or "medium",
                    "parallel_role": str(planned_binding.get("parallel_role", "")).strip(),
                }
            else:
                adapter = _pick_adapter(tool_label, acquisition_hand, maps)
                candidate = _pick_route_candidate(adapter, acquisition_hand, maps) if adapter else {}
            normalized_output = row.get("normalized_task_output", {}) or {}
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
                tool_label=tool_label,
                status=str(row.get("status", "")).strip() or "failed",
                source_url=source_url,
                retrieved_at=str(report_payload.get("generated_at", "")).strip(),
                field_coverage=float(normalized_output.get("field_completeness", 0.0) or 0.0),
                populated_fields=[str(item) for item in normalized_output.get("populated_fields", []) or [] if str(item).strip()],
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
        consensus_row["synthesis_status"] = str(synthesis.get("synthesis_status", "")).strip()
        consensus_row["final_field_count"] = len((synthesis.get("final_fields", {}) or {}).keys())
        consensus_row["cross_validated_field_count"] = len(synthesis.get("cross_validated_fields", []) or [])
        consensus_row["conflicted_field_count"] = len(synthesis.get("conflicted_fields", []) or [])
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
    cross_validated_field_total = sum(len(item.get("cross_validated_fields", []) or []) for item in site_synthesized_outputs)
    conflicted_field_total = sum(len(item.get("conflicted_fields", []) or []) for item in site_synthesized_outputs)
    missing_field_total = sum(len(item.get("missing_fields", []) or []) for item in site_synthesized_outputs)
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
                ["capture_missing_fields_via_backup_route"]
                if missing_field_total
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
            "cross_validated_field_total": cross_validated_field_total,
            "conflicted_field_total": conflicted_field_total,
            "missing_field_total": missing_field_total,
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
        f"- Validation diversity: `{overall.get('validation_diversity_status', '')}`",
        f"- Planned routes: `{', '.join(summary.get('planned_route_ids', []) or [])}`",
        f"- Executed routes: `{', '.join(summary.get('executed_route_ids', []) or [])}`",
        f"- Planned but not executed: `{', '.join(summary.get('planned_but_not_executed_route_ids', []) or [])}`",
        "",
    ]
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
                f"- Winner route: `{winner.get('route_id', '')}`",
                f"- Winner adapter: `{winner.get('adapter_id', '')}`",
                f"- Winner tool: `{winner.get('tool_label', '')}`",
                f"- Winner status: `{winner.get('status', '')}`",
                f"- Winner field coverage: `{winner.get('field_coverage', 0.0)}`",
            ]
        )
        if synthesized.get("final_fields"):
            lines.append("- Final fields:")
            for key, value in (synthesized.get("final_fields", {}) or {}).items():
                lines.append(f"  - {key}: {value}")
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
