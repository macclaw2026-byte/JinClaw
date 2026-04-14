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
- 文件路径：`tools/openmoss/control_center/orchestrator.py`
- 文件作用：负责把“用户的一句话目标”编排成 runtime 能理解和执行的任务合同。
- 顶层函数：_utc_now_iso、_write_json、_derive_allowed_tools、_merge_inherited_intent、_requires_explicit_business_proof、_business_outcome_verifier、derive_business_verification_requirements、_derive_stage_contracts、build_control_center_package、main。
- 顶层类：无顶层类。
- 主流程定位：
  1. 收到 task_id + goal 后，先做 intent / mission profile 识别。
  2. 再组装 candidate plans、selected plan、approval、domain profile、拓扑图等控制中心产物。
  3. 最后把这些结构压成 metadata、stage contracts 和 done definition，交给 manager 写成 contract.json。
"""
from __future__ import annotations

import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

from control_center_schemas import (
    build_governance_policy_schema,
    build_protocol_pack_schema,
    build_readiness_dashboard_schema,
    build_stage_contract_schema,
    build_verifier_schema,
)

WORKSPACE_ROOT = Path("/Users/mac_claw/.openclaw/workspace")
GSTACK_LITE_PROMPT_PATH = WORKSPACE_ROOT / "compat/gstack/prompts/jinclaw-gstack-lite.md"
GSTACK_PLAN_PROMPT_PATH = WORKSPACE_ROOT / "compat/gstack/prompts/jinclaw-gstack-plan.md"
AUTONOMY_DIR = WORKSPACE_ROOT / "tools/openmoss/autonomy"
if str(AUTONOMY_DIR) not in sys.path:
    sys.path.insert(0, str(AUTONOMY_DIR))

from approval_gate import review_plan
from acquisition_hand_builder import build_acquisition_hand
from adoption_flow import build_adoption_flow
from adaptive_fetch_router import build_fetch_route
from authorized_session_manager import build_authorized_session_plan
from bdi_state import build_bdi_state
from capability_registry import build_capability_registry
from challenge_classifier import classify_challenge
from crawler_layer import build_crawler_plan
from domain_profile_store import build_domain_profile
from event_bus import publish_event
from external_tool_scorer import score_external_options
from fractal_decomposer import build_fractal_loops
from htn_planner import build_htn_tree, select_htn_focus
from human_checkpoint import build_human_checkpoint
from intent_analyzer import analyze_intent
from mission_profiles import detect_root_mission_profile
from paths import APPROVALS_ROOT, MISSIONS_ROOT
from plan_reselector import reselect_plan
from proposal_judge import judge_proposals
from promotion_engine import load_doctor_strategy_rules, load_operator_discipline_rules
from resource_scout import build_resource_scout_brief
from solution_arbitrator import arbitrate_solution_path
from stpa_auditor import audit_mission
from topology_mapper import build_topology
from workflow_planner import build_workflow_blueprint


GOAL_SEQUENCE_TOKENS = (
    "然后",
    "接着",
    "最后",
    "逐个",
    "每个",
    "全部",
    "全量",
    "直到",
    "持续",
    "闭环",
    "并且",
    "以及",
)
PLAN_ONLY_TOKENS = (
    "只做规划",
    "只做方案",
    "先出方案",
    "先给方案",
    "先做计划",
    "不要实施",
    "不要写代码",
    "不进入实现",
    "plan only",
    "planning only",
    "do not implement",
    "do not build",
    "save the plan",
    "spec only",
)
IMPLEMENT_TOKENS = (
    "build",
    "implement",
    "fix",
    "debug",
    "refactor",
    "deploy",
    "ship",
    "code",
    "写代码",
    "实现",
    "修复",
    "重构",
    "部署",
    "交付",
    "上线",
)
SMALL_TASK_TOKENS = (
    "typo",
    "readme",
    "wording",
    "rename",
    "small patch",
    "minor fix",
    "one-line",
    "错别字",
    "文案",
    "改名",
    "小修",
    "小补丁",
)
REVIEW_HEAVY_TOKENS = (
    "architecture",
    "review",
    "strategy",
    "design",
    "ux",
    "规划",
    "方案",
    "评审",
    "架构",
    "策略",
)
MISSION_TOKENS = (
    "project",
    "objective",
    "platform",
    "system",
    "workflow",
    "engine",
    "dashboard",
    "course",
    "training",
    "assessment",
    "evaluation",
    "产品",
    "应用",
    "平台",
    "系统",
    "工作流",
    "引擎",
    "课程",
    "培训",
    "评估",
    "胜任力",
    "完整",
)


def _goal_has_any(goal: str, tokens: tuple[str, ...]) -> bool:
    return any(token in str(goal or "").lower() for token in tokens)


def _load_prompt_text(path: Path) -> str:
    """
    中文注解：
    - 功能：读取 prompt 资产文件。
    - 设计意图：方法论前言必须文件化，避免被散落在代码里难以演进和审计。
    """
    if not path.exists():
        return ""
    return path.read_text(encoding="utf-8")


def _goal_prefers_planning_only(goal: str) -> bool:
    """
    中文注解：
    - 功能：判断目标是否明确要求“只规划、不实施”。
    - 设计意图：plan-only 任务必须被当成独立治理模式，不能误入完整 build/execute 流程。
    """
    normalized_goal = str(goal or "").lower()
    return any(token in normalized_goal for token in PLAN_ONLY_TOKENS)


def _goal_implies_small_patch(goal: str) -> bool:
    """
    中文注解：
    - 功能：识别偏轻量的单步修补任务。
    - 设计意图：避免简单任务被套上 mission 级治理开销。
    """
    normalized_goal = str(goal or "").lower()
    return any(token in normalized_goal for token in SMALL_TASK_TOKENS)


def _is_user_visible_task(intent: Dict[str, object]) -> bool:
    task_types = {str(item).strip().lower() for item in intent.get("task_types", []) if str(item).strip()}
    return bool(task_types & {"web", "marketplace", "image"})


def _review_roles_for_tier(tier: str) -> List[str]:
    if tier == "lite":
        return ["engineering_review", "security_review"]
    if tier == "standard":
        return ["product_review", "engineering_review", "security_review"]
    if tier == "plan_only":
        return ["product_review", "engineering_review", "design_review"]
    return ["product_review", "engineering_review", "design_review", "security_review", "devex_review"]


def _default_stage_gate_policy(include_execute: bool = True) -> Dict[str, object]:
    """
    中文注解：
    - 功能：生成标准 stage gate policy。
    - 设计意图：把复杂/评审型任务的阶段门禁从硬编码字典提升为可复用协议部件。
    """
    policy: Dict[str, object] = {
        "understand": {
            "required_artifact_keys": ["mission_brief", "scope_constraints", "success_definition"],
            "require_summary_nonempty": True,
        },
        "plan": {
            "required_artifact_keys": ["execution_plan", "review_bundle", "protocol_pack", "test_strategy"],
            "require_summary_nonempty": True,
        },
        "verify": {
            "required_artifact_keys": ["verification_report", "acceptance_decision", "remaining_risks"],
            "require_summary_nonempty": True,
        },
        "learn": {
            "required_artifact_keys": ["postmortem", "reusable_rule", "followup_risks"],
            "require_summary_nonempty": True,
        },
    }
    if include_execute:
        policy["execute"] = {
            "required_artifact_keys": ["delivery_evidence", "implementation_delta", "test_signal"],
            "require_summary_nonempty": True,
            "require_evidence_refs": True,
        }
    return policy


def _is_complex_delivery_task(
    goal: str,
    intent: Dict[str, object],
    mission_profile: Dict[str, object],
    coding_methodology: Dict[str, object],
) -> bool:
    """
    中文注解：
    - 功能：判断一个任务是否应进入“复杂任务总控流程”。
    - 设计意图：把真正需要阶段产物、阶段验收、阶段测试和强放行门禁的任务识别出来。
    """
    normalized_goal = str(goal or "").lower()
    task_types = {str(item).strip().lower() for item in intent.get("task_types", []) if str(item).strip()}
    if mission_profile.get("matched"):
        return True
    if len(_derive_execute_deliverables(goal)) >= 3:
        return True
    if sum(1 for token in MISSION_TOKENS if token in normalized_goal) >= 2:
        return True
    if coding_methodology.get("enabled") and (
        {"code", "web", "data"} & task_types
        or any(token in normalized_goal for token in ("build", "implement", "develop", "integrate", "构建", "实现", "开发", "接入"))
    ):
        return True
    return False


def _derive_governance_tier(
    goal: str,
    intent: Dict[str, object],
    mission_profile: Dict[str, object],
    coding_methodology: Dict[str, object],
) -> Dict[str, object]:
    """
    中文注解：
    - 功能：推导治理强度分档。
    - 设计意图：从二元复杂度升级为多档治理模型，让简单任务不过度治理、中等任务不过度放养、plan-only 不误入实现链。
    """
    normalized_goal = str(goal or "").lower()
    task_types = {str(item).strip().lower() for item in intent.get("task_types", []) if str(item).strip()}
    deliverables = _derive_execute_deliverables(goal)
    deliverable_count = len(deliverables)
    signals: List[str] = []
    rationale: List[str] = []

    if mission_profile.get("matched"):
        signals.append("mission_profile_matched")
        rationale.append("命中了 root mission profile，需要按更强治理处理。")

    plan_only = _goal_prefers_planning_only(goal)
    if plan_only:
        signals.append("explicit_plan_only_goal")
        rationale.append("目标明确要求只做规划，不进入实施。")
        return {
            "tier": "plan_only",
            "plan_only": True,
            "signals": signals,
            "rationale": rationale,
            "deliverable_count": deliverable_count,
        }

    if _goal_implies_small_patch(goal) and deliverable_count <= 1 and not mission_profile.get("matched"):
        signals.append("small_patch_signal")
        rationale.append("目标更像单步、小修、小范围补丁。")
        return {
            "tier": "lite",
            "plan_only": False,
            "signals": signals,
            "rationale": rationale,
            "deliverable_count": deliverable_count,
        }

    if _is_complex_delivery_task(goal, intent, mission_profile, coding_methodology):
        signals.append("complex_delivery_signal")
        rationale.append("任务具备 feature/project/objective 级复杂度或多阶段交付属性。")

    if deliverable_count >= 4:
        signals.append("many_deliverables")
        rationale.append("execute 可交付物较多，说明需要 mission 级分解与门禁。")

    if coding_methodology.get("enabled"):
        signals.append("coding_methodology_enabled")
        rationale.append("命中了 coding methodology，需要更明确的计划和验证纪律。")

    if deliverable_count >= 4 or mission_profile.get("matched") or (_is_complex_delivery_task(goal, intent, mission_profile, coding_methodology) and len(task_types) >= 2):
        return {
            "tier": "mission",
            "plan_only": False,
            "signals": signals,
            "rationale": rationale,
            "deliverable_count": deliverable_count,
        }

    reviewed_shape = (
        deliverable_count >= 2
        or (coding_methodology.get("enabled") and bool(task_types & {"code", "web", "data"}))
        or (_goal_has_any(goal, REVIEW_HEAVY_TOKENS) and bool(task_types))
        or (intent.get("needs_browser") and intent.get("requires_external_information"))
    )
    if reviewed_shape:
        signals.append("reviewed_shape")
        rationale.append("任务是多步骤/多视角决策，适合进入 reviewed 治理。")
        return {
            "tier": "reviewed",
            "plan_only": False,
            "signals": signals,
            "rationale": rationale,
            "deliverable_count": deliverable_count,
        }

    standard_shape = (
        deliverable_count >= 1
        or task_types != {"general"}
        or intent.get("requires_external_information")
        or intent.get("needs_browser")
    )
    if standard_shape:
        signals.append("standard_shape")
        rationale.append("任务具备普通多步骤特征，但还不需要完整 review gauntlet。")
        return {
            "tier": "standard",
            "plan_only": False,
            "signals": signals,
            "rationale": rationale,
            "deliverable_count": deliverable_count,
        }

    signals.append("default_lite")
    rationale.append("没有命中高复杂度或多步骤信号，按轻量治理处理。")
    return {
        "tier": "lite",
        "plan_only": False,
        "signals": signals,
        "rationale": rationale,
        "deliverable_count": deliverable_count,
    }


def _derive_governance_policy(tier: str) -> Dict[str, object]:
    """
    中文注解：
    - 功能：把治理等级映射成可消费的治理策略。
    - 设计意图：tier 只负责分档，policy 才负责表达“要不要 artifacts/reviews/verifier/postmortem/auto-complete”。
    """
    tier = str(tier or "standard").strip() or "standard"
    if tier == "lite":
        return build_governance_policy_schema(
            "lite",
            require_stage_artifacts=False,
            require_plan_reviews=False,
            require_full_verifier=False,
            require_postmortem=True,
            require_stage_acceptance_before_progress=False,
            require_test_evidence_for_execute=False,
            allow_execute_stage=True,
            allow_execute_auto_complete=True,
            allow_verify_auto_complete=False,
            strict_release_gate=False,
            review_roles=_review_roles_for_tier("lite"),
            review_depth="lite",
            readiness_profile="lite",
            compatibility_controller_enabled=False,
            stage_gate_policy={},
        )
    if tier == "standard":
        return build_governance_policy_schema(
            "standard",
            require_stage_artifacts=False,
            require_plan_reviews=True,
            require_full_verifier=False,
            require_postmortem=True,
            require_stage_acceptance_before_progress=False,
            require_test_evidence_for_execute=False,
            allow_execute_stage=True,
            allow_execute_auto_complete=True,
            allow_verify_auto_complete=False,
            strict_release_gate=False,
            review_roles=_review_roles_for_tier("standard"),
            review_depth="standard",
            readiness_profile="standard",
            compatibility_controller_enabled=False,
            stage_gate_policy={},
        )
    if tier == "plan_only":
        return build_governance_policy_schema(
            "plan_only",
            require_stage_artifacts=True,
            require_plan_reviews=True,
            require_full_verifier=True,
            require_postmortem=True,
            require_stage_acceptance_before_progress=True,
            require_test_evidence_for_execute=False,
            allow_execute_stage=False,
            allow_execute_auto_complete=False,
            allow_verify_auto_complete=False,
            strict_release_gate=True,
            review_roles=_review_roles_for_tier("plan_only"),
            review_depth="plan_only",
            readiness_profile="plan_only",
            compatibility_controller_enabled=True,
            stage_gate_policy=_default_stage_gate_policy(include_execute=False),
        )
    if tier == "mission":
        return build_governance_policy_schema(
            "mission",
            require_stage_artifacts=True,
            require_plan_reviews=True,
            require_full_verifier=True,
            require_postmortem=True,
            require_stage_acceptance_before_progress=True,
            require_test_evidence_for_execute=True,
            allow_execute_stage=True,
            allow_execute_auto_complete=False,
            allow_verify_auto_complete=False,
            strict_release_gate=True,
            review_roles=_review_roles_for_tier("mission"),
            review_depth="full",
            readiness_profile="mission",
            compatibility_controller_enabled=True,
            stage_gate_policy=_default_stage_gate_policy(include_execute=True),
        )
    return build_governance_policy_schema(
        "reviewed",
        require_stage_artifacts=True,
        require_plan_reviews=True,
        require_full_verifier=True,
        require_postmortem=True,
        require_stage_acceptance_before_progress=True,
        require_test_evidence_for_execute=True,
        allow_execute_stage=True,
        allow_execute_auto_complete=False,
        allow_verify_auto_complete=False,
        strict_release_gate=False,
        review_roles=_review_roles_for_tier("reviewed"),
        review_depth="reviewed",
        readiness_profile="reviewed",
        compatibility_controller_enabled=True,
        stage_gate_policy=_default_stage_gate_policy(include_execute=True),
    )


def _derive_complex_task_controller(
    goal: str,
    intent: Dict[str, object],
    mission_profile: Dict[str, object],
    coding_methodology: Dict[str, object],
    governance: Dict[str, object] | None = None,
) -> Dict[str, object]:
    """
    中文注解：
    - 功能：生成复杂任务总控兼容配置。
    - 设计意图：旧链路仍可读取 `complex_task_controller`，但其值现在由新治理层映射生成，避免双轨逻辑漂移。
    """
    governance = governance or {}
    tier = str(governance.get("tier", "")).strip() or _derive_governance_tier(goal, intent, mission_profile, coding_methodology).get("tier", "standard")
    policy = governance.get("policy", {}) or _derive_governance_policy(tier)
    enabled = bool(policy.get("compatibility_controller_enabled") or policy.get("require_stage_artifacts"))
    return {
        "enabled": enabled,
        "controller": "complex_task_delivery_guard",
        "governance_tier": tier,
        "require_stage_artifacts": bool(policy.get("require_stage_artifacts")),
        "require_stage_acceptance_before_progress": bool(policy.get("require_stage_acceptance_before_progress")),
        "require_verify_stage_report": bool(policy.get("require_full_verifier")),
        "require_test_evidence_for_execute": bool(policy.get("require_test_evidence_for_execute")),
        "require_postmortem_before_completion": bool(policy.get("require_postmortem")),
        "strict_release_gate": bool(policy.get("strict_release_gate")),
        "stage_gate_policy": dict(policy.get("stage_gate_policy", {}) or {}),
    }


def _is_coding_task(intent: Dict[str, object]) -> bool:
    """
    中文注解：
    - 功能：判断当前任务是否属于应注入 JinClaw GStack-Lite 编码纪律的 coding task。
    - 设计意图：只给代码型任务注入，不污染一般研究、业务执行或纯状态查询任务。
    """
    task_types = {str(item).strip().lower() for item in intent.get("task_types", []) if str(item).strip()}
    goal = str(intent.get("goal", "") or "").lower()
    if "code" in task_types:
        return True
    coding_tokens = (
        "build",
        "implement",
        "fix",
        "debug",
        "refactor",
        "test",
        "optimize",
        "optimization",
        "improve",
        "stabilize",
        "harden",
        "integrate",
        "代码",
        "修复",
        "实现",
        "重构",
        "优化",
        "改进",
        "稳定",
        "加固",
        "融合",
        "接入",
    )
    return any(token in goal for token in coding_tokens)


def _derive_coding_methodology(intent: Dict[str, object]) -> Dict[str, object]:
    """
    中文注解：
    - 功能：为 coding task 生成方法论注入包。
    - 输出：供 runtime/context_builder/后续 ACP spawn 读取的结构化 metadata。
    """
    is_coding = _is_coding_task(intent)
    if not is_coding:
        return {
            "enabled": False,
            "methodology": "jinclaw-native",
            "lifecycle": [],
            "prompt_path": "",
            "prompt_text": "",
        }
    lifecycle = ["think", "plan", "build", "review", "test", "ship", "reflect"]
    prompt_text = _load_prompt_text(GSTACK_LITE_PROMPT_PATH)
    return {
        "enabled": True,
        "methodology": "jinclaw-gstack-lite",
        "lifecycle": lifecycle,
        "prompt_path": str(GSTACK_LITE_PROMPT_PATH) if GSTACK_LITE_PROMPT_PATH.exists() else "",
        "prompt_text": prompt_text,
        "reporting_contract": {
            "require_stage_completion_status": True,
            "require_evidence": True,
            "require_unresolved_risks": True,
            "require_recommended_next_step": True,
        },
    }


def _derive_goal_guardian(
    goal: str,
    intent: Dict[str, object],
    mission_profile: Dict[str, object],
    coding_methodology: Dict[str, object],
    governance: Dict[str, object] | None = None,
    operating_discipline: Dict[str, object] | None = None,
) -> Dict[str, object]:
    """
    中文注解：
    - 功能：为复杂任务生成“目标守护”配置。
    - 设计意图：
      1. 让医生与 runtime 明确知道：任务完成前不能静默停下；
      2. 完成后必须写复盘，复盘未落盘前不算真正结束；
      3. 优化类任务默认按一次 coding mission 处理，强制套用 gstack-lite 节奏。
    """
    normalized_goal = str(goal or "").lower()
    governance = governance or {}
    tier = str(governance.get("tier", "standard")).strip() or "standard"
    policy = governance.get("policy", {}) or _derive_governance_policy(tier)
    optimization_task = any(
        token in normalized_goal
        for token in ("optimize", "optimization", "improve", "stabilize", "refactor", "优化", "改进", "稳定", "重构", "升级")
    )
    strict_goal = _goal_requires_strict_continuation(goal, intent, mission_profile, governance=governance)
    rule_lookup = (operating_discipline or {}).get("rule_lookup", {}) or {}
    return {
        "enabled": True,
        "guardian_process": "system_doctor",
        "governance_tier": tier,
        "verify_every_step": True,
        "strict_continuation_required": strict_goal,
        "require_postmortem_before_completion": bool(policy.get("require_postmortem", True)),
        "postmortem_stage": "learn",
        "postmortem_required_fields": [
            "goal",
            "done_definition",
            "what_worked",
            "what_failed",
            "remaining_risks",
            "next_reusable_rule",
        ],
        "stuck_escalation_policy": {
            "enabled": True,
            "default_mode": "deep_research_then_ask_user",
            "deep_research_first": bool((rule_lookup.get("deep_research_before_ask_user", {}) or {}).get("enabled", True)),
            "ask_user_when_human_decision_required": bool((rule_lookup.get("ask_user_when_direction_changes", {}) or {}).get("enabled", True)),
            "fail_closed_on_uncertain_permissions": bool((rule_lookup.get("fail_closed_on_uncertain_permissions", {}) or {}).get("enabled", True)),
        },
        "optimization_task": optimization_task,
        "optimization_requires_gstack": bool(optimization_task or coding_methodology.get("enabled")),
    }


def _utc_now_iso() -> str:
    """
    中文注解：
    - 功能：实现 `_utc_now_iso` 对应的处理逻辑。
    - 角色：属于本模块中的内部辅助逻辑；私有函数通常服务同文件主流程，公共函数通常作为跨模块入口或能力接口。
    - 调用关系：建议结合本文件的模块说明、调用方以及同名相关辅助函数一起阅读。
    """
    return datetime.now(timezone.utc).isoformat()


def _write_json(path: Path, payload) -> None:
    """
    中文注解：
    - 功能：实现 `_write_json` 对应的处理逻辑。
    - 角色：属于本模块中的内部辅助逻辑；私有函数通常服务同文件主流程，公共函数通常作为跨模块入口或能力接口。
    - 调用关系：建议结合本文件的模块说明、调用方以及同名相关辅助函数一起阅读。
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _derive_allowed_tools(blueprint: Dict[str, object]) -> List[str]:
    """
    中文注解：
    - 功能：实现 `_derive_allowed_tools` 对应的处理逻辑。
    - 角色：属于本模块中的内部辅助逻辑；私有函数通常服务同文件主流程，公共函数通常作为跨模块入口或能力接口。
    - 调用关系：建议结合本文件的模块说明、调用方以及同名相关辅助函数一起阅读。
    """
    tools = ["rg"]
    intent = blueprint.get("intent", {})
    if intent.get("needs_browser"):
        tools.extend(["browser", "agent-browser"])
    if intent.get("requires_external_information"):
        tools.extend(["web", "search", "crawl4ai"])
    if "web" in intent.get("task_types", []) or "data" in intent.get("task_types", []):
        tools.extend(["crawl4ai", "httpx", "curl_cffi", "selectolax", "scrapy", "crawlee"])
    if intent.get("needs_browser") or str(blueprint.get("selected_plan", {}).get("plan_id", "")) == "browser_evidence":
        tools.extend(["playwright", "playwright_stealth"])
    acquisition_hand = blueprint.get("acquisition_hand", {}) or {}
    tools.extend([str(item) for item in acquisition_hand.get("recommended_tools", []) if str(item).strip()])
    return sorted(dict.fromkeys(tools))


