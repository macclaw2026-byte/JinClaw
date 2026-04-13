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
