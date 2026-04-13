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

SITE_CORE_FIELDS = {
    "amazon": ["title", "price", "link"],
    "walmart": ["title", "price", "link"],
    "temu": ["title", "price", "link"],
    "1688": ["title", "price", "supplier", "link"],
    "default": ["title", "link"],
}

SITE_STRETCH_FIELDS = {
    "amazon": ["rating", "reviews"],
    "walmart": ["rating"],
    "temu": ["promo"],
    "1688": ["moq"],
    "default": [],
}

FIELD_SIGNAL_MAP = {
    "price": ["price", "pricing", "报价", "价格", "售价"],
    "rating": ["rating", "score", "stars", "评分", "星级"],
    "reviews": ["review", "reviews", "comments", "comment", "评论", "评价"],
    "link": ["link", "url", "source", "citation", "来源", "链接"],
    "title": ["title", "name", "product name", "商品名", "名称", "标题"],
    "promo": ["promo", "promotion", "discount", "coupon", "优惠", "折扣"],
    "supplier": ["supplier", "vendor", "factory", "manufacturer", "供应商", "厂家", "工厂"],
    "moq": ["moq", "minimum order", "起订量", "最小起订量"],
    "stock": ["stock", "inventory", "availability", "库存", "现货"],
    "sku": ["sku", "asin", "item id", "listing id", "货号"],
    "brand": ["brand", "品牌"],
}