def _merge_inherited_intent(intent: Dict[str, object], inherited_intent: Dict[str, object] | None) -> Dict[str, object]:
    """
    中文注解：
    - 功能：实现 `_merge_inherited_intent` 对应的处理逻辑。
    - 角色：属于本模块中的内部辅助逻辑；私有函数通常服务同文件主流程，公共函数通常作为跨模块入口或能力接口。
    - 调用关系：建议结合本文件的模块说明、调用方以及同名相关辅助函数一起阅读。
    """
    if not inherited_intent:
        return intent
    merged = dict(intent)
    inherited_task_types = [str(item) for item in inherited_intent.get("task_types", []) if str(item)]
    current_task_types = [str(item) for item in intent.get("task_types", []) if str(item)]
    if current_task_types == ["general"] and inherited_task_types and inherited_task_types != ["general"]:
        merged["task_types"] = inherited_task_types
    for key in ("keywords", "domains", "likely_platforms"):
        merged[key] = sorted(
            dict.fromkeys(
                [str(item) for item in intent.get(key, []) if str(item)]
                + [str(item) for item in inherited_intent.get(key, []) if str(item)]
            )
        )
    normalized_goal = str(intent.get("goal", "") or "").replace(" ", "")
    is_browser_marketplace_followup = (
        bool(intent.get("needs_browser"))
        and "marketplace" in {str(item) for item in merged.get("task_types", [])}
        and ("listing页面" in normalized_goal or "draft" in normalized_goal.lower() or "seller" in normalized_goal.lower())
    )
    merged["requires_external_information"] = bool(intent.get("requires_external_information") or inherited_intent.get("requires_external_information"))
    merged["needs_browser"] = bool(intent.get("needs_browser") or inherited_intent.get("needs_browser"))
    merged["needs_verification"] = bool(intent.get("needs_verification") or inherited_intent.get("needs_verification"))
    if is_browser_marketplace_followup:
        merged["may_download_artifacts"] = bool(intent.get("may_download_artifacts"))
        merged["may_execute_external_code"] = bool(intent.get("may_execute_external_code"))
    else:
        merged["may_download_artifacts"] = bool(intent.get("may_download_artifacts") or inherited_intent.get("may_download_artifacts"))
        merged["may_execute_external_code"] = bool(intent.get("may_execute_external_code") or inherited_intent.get("may_execute_external_code"))
    if str(intent.get("risk_level", "low")).lower() == "low":
        merged["risk_level"] = inherited_intent.get("risk_level", intent.get("risk_level", "low"))
    inherited_constraints = [str(item) for item in inherited_intent.get("hard_constraints", []) if str(item)]
    current_constraints = [str(item) for item in intent.get("hard_constraints", []) if str(item)]
    merged["hard_constraints"] = sorted(dict.fromkeys(current_constraints + inherited_constraints))
    return merged


