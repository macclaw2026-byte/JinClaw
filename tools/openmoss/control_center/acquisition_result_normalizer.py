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
    build_acquisition_route_result_schema,
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
            validation_status = "cross_validated"
            notes.append("至少存在一条路线与赢家在共享字段上达成一致。")
        else:
            validation_status = "weak_validation"
            notes.append("存在多路线，但共享字段不足，验证强度有限。")
            recommended_next_actions.append("capture_additional_validation_route_if_needed")

    if str(winner.get("status", "")).strip() != "usable":
        requires_review = True
        notes.append("赢家路线只有 partial 质量，建议保守处理。")
        recommended_next_actions.append("improve_field_coverage_before_release")

    return {
        "site": site,
        "decision": "clear_winner" if not requires_review else "needs_review",
        "validation_status": validation_status,
        "winner": {
            "route_id": str(winner.get("route_id", "")).strip(),
            "adapter_id": str(winner.get("adapter_id", "")).strip(),
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
            route_run = build_acquisition_route_result_schema(
                site=site_id,
                route_id=str(candidate.get("route_id", "")).strip() or f"executed:{_normalized(tool_label)}",
                adapter_id=str((adapter or {}).get("adapter_id", "")).strip(),
                route_type=str((candidate or {}).get("route_type", "")).strip() or str((adapter or {}).get("route_type", "")).strip(),
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
        site_consensus_rows.append(_site_consensus(site_id, site_route_runs, acquisition_hand))

    planned_route_ids = execution_plan.get("active_route_ids") or _planned_route_ids(acquisition_hand)
    executed_route_ids = _unique_preserve([str(item.get("route_id", "")).strip() for item in route_runs if str(item.get("route_id", "")).strip()])
    planned_but_not_executed = [route_id for route_id in planned_route_ids if route_id not in set(executed_route_ids)]
    global_skipped_route_ids = execution_plan.get("skipped_route_ids", []) or []

    sites_total = len(site_consensus_rows)
    sites_clear_winner = sum(1 for item in site_consensus_rows if item.get("decision") == "clear_winner")
    sites_needs_review = sum(1 for item in site_consensus_rows if bool(item.get("requires_review")))
    sites_cross_validated = sum(1 for item in site_consensus_rows if item.get("validation_status") == "cross_validated")
    sites_blocked = sum(1 for item in site_consensus_rows if item.get("decision") == "insufficient_evidence")

    consensus_status = "insufficient_evidence"
    if sites_needs_review:
        consensus_status = "needs_review"
    elif sites_total and sites_clear_winner == sites_total and sites_cross_validated:
        consensus_status = "cross_route_validated"
    elif sites_total and sites_clear_winner == sites_total:
        consensus_status = "clear_winner"

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
                ["review_conflicting_route_outputs_before_release"]
                if consensus_status == "needs_review"
                else []
            ),
            *(
                ["switch_route_or_pause_for_human_checkpoint"]
                if sites_blocked
                else []
            ),
            *[
                str(action).strip()
                for item in site_consensus_rows
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
        overall_summary={
            "consensus_status": consensus_status,
            "sites_total": sites_total,
            "sites_clear_winner": sites_clear_winner,
            "sites_cross_validated": sites_cross_validated,
            "sites_needs_review": sites_needs_review,
            "sites_blocked": sites_blocked,
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
        f"- Planned routes: `{', '.join(summary.get('planned_route_ids', []) or [])}`",
        f"- Executed routes: `{', '.join(summary.get('executed_route_ids', []) or [])}`",
        f"- Planned but not executed: `{', '.join(summary.get('planned_but_not_executed_route_ids', []) or [])}`",
        "",
    ]
    for site in summary.get("site_consensus", []) or []:
        winner = site.get("winner", {}) or {}
        lines.extend(
            [
                f"## {site.get('site', '')}",
                "",
                f"- Decision: `{site.get('decision', '')}`",
                f"- Validation: `{site.get('validation_status', '')}`",
                f"- Winner route: `{winner.get('route_id', '')}`",
                f"- Winner adapter: `{winner.get('adapter_id', '')}`",
                f"- Winner tool: `{winner.get('tool_label', '')}`",
                f"- Winner status: `{winner.get('status', '')}`",
                f"- Winner field coverage: `{winner.get('field_coverage', 0.0)}`",
            ]
        )
        if site.get("notes"):
            lines.append("- Notes:")
            for note in site.get("notes", []) or []:
                lines.append(f"  - {note}")
        if site.get("recommended_next_actions"):
            lines.append("- Recommended next actions:")
            for action in site.get("recommended_next_actions", []) or []:
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