SITE_ALIASES = {
    "amazon": ["amazon", "amazon.com"],
    "walmart": ["walmart", "walmart.com"],
    "temu": ["temu", "temu.com"],
    "1688": ["1688", "alibaba.com"],
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


def _derive_target_sites(intent: Dict[str, Any], route_candidates: List[Dict[str, Any]]) -> List[str]:
    """
    中文注解：
    - 功能：从 intent/domain/route 偏好中抽取当前任务最可能涉及的站点集合。
    - 设计意图：delivery requirements 需要知道“按哪个站点语义”来设置核心字段与扩展字段。
    """
    values: List[str] = []
    for item in intent.get("likely_platforms", []) or []:
        text = str(item).strip().lower()
        if text:
            values.append(text)
    for domain in intent.get("domains", []) or []:
        lowered = str(domain).strip().lower()
        for site, aliases in SITE_ALIASES.items():
            if any(alias in lowered for alias in aliases):
                values.append(site)
    for candidate in route_candidates:
        for site in candidate.get("preferred_sites", []) or []:
            text = str(site).strip().lower()
            if text:
                values.append(text)
    targets = [site for site in _dedupe_strings(values) if site in SITE_CORE_FIELDS]
    return targets or ["default"]


def _goal_field_signals(goal: str) -> List[str]:
    """
    中文注解：
    - 功能：从用户目标里抽取显式点名的数据字段信号。
    - 设计意图：让 acquisition hand 的交付标准优先服从“这次任务真正要什么字段”，而不是永远套固定站点模板。
    """
    normalized = str(goal or "").lower()
    return [
        field_name
        for field_name, tokens in FIELD_SIGNAL_MAP.items()
        if any(token in normalized for token in tokens)
    ]


def _derive_delivery_requirements(
    goal: str,
    intent: Dict[str, Any],
    route_candidates: List[Dict[str, Any]],
) -> Dict[str, Any]:
    """
    中文注解：
    - 功能：推导 acquisition hand 的交付字段要求与 release 规则。
    - 输入角色：消费 goal/intent/route 候选，识别这次任务真正必须拿到哪些字段。
    - 输出角色：供 execution summary、verifier、doctor 用同一份结构判断“能不能交付”。
    """
    target_sites = _derive_target_sites(intent, route_candidates)
    explicit_fields = _dedupe_strings(_goal_field_signals(goal))
    task_types = {str(item).strip().lower() for item in intent.get("task_types", []) if str(item).strip()}
    required_fields_by_site: Dict[str, List[str]] = {}
    stretch_fields_by_site: Dict[str, List[str]] = {}
    field_priority: Dict[str, str] = {}
    rationale: List[str] = []
    for site in target_sites:
        base_required = list(SITE_CORE_FIELDS.get(site, SITE_CORE_FIELDS["default"]))
        base_stretch = list(SITE_STRETCH_FIELDS.get(site, SITE_STRETCH_FIELDS["default"]))
        known_fields = _dedupe_strings([*base_required, *base_stretch, *explicit_fields])
        if explicit_fields:
            required = [field for field in explicit_fields if field in known_fields]
            if not required:
                required = list(base_required)
            if site != "default" and "title" not in required:
                required = ["title", *required]
            if ("web" in task_types or "data" in task_types or intent.get("requires_external_information")) and "link" not in required:
                required.append("link")
            required = _dedupe_strings(required)
            stretch = [field for field in [*base_required, *base_stretch] if field not in required]
            rationale.append(f"目标文本显式点名字段 `{', '.join(explicit_fields)}`，因此按任务字段优先定义 `{site}` 的交付标准。")
        else:
            required = list(base_required)
            stretch = [field for field in base_stretch if field not in required]
            rationale.append(f"目标文本未显式点名字段，沿用 `{site}` 的核心字段模板。")
        required_fields_by_site[site] = required
        stretch_fields_by_site[site] = _dedupe_strings(stretch)
        for field_name in required:
            field_priority[field_name] = "required"
        for field_name in stretch_fields_by_site[site]:
            field_priority.setdefault(field_name, "stretch")
    return {
        "target_sites": target_sites,
        "goal_field_signals": explicit_fields,
        "required_fields_by_site": required_fields_by_site,
        "stretch_fields_by_site": stretch_fields_by_site,
        "field_priority": field_priority,
        "release_rules": {
            "block_release_when_required_fields_missing": True,
            "allow_release_with_missing_stretch_fields": True,
            "minimum_required_field_coverage_ratio": 1.0,
            "freshness_preferred": _goal_time_sensitivity(goal) == "fresh",
        },
        "notes": _dedupe_strings(rationale),
    }


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


def _candidate_validation_family(candidate: Dict[str, Any]) -> str:
    """
    中文注解：
    - 功能：读取 route candidate 的验证家族；缺失时回退到 route_type。
    - 设计意图：后续执行策略与结果共识都要区分“真正独立的验证”与“同家族换皮验证”。
    """
    return str(candidate.get("validation_family", "")).strip() or str(candidate.get("route_type", "")).strip() or "unknown"


def _candidate_priority_key(candidate: Dict[str, Any]) -> tuple[float, int, str]:
    return (
        -float(candidate.get("priority_score", 0.0) or 0.0),
        RISK_RANK.get(str(candidate.get("risk_level", "medium")).strip(), 2),
        str(candidate.get("route_id", "")).strip(),
    )


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
        "validation_family": str(adapter.get("validation_family", "")).strip() or route_type or "unknown",
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
        adapter = adapters_by_id.get(adapter_id, {})
        stack_score_key = str(adapter.get("stack_id", "")).strip() or adapter_id
        score_payload = score_map.get(stack_score_key, {})
        score = float(score_payload.get("score", 0.0) or 0.0)
        if route_type == str(fetch_route.get("current_route", "")).strip():
            score += 10
        if stack_score_key == str((crawler.get("selected_stack", {}) or {}).get("stack_id", "")).strip():
            score += 15
        if route_type == "human_checkpoint":
            score = max(score, 20.0 if _challenge_severity_rank(challenge) >= 2 else 5.0)
        rationale = [str(item) for item in (score_payload.get("rationale", []) or []) if str(item).strip()]
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
        key=_candidate_priority_key,
    )
    primary = next((item for item in ordered if str(item.get("route_type", "")).strip() != "human_checkpoint"), {})
    primary_route_id = str(primary.get("route_id", "")).strip()
    primary_adapter_id = str(primary.get("adapter_id", "")).strip()
    primary_route_type = str(primary.get("route_type", "")).strip()
    primary_family = _candidate_validation_family(primary)
    validation_pool = [
        item
        for item in ordered
        if str(item.get("route_id", "")).strip() != primary_route_id
        and bool(item.get("can_run_parallel"))
        and str(item.get("route_type", "")).strip() not in {"browser_render", "authorized_session", "human_checkpoint"}
        and (
            (primary_adapter_id and str(item.get("adapter_id", "")).strip() != primary_adapter_id)
            or (not primary_adapter_id and str(item.get("route_type", "")).strip() != primary_route_type)
        )
    ]
    diverse_validation_pool = [
        item for item in validation_pool if _candidate_validation_family(item) and _candidate_validation_family(item) != primary_family
    ]
    validation = sorted(diverse_validation_pool or validation_pool, key=_candidate_priority_key)[0] if (diverse_validation_pool or validation_pool) else {}
    validation_route_id = str(validation.get("route_id", "")).strip()
    escalation_pool = [
        item
        for item in ordered
        if str(item.get("route_id", "")).strip() not in {primary_route_id, validation_route_id}
    ]
    escalation = escalation_pool[0] if escalation_pool else {}
    escalation_route_id = str(escalation.get("route_id", "")).strip()

    for item in ordered:
        route_id = str(item.get("route_id", "")).strip()
        if route_id and route_id == primary_route_id:
            item["parallel_role"] = "primary_delivery"
            continue
        if route_id and route_id == validation_route_id:
            item["parallel_role"] = "validation_probe"
            item["validation_relationship"] = (
                "independent_family"
                if _candidate_validation_family(item) and _candidate_validation_family(item) != primary_family
                else "same_family_backup"
            )
            continue
        if route_id and route_id == escalation_route_id:
            item["parallel_role"] = "escalation_backup"
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
    validation_families = _dedupe_strings(
        [
            _candidate_validation_family(item)
            for item in [primary, *validation]
            if item and _candidate_validation_family(item) != "unknown"
        ]
    )
    validation_diversity_status = "no_validation"
    if validation:
        validation_diversity_status = "independent_family" if len(validation_families) >= 2 else "same_family_only"
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
    if validation and len(validation_families) < 2:
        stop_conditions.append("capture_independent_validation_family_before_release")
    return {
        "mode": mode,
        "primary_route_id": str(primary.get("route_id", "")).strip(),
        "validation_route_ids": [str(item.get("route_id", "")).strip() for item in validation if str(item.get("route_id", "")).strip()],
        "escalation_route_ids": [str(item.get("route_id", "")).strip() for item in escalation if str(item.get("route_id", "")).strip()],
        "allow_parallel_validation": allow_parallel,
        "validation_families": validation_families,
        "validation_family_count": len(validation_families),
        "validation_diversity_status": validation_diversity_status,
        "stop_conditions": _dedupe_strings(stop_conditions),
    }