def _derive_execute_deliverables(goal: str) -> List[Dict[str, object]]:
    """
    中文注解：
    - 功能：从用户目标里提炼一组“执行阶段需要逐项交付的 deliverables”。
    - 设计意图：把原来过粗的 execute 阶段再拆细一层，避免系统做完一步就误以为整段 execute 已经足够完成。
    """
    normalized = str(goal or "").replace("\n", " ")
    normalized = re.sub(r"\s+", " ", normalized).strip()
    if not normalized:
        return []
    raw_parts = re.split(r"[；;。.!?\n]|(?:以及)|(?:并且)|(?:然后)|(?:接着)|(?:最后)|(?:同时)|、", normalized)
    candidates: List[str] = []
    for part in raw_parts:
        text = re.sub(r"^\s*(?:\d+[\.\)、:：]\s*)?", "", part).strip(" ，,、；;。.")
        if len(text) < 4:
            continue
        if text in candidates:
            continue
        candidates.append(text)
    deliverables: List[Dict[str, object]] = []
    for idx, text in enumerate(candidates[:8], start=1):
        deliverables.append(
            {
                "id": f"execute-{idx}",
                "title": text,
                "stage": "execute",
                "required": True,
                "completion_mode": "stepwise_progress",
            }
        )
    return deliverables


def _goal_requires_strict_continuation(
    goal: str,
    intent: Dict[str, object],
    mission_profile: Dict[str, object],
    governance: Dict[str, object] | None = None,
) -> bool:
    """
    中文注解：
    - 功能：判断某个 goal 是否属于“多步骤且不能宽松自动收口”的任务。
    - 作用：命中后会强制 execute 阶段进入 milestone 驱动模式，不再只因为一次 wait 成功就自动当成整段 execute 完成。
    """
    governance = governance or {}
    if str(governance.get("tier", "")).strip() == "plan_only":
        return False
    normalized_goal = str(goal or "").lower()
    task_types = {str(item).strip().lower() for item in intent.get("task_types", []) if str(item).strip()}
    if mission_profile.get("matched"):
        return True
    if any(token in goal for token in GOAL_SEQUENCE_TOKENS):
        return True
    if re.search(r"(1[\.\)、:：]|2[\.\)、:：]|3[\.\)、:：])", goal):
        return True
    if len(_derive_execute_deliverables(goal)) >= 2:
        return True
    if task_types & {"data", "marketplace", "web", "code"} and any(token in normalized_goal for token in ["pipeline", "engine", "workflow", "daily", "report"]):
        return True
    return False


def _derive_task_milestones(
    task_id: str,
    goal: str,
    intent: Dict[str, object],
    mission_profile: Dict[str, object],
    governance: Dict[str, object] | None = None,
) -> List[Dict[str, object]]:
    """
    中文注解：
    - 功能：生成任务级 milestones。
    - 结构：默认包含阶段里程碑；如果是多步骤目标，还会额外生成 execute deliverables。
    """
    governance = governance or {}
    policy = governance.get("policy", {}) or _derive_governance_policy(str(governance.get("tier", "standard")))
    milestones: List[Dict[str, object]] = [
        {"id": "understand", "title": "完成理解与盘点", "stage": "understand", "required": True, "completion_mode": "stage_completion"},
        {"id": "plan", "title": "完成计划与方案选择", "stage": "plan", "required": True, "completion_mode": "stage_completion"},
        {"id": "verify", "title": "完成验证", "stage": "verify", "required": True, "completion_mode": "stage_completion"},
        {"id": "learn", "title": "完成学习收口", "stage": "learn", "required": True, "completion_mode": "stage_completion"},
    ]
    if not bool(policy.get("allow_execute_stage", True)):
        return milestones
    deliverables = _derive_execute_deliverables(goal) if _goal_requires_strict_continuation(goal, intent, mission_profile, governance=governance) else []
    if deliverables:
        milestones.extend(deliverables)
    else:
        milestones.append(
            {
                "id": "execute",
                "title": "完成执行主阶段",
                "stage": "execute",
                "required": True,
                "completion_mode": "stage_completion",
            }
        )
    return milestones


def _requires_explicit_business_proof(intent: Dict[str, object], selected_plan: Dict[str, object]) -> bool:
    """
    中文注解：
    - 功能：实现 `_requires_explicit_business_proof` 对应的处理逻辑。
    - 角色：属于本模块中的内部辅助逻辑；私有函数通常服务同文件主流程，公共函数通常作为跨模块入口或能力接口。
    - 调用关系：建议结合本文件的模块说明、调用方以及同名相关辅助函数一起阅读。
    """
    task_types = {str(item).strip().lower() for item in intent.get("task_types", []) if str(item).strip()}
    goal = str(intent.get("goal", "")).lower()
    return bool(
        intent.get("needs_browser")
        and (
            "marketplace" in task_types
            or "image" in task_types
            or any(token in goal for token in ["upload", "上传", "product", "详情页", "detail page", "image area", "图片区"])
            or str(selected_plan.get("plan_id", "")) == "local_image_pipeline"
        )
    )


def _business_outcome_verifier(task_id: str) -> Dict[str, object]:
    """
    中文注解：
    - 功能：实现 `_business_outcome_verifier` 对应的处理逻辑。
    - 角色：属于本模块中的内部辅助逻辑；私有函数通常服务同文件主流程，公共函数通常作为跨模块入口或能力接口。
    - 调用关系：建议结合本文件的模块说明、调用方以及同名相关辅助函数一起阅读。
    """
    return build_verifier_schema(
        "all",
        checks=[
            {"type": "task_state_metadata_equals", "task_id": task_id, "field": "business_outcome.goal_satisfied", "equals": True},
            {"type": "task_state_metadata_equals", "task_id": task_id, "field": "business_outcome.user_visible_result_confirmed", "equals": True},
            {"type": "task_state_metadata_nonempty", "task_id": task_id, "field": "business_outcome.proof_summary"},
        ],
    )


