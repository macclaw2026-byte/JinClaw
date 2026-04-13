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
- 文件路径：`tools/openmoss/control_center/acquisition_hand_builder.py`
- 文件作用：把分散的 fetch route / crawler / challenge / knowledge 结构装配成统一的 acquisition hand 协议。
- 顶层函数：build_acquisition_hand、main。
- 顶层类：无顶层类。
"""
from __future__ import annotations

import json
from typing import Any, Dict, List

from acquisition_adapter_registry import build_acquisition_adapter_registry
from control_center_schemas import (
    build_acquisition_consensus_schema,
    build_acquisition_hand_schema,
)


RISK_RANK = {
    "low": 1,
    "medium": 2,
    "high": 3,
}


def _dedupe_strings(values: List[str]) -> List[str]:
    """
    中文注解：
    - 功能：对字符串列表去重并保持顺序。
    - 设计意图：协议输出里多个上游来源经常会产生重复工具/路由，需要统一清洗。
    """
    seen: set[str] = set()
    result: List[str] = []
    for item in values:
        text = str(item).strip()
        if not text or text in seen:
            continue
        seen.add(text)
        result.append(text)
    return result


def _goal_time_sensitivity(goal: str) -> str:
    """
    中文注解：
    - 功能：从目标文本中提取时效敏感度。
    - 设计意图：数据获取策略需要区分“静态研究”与“最新/今日数据”，决定 freshness 权重。
    """
    normalized = str(goal or "").lower()
    if any(token in normalized for token in ["latest", "today", "current", "recent", "最新", "今天", "当前", "最近", "实时"]):
        return "fresh"
    return "normal"


def _risk_bucket(score: float) -> str:
    if score >= 75:
        return "high"
    if score >= 45:
        return "medium"
    return "low"


def _adapter_for_route(route_name: str, adapter_registry: Dict[str, Any]) -> List[str]:
    return [
        str(item)
        for item in (adapter_registry.get("route_to_enabled_adapter_ids", {}) or {}).get(route_name, [])
        if str(item).strip()
    ]


def _adapters_for_stack(stack_id: str, adapter_registry: Dict[str, Any]) -> List[str]:
    """
    中文注解：
    - 功能：把 crawler 的 stack 选择映射成 acquisition market 中当前可执行的 concrete adapters。
    - 设计意图：让 stack-level 评分结果与 adapter-level 路由执行保持兼容，而不是二选一重写。
    """
    return [
        str(item)
        for item in (adapter_registry.get("stack_to_enabled_adapter_ids", {}) or {}).get(stack_id, [])
        if str(item).strip()
    ]


def _challenge_severity_rank(challenge: Dict[str, Any]) -> int:
    return {
        "none": 0,
        "low": 1,
        "medium": 2,
        "high": 3,
    }.get(str(challenge.get("severity", "none")).strip().lower(), 0)


def _make_route_candidate(
    *,
    adapter: Dict[str, Any] | None,
    route_type: str,
    source: str,
    priority_score: float,
    why: List[str],
    index: int,
) -> Dict[str, Any]:
    """
    中文注解：
    - 功能：构造标准 route candidate。
    - 设计意图：主路线、验证路线、升级路线都使用同一结构，便于后续 consensus 和 runtime 消费。
    """
    adapter = adapter or {}
    adapter_id = str(adapter.get("adapter_id", "")).strip()
    route_id = f"{source}:{adapter_id or route_type or 'human_checkpoint'}:{index}"
    risk_level = str(adapter.get("risk_level", "high" if route_type == "human_checkpoint" else "medium")).strip() or "medium"
    requires_review = bool(
        adapter.get("auth_requirement") not in {"", "none"}
        or route_type in {"authorized_session", "human_checkpoint"}
        or risk_level == "high"
    )
    can_run_parallel = bool(adapter.get("supports_parallel_validation")) and route_type not in {"authorized_session", "human_checkpoint"}
    return {
        "route_id": route_id,
        "adapter_id": adapter_id,
        "route_type": route_type,
        "label": str(adapter.get("label", "")).strip() or route_type,
        "source": source,
        "priority_score": round(float(priority_score or 0.0), 2),
        "priority_bucket": _risk_bucket(priority_score),
        "risk_level": risk_level,
        "anti_bot_readiness": str(adapter.get("anti_bot_readiness", "medium")).strip() or "medium",
        "tools": [str(item) for item in adapter.get("tools", []) if str(item).strip()],
        "requires_review": requires_review,
        "can_run_parallel": can_run_parallel,
        "preferred_sites": [str(item) for item in adapter.get("preferred_sites", []) if str(item).strip()],
        "why": [str(item) for item in why if str(item).strip()],
        "parallel_role": "",
    }


def _derive_route_candidates(
    fetch_route: Dict[str, Any],
    crawler: Dict[str, Any],
    adapter_registry: Dict[str, Any],
    challenge: Dict[str, Any],
) -> List[Dict[str, Any]]:
    """
    中文注解：
    - 功能：把 crawler 评分、fetch ladder 和 challenge posture 合成为可执行 route candidates。
    - 设计意图：不再只选一个栈，而是显式给出主路线、验证路线和升级路线。
    """
    adapters_by_id = {
        str(item.get("adapter_id", "")).strip(): item
        for item in adapter_registry.get("adapters", []) or []
        if str(item.get("adapter_id", "")).strip()
    }
    score_map = {
        str(item.get("stack_id", "")).strip(): item
        for item in crawler.get("scores", []) or []
        if str(item.get("stack_id", "")).strip()
    }
    candidates: List[Dict[str, Any]] = []
    seen_fingerprints: set[str] = set()

    def _append(route_type: str, adapter_id: str, source: str, extra_why: List[str]) -> None:
        fingerprint = f"{route_type}::{adapter_id or 'none'}"
        if fingerprint in seen_fingerprints:
            return
        seen_fingerprints.add(fingerprint)
        score_payload = score_map.get(adapter_id, {})
        score = float(score_payload.get("score", 0.0) or 0.0)
        if route_type == str(fetch_route.get("current_route", "")).strip():
            score += 10
        if adapter_id == str((crawler.get("selected_stack", {}) or {}).get("stack_id", "")).strip():
            score += 15
        if route_type == "human_checkpoint":
            score = max(score, 20.0 if _challenge_severity_rank(challenge) >= 2 else 5.0)
        rationale = [str(item) for item in (score_payload.get("rationale", []) or []) if str(item).strip()]
        adapter = adapters_by_id.get(adapter_id, {})
        execution_profile = str(adapter.get("execution_profile", "")).strip()
        if route_type == str(challenge.get("recommended_route", "")).strip():
            score += 8
        if route_type == "browser_render" and execution_profile in {"stealth_scroll_capture", "scroll_capture"}:
            score += 4 if _challenge_severity_rank(challenge) >= 1 else 2
        candidate = _make_route_candidate(
            adapter=adapter,
            route_type=route_type,
            source=source,
            priority_score=score,
            why=[*extra_why, *rationale],
            index=len(candidates) + 1,
        )
        candidates.append(candidate)

    selected_stack = str((crawler.get("selected_stack", {}) or {}).get("stack_id", "")).strip()
    if selected_stack:
        selected_adapters = _adapters_for_stack(selected_stack, adapter_registry)
        if selected_adapters:
            primary_adapter_id = selected_adapters[0]
            adapter = adapters_by_id.get(primary_adapter_id, {})
            _append(
                str(adapter.get("route_type", "")).strip() or str(fetch_route.get("current_route", "")).strip() or "static_fetch",
                primary_adapter_id,
                "crawler.selected_stack",
                [f"当前 crawler 评分认为 `{selected_stack}` 是主抓取栈，因此优先选择其首个 concrete adapter。"],
            )

    for stack_id in [str(item) for item in crawler.get("fallback_stacks", []) if str(item).strip()]:
        fallback_adapters = _adapters_for_stack(stack_id, adapter_registry)
        if not fallback_adapters:
            continue
        adapter = adapters_by_id.get(fallback_adapters[0], {})
        _append(
            str(adapter.get("route_type", "")).strip() or "static_fetch",
            fallback_adapters[0],
            "crawler.fallback_stack",
            [f"保留 `{stack_id}` 的 concrete adapter 作为回退路线。"],
        )

    for route_name in [str(item) for item in fetch_route.get("route_ladder", []) if str(item).strip()]:
        adapter_ids = _adapter_for_route(route_name, adapter_registry)
        if not adapter_ids and route_name == "human_checkpoint":
            _append("human_checkpoint", "", "fetch_route.ladder", ["当前 route ladder 已经保留人工检查点。"])
            continue
        for adapter_id in adapter_ids:
            _append(route_name, adapter_id, "fetch_route.ladder", [f"fetch ladder 建议保留 `{route_name}` 这条路线。"])

    ordered = sorted(
        candidates,
        key=lambda item: (
            -float(item.get("priority_score", 0.0) or 0.0),
            RISK_RANK.get(str(item.get("risk_level", "medium")).strip(), 2),
            str(item.get("route_type", "")),
        ),
    )
    primary_assigned = False
    validation_assigned = False
    escalation_assigned = False
    primary_adapter_id = ""
    primary_route_type = ""
    for item in ordered:
        route_type = str(item.get("route_type", "")).strip()
        if not primary_assigned and route_type != "human_checkpoint":
            item["parallel_role"] = "primary_delivery"
            primary_assigned = True
            primary_adapter_id = str(item.get("adapter_id", "")).strip()
            primary_route_type = route_type
            continue
        if (
            not validation_assigned
            and bool(item.get("can_run_parallel"))
            and route_type not in {"browser_render", "authorized_session"}
            and (
                (primary_adapter_id and str(item.get("adapter_id", "")).strip() != primary_adapter_id)
                or (not primary_adapter_id and route_type != primary_route_type)
            )
        ):
            item["parallel_role"] = "validation_probe"
            validation_assigned = True
            continue
        if not escalation_assigned:
            item["parallel_role"] = "escalation_backup"
            escalation_assigned = True
            continue
        item["parallel_role"] = "reserve"
    return ordered


def _derive_execution_strategy(
    route_candidates: List[Dict[str, Any]],
    challenge: Dict[str, Any],
) -> Dict[str, Any]:
    """
    中文注解：
    - 功能：为 acquisition hand 推导执行策略。
    - 设计意图：明确什么时候单线跑、什么时候双线比对、什么时候只保留人工/审批升级路线。
    """
    primary = next((item for item in route_candidates if item.get("parallel_role") == "primary_delivery"), {})
    validation = [item for item in route_candidates if item.get("parallel_role") == "validation_probe"]
    escalation = [item for item in route_candidates if item.get("parallel_role") == "escalation_backup"]
    severity_rank = _challenge_severity_rank(challenge)
    mode = "single_route"
    if validation and severity_rank >= 2:
        mode = "multi_route_consensus"
    elif validation:
        mode = "dual_validation"
    elif not primary and escalation:
        mode = "escalation_only"
    allow_parallel = mode in {"dual_validation", "multi_route_consensus"} and not bool(challenge.get("requires_human_checkpoint"))
    stop_conditions = [
        "stop_when_human_verification_gate_appears",
        "stop_when_authorized_session_is_required_but_not_approved",
        "stop_when_multiple_routes_disagree_without_clear_provenance_winner",
    ]
    if bool(challenge.get("requires_human_checkpoint")):
        stop_conditions.append("pause_for_human_checkpoint_instead_of_forcing_progress")
    return {
        "mode": mode,
        "primary_route_id": str(primary.get("route_id", "")).strip(),
        "validation_route_ids": [str(item.get("route_id", "")).strip() for item in validation if str(item.get("route_id", "")).strip()],
        "escalation_route_ids": [str(item.get("route_id", "")).strip() for item in escalation if str(item.get("route_id", "")).strip()],
        "allow_parallel_validation": allow_parallel,
        "stop_conditions": _dedupe_strings(stop_conditions),
    }


def _derive_result_consensus(
    goal: str,
    knowledge_basis: Dict[str, Any],
    route_candidates: List[Dict[str, Any]],
    challenge: Dict[str, Any],
) -> Dict[str, Any]:
    """
    中文注解：
    - 功能：生成多路线结果比对规则。
    - 设计意图：系统不只知道“抓到了”，还知道“怎样从多条结果里选最可信的那条”。
    """
    fresh_weight = 5 if _goal_time_sensitivity(goal) == "fresh" else 3
    challenge_rank = _challenge_severity_rank(challenge)
    route_diversity_required = len([item for item in route_candidates if item.get("route_type") != "human_checkpoint"]) >= 2
    comparison_axes = [
        {"name": "source_trust", "weight": 5, "why": "优先官方/结构化/已验证来源。"},
        {"name": "field_completeness", "weight": 5, "why": "最终结果要尽量覆盖任务要求字段。"},
        {"name": "freshness", "weight": fresh_weight, "why": "时效敏感任务必须提高 freshness 权重。"},
        {"name": "site_readiness", "weight": 4 if challenge_rank >= 2 else 3, "why": "遇到反爬/风控时，优先已验证可用路线。"},
        {"name": "cross_route_agreement", "weight": 4 if route_diversity_required else 2, "why": "多路线结果越一致，可信度越高。"},
        {"name": "route_risk", "weight": 3, "why": "质量接近时优先低风险路线。"},
        {"name": "cost_efficiency", "weight": 2, "why": "避免每次都直接升级到高成本浏览器链。"},
    ]
    return build_acquisition_consensus_schema(
        consensus_mode="best_evidence_wins_with_validation_bias",
        comparison_axes=comparison_axes,
        tie_breakers=[
            "prefer_lower_risk_route_when_quality_is_similar",
            "prefer_verified_site_route_when_challenge_is_present",
            "prefer_route_with_clearer_provenance",
        ],
        required_provenance_fields=[
            "route_id",
            "adapter_id",
            "source_url",
            "retrieved_at",
            "status",
            "field_coverage",
            "evidence_ref",
        ],
        must_compare_when_multiple_routes=len(route_candidates) >= 2,
        route_diversity_required=route_diversity_required,
        prefer_low_risk_when_quality_similar=True,
        prefer_verified_site_route=challenge_rank >= 2,
        knowledge_basis_hint=str(knowledge_basis.get("recommended_basis", "")).strip(),
    )


def build_acquisition_hand(
    task_id: str,
    goal: str,
    intent: Dict[str, Any],
    governance: Dict[str, Any],
    selected_plan: Dict[str, Any],
    challenge: Dict[str, Any],
    fetch_route: Dict[str, Any],
    crawler: Dict[str, Any],
    knowledge_basis: Dict[str, Any],
    protocol_pack: Dict[str, Any],
    capabilities: Dict[str, Any],
) -> Dict[str, Any]:
    """
    中文注解：
    - 功能：构建 acquisition hand 总协议。
    - 输入角色：消费 intent/governance/challenge/fetch_route/crawler/knowledge 等控制中心产物。
    - 输出角色：给 runtime、doctor、stage context 和后续 adapter 市场提供统一取数控制面。
    """
    enabled = bool(intent.get("requires_external_information") or "web" in intent.get("task_types", []) or "data" in intent.get("task_types", []))
    adapter_registry = build_acquisition_adapter_registry(capabilities)
    route_candidates = _derive_route_candidates(fetch_route, crawler, adapter_registry, challenge) if enabled else []
    execution_strategy = _derive_execution_strategy(route_candidates, challenge) if enabled else {
        "mode": "disabled",
        "primary_route_id": "",
        "validation_route_ids": [],
        "escalation_route_ids": [],
        "allow_parallel_validation": False,
        "stop_conditions": [],
    }
    result_consensus = _derive_result_consensus(goal, knowledge_basis, route_candidates, challenge) if enabled else build_acquisition_consensus_schema()
    recommended_tools = _dedupe_strings(
        [tool for row in route_candidates for tool in row.get("tools", []) if str(tool).strip()]
    )
    primary_route = next((item for item in route_candidates if item.get("route_id") == execution_strategy.get("primary_route_id")), {})
    validation_routes = [
        next((item for item in route_candidates if item.get("route_id") == route_id), {})
        for route_id in execution_strategy.get("validation_route_ids", []) or []
    ]
    return build_acquisition_hand_schema(
        task_id=task_id,
        enabled=enabled,
        target_profile={
            "goal": goal,
            "task_types": [str(item) for item in intent.get("task_types", []) if str(item).strip()],
            "domains": [str(item) for item in intent.get("domains", []) if str(item).strip()],
            "likely_platforms": [str(item) for item in intent.get("likely_platforms", []) if str(item).strip()],
            "needs_browser": bool(intent.get("needs_browser")),
            "time_sensitivity": _goal_time_sensitivity(goal),
            "selected_plan_id": str(selected_plan.get("plan_id", "")).strip(),
        },
        governance_binding={
            "tier": str(governance.get("tier", "standard")).strip() or "standard",
            "protocol_pack_id": str(protocol_pack.get("pack_id", "")).strip(),
            "fail_closed": True,
        },
        challenge_assessment=challenge,
        routing_policy={
            "official_first": bool(fetch_route.get("official_first", True)),
            "browser_last_before_authorized": bool(fetch_route.get("browser_last_before_authorized", True)),
            "authorized_session_requires_review": bool((fetch_route.get("strategy", {}) or {}).get("authorized_session_requires_review", True)),
            "never_bypass_verification": bool((fetch_route.get("strategy", {}) or {}).get("never_bypass_verification", True)),
            "direction_changes_require_user_confirmation": bool((governance.get("policy", {}) or {}).get("user_confirmation_for_direction_change", True)),
        },
        adapter_registry=adapter_registry,
        route_candidates=route_candidates,
        execution_strategy=execution_strategy,
        result_consensus=result_consensus,
        evidence_contract={
            "must_return_structured_data": True,
            "must_record_route_choice": True,
            "must_record_route_failures": True,
            "must_record_coverage_and_gaps": True,
            "must_record_provenance": True,
        },
        learning_contract={
            "must_write_site_lesson_when_blocked": enabled,
            "must_promote_successful_route_candidates": enabled,
            "writeback_targets": ["crawler_capability_profile", "mission_memory", "project_feedback"],
        },
        recommended_tools=recommended_tools,
        compatibility={
            "crawler_enabled": bool(crawler.get("enabled")),
            "crawler_execution_mode": str(crawler.get("execution_mode", "")).strip(),
            "crawler_selected_stack": str((crawler.get("selected_stack", {}) or {}).get("stack_id", "")).strip(),
            "crawler_fallback_stacks": [str(item) for item in crawler.get("fallback_stacks", []) if str(item).strip()],
        },
        summary={
            "mode": execution_strategy.get("mode", "disabled"),
            "primary_route": {
                "route_id": str(primary_route.get("route_id", "")).strip(),
                "route_type": str(primary_route.get("route_type", "")).strip(),
                "adapter_id": str(primary_route.get("adapter_id", "")).strip(),
            },
            "validation_routes": [
                {
                    "route_id": str(item.get("route_id", "")).strip(),
                    "route_type": str(item.get("route_type", "")).strip(),
                    "adapter_id": str(item.get("adapter_id", "")).strip(),
                }
                for item in validation_routes
                if item
            ],
            "recommended_tools": recommended_tools,
        },
    )


def main() -> int:
    """
    中文注解：
    - 功能：作为本模块调试入口，输出 acquisition hand 的帮助说明。
    - 设计意图：真实构建仍通过 orchestrator 汇编，这里只保留一个简单入口防止误用。
    """
    print(json.dumps({"message": "Use build_acquisition_hand() from orchestrator."}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