def _derive_result_consensus(
    goal: str,
    knowledge_basis: Dict[str, Any],
    route_candidates: List[Dict[str, Any]],
    challenge: Dict[str, Any],
    delivery_requirements: Dict[str, Any],
) -> Dict[str, Any]:
    """
    中文注解：
    - 功能：生成多路线结果比对规则。
    - 设计意图：系统不只知道“抓到了”，还知道“怎样从多条结果里选最可信的那条”。
    """
    fresh_weight = 5 if _goal_time_sensitivity(goal) == "fresh" else 3
    challenge_rank = _challenge_severity_rank(challenge)
    live_candidates = [item for item in route_candidates if item.get("route_type") != "human_checkpoint"]
    validation_families = _dedupe_strings([_candidate_validation_family(item) for item in live_candidates if _candidate_validation_family(item) != "unknown"])
    route_diversity_required = len(live_candidates) >= 2
    has_required_field_contract = any(
        [str(field).strip() for fields in (delivery_requirements.get("required_fields_by_site", {}) or {}).values() for field in (fields or [])]
    )
    comparison_axes = [
        {"name": "source_trust", "weight": 5, "why": "优先官方/结构化/已验证来源。"},
        {"name": "required_field_coverage", "weight": 6 if has_required_field_contract else 4, "why": "先满足本次任务真正 required 的字段，再考虑扩展字段。"},
        {"name": "field_completeness", "weight": 5, "why": "最终结果要尽量覆盖任务要求字段。"},
        {"name": "freshness", "weight": fresh_weight, "why": "时效敏感任务必须提高 freshness 权重。"},
        {"name": "site_readiness", "weight": 4 if challenge_rank >= 2 else 3, "why": "遇到反爬/风控时，优先已验证可用路线。"},
        {"name": "cross_route_agreement", "weight": 4 if route_diversity_required else 2, "why": "多路线结果越一致，可信度越高。"},
        {"name": "validation_family_diversity", "weight": 4 if len(validation_families) >= 2 else 2, "why": "优先不同证据家族形成的交叉验证，而不是同家族换壳确认。"},
        {"name": "route_risk", "weight": 3, "why": "质量接近时优先低风险路线。"},
        {"name": "cost_efficiency", "weight": 2, "why": "避免每次都直接升级到高成本浏览器链。"},
    ]
    return build_acquisition_consensus_schema(
        consensus_mode="best_evidence_wins_with_validation_bias",
        comparison_axes=comparison_axes,
        tie_breakers=[
            "prefer_route_with_higher_required_field_coverage",
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
            "validation_family",
            "evidence_ref",
        ],
        must_compare_when_multiple_routes=len(route_candidates) >= 2,
        route_diversity_required=route_diversity_required,
        minimum_validation_family_count=2 if route_diversity_required and len(validation_families) >= 2 else 1,
        prefer_independent_validation=len(validation_families) >= 2,
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
    delivery_requirements = _derive_delivery_requirements(goal, intent, route_candidates) if enabled else {}
    execution_strategy = _derive_execution_strategy(route_candidates, challenge) if enabled else {
        "mode": "disabled",
        "primary_route_id": "",
        "validation_route_ids": [],
        "escalation_route_ids": [],
        "allow_parallel_validation": False,
        "stop_conditions": [],
    }
    result_consensus = _derive_result_consensus(goal, knowledge_basis, route_candidates, challenge, delivery_requirements) if enabled else build_acquisition_consensus_schema()
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
        delivery_requirements=delivery_requirements,
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
                "validation_family": _candidate_validation_family(primary_route) if primary_route else "",
            },
            "validation_routes": [
                {
                    "route_id": str(item.get("route_id", "")).strip(),
                    "route_type": str(item.get("route_type", "")).strip(),
                    "adapter_id": str(item.get("adapter_id", "")).strip(),
                    "validation_family": _candidate_validation_family(item),
                }
                for item in validation_routes
                if item
            ],
            "validation_diversity_status": str(execution_strategy.get("validation_diversity_status", "")).strip(),
            "target_sites": list(delivery_requirements.get("target_sites", []) or []),
            "required_fields_by_site": dict(delivery_requirements.get("required_fields_by_site", {}) or {}),
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