def derive_business_verification_requirements(intent: Dict[str, object]) -> Dict[str, object]:
    """
    中文注解：
    - 功能：实现 `derive_business_verification_requirements` 对应的处理逻辑。
    - 角色：属于本模块中的对外可见逻辑；私有函数通常服务同文件主流程，公共函数通常作为跨模块入口或能力接口。
    - 调用关系：建议结合本文件的模块说明、调用方以及同名相关辅助函数一起阅读。
    """
    goal = str(intent.get("goal", "") or "")
    goal_lower = goal.lower()
    requirements: Dict[str, object] = {}
    normalized_goal = goal.replace(" ", "")
    batch_draft_listings_goal = (
        ("draft" in goal_lower or "草稿" in goal or "listing页面所有draft" in normalized_goal or "所有draft状态" in normalized_goal)
        and ("listing" in goal_lower or "listing页面" in normalized_goal or "seller" in goal_lower or "seller中心" in normalized_goal)
    )

    if batch_draft_listings_goal:
        return {
            "draft_visible_count_at_most": 0,
            "batch_listings_mode": True,
        }

    if any(token in goal for token in ["至少3张场景图", "至少 3 张场景图", "至少三张场景图", "至少 3 张"]):
        requirements["scene_image_count_at_least"] = 3
    if any(token in goal for token in ["排到前面", "排到最前", "第8张"]):
        requirements["scene_image_position_max"] = 3
    if "packing unit" in goal_lower or "补齐缺失参数" in goal:
        requirements["packing_units_at_least"] = 1
        requirements["form_must_be_valid"] = True
    if any(token in goal for token in ["提交审核", "提审", "submit for review"]):
        requirements["review_status_not_in"] = ["DRAFT"]
        requirements["form_must_be_valid"] = True

    return requirements


def _build_role_review(
    reviewer: str,
    *,
    summary: str,
    concerns: List[str] | None = None,
    recommendations: List[str] | None = None,
    must_fix_before_execute: List[str] | None = None,
    ask_user_before_changing_direction: List[str] | None = None,
) -> Dict[str, object]:
    """
    中文注解：
    - 功能：构造统一形状的角色评审记录。
    - 设计意图：让各类 review 都能用同一个 schema 输出 concerns / recommendations / must-fix / 改向确认。
    """
    direction_items = [str(item).strip() for item in (ask_user_before_changing_direction or []) if str(item).strip()]
    return {
        "reviewer": reviewer,
        "summary": summary,
        "concerns": [str(item).strip() for item in (concerns or []) if str(item).strip()],
        "recommendations": [str(item).strip() for item in (recommendations or []) if str(item).strip()],
        "must_fix_before_execute": [str(item).strip() for item in (must_fix_before_execute or []) if str(item).strip()],
        "ask_user_before_changing_direction": direction_items,
        "direction_change_recommendation": bool(direction_items),
        "requires_user_confirmation": bool(direction_items),
    }


def _derive_plan_reviews(
    intent: Dict[str, object],
    candidate_plans: List[Dict[str, object]],
    selected_plan: Dict[str, object],
    governance: Dict[str, object],
) -> Dict[str, object]:
    """
    中文注解：
    - 功能：为 selected plan 生成角色化审议链。
    - 设计意图：把“候选方案评分器”升级为“多角色评议 bundle”，让计划质量不只体现在分数，还体现在不同视角各自担心什么。
    """
    goal = str(intent.get("goal", "") or "")
    normalized_goal = goal.lower()
    task_types = {str(item).strip().lower() for item in intent.get("task_types", []) if str(item).strip()}
    tier = str(governance.get("tier", "standard")).strip() or "standard"
    policy = governance.get("policy", {}) or {}
    active_reviewers = list(policy.get("review_roles", []))
    reviews: Dict[str, Dict[str, object]] = {}
    alternatives = [str(plan.get("plan_id", "")) for plan in candidate_plans if str(plan.get("plan_id", "")) and plan.get("plan_id") != selected_plan.get("plan_id")]
    selected_fit = str(selected_plan.get("fit", "")).strip()
    selected_steps = [str(item).strip() for item in selected_plan.get("steps", []) if str(item).strip()]
    short_goal = _goal_implies_small_patch(goal)
    user_visible_task = _is_user_visible_task(intent)
    external_actions = list(selected_plan.get("external_actions", []) or [])
    pending_direction_confirmations: List[Dict[str, object]] = []
    consolidated_must_fix: List[str] = []

    if "product_review" in active_reviewers:
        concerns = []
        recommendations = []
        must_fix = []
        ask_user = []
        if selected_fit == "fallback" and alternatives:
            concerns.append("当前 selected plan 属于 fallback，但仍存在更强 fit 的备选路径。")
            must_fix.append("记录为什么 fallback 路径仍优于其他 strong/primary 备选。")
        if len(selected_steps) < 3:
            concerns.append("计划步骤较粗，容易在执行期发生 scope 漂移。")
            recommendations.append("把计划补成更明确的 3-5 步业务序列。")
        if short_goal and tier in {"reviewed", "mission"}:
            ask_user.append("当前治理判断认为这是多步骤交付；如果你只想保留小修范围，需要你明确确认继续缩小 scope。")
        if not concerns:
            recommendations.append("当前计划和用户目标基本对齐，继续保持 scope discipline。")
        reviews["product_review"] = _build_role_review(
            "product_review",
            summary="评估 selected plan 是否真的解决用户问题，而不是只满足字面动作。",
            concerns=concerns,
            recommendations=recommendations,
            must_fix_before_execute=must_fix,
            ask_user_before_changing_direction=ask_user,
        )

    if "engineering_review" in active_reviewers:
        concerns = []
        recommendations = []
        must_fix = []
        if "code" in task_types and not any("test" in step.lower() for step in selected_steps):
            concerns.append("计划步骤没有显式测试路径，后续容易把验证挤到最后。")
            must_fix.append("在 plan 中显式写出 test strategy 和 regression path。")
        if "code" in task_types and tier in {"reviewed", "mission"}:
            must_fix.append("补齐 module breakdown，避免 execute 阶段再边写边猜模块边界。")
        if len(selected_steps) > 6:
            concerns.append("计划步骤偏长，说明实现边界可能还不够聚焦。")
            recommendations.append("合并重复动作，先锁定核心主路径，再拆支线。")
        if not concerns and not must_fix:
            recommendations.append("当前工程路径足够清晰，后续重点保持模块边界和测试闭环。")
        reviews["engineering_review"] = _build_role_review(
            "engineering_review",
            summary="检查架构合理性、可测试性、模块边界和实现顺序。",
            concerns=concerns,
            recommendations=recommendations,
            must_fix_before_execute=must_fix,
        )

    if "design_review" in active_reviewers:
        concerns = []
        recommendations = []
        must_fix = []
        if user_visible_task:
            if not any(token in " ".join(selected_steps).lower() for token in ["review", "verify", "qa", "screenshot", "validate", "体验", "验证"]):
                concerns.append("这是用户可见结果任务，但计划里缺少明确的体验/界面质量检查动作。")
                must_fix.append("加入 user-visible acceptance path，例如截图、流程检查或设计回看。")
            recommendations.append("对用户可见输出保持 intentional design，避免默认模板感。")
        else:
            recommendations.append("当前任务用户可见面较弱，设计 review 以边界检查为主。")
        reviews["design_review"] = _build_role_review(
            "design_review",
            summary="从用户可见质量和交互风险角度审视计划。",
            concerns=concerns,
            recommendations=recommendations,
            must_fix_before_execute=must_fix,
        )

    if "security_review" in active_reviewers:
        concerns = []
        recommendations = []
        must_fix = []
        ask_user = []
        if external_actions:
            concerns.append("selected plan 含外部动作，需要更严格的批准与来源审查。")
            must_fix.append("确保 approval/policy 已记录所有外部动作的待批项。")
        if intent.get("needs_browser"):
            recommendations.append("优先使用最低权限的采集路线，浏览器只在确实需要时上场。")
        if selected_plan.get("plan_id") == "audited_external_extension":
            ask_user.append("当前方案建议进入外部扩展路径；这属于战略性方向变化，需要你显式确认。")
        reviews["security_review"] = _build_role_review(
            "security_review",
            summary="评估风险、权限、外部依赖和执行边界。",
            concerns=concerns,
            recommendations=recommendations,
            must_fix_before_execute=must_fix,
            ask_user_before_changing_direction=ask_user,
        )

    if "devex_review" in active_reviewers:
        concerns = []
        recommendations = []
        must_fix = []
        if task_types & {"code", "dependency"}:
            if not any(token in " ".join(selected_steps).lower() for token in ["doc", "run", "command", "test", "verify", "文档", "命令"]):
                concerns.append("计划缺少 operator/devex 视角的可运行说明，后续维护成本会偏高。")
                must_fix.append("补齐 run/test/verify 命令或 operator handoff 说明。")
            recommendations.append("为后续维护者保留最小可复跑路径。")
        else:
            recommendations.append("当前任务 DevEx 风险较低，以可解释输出为主。")
        reviews["devex_review"] = _build_role_review(
            "devex_review",
            summary="检查后续开发/维护成本、可读性、调试性与扩展性。",
            concerns=concerns,
            recommendations=recommendations,
            must_fix_before_execute=must_fix,
        )

    for review in reviews.values():
        for item in review.get("must_fix_before_execute", []):
            if item not in consolidated_must_fix:
                consolidated_must_fix.append(item)
        if review.get("direction_change_recommendation"):
            pending_direction_confirmations.append(
                {
                    "reviewer": review.get("reviewer", ""),
                    "recommendation": review.get("ask_user_before_changing_direction", []),
                    "why": review.get("summary", ""),
                    "requires_user_confirmation": True,
                }
            )

    return {
        "review_bundle_id": f"plan-reviews:{tier}",
        "governance_tier": tier,
        "active_reviewers": active_reviewers,
        "reviews": reviews,
        "must_fix_before_execute": consolidated_must_fix,
        "pending_direction_confirmations": pending_direction_confirmations,
        "selected_plan_fit": selected_fit,
        "alternative_plan_ids": alternatives,
    }


