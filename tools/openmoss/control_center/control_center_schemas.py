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
- 文件路径：`tools/openmoss/control_center/control_center_schemas.py`
- 文件作用：集中定义 control center 内部协议对象的“单一真源雏形”。
- 设计意图：
  1. 避免 stage/verifier/governance/protocol/readiness 结构散落在多个文件里各自拼字典；
  2. 让 orchestrator、runtime、operator 文档后续都能围绕统一 schema 演化；
  3. 先做轻量 schema builder，而不是引入复杂生成器或黑箱协议层。
"""
from __future__ import annotations

from typing import Any, Dict, List


def _merge_payload(base: Dict[str, Any], overrides: Dict[str, Any] | None = None) -> Dict[str, Any]:
    """
    中文注解：
    - 功能：在不丢失默认字段的前提下，把 overrides 合并进标准 schema。
    - 设计意图：所有 schema builder 都先有默认形状，再按场景补值，避免字段飘来飘去。
    """
    merged = dict(base)
    for key, value in (overrides or {}).items():
        merged[key] = value
    return merged


def build_stage_contract_schema(
    *,
    name: str,
    goal: str = "",
    expected_output: str = "",
    acceptance_check: str = "",
    next_stage_trigger: str = "",
    fallback_rule: str = "",
    primary_monitor: str = "",
    backstop_monitor: str = "",
    miss_detection_signal: str = "",
    verifier: Dict[str, Any] | None = None,
    execution_policy: Dict[str, Any] | None = None,
    verification_guidance: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    """
    中文注解：
    - 功能：构造标准化 stage contract。
    - 输出角色：给 orchestrator 生成 contract.stages，同时作为后续 runtime/doctor 的稳定协议面。
    """
    return {
        "name": str(name).strip(),
        "goal": goal,
        "expected_output": expected_output,
        "acceptance_check": acceptance_check,
        "next_stage_trigger": next_stage_trigger,
        "fallback_rule": fallback_rule,
        "primary_monitor": primary_monitor,
        "backstop_monitor": backstop_monitor,
        "miss_detection_signal": miss_detection_signal,
        "verifier": verifier or {},
        "execution_policy": execution_policy or {},
        "verification_guidance": verification_guidance or {},
    }


def build_verifier_schema(
    verifier_type: str = "none",
    *,
    checks: List[Dict[str, Any]] | None = None,
    **extra: Any,
) -> Dict[str, Any]:
    """
    中文注解：
    - 功能：构造标准 verifier schema。
    - 设计意图：让 stage verifier 和未来 operator/runtime 文档围绕同一种结构表达。
    """
    payload: Dict[str, Any] = {
        "type": str(verifier_type or "none"),
        "checks": list(checks or []),
    }
    return _merge_payload(payload, extra)


def build_governance_policy_schema(
    tier: str,
    *,
    require_stage_artifacts: bool = False,
    require_plan_reviews: bool = False,
    require_full_verifier: bool = False,
    require_postmortem: bool = True,
    require_stage_acceptance_before_progress: bool = False,
    require_test_evidence_for_execute: bool = False,
    allow_execute_stage: bool = True,
    allow_execute_auto_complete: bool = True,
    allow_verify_auto_complete: bool = False,
    strict_release_gate: bool = False,
    review_roles: List[str] | None = None,
    review_depth: str = "standard",
    readiness_profile: str = "default",
    user_confirmation_for_direction_change: bool = True,
    compatibility_controller_enabled: bool = False,
    stage_gate_policy: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    """
    中文注解：
    - 功能：构造治理策略 schema。
    - 设计意图：把“治理等级”和“治理动作”分开，避免 tier 只是一个名字却没有可消费规则。
    """
    return {
        "tier": str(tier).strip() or "standard",
        "require_stage_artifacts": bool(require_stage_artifacts),
        "require_plan_reviews": bool(require_plan_reviews),
        "require_full_verifier": bool(require_full_verifier),
        "require_postmortem": bool(require_postmortem),
        "require_stage_acceptance_before_progress": bool(require_stage_acceptance_before_progress),
        "require_test_evidence_for_execute": bool(require_test_evidence_for_execute),
        "allow_execute_stage": bool(allow_execute_stage),
        "allow_execute_auto_complete": bool(allow_execute_auto_complete),
        "allow_verify_auto_complete": bool(allow_verify_auto_complete),
        "strict_release_gate": bool(strict_release_gate),
        "review_roles": list(review_roles or []),
        "review_depth": review_depth,
        "readiness_profile": readiness_profile,
        "user_confirmation_for_direction_change": bool(user_confirmation_for_direction_change),
        "compatibility_controller_enabled": bool(compatibility_controller_enabled),
        "stage_gate_policy": dict(stage_gate_policy or {}),
    }


def build_protocol_pack_schema(
    pack_id: str,
    *,
    tier: str,
    scenario: str = "",
    stage_order: List[str] | None = None,
    must_follow_rules: List[str] | None = None,
    required_artifacts: List[str] | None = None,
    optional_artifacts: List[str] | None = None,
    skippable_stages: List[str] | None = None,
    methodology_prompt_profile: str = "jinclaw-native",
    review_bundle_required: List[str] | None = None,
) -> Dict[str, Any]:
    """
    中文注解：
    - 功能：构造 protocol pack schema。
    - 设计意图：不同强度任务共享一套显式“执行协议包”，而不是靠隐含 prompt 纪律来猜。
    """
    return {
        "pack_id": str(pack_id).strip(),
        "tier": str(tier).strip() or "standard",
        "scenario": scenario,
        "stage_order": list(stage_order or []),
        "must_follow_rules": list(must_follow_rules or []),
        "required_artifacts": list(required_artifacts or []),
        "optional_artifacts": list(optional_artifacts or []),
        "skippable_stages": list(skippable_stages or []),
        "methodology_prompt_profile": methodology_prompt_profile,
        "review_bundle_required": list(review_bundle_required or []),
    }


def build_readiness_dashboard_schema(
    *,
    plan_readiness: Dict[str, Any] | None = None,
    execute_readiness: Dict[str, Any] | None = None,
    verify_readiness: Dict[str, Any] | None = None,
    release_readiness: Dict[str, Any] | None = None,
    blocking_items: List[Dict[str, Any]] | None = None,
    missing_artifacts: List[str] | None = None,
    pending_decisions: List[Dict[str, Any]] | None = None,
) -> Dict[str, Any]:
    """
    中文注解：
    - 功能：构造 readiness dashboard schema。
    - 设计意图：把“为什么现在还不能进入下一步”结构化表达出来，给 runtime/doctor/UI 统一消费。
    """
    return {
        "plan_readiness": dict(plan_readiness or {}),
        "execute_readiness": dict(execute_readiness or {}),
        "verify_readiness": dict(verify_readiness or {}),
        "release_readiness": dict(release_readiness or {}),
        "blocking_items": list(blocking_items or []),
        "missing_artifacts": list(missing_artifacts or []),
        "pending_decisions": list(pending_decisions or []),
    }


def build_acquisition_adapter_schema(
    adapter_id: str,
    *,
    label: str = "",
    stack_id: str = "",
    route_type: str = "",
    enabled: bool = False,
    detected: bool | None = None,
    runtime_ready: bool | None = None,
    selection_state: str = "",
    tools: List[str] | None = None,
    tool_labels: List[str] | None = None,
    execution_tool_id: str = "",
    execution_runtime: str = "",
    execution_profile: str = "",
    validation_family: str = "",
    best_for: List[str] | None = None,
    strengths: List[str] | None = None,
    limits: List[str] | None = None,
    risk_level: str = "medium",
    anti_bot_readiness: str = "medium",
    auth_requirement: str = "none",
    cost_profile: str = "medium",
    structured_output_level: str = "medium",
    supports_parallel_validation: bool = False,
    preferred_sites: List[str] | None = None,
    notes: List[str] | None = None,
) -> Dict[str, Any]:
    """
    中文注解：
    - 功能：构造 acquisition adapter schema。
    - 设计意图：把不同抓取/取数 adapter 的能力画像集中成统一结构，给 orchestrator、runtime、doctor 共用。
    """
    return {
        "adapter_id": str(adapter_id).strip(),
        "label": label,
        "stack_id": stack_id,
        "route_type": route_type,
        "enabled": bool(enabled),
        "detected": bool(enabled if detected is None else detected),
        "runtime_ready": bool(enabled if runtime_ready is None else runtime_ready),
        "selection_state": selection_state or ("ready" if enabled else "unavailable"),
        "tools": list(tools or []),
        "tool_labels": list(tool_labels or []),
        "execution_tool_id": str(execution_tool_id).strip(),
        "execution_runtime": str(execution_runtime).strip(),
        "execution_profile": str(execution_profile).strip(),
        "validation_family": str(validation_family).strip(),
        "best_for": list(best_for or []),
        "strengths": list(strengths or []),
        "limits": list(limits or []),
        "risk_level": risk_level,
        "anti_bot_readiness": anti_bot_readiness,
        "auth_requirement": auth_requirement,
        "cost_profile": cost_profile,
        "structured_output_level": structured_output_level,
        "supports_parallel_validation": bool(supports_parallel_validation),
        "preferred_sites": list(preferred_sites or []),
        "notes": list(notes or []),
    }


def build_acquisition_consensus_schema(
    *,
    consensus_mode: str = "best_evidence_wins",
    comparison_axes: List[Dict[str, Any]] | None = None,
    tie_breakers: List[str] | None = None,
    required_provenance_fields: List[str] | None = None,
    must_compare_when_multiple_routes: bool = True,
    route_diversity_required: bool = False,
    minimum_validation_family_count: int = 1,
    prefer_independent_validation: bool = False,
    prefer_low_risk_when_quality_similar: bool = True,
    prefer_verified_site_route: bool = False,
    knowledge_basis_hint: str = "",
) -> Dict[str, Any]:
    """
    中文注解：
    - 功能：构造 acquisition result consensus schema。
    - 设计意图：把“多路线结果如何比对、如何选优”标准化，避免不同执行器各自猜规则。
    """
    return {
        "consensus_mode": consensus_mode,
        "comparison_axes": list(comparison_axes or []),
        "tie_breakers": list(tie_breakers or []),
        "required_provenance_fields": list(required_provenance_fields or []),
        "must_compare_when_multiple_routes": bool(must_compare_when_multiple_routes),
        "route_diversity_required": bool(route_diversity_required),
        "minimum_validation_family_count": max(1, int(minimum_validation_family_count or 1)),
        "prefer_independent_validation": bool(prefer_independent_validation),
        "prefer_low_risk_when_quality_similar": bool(prefer_low_risk_when_quality_similar),
        "prefer_verified_site_route": bool(prefer_verified_site_route),
        "knowledge_basis_hint": knowledge_basis_hint,
    }


def build_acquisition_hand_schema(
    *,
    task_id: str,
    enabled: bool,
    target_profile: Dict[str, Any] | None = None,
    delivery_requirements: Dict[str, Any] | None = None,
    governance_binding: Dict[str, Any] | None = None,
    challenge_assessment: Dict[str, Any] | None = None,
    routing_policy: Dict[str, Any] | None = None,
    adapter_registry: Dict[str, Any] | None = None,
    route_candidates: List[Dict[str, Any]] | None = None,
    execution_strategy: Dict[str, Any] | None = None,
    result_consensus: Dict[str, Any] | None = None,
    evidence_contract: Dict[str, Any] | None = None,
    learning_contract: Dict[str, Any] | None = None,
    recommended_tools: List[str] | None = None,
    compatibility: Dict[str, Any] | None = None,
    summary: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    """
    中文注解：
    - 功能：构造 acquisition hand 总协议 schema。
    - 设计意图：把 JinClaw/OpenClaw 的外部数据获取能力从零散 crawler 元数据升级成统一、可治理、可消费的“取数之手”。
    """
    return {
        "version": "acquisition-hand-v1",
        "task_id": task_id,
        "enabled": bool(enabled),
        "target_profile": dict(target_profile or {}),
        "delivery_requirements": dict(delivery_requirements or {}),
        "governance_binding": dict(governance_binding or {}),
        "challenge_assessment": dict(challenge_assessment or {}),
        "routing_policy": dict(routing_policy or {}),
        "adapter_registry": dict(adapter_registry or {}),
        "route_candidates": list(route_candidates or []),
        "execution_strategy": dict(execution_strategy or {}),
        "result_consensus": dict(result_consensus or {}),
        "evidence_contract": dict(evidence_contract or {}),
        "learning_contract": dict(learning_contract or {}),
        "recommended_tools": list(recommended_tools or []),
        "compatibility": dict(compatibility or {}),
        "summary": dict(summary or {}),
    }


def build_acquisition_route_result_schema(
    *,
    site: str,
    route_id: str = "",
    adapter_id: str = "",
    route_type: str = "",
    validation_family: str = "",
    tool_label: str = "",
    status: str = "failed",
    source_url: str = "",
    retrieved_at: str = "",
    field_coverage: float = 0.0,
    required_field_coverage: float = 0.0,
    populated_fields: List[str] | None = None,
    required_fields_present: List[str] | None = None,
    missing_required_fields: List[str] | None = None,
    arbitration_score: int = 0,
    evidence_ref: str = "",
    route_risk: str = "medium",
    preferred_site_match: bool = False,
    task_fields: Dict[str, Any] | None = None,
    notes: List[str] | None = None,
) -> Dict[str, Any]:
    """
    中文注解：
    - 功能：构造 acquisition 单条路线执行结果 schema。
    - 设计意图：把不同工具、不同抓取路线产出的证据统一到一层可比较结构上。
    """
    return {
        "site": str(site).strip(),
        "route_id": str(route_id).strip(),
        "adapter_id": str(adapter_id).strip(),
        "route_type": str(route_type).strip(),
        "validation_family": str(validation_family).strip(),
        "tool_label": str(tool_label).strip(),
        "status": str(status).strip() or "failed",
        "source_url": str(source_url).strip(),
        "retrieved_at": str(retrieved_at).strip(),
        "field_coverage": round(float(field_coverage or 0.0), 3),
        "required_field_coverage": round(float(required_field_coverage or 0.0), 3),
        "populated_fields": list(populated_fields or []),
        "required_fields_present": list(required_fields_present or []),
        "missing_required_fields": list(missing_required_fields or []),
        "arbitration_score": int(arbitration_score or 0),
        "evidence_ref": str(evidence_ref).strip(),
        "route_risk": str(route_risk).strip() or "medium",
        "preferred_site_match": bool(preferred_site_match),
        "task_fields": dict(task_fields or {}),
        "notes": list(notes or []),
    }


def build_acquisition_field_provenance_schema(
    *,
    field_name: str,
    selected_value: Any = "",
    selected_route_id: str = "",
    selected_adapter_id: str = "",
    selected_tool_label: str = "",
    confidence: str = "single_route",
    supporting_route_ids: List[str] | None = None,
    supporting_validation_families: List[str] | None = None,
    disagreeing_route_ids: List[str] | None = None,
    disagreeing_validation_families: List[str] | None = None,
    supporting_values: List[Any] | None = None,
    notes: List[str] | None = None,
) -> Dict[str, Any]:
    """
    中文注解：
    - 功能：构造字段级 provenance schema。
    - 设计意图：不仅要知道最终字段值是什么，还要知道它来自哪条路线、有没有交叉验证、是否存在冲突。
    """
    return {
        "field_name": str(field_name).strip(),
        "selected_value": selected_value,
        "selected_route_id": str(selected_route_id).strip(),
        "selected_adapter_id": str(selected_adapter_id).strip(),
        "selected_tool_label": str(selected_tool_label).strip(),
        "confidence": str(confidence).strip() or "single_route",
        "supporting_route_ids": list(supporting_route_ids or []),
        "supporting_validation_families": list(supporting_validation_families or []),
        "disagreeing_route_ids": list(disagreeing_route_ids or []),
        "disagreeing_validation_families": list(disagreeing_validation_families or []),
        "supporting_values": list(supporting_values or []),
        "notes": list(notes or []),
    }


def build_acquisition_site_synthesis_schema(
    *,
    site: str,
    synthesis_status: str = "blocked",
    final_fields: Dict[str, Any] | None = None,
    field_provenance: Dict[str, Dict[str, Any]] | None = None,
    required_fields: List[str] | None = None,
    stretch_fields: List[str] | None = None,
    missing_fields: List[str] | None = None,
    missing_required_fields: List[str] | None = None,
    missing_stretch_fields: List[str] | None = None,
    required_field_coverage_ratio: float = 0.0,
    release_ready: bool = False,
    cross_validated_fields: List[str] | None = None,
    conflicted_fields: List[str] | None = None,
    supporting_route_ids: List[str] | None = None,
    recommended_next_actions: List[str] | None = None,
    notes: List[str] | None = None,
) -> Dict[str, Any]:
    """
    中文注解：
    - 功能：构造站点级字段融合输出 schema。
    - 设计意图：让 acquisition hand 的最终交付不只是“站点赢家”，而是“站点最佳结构化结果 + 每个字段的证据说明”。
    """
    return {
        "site": str(site).strip(),
        "synthesis_status": str(synthesis_status).strip() or "blocked",
        "final_fields": dict(final_fields or {}),
        "field_provenance": dict(field_provenance or {}),
        "required_fields": list(required_fields or []),
        "stretch_fields": list(stretch_fields or []),
        "missing_fields": list(missing_fields or []),
        "missing_required_fields": list(missing_required_fields or []),
        "missing_stretch_fields": list(missing_stretch_fields or []),
        "required_field_coverage_ratio": round(float(required_field_coverage_ratio or 0.0), 3),
        "release_ready": bool(release_ready),
        "cross_validated_fields": list(cross_validated_fields or []),
        "conflicted_fields": list(conflicted_fields or []),
        "supporting_route_ids": list(supporting_route_ids or []),
        "recommended_next_actions": list(recommended_next_actions or []),
        "notes": list(notes or []),
    }


def build_acquisition_execution_summary_schema(
    *,
    task_id: str,
    goal: str = "",
    generated_at: str = "",
    report_path: str = "",
    planned_route_ids: List[str] | None = None,
    executed_route_ids: List[str] | None = None,
    planned_but_not_executed_route_ids: List[str] | None = None,
    route_runs: List[Dict[str, Any]] | None = None,
    site_consensus: List[Dict[str, Any]] | None = None,
    site_synthesized_outputs: List[Dict[str, Any]] | None = None,
    overall_summary: Dict[str, Any] | None = None,
    recommended_next_actions: List[str] | None = None,
) -> Dict[str, Any]:
    """
    中文注解：
    - 功能：构造 acquisition 执行摘要 schema。
    - 设计意图：让 runtime、verifier、doctor 都围绕同一份执行后证据理解“计划了什么、实际跑了什么、哪条路线赢了，以及最终字段如何被融合出来”。
    """
    return {
        "version": "acquisition-execution-summary-v2",
        "task_id": str(task_id).strip(),
        "goal": goal,
        "generated_at": generated_at,
        "report_path": report_path,
        "planned_route_ids": list(planned_route_ids or []),
        "executed_route_ids": list(executed_route_ids or []),
        "planned_but_not_executed_route_ids": list(planned_but_not_executed_route_ids or []),
        "route_runs": list(route_runs or []),
        "site_consensus": list(site_consensus or []),
        "site_synthesized_outputs": list(site_synthesized_outputs or []),
        "overall_summary": dict(overall_summary or {}),
        "recommended_next_actions": list(recommended_next_actions or []),
    }