def _derive_operating_discipline(
    goal: str,
    intent: Dict[str, object],
    governance: Dict[str, object],
    coding_methodology: Dict[str, object],
    mission_profile: Dict[str, object],
) -> Dict[str, object]:
    """
    中文注解：
    - 功能：把分散的行为纪律汇总为统一 operating discipline。
    - 设计意图：下游 agent/runtime/doctor 读取一份纪律对象就能知道“应该怎么做”，而不是到处拼 coding_methodology / guardian / doctor hints。
    """
    tier = str(governance.get("tier", "standard")).strip() or "standard"
    method = str(coding_methodology.get("methodology", "jinclaw-native")).strip() or "jinclaw-native"
    promoted_operator_rules = load_operator_discipline_rules()

    def _rule(key: str, section: str, statement: str, enabled: bool = True, reason: str = "") -> Dict[str, object]:
        return {
            "key": key,
            "section": section,
            "enabled": bool(enabled),
            "statement": statement,
            "reason": reason,
        }

    principles = [
        _rule("search_before_build", "principles", "先搜 Layer 1 tried-and-true，再看 Layer 2 new-and-popular，最后用 Layer 3 first-principles 做独立判断。", True, "吸收 gstack 的 layered knowledge 与 search-before-build 思路。"),
        _rule("user_sovereignty", "principles", "AI 的建议永远只是 recommendation，不是替用户做战略决定。", True, "把用户主权提升为一级治理原则。"),
        _rule("must_produce_evidence", "principles", "任何完成声明都必须绑定可追溯证据，而不是口头叙述。", True, "保持 evidence-over-narration。"),
        _rule("prefer_complete_solution_for_boiled_lake", "principles", "在 AI 把边际成本压低的情况下，优先做完整闭环而不是廉价 shortcut。", tier in {"reviewed", "mission", "plan_only"}, "吸收 gstack 的 Boil the Lake 完整性交付观。"),
        _rule("fail_closed_on_uncertain_permissions", "principles", "权限、来源、执行边界不确定时默认不放行。", True, "保持 fail-closed 倾向。"),
    ]
    execution_rules = [
        _rule("deep_research_before_ask_user", "execution_rules", "能通过本地/外部证据自行澄清的问题先研究，再 ask user。", True, "减少把可自证问题反甩给用户。"),
        _rule("self_review_before_done", "execution_rules", "结束前先做自查：遗漏文件、未覆盖风险、未验证路径、与既有模式不一致。", True, "吸收 gstack-lite 的自审纪律。"),
        _rule("report_unresolved_risks", "execution_rules", "即使任务完成，也必须显式报告未解决风险与后续建议。", True, "避免假完结。"),
    ]
    escalation_rules = [
        _rule("ask_user_when_direction_changes", "escalation_rules", "当建议改变用户显式方向、扩大/缩小 scope、切换战略路线时，必须 ask user。", True, "落实 user sovereignty。"),
        _rule("deep_research_then_ask_user", "escalation_rules", "卡住时优先深挖证据，再把真正需要人判断的部分呈给用户。", True, "避免低质量升级。"),
    ]
    completion_rules = [
        _rule(
            "continue_until_goal_fully_satisfied",
            "completion_rules",
            "默认停点不是一轮 PR 或一次局部修补完成，而是最终目标真正达到、或明确撞上治理/权限边界。未达成前继续优化，不把里程碑误当终点。",
            True,
            "把“目标闭环优先于轮次闭环”固化为基础执行纪律，避免把单轮 PR 误当自然停点。",
        ),
        _rule("must_write_postmortem_before_close", "completion_rules", "关闭任务前必须写 postmortem / reusable rule。", True, "保持 learn 阶段的闭环价值。"),
        _rule("must_reference_protocol_pack", "completion_rules", "执行与回报都应遵守 protocol pack，而不是随意跳流程。", True, "让协议包成为稳定消费入口。"),
    ]
    for promoted_rule in promoted_operator_rules:
        section = str(promoted_rule.get("section", "")).strip() or "execution_rules"
        target = {
            "principles": principles,
            "execution_rules": execution_rules,
            "escalation_rules": escalation_rules,
            "completion_rules": completion_rules,
        }.get(section, execution_rules)
        target.append(
            _rule(
                str(promoted_rule.get("discipline_key", "")).strip(),
                section,
                str(promoted_rule.get("statement", "")).strip(),
                bool(promoted_rule.get("enabled", True)),
                str(promoted_rule.get("reason", "")).strip() or "来自 durable operator discipline。",
            )
        )
    all_rules = principles + execution_rules + escalation_rules + completion_rules
    rule_lookup = {str(item.get("key", "")).strip(): item for item in all_rules}
    continue_until_goal_fully_satisfied = bool(
        (rule_lookup.get("continue_until_goal_fully_satisfied", {}) or {}).get("enabled")
    )
    return {
        "discipline_id": "jinclaw-operating-discipline-v2",
        "governance_tier": tier,
        "coding_methodology": method,
        "mission_profile_id": mission_profile.get("profile_id", ""),
        "promoted_operator_rule_count": len(promoted_operator_rules),
        "promoted_operator_rule_keys": [
            str(item.get("discipline_key", "")).strip()
            for item in promoted_operator_rules
            if str(item.get("discipline_key", "")).strip()
        ],
        "principles": principles,
        "execution_rules": execution_rules,
        "escalation_rules": escalation_rules,
        "completion_rules": completion_rules,
        "rule_lookup": rule_lookup,
        "enabled_rule_keys": [key for key, item in rule_lookup.items() if item.get("enabled")],
        "completion_guard": {
            "default_stop_condition": "goal_complete_or_boundary" if continue_until_goal_fully_satisfied else "stage_complete",
            "requires_goal_completion_proof": continue_until_goal_fully_satisfied,
            "treat_pr_as_milestone_only": continue_until_goal_fully_satisfied,
            "treat_round_as_milestone_only": continue_until_goal_fully_satisfied,
            "non_terminal_milestones": [
                "round_completed",
                "tests_green",
                "commit_pushed",
                "pr_opened",
                "partial_fix_validated",
            ],
            "terminal_boundaries": [
                "governance_boundary",
                "permission_boundary",
                "safety_boundary",
            ],
        },
    }


def _derive_knowledge_basis(
    intent: Dict[str, object],
    selected_plan: Dict[str, object],
    scout: Dict[str, object],
    fetch_route: Dict[str, object],
) -> Dict[str, object]:
    """
    中文注解：
    - 功能：把搜索与判断升级成分层知识模型。
    - 设计意图：不是所有搜索结果都同权；需要明确哪些属于成熟共识、哪些只是近期流行、哪些是当前任务的 first-principles 推理。
    """
    layer1_candidates: List[str] = []
    layer2_candidates: List[str] = []
    layer3_observations: List[str] = []
    eureka_moments: List[str] = []
    known_uncertainties: List[str] = []
    trusted_source_types = [str(item) for item in scout.get("trusted_source_types", []) if str(item).strip()]
    route_ladder = [str(item) for item in fetch_route.get("route_ladder", []) if str(item).strip()]
    plan_id = str(selected_plan.get("plan_id", "")).strip()

    if trusted_source_types:
        layer1_candidates.extend(trusted_source_types)
    if route_ladder:
        layer1_candidates.append(f"preferred_fetch_ladder:{'->'.join(route_ladder[:4])}")
    if not selected_plan.get("external_actions"):
        layer1_candidates.append("existing_local_capabilities")
    if scout.get("queries"):
        layer2_candidates.extend([str(item) for item in scout.get("queries", [])[:4] if str(item).strip()])

    if plan_id == "in_house_capability_rebuild":
        observation = "本任务更适合抽取外部模式后在本地重建，而不是直接信任第三方 artifact。"
        layer3_observations.append(observation)
        eureka_moments.append("useful_external_pattern_without_external_trust")
    elif plan_id == "browser_evidence":
        layer3_observations.append("静态信息不足以支撑判断时，用受控浏览器收集证据比直接猜测更可靠。")
    else:
        layer3_observations.append("优先从现有本地能力与官方来源出发，再决定是否需要更高风险扩展。")

    if "human_checkpoint" in route_ladder:
        known_uncertainties.append("当前 fetch ladder 保留 human checkpoint，说明仍存在需要人工确认的风险面。")
    if "authorized_session" in route_ladder:
        known_uncertainties.append("当前任务可能需要授权会话，说明公开证据链可能不足。")
    if intent.get("requires_external_information") and not scout.get("queries"):
        known_uncertainties.append("任务依赖外部信息，但当前 scout 查询仍然偏少。")

    recommended_basis = "layer1+layer3"
    if intent.get("requires_external_information") and layer2_candidates:
        recommended_basis = "layer1+layer2+layer3"

    return {
        "layer1_candidates": layer1_candidates,
        "layer2_candidates": layer2_candidates,
        "layer3_observations": layer3_observations,
        "recommended_basis": recommended_basis,
        "eureka_moments": eureka_moments,
        "known_uncertainties": known_uncertainties,
    }


def _derive_verification_guidance(
    stage_name: str,
    verifier: Dict[str, object],
    governance: Dict[str, object],
) -> Dict[str, object]:
    """
    中文注解：
    - 功能：把 verifier 从“pass/fail 检查器”升级成“失败后怎么继续”的 remediation 指南。
    - 设计意图：下游 agent 不只知道“失败了”，还知道合法下一步是补 artifact、重跑 verify、replan 还是 ask user。
    """
    checks = list((verifier or {}).get("checks", []) or [])
    types = {str(item.get("type", "")).strip() for item in checks if isinstance(item, dict)}
    tier = str(governance.get("tier", "standard")).strip() or "standard"
    failure_modes: List[Dict[str, object]] = []

    def _add_failure_mode(code: str, when: str, actions: List[str], *, can_retry: bool = True, should_replan: bool = False, requires_human: bool = False) -> None:
        failure_modes.append(
            {
                "code": code,
                "when": when,
                "recommended_next_actions": actions,
                "can_retry": can_retry,
                "should_replan": should_replan,
                "requires_human_decision": requires_human,
            }
        )

    if "task_state_metadata_equals" in types or "task_state_metadata_nonempty" in types:
        _add_failure_mode(
            "business_proof_missing",
            "业务级 proof / proof_summary / user-visible confirmation 缺失",
            ["补写或重采 business proof", "重新 snapshot 真实结果", "重跑 verify"],
            can_retry=True,
            should_replan=False,
        )
    if "task_stage_artifacts_ready" in types:
        _add_failure_mode(
            "stage_artifacts_missing",
            "阶段 required artifacts 或 summary 没写完整",
            ["补写 stage artifacts", "补齐 summary/evidence refs", "重新运行当前 stage verifier"],
            can_retry=True,
            should_replan=False,
        )
    if "task_milestones_complete" in types:
        _add_failure_mode(
            "milestone_incomplete",
            "required execute milestones 尚未完成",
            ["回到 execute 补齐未完成 milestone", "更新 milestone progress", "完成后重新进入 verify"],
            can_retry=True,
            should_replan=False,
        )
    if "task_liveness_ok" in types:
        _add_failure_mode(
            "liveness_insufficient",
            "任务缺少真实推进证据，存在假等待/假忙风险",
            ["补充真实执行证据", "修复等待状态", "必要时触发 targeted debug"],
            can_retry=True,
            should_replan=tier in {"reviewed", "mission"},
        )
    if "task_conformance_ok" in types:
        _add_failure_mode(
            "governance_conformance_violation",
            "阶段推进顺序或严格推进约束被破坏",
            ["回滚到合法阶段", "修复 contract/state 漂移", "必要时重选计划"],
            can_retry=False,
            should_replan=tier in {"reviewed", "mission"},
        )
    if "crawler_report_complete" in types:
        _add_failure_mode(
            "crawler_report_missing",
            "crawler 运行缺少结构化报告",
            ["重写 crawler report", "重新同步 output artifacts", "补齐后重跑 verify"],
            can_retry=True,
            should_replan=False,
        )
    if "acquisition_summary_complete" in types:
        _add_failure_mode(
            "acquisition_summary_missing",
            "缺少 acquisition execution summary，无法解释计划路线与实际执行结果",
            ["补写 acquisition summary", "同步 planned-vs-executed route gaps", "补齐后重跑 verify"],
            can_retry=True,
            should_replan=False,
        )
    if "command_exit_zero" in types:
        _add_failure_mode(
            "verification_command_failed",
            "命令级 verifier 失败",
            ["检查命令前提条件", "修复路径/依赖/输出文件", "命令通过后重跑 verifier"],
            can_retry=True,
            should_replan=False,
        )

    recommended_next_actions: List[str] = []
    for item in failure_modes:
        for action in item.get("recommended_next_actions", []):
            if action not in recommended_next_actions:
                recommended_next_actions.append(action)

    return {
        "stage_name": stage_name,
        "verifier_type": str((verifier or {}).get("type", "none")).strip() or "none",
        "failure_modes": failure_modes,
        "recommended_next_actions": recommended_next_actions,
        "can_retry": any(bool(item.get("can_retry")) for item in failure_modes) if failure_modes else False,
        "should_replan": any(bool(item.get("should_replan")) for item in failure_modes),
        "requires_human_decision": any(bool(item.get("requires_human_decision")) for item in failure_modes),
    }


def _derive_protocol_pack(
    governance: Dict[str, object],
    operating_discipline: Dict[str, object],
    plan_reviews: Dict[str, object],
) -> Dict[str, object]:
    """
    中文注解：
    - 功能：为不同治理强度任务生成 protocol pack。
    - 设计意图：spawned session / runtime 不再靠隐式经验判断强度，而是读一个显式协议包。
    """
    tier = str(governance.get("tier", "standard")).strip() or "standard"
    policy = governance.get("policy", {}) or {}
    pack_id = {
        "lite": "orchestrator-lite",
        "standard": "orchestrator-standard",
        "reviewed": "orchestrator-full",
        "mission": "orchestrator-mission",
        "plan_only": "orchestrator-plan-only",
    }.get(tier, "orchestrator-standard")
    stage_order = ["understand", "plan", "verify", "learn"] if not policy.get("allow_execute_stage", True) else ["understand", "plan", "execute", "verify", "learn"]
    required_artifacts = ["mission_brief", "review_bundle", "protocol_pack"]
    if policy.get("allow_execute_stage", True):
        required_artifacts.append("delivery_evidence")
    if policy.get("require_postmortem"):
        required_artifacts.append("postmortem")
    if tier in {"reviewed", "mission"}:
        required_artifacts.append("test_signal")
    return build_protocol_pack_schema(
        pack_id,
        tier=tier,
        scenario={
            "lite": "single-step-or-small-patch",
            "standard": "ordinary-multi-step-task",
            "reviewed": "multi-perspective-reviewed-delivery",
            "mission": "full-complex-mission-delivery",
            "plan_only": "planning-without-implementation",
        }.get(tier, "ordinary-multi-step-task"),
        stage_order=stage_order,
        must_follow_rules=list((operating_discipline or {}).get("enabled_rule_keys", [])),
        required_artifacts=required_artifacts,
        optional_artifacts=["remaining_risks", "implementation_delta", "verification_report"],
        skippable_stages=[] if policy.get("allow_execute_stage", True) else ["execute"],
        methodology_prompt_profile=str((operating_discipline or {}).get("coding_methodology", "jinclaw-native")),
        review_bundle_required=list(plan_reviews.get("active_reviewers", [])),
    )


def _derive_readiness_dashboard(
    task_id: str,
    stages: List[Dict[str, object]],
    governance: Dict[str, object],
    plan_reviews: Dict[str, object],
) -> Dict[str, object]:
    """
    中文注解：
    - 功能：生成 contract 级 readiness dashboard。
    - 设计意图：让系统能结构化解释“为什么当前还不能进入下一阶段”，而不是只在运行时靠一句 blocker 文本。
    """
    policy = governance.get("policy", {}) or {}
    pending_decisions = list(plan_reviews.get("pending_direction_confirmations", []) or [])
    must_fix = [str(item).strip() for item in (plan_reviews.get("must_fix_before_execute", []) or []) if str(item).strip()]
    missing_artifacts: List[str] = []
    for stage in stages:
        stage_policy = dict(stage.get("execution_policy", {}) or {})
        missing_artifacts.extend([str(item) for item in stage_policy.get("required_artifact_keys", []) if str(item).strip()])
    missing_artifacts = sorted(dict.fromkeys(missing_artifacts))
    blocking_items: List[Dict[str, object]] = [
        {"type": "must_fix_before_execute", "item": item, "stage": "plan"}
        for item in must_fix
    ]
    blocking_items.extend(
        {
            "type": "strategic_direction_confirmation",
            "item": " / ".join(item.get("recommendation", []) or []),
            "stage": "plan",
            "reviewer": item.get("reviewer", ""),
        }
        for item in pending_decisions
    )
    plan_ready = not must_fix and not pending_decisions
    execute_applicable = bool(policy.get("allow_execute_stage", True))
    execute_ready = execute_applicable and plan_ready
    verify_ready = plan_ready
    release_ready = not policy.get("require_postmortem", True) and plan_ready
    return build_readiness_dashboard_schema(
        plan_readiness={
            "ready": plan_ready,
            "required_reviews": plan_reviews.get("active_reviewers", []),
            "must_fix_before_execute": must_fix,
            "pending_direction_confirmations": pending_decisions,
        },
        execute_readiness={
            "applicable": execute_applicable,
            "ready": execute_ready,
            "blocking_items": must_fix + ["pending_direction_confirmations"] if pending_decisions else must_fix,
            "required_artifacts": missing_artifacts,
        },
        verify_readiness={
            "applicable": True,
            "ready": verify_ready,
            "requires_runtime_evidence": True,
            "required_artifacts": missing_artifacts,
        },
        release_readiness={
            "applicable": True,
            "ready": release_ready,
            "requires_postmortem": bool(policy.get("require_postmortem", True)),
            "requires_full_verifier": bool(policy.get("require_full_verifier", False)),
        },
        blocking_items=blocking_items,
        missing_artifacts=missing_artifacts,
        pending_decisions=pending_decisions,
    )


def _augment_approval_with_direction_confirmations(
    task_id: str,
    approval: Dict[str, object],
    plan_reviews: Dict[str, object],
    governance: Dict[str, object],
) -> Dict[str, object]:
    """
    中文注解：
    - 功能：把战略性改向确认注入 approval payload。
    - 设计意图：操作性审批和战略性改向确认都进入同一治理面，但要显式区分类型，且改向只能 recommendation，不能自动执行。
    """
    policy = governance.get("policy", {}) or {}
    if not bool(policy.get("user_confirmation_for_direction_change", True)):
        return approval
    pending_confirmations = list(plan_reviews.get("pending_direction_confirmations", []) or [])
    if not pending_confirmations:
        return approval
    payload = json.loads(json.dumps(approval, ensure_ascii=False))
    decisions = dict(payload.get("decisions", {}) or {})
    pending = list(payload.get("pending", []) or [])
    existing_items = {
        str(item.get("reviewer", "")) + "::" + " | ".join(item.get("recommendation", []) or [])
        for item in payload.get("pending_direction_confirmations", []) or []
        if isinstance(item, dict)
    }
    records: List[Dict[str, object]] = []
    next_index = len([key for key in decisions if ":direction_change:" in key]) + 1
    for item in pending_confirmations:
        fingerprint = str(item.get("reviewer", "")) + "::" + " | ".join(item.get("recommendation", []) or [])
        if fingerprint in existing_items:
            continue
        approval_id = f"{task_id}:direction_change:{next_index}"
        next_index += 1
        recommendation = [str(row) for row in item.get("recommendation", []) if str(row).strip()]
        record = {
            "id": approval_id,
            "status": "pending",
            "type": "strategic_direction_change",
            "reason": str(item.get("why", "")).strip(),
            "risk": "strategic",
            "approval_mode": "user_confirmation",
            "reviewed_at": _utc_now_iso(),
            "direction_change_recommendation": True,
            "requires_user_confirmation": True,
            "recommendation": recommendation,
            "reviewer": str(item.get("reviewer", "")).strip(),
        }
        decisions[approval_id] = record
        pending.append(approval_id)
        records.append(record)
    if not records:
        return payload
    payload["decisions"] = decisions
    payload["pending"] = sorted(dict.fromkeys(pending))
    payload["pending_direction_confirmations"] = list(payload.get("pending_direction_confirmations", []) or []) + records
    payload["direction_change_recommendation"] = True
    payload["requires_user_confirmation"] = True
    payload["governance_type"] = "approval+direction"
    _write_json(APPROVALS_ROOT / f"{task_id}.json", payload)
    return payload


def _build_stage(
    *,
    name: str,
    goal: str,
    expected_output: str,
    acceptance_check: str,
    execution_policy: Dict[str, object],
    verifier: Dict[str, object] | None,
    governance: Dict[str, object],
) -> Dict[str, object]:
    verifier_payload = verifier or {}
    return build_stage_contract_schema(
        name=name,
        goal=goal,
        expected_output=expected_output,
        acceptance_check=acceptance_check,
        verifier=verifier_payload,
        execution_policy=execution_policy,
        verification_guidance=_derive_verification_guidance(name, verifier_payload, governance),
    )


def _derive_stage_contracts(task_id: str, blueprint: Dict[str, object]) -> List[Dict[str, object]]:
    """
    中文注解：
    - 功能：把高层 blueprint 落成 runtime 真正使用的阶段合同列表。
    - 关键职责：
      - 给每个阶段定义 goal / expected_output / acceptance_check
      - 决定 execute / verify 阶段是否需要强 verifier
      - 针对 mission profile（例如 neosgo lead engine）覆盖默认阶段模板
    - 调用关系：build_control_center_package 会在最后调用这里；manager 创建 task 时写入的 `contract.stages` 就来自这里。
    """
    intent = blueprint["intent"]
    selected_plan = blueprint["selected_plan"]
    approval = blueprint["approval"]
    crawler = blueprint.get("crawler", {}) or {}
    crawler_enabled = bool(crawler.get("enabled"))
    mission_profile = blueprint.get("mission_profile", {}) or {}
    governance = blueprint.get("governance", {}) or {}
    policy = governance.get("policy", {}) or _derive_governance_policy(str(governance.get("tier", "standard")))
    strict_continuation_required = bool(blueprint.get("strict_continuation_required"))
    complex_task_controller = blueprint.get("complex_task_controller", {}) or {}
    plan_reviews = blueprint.get("plan_reviews", {}) or {}
    protocol_pack = blueprint.get("protocol_pack", {}) or {}
    acquisition_hand = blueprint.get("acquisition_hand", {}) or {}
    pending_approvals = approval.get("pending", [])
    require_business_proof = _requires_explicit_business_proof(intent, selected_plan)
    plan_only = not bool(policy.get("allow_execute_stage", True))

    execute_policy = {
        "approval_requirements": list((approval.get("decisions", {}) or {}).keys()),
        "approval_pending_ids": pending_approvals,
        "auto_complete_on_wait_ok": bool(policy.get("allow_execute_auto_complete", True)),
        "governance_tier": governance.get("tier", "standard"),
        "protocol_pack_id": protocol_pack.get("pack_id", ""),
        "must_fix_before_execute": list(plan_reviews.get("must_fix_before_execute", [])),
        "require_plan_reviews": bool(policy.get("require_plan_reviews", False)),
    }
    if strict_continuation_required:
        execute_policy["auto_complete_on_wait_ok"] = False
        execute_policy["completion_mode"] = "milestone_driven"
    verify_verifier = build_verifier_schema(
        "all",
        checks=[
            {"type": "command_exit_zero", "command": ["/bin/zsh", "-lc", "test -d /Users/mac_claw/.openclaw/workspace"]},
        ],
    )
    execute_verifier: Dict[str, object] = {}
    if require_business_proof:
        execute_policy["require_verifier_before_complete"] = True
        execute_verifier = _business_outcome_verifier(task_id)
        verify_verifier = _business_outcome_verifier(task_id)
    if crawler_enabled:
        crawler_checks = [
            {"type": "crawler_report_complete", "task_id": task_id},
            *([{"type": "acquisition_summary_complete", "task_id": task_id}] if acquisition_hand.get("enabled") else []),
            *_business_outcome_verifier(task_id).get("checks", []),
        ]
        existing_checks = list(verify_verifier.get("checks", []))
        verify_verifier = build_verifier_schema("all", checks=existing_checks + crawler_checks)

    if mission_profile.get("profile_id") == "neosgo_lead_engine":
        execute_policy["auto_complete_on_wait_ok"] = False
        verify_checks = [
            {"type": "file_exists", "path": str(Path("/Users/mac_claw/.openclaw/workspace/data/neosgo_leads.duckdb"))},
            {"type": "task_state_metadata_nonempty", "task_id": task_id, "field": "contract_metadata.control_center.mission_profile_id"},
            {"type": "task_milestones_complete", "task_id": task_id},
            {"type": "task_liveness_ok", "task_id": task_id},
            {"type": "task_conformance_ok", "task_id": task_id},
        ]
        return [
            _build_stage(
                name="understand",
                goal="Inventory the local Neosgo lead-engine assets: current DuckDB state, download archives, prior reports, and execution boundaries.",
                expected_output="lead-engine inventory and environment brief",
                acceptance_check="inventory, counts, and source locations are recorded into task metadata and mission summary",
                execution_policy={"auto_complete_on_wait_ok": True},
                verifier={},
                governance=governance,
            ),
            _build_stage(
                name="plan",
                goal="Translate the ideal plan into an executable phased root mission for data ingress, normalization, prospect scoring, strategy, outreach, and daily reporting.",
                expected_output="phased lead-engine execution contract and phase order",
                acceptance_check="phase sequence, next deliverables, and reporting cadence are recorded clearly",
                execution_policy={"auto_complete_on_wait_ok": True},
                verifier={},
                governance=governance,
            ),
            _build_stage(
                name="execute",
                goal="Continuously execute the Neosgo lead-engine phases in order: import remaining archives, normalize and deduplicate records, derive prospect scoring logic and personas, produce marketing/outreach strategy, and keep a daily report loop alive.",
                expected_output="observable progress artifacts such as database growth, imported file inventory, reports, scoring logic, and outreach artifacts",
                acceptance_check="the mission keeps making real progress or escalates a truthful blocker instead of silently waiting",
                execution_policy=execute_policy,
                verifier=build_verifier_schema(
                    "all",
                    checks=[
                        {"type": "file_exists", "path": str(Path("/Users/mac_claw/.openclaw/workspace/data/neosgo_leads.duckdb"))},
                        {"type": "file_exists", "path": str(mission_profile.get("ideal_plan_path", ""))},
                    ],
                ),
                governance=governance,
            ),
            _build_stage(
                name="verify",
                goal="Verify the lead-engine root mission still has a truthful active plan, a real data warehouse, and no silent waiting without liveness evidence.",
                expected_output="verification decision with waiting/run liveness and current phase evidence",
                acceptance_check="verification records the truthful task status and either confirms progress or escalates a concrete blocker",
                execution_policy={"auto_complete_on_wait_ok": False},
                verifier=build_verifier_schema("all", checks=verify_checks),
                governance=governance,
            ),
            _build_stage(
                name="learn",
                goal="Persist lead-engine lessons, scoring refinements, marketing improvements, and daily reporting guidance.",
                expected_output="updated learning artifacts, reusable lead-engine guidance, and a written postmortem",
                acceptance_check="learning artifacts, truthful progress summary, and postmortem are written",
                execution_policy={"auto_complete_on_wait_ok": True},
                verifier={},
                governance=governance,
            ),
        ]

    verify_checks = list(verify_verifier.get("checks", []))
    if strict_continuation_required:
        verify_checks.extend(
            [
                {"type": "task_milestones_complete", "task_id": task_id},
                {"type": "task_liveness_ok", "task_id": task_id},
                {"type": "task_conformance_ok", "task_id": task_id},
            ]
        )
        verify_verifier = build_verifier_schema("all", checks=verify_checks)

    common_policy: Dict[str, object] = {
        "governance_tier": governance.get("tier", "standard"),
        "protocol_pack_id": protocol_pack.get("pack_id", ""),
        "require_plan_reviews": bool(policy.get("require_plan_reviews", False)),
        "must_fix_before_execute": list(plan_reviews.get("must_fix_before_execute", [])),
        "acquisition_hand_enabled": bool(acquisition_hand.get("enabled")),
        "primary_acquisition_route": str(((acquisition_hand.get("summary", {}) or {}).get("primary_route", {}) or {}).get("route_id", "")).strip(),
        "validation_acquisition_routes": [str(item) for item in ((acquisition_hand.get("execution_strategy", {}) or {}).get("validation_route_ids", []) or []) if str(item).strip()],
    }

    stages: List[Dict[str, object]] = [
        _build_stage(
            name="understand",
            goal="Analyze the instruction, constraints, desired outcome, and security posture",
            expected_output="structured mission brief",
            acceptance_check="mission brief written into task metadata",
            execution_policy={**common_policy, "auto_complete_on_wait_ok": True},
            verifier={},
            governance=governance,
        ),
        _build_stage(
            name="plan",
            goal="Compare multiple safe execution plans and select the best approved path",
            expected_output="candidate plan set, chosen plan, role reviews, and protocol pack",
            acceptance_check="selected plan + role reviews + must-fix items recorded",
            execution_policy={**common_policy, "auto_complete_on_wait_ok": True},
            verifier={},
            governance=governance,
        ),
    ]

    if not plan_only:
        stages.append(
            _build_stage(
                name="execute",
                goal=f"Execute the selected plan safely: {selected_plan.get('summary', '')}",
                expected_output="real progress toward the user goal with evidence and acquisition artifacts when external data is required",
                acceptance_check="execution evidence recorded without violating security boundaries; acquisition route choice, provenance, and must-fix plan items must be cleared before execute can pass",
                execution_policy={**common_policy, **execute_policy},
                verifier=execute_verifier,
                governance=governance,
            )
        )
    stages.extend(
        [
            _build_stage(
                name="verify",
                goal="Verify the goal is actually satisfied and the path stayed within security policy" if not plan_only else "Verify the planning package is coherent, role-reviewed, and ready for later implementation without hidden blockers",
                expected_output="verification decision and evidence" if not plan_only else "planning verification decision and handoff digest",
                acceptance_check="verifier passes with business-level proof when required and no unresolved approval or security blockers remain" if not plan_only else "the reviewed plan, protocol pack, readiness dashboard, and unresolved decisions are all recorded truthfully",
                execution_policy={**common_policy, "auto_complete_on_wait_ok": False},
                verifier=verify_verifier,
                governance=governance,
            ),
            _build_stage(
                name="learn",
                goal="Persist lessons, promoted rules, reusable guidance, and a completion postmortem before closure" if not plan_only else "Persist planning lessons, reusable guidance, and next-step recommendations before closing the planning task",
                expected_output="updated learning artifacts, task summary, and written postmortem",
                acceptance_check="learning artifacts and postmortem are written successfully",
                execution_policy={**common_policy, "auto_complete_on_wait_ok": True},
                verifier={},
                governance=governance,
            ),
        ]
    )

    if not complex_task_controller.get("enabled"):
        return stages

    stage_gate_policy = complex_task_controller.get("stage_gate_policy", {}) or {}
    enriched: List[Dict[str, object]] = []
    for stage in stages:
        stage_name = str(stage.get("name", "")).strip()
        policy_payload = dict(stage.get("execution_policy", {}) or {})
        gate = dict(stage_gate_policy.get(stage_name, {}) or {})
        policy_payload["complex_task_controller"] = True
        policy_payload["require_stage_artifacts_before_complete"] = bool(policy.get("require_stage_artifacts", False))
        policy_payload["required_artifact_keys"] = list(gate.get("required_artifact_keys", []))
        policy_payload["require_summary_nonempty"] = bool(gate.get("require_summary_nonempty", True))
        if stage_name == "execute":
            policy_payload["require_evidence_refs_for_completion"] = bool(gate.get("require_evidence_refs", True))
            policy_payload["require_verifier_before_complete"] = True
        stage["execution_policy"] = policy_payload
        if policy.get("require_stage_artifacts") and stage_name in {"understand", "plan", "execute"}:
            stage["verifier"] = build_verifier_schema("task_stage_artifacts_ready", task_id=task_id, stage=stage_name)
        elif stage_name == "verify":
            existing_checks = list(((stage.get("verifier", {}) or {}).get("checks", []) or []))
            artifact_checks = [
                {"type": "task_stage_artifacts_ready", "task_id": task_id, "stage": "understand"},
                {"type": "task_stage_artifacts_ready", "task_id": task_id, "stage": "plan"},
            ]
            if not plan_only:
                artifact_checks.append({"type": "task_stage_artifacts_ready", "task_id": task_id, "stage": "execute"})
            stage["verifier"] = build_verifier_schema("all", checks=[*existing_checks, *artifact_checks])
        stage["verification_guidance"] = _derive_verification_guidance(stage_name, stage.get("verifier", {}) or {}, governance)
        enriched.append(stage)
    return enriched


def build_control_center_package(task_id: str, goal: str, *, source: str = "manual", inherited_intent: Dict[str, object] | None = None) -> Dict[str, object]:
    """
    中文注解：
    - 功能：构建一个完整的 control center package，供后续创建 TaskContract 使用。
    - 输出内容包括：
      - intent / inherited_intent
      - candidate_plans / selected_plan
      - approval / topology / htn / fractal / stpa
      - business_verification_requirements
      - metadata 和最终 stage contracts
    - 调用关系：brain_router._build_task 和 task_ingress 都会走到这里；这里是“自然语言目标 -> 结构化 contract 原材料”的核心汇编点。
    """
    raw_intent = analyze_intent(goal, source=source)
    intent = _merge_inherited_intent(raw_intent, inherited_intent)
    mission_profile = detect_root_mission_profile(goal, task_id=task_id, intent=intent)
    coding_methodology = _derive_coding_methodology(intent)
    governance_tier = _derive_governance_tier(goal, intent, mission_profile, coding_methodology)
    governance = {
        **governance_tier,
        "policy": _derive_governance_policy(str(governance_tier.get("tier", "standard"))),
    }
    if mission_profile.get("matched"):
        intent["done_definition"] = str(mission_profile.get("done_definition", intent.get("done_definition", "")))
    if str(governance.get("tier", "")).strip() == "plan_only":
        intent["done_definition"] = "Plan reviewed, handoff package recorded, unresolved decisions documented, and no implementation executed"

    capabilities = build_capability_registry()
    blueprint = build_workflow_blueprint(intent, capabilities)
    provisional_plan = blueprint.get("selected_plan", {}) or {}
    domain_profile = build_domain_profile(task_id, intent)
    challenge = classify_challenge(task_id, [], {"status": "planning", "current_stage": "understand"})
    provisional_fetch_route = build_fetch_route(task_id, intent, provisional_plan, domain_profile, challenge)
    provisional_scout = build_resource_scout_brief(intent, provisional_plan, domain_profile, provisional_fetch_route)
    provisional_knowledge_basis = _derive_knowledge_basis(intent, provisional_plan, provisional_scout, provisional_fetch_route)
    judgment = judge_proposals(intent, capabilities, blueprint["candidate_plans"], knowledge_basis=provisional_knowledge_basis)
    tool_scores = score_external_options(task_id, intent, blueprint["candidate_plans"], capabilities)
    reselection = reselect_plan(task_id, intent, blueprint["candidate_plans"], judgment, tool_scores)
    selected_plan = reselection["final_selected_plan"]
    scored_by_id = {str(item.get("plan_id", "")): item for item in judgment.get("scores", [])}
    judgment["final_selected_plan"] = selected_plan
    judgment["final_selected_score"] = scored_by_id.get(str(selected_plan.get("plan_id", "")), judgment.get("selected_score", {}))

    approval = review_plan(task_id, selected_plan)
    plan_reviews = _derive_plan_reviews(intent, blueprint["candidate_plans"], selected_plan, governance)
    approval = _augment_approval_with_direction_confirmations(task_id, approval, plan_reviews, governance)
    operating_discipline = _derive_operating_discipline(goal, intent, governance, coding_methodology, mission_profile)
    goal_guardian = _derive_goal_guardian(goal, intent, mission_profile, coding_methodology, governance, operating_discipline)
    complex_task_controller = _derive_complex_task_controller(goal, intent, mission_profile, coding_methodology, governance)
    doctor_strategy_hints = load_doctor_strategy_rules()[:8]
    strict_continuation_required = _goal_requires_strict_continuation(goal, intent, mission_profile, governance=governance)
    task_milestones = _derive_task_milestones(task_id, goal, intent, mission_profile, governance=governance)

    tool_score_map = {str(item.get("plan_id", "")): item for item in tool_scores.get("scores", [])}
    adoption_flow = build_adoption_flow(task_id, selected_plan, approval, tool_score_map.get(str(selected_plan.get("plan_id", "")), {}))
    authorized_session = build_authorized_session_plan(task_id, intent, challenge)
    human_checkpoint = build_human_checkpoint(task_id, challenge)
    if approval.get("pending_direction_confirmations"):
        human_checkpoint = {
            **human_checkpoint,
            "checkpoint_kinds": sorted(
                dict.fromkeys(list(human_checkpoint.get("checkpoint_kinds", []) or []) + ["strategic_direction_change"])
            ),
        }
    fetch_route = build_fetch_route(task_id, intent, selected_plan, domain_profile, challenge)
    crawler = build_crawler_plan(task_id, intent, selected_plan, domain_profile, fetch_route, challenge)
    business_verification_requirements = derive_business_verification_requirements(intent)
    scout = build_resource_scout_brief(intent, selected_plan, domain_profile, fetch_route)
    knowledge_basis = _derive_knowledge_basis(intent, selected_plan, scout, fetch_route)
    arbitration = arbitrate_solution_path(
        intent,
        selected_plan,
        approval,
        capabilities,
        knowledge_basis=knowledge_basis,
        plan_reviews=plan_reviews,
        governance=governance,
    )
    protocol_pack = _derive_protocol_pack(governance, operating_discipline, plan_reviews)
    acquisition_hand = build_acquisition_hand(
        task_id,
        goal,
        intent,
        governance,
        selected_plan,
        challenge,
        fetch_route,
        crawler,
        knowledge_basis,
        protocol_pack,
        capabilities,
    )
    topology = build_topology(intent, selected_plan)
    fractal = build_fractal_loops(intent, selected_plan, topology)
    htn = build_htn_tree(intent, selected_plan, topology, fractal)
    initial_htn_focus = select_htn_focus(htn, "understand", 0)
    stpa = audit_mission(intent, selected_plan, topology, approval)
    initial_bdi = build_bdi_state(
        intent,
        selected_plan,
        approval,
        {"current_stage": "understand", "status": "planning", "blockers": []},
        initial_htn_focus,
        arbitration,
    )
    stages = _derive_stage_contracts(
        task_id,
        {
            **blueprint,
            "approval": approval,
            "intent": intent,
            "selected_plan": selected_plan,
            "mission_profile": mission_profile,
            "strict_continuation_required": strict_continuation_required,
            "crawler": crawler,
            "complex_task_controller": complex_task_controller,
            "governance": governance,
            "plan_reviews": plan_reviews,
            "protocol_pack": protocol_pack,
            "acquisition_hand": acquisition_hand,
        },
    )
    readiness_dashboard = _derive_readiness_dashboard(task_id, stages, governance, plan_reviews)
    mission = {
        "task_id": task_id,
        "created_at": _utc_now_iso(),
        "intent": intent,
        "capabilities": capabilities,
        "candidate_plans": blueprint["candidate_plans"],
        "selected_plan": selected_plan,
        "proposal_judgment": judgment,
        "tool_scores": tool_scores,
        "reselection": reselection,
        "topology": topology,
        "fractal_loops": fractal,
        "htn": htn,
        "initial_bdi": initial_bdi,
        "stpa": stpa,
        "approval": approval,
        "domain_profile": domain_profile,
        "challenge": challenge,
        "authorized_session": authorized_session,
        "human_checkpoint": human_checkpoint,
        "fetch_route": fetch_route,
        "crawler": crawler,
        "acquisition_hand": acquisition_hand,
        "business_verification_requirements": business_verification_requirements,
        "resource_scout": scout,
        "knowledge_basis": knowledge_basis,
        "arbitration": arbitration,
        "adoption_flow": adoption_flow,
        "mission_profile": mission_profile,
        "coding_methodology": coding_methodology,
        "goal_guardian": goal_guardian,
        "complex_task_controller": complex_task_controller,
        "doctor_strategy_hints": doctor_strategy_hints,
        "strict_continuation_required": strict_continuation_required,
        "task_milestones": task_milestones,
        "governance": governance,
        "plan_reviews": plan_reviews,
        "operating_discipline": operating_discipline,
        "protocol_pack": protocol_pack,
        "readiness_dashboard": readiness_dashboard,
    }
    should_clone_capability = selected_plan.get("plan_id") == "in_house_capability_rebuild"
    if should_clone_capability:
        clone_event = publish_event("capability.clone_requested", {"task_id": task_id, "mission": mission})
        mission["capability_clone"] = clone_event.get("emitted_hooks", [{}])[0].get("clone", {}) if clone_event.get("emitted_hooks") else {}
    _write_json(MISSIONS_ROOT / f"{task_id}.json", mission)
    publish_event("mission.built", {"task_id": task_id, "mission": mission})
    if reselection.get("switched"):
        publish_event("plan.reselected", {"task_id": task_id, "mission": mission, "reselection": reselection})
    metadata = {
        "control_center": {
            "mission_path": str(MISSIONS_ROOT / f"{task_id}.json"),
            "raw_intent": raw_intent,
            "inherited_intent": inherited_intent or {},
            "intent": intent,
            "candidate_plans": blueprint["candidate_plans"],
            "selected_plan": selected_plan,
            "proposal_judgment": judgment,
            "tool_scores": tool_scores,
            "reselection": reselection,
            "capabilities_snapshot": blueprint["capabilities_snapshot"],
            "topology": topology,
            "fractal_loops": fractal,
            "htn": htn,
            "initial_bdi": initial_bdi,
            "stpa": stpa,
            "approval": approval,
            "domain_profile": domain_profile,
            "challenge": challenge,
            "authorized_session": authorized_session,
            "human_checkpoint": human_checkpoint,
            "fetch_route": fetch_route,
            "crawler": crawler,
            "acquisition_hand": acquisition_hand,
            "business_verification_requirements": business_verification_requirements,
            "strict_continuation_required": strict_continuation_required,
            "task_milestones": task_milestones,
            "resource_scout": scout,
            "knowledge_basis": knowledge_basis,
            "arbitration": arbitration,
            "adoption_flow": adoption_flow,
            "capability_clone": mission.get("capability_clone", {}),
            "mission_profile_id": mission_profile.get("profile_id", ""),
            "mission_profile": mission_profile,
            "coding_methodology": coding_methodology,
            "goal_guardian": goal_guardian,
            "complex_task_controller": complex_task_controller,
            "doctor_strategy_hints": doctor_strategy_hints,
            "governance": governance,
            "plan_reviews": plan_reviews,
            "operating_discipline": operating_discipline,
            "protocol_pack": protocol_pack,
            "readiness_dashboard": readiness_dashboard,
        },
        "approval": approval,
        "security": {
            "principle": "solve_by_all_reasonable_means_without_crossing_security_boundaries",
            "pending_approvals": approval.get("pending", []),
        },
        "created_by": source,
    }
    return {
        "task_id": task_id,
        "goal": goal,
        "done_definition": intent["done_definition"],
        "hard_constraints": intent["hard_constraints"],
        "allowed_tools": _derive_allowed_tools({**blueprint, "intent": intent, "selected_plan": selected_plan, "acquisition_hand": acquisition_hand}),
        "stages": stages,
        "metadata": metadata,
        "mission_path": str(MISSIONS_ROOT / f"{task_id}.json"),
    }


def main() -> int:
    """
    中文注解：
    - 功能：实现 `main` 对应的处理逻辑。
    - 角色：属于本模块中的对外可见逻辑；私有函数通常服务同文件主流程，公共函数通常作为跨模块入口或能力接口。
    - 调用关系：建议结合本文件的模块说明、调用方以及同名相关辅助函数一起阅读。
    """
    import argparse

    parser = argparse.ArgumentParser(description="Build a single control-center task package from a goal")
    parser.add_argument("--task-id", required=True)
    parser.add_argument("--goal", required=True)
    parser.add_argument("--source", default="manual")
    args = parser.parse_args()
    print(json.dumps(build_control_center_package(args.task_id, args.goal, source=args.source), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
