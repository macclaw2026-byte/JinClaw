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
from typing import Dict, List

WORKSPACE_ROOT = Path("/Users/mac_claw/.openclaw/workspace")
GSTACK_LITE_PROMPT_PATH = WORKSPACE_ROOT / "compat/gstack/prompts/jinclaw-gstack-lite.md"
AUTONOMY_DIR = WORKSPACE_ROOT / "tools/openmoss/autonomy"
if str(AUTONOMY_DIR) not in sys.path:
    sys.path.insert(0, str(AUTONOMY_DIR))

from approval_gate import review_plan
from adoption_flow import build_adoption_flow
from adaptive_fetch_router import build_fetch_route
from bdi_state import build_bdi_state
from capability_registry import build_capability_registry
from challenge_classifier import classify_challenge
from authorized_session_manager import build_authorized_session_plan
from crawler_layer import build_crawler_plan
from domain_profile_store import build_domain_profile
from event_bus import publish_event
from external_tool_scorer import score_external_options
from fractal_decomposer import build_fractal_loops
from htn_planner import build_htn_tree, select_htn_focus
from intent_analyzer import analyze_intent
from paths import MISSIONS_ROOT
from plan_reselector import reselect_plan
from proposal_judge import judge_proposals
from human_checkpoint import build_human_checkpoint
from resource_scout import build_resource_scout_brief
from solution_arbitrator import arbitrate_solution_path
from stpa_auditor import audit_mission
from topology_mapper import build_topology
from workflow_planner import build_workflow_blueprint
from mission_profiles import detect_root_mission_profile
from promotion_engine import load_doctor_strategy_rules


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
    complex_tokens = (
        "app",
        "application",
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
        "交付",
        "完整",
    )
    if sum(1 for token in complex_tokens if token in normalized_goal) >= 2:
        return True
    if coding_methodology.get("enabled") and (
        {"code", "web", "data"} & task_types
        or any(token in normalized_goal for token in ("build", "implement", "develop", "integrate", "构建", "实现", "开发", "接入"))
    ):
        return True
    return False


def _derive_complex_task_controller(
    goal: str,
    intent: Dict[str, object],
    mission_profile: Dict[str, object],
    coding_methodology: Dict[str, object],
) -> Dict[str, object]:
    """
    中文注解：
    - 功能：生成复杂任务总控配置。
    - 设计意图：让复杂任务天然带上阶段产物、阶段验收、阶段测试和不达标不放行的强约束。
    """
    enabled = _is_complex_delivery_task(goal, intent, mission_profile, coding_methodology)
    return {
        "enabled": enabled,
        "controller": "complex_task_delivery_guard",
        "require_stage_artifacts": enabled,
        "require_stage_acceptance_before_progress": enabled,
        "require_verify_stage_report": enabled,
        "require_test_evidence_for_execute": enabled,
        "require_postmortem_before_completion": True,
        "strict_release_gate": enabled,
        "stage_gate_policy": {
            "understand": {
                "required_artifact_keys": ["mission_brief", "scope_constraints", "success_definition"],
                "require_summary_nonempty": True,
            },
            "plan": {
                "required_artifact_keys": ["execution_plan", "module_breakdown", "test_strategy"],
                "require_summary_nonempty": True,
            },
            "execute": {
                "required_artifact_keys": ["delivery_evidence", "implementation_delta", "test_signal"],
                "require_summary_nonempty": True,
                "require_evidence_refs": True,
            },
            "verify": {
                "required_artifact_keys": ["verification_report", "acceptance_decision", "remaining_risks"],
                "require_summary_nonempty": True,
            },
            "learn": {
                "required_artifact_keys": ["postmortem", "reusable_rule", "followup_risks"],
                "require_summary_nonempty": True,
            },
        },
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


def _load_gstack_lite_prompt() -> str:
    """
    中文注解：
    - 功能：读取 JinClaw 自有的 gstack-lite discipline prompt。
    - 设计意图：保持 prompt 为文件化资产，便于审阅、升级和替换。
    """
    if not GSTACK_LITE_PROMPT_PATH.exists():
        return ""
    return GSTACK_LITE_PROMPT_PATH.read_text(encoding="utf-8")


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
    prompt_text = _load_gstack_lite_prompt()
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
    optimization_task = any(
        token in normalized_goal
        for token in ("optimize", "optimization", "improve", "stabilize", "refactor", "优化", "改进", "稳定", "重构", "升级")
    )
    strict_goal = _goal_requires_strict_continuation(goal, intent, mission_profile)
    return {
        "enabled": True,
        "guardian_process": "system_doctor",
        "verify_every_step": True,
        "strict_continuation_required": strict_goal,
        "require_postmortem_before_completion": True,
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
            "deep_research_first": True,
            "ask_user_when_human_decision_required": True,
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


def _goal_requires_strict_continuation(goal: str, intent: Dict[str, object], mission_profile: Dict[str, object]) -> bool:
    """
    中文注解：
    - 功能：判断某个 goal 是否属于“多步骤且不能宽松自动收口”的任务。
    - 作用：命中后会强制 execute 阶段进入 milestone 驱动模式，不再只因为一次 wait 成功就自动当成整段 execute 完成。
    """
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


def _derive_task_milestones(task_id: str, goal: str, intent: Dict[str, object], mission_profile: Dict[str, object]) -> List[Dict[str, object]]:
    """
    中文注解：
    - 功能：生成任务级 milestones。
    - 结构：默认包含阶段里程碑；如果是多步骤目标，还会额外生成 execute deliverables。
    """
    milestones: List[Dict[str, object]] = [
        {"id": "understand", "title": "完成理解与盘点", "stage": "understand", "required": True, "completion_mode": "stage_completion"},
        {"id": "plan", "title": "完成计划与方案选择", "stage": "plan", "required": True, "completion_mode": "stage_completion"},
        {"id": "verify", "title": "完成验证", "stage": "verify", "required": True, "completion_mode": "stage_completion"},
        {"id": "learn", "title": "完成学习收口", "stage": "learn", "required": True, "completion_mode": "stage_completion"},
    ]
    deliverables = _derive_execute_deliverables(goal) if _goal_requires_strict_continuation(goal, intent, mission_profile) else []
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
    return {
        "type": "all",
        "checks": [
            {"type": "task_state_metadata_equals", "task_id": task_id, "field": "business_outcome.goal_satisfied", "equals": True},
            {"type": "task_state_metadata_equals", "task_id": task_id, "field": "business_outcome.user_visible_result_confirmed", "equals": True},
            {"type": "task_state_metadata_nonempty", "task_id": task_id, "field": "business_outcome.proof_summary"},
        ],
    }


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
    strict_continuation_required = bool(blueprint.get("strict_continuation_required"))
    complex_task_controller = blueprint.get("complex_task_controller", {}) or {}
    pending_approvals = approval.get("pending", [])
    require_business_proof = _requires_explicit_business_proof(intent, selected_plan)
    execute_policy = {
        "approval_requirements": list(approval.get("decisions", {}).keys()),
        "approval_pending_ids": pending_approvals,
        "auto_complete_on_wait_ok": True,
    }
    if strict_continuation_required:
        execute_policy["auto_complete_on_wait_ok"] = False
        execute_policy["completion_mode"] = "milestone_driven"
    verify_verifier = {
        "type": "all",
        "checks": [
            {"type": "command_exit_zero", "command": ["/bin/zsh", "-lc", "test -d /Users/mac_claw/.openclaw/workspace"]},
        ],
    }
    execute_verifier: Dict[str, object] = {}
    if require_business_proof:
        execute_policy["require_verifier_before_complete"] = True
        execute_verifier = _business_outcome_verifier(task_id)
        verify_verifier = _business_outcome_verifier(task_id)
    if crawler_enabled:
        crawler_checks = [
            {"type": "crawler_report_complete", "task_id": task_id},
            *_business_outcome_verifier(task_id).get("checks", []),
        ]
        existing_checks = list(verify_verifier.get("checks", []))
        verify_verifier = {"type": "all", "checks": existing_checks + crawler_checks}
    # 命中 mission profile 时，优先使用为该 root mission 量身定制的阶段合同，
    # 而不是走通用五阶段模板。这样 runtime / doctor / verifier 在后面才能读到更贴近业务的目标。
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
            {
                "name": "understand",
                "goal": "Inventory the local Neosgo lead-engine assets: current DuckDB state, download archives, prior reports, and execution boundaries.",
                "expected_output": "lead-engine inventory and environment brief",
                "acceptance_check": "inventory, counts, and source locations are recorded into task metadata and mission summary",
                "execution_policy": {"auto_complete_on_wait_ok": True},
            },
            {
                "name": "plan",
                "goal": "Translate the ideal plan into an executable phased root mission for data ingress, normalization, prospect scoring, strategy, outreach, and daily reporting.",
                "expected_output": "phased lead-engine execution contract and phase order",
                "acceptance_check": "phase sequence, next deliverables, and reporting cadence are recorded clearly",
                "execution_policy": {"auto_complete_on_wait_ok": True},
            },
            {
                "name": "execute",
                "goal": (
                    "Continuously execute the Neosgo lead-engine phases in order: import remaining archives, normalize and deduplicate records, "
                    "derive prospect scoring logic and personas, produce marketing/outreach strategy, and keep a daily report loop alive."
                ),
                "expected_output": "observable progress artifacts such as database growth, imported file inventory, reports, scoring logic, and outreach artifacts",
                "acceptance_check": "the mission keeps making real progress or escalates a truthful blocker instead of silently waiting",
                "verifier": {
                    "type": "all",
                    "checks": [
                        {"type": "file_exists", "path": str(Path("/Users/mac_claw/.openclaw/workspace/data/neosgo_leads.duckdb"))},
                        {"type": "file_exists", "path": str(mission_profile.get("ideal_plan_path", ""))},
                    ],
                },
                "execution_policy": execute_policy,
            },
            {
                "name": "verify",
                "goal": "Verify the lead-engine root mission still has a truthful active plan, a real data warehouse, and no silent waiting without liveness evidence.",
                "expected_output": "verification decision with waiting/run liveness and current phase evidence",
                "acceptance_check": "verification records the truthful task status and either confirms progress or escalates a concrete blocker",
                "verifier": {
                    "type": "all",
                    "checks": verify_checks,
                },
                "execution_policy": {"auto_complete_on_wait_ok": False},
            },
            {
                "name": "learn",
                "goal": "Persist lead-engine lessons, scoring refinements, marketing improvements, and daily reporting guidance.",
                "expected_output": "updated learning artifacts, reusable lead-engine guidance, and a written postmortem",
                "acceptance_check": "learning artifacts, truthful progress summary, and postmortem are written",
                "execution_policy": {"auto_complete_on_wait_ok": True},
            },
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
        verify_verifier = {"type": "all", "checks": verify_checks}
    stages = [
        {
            "name": "understand",
            "goal": "Analyze the instruction, constraints, desired outcome, and security posture",
            "expected_output": "structured mission brief",
            "acceptance_check": "mission brief written into task metadata",
            "execution_policy": {"auto_complete_on_wait_ok": True},
        },
        {
            "name": "plan",
            "goal": "Compare multiple safe execution plans and select the best approved path",
            "expected_output": "candidate plan set and chosen plan",
            "acceptance_check": "selected plan recorded with alternatives",
            "execution_policy": {"auto_complete_on_wait_ok": True},
        },
        {
            "name": "execute",
            "goal": f"Execute the selected plan safely: {selected_plan.get('summary', '')}",
            "expected_output": "real progress toward the user goal with evidence and crawler artifacts when external data is required",
            "acceptance_check": "execution evidence recorded without violating security boundaries; crawler tasks must produce structured reports and explicit business proof before they can pass verification",
            "verifier": execute_verifier,
            "execution_policy": execute_policy,
        },
        {
            "name": "verify",
            "goal": "Verify the goal is actually satisfied and the path stayed within security policy",
            "expected_output": "verification decision and evidence",
            "acceptance_check": "verifier passes with business-level proof when required and no unresolved approval or security blockers remain",
            "verifier": verify_verifier,
            "execution_policy": {"auto_complete_on_wait_ok": False},
        },
        {
            "name": "learn",
            "goal": "Persist lessons, promoted rules, reusable guidance, and a completion postmortem before closure",
            "expected_output": "updated learning artifacts, task summary, and written postmortem",
            "acceptance_check": "learning artifacts and postmortem are written successfully",
            "execution_policy": {"auto_complete_on_wait_ok": True},
        },
    ]
    if not complex_task_controller.get("enabled"):
        return stages
    stage_gate_policy = complex_task_controller.get("stage_gate_policy", {}) or {}
    enriched: List[Dict[str, object]] = []
    for stage in stages:
        stage_name = str(stage.get("name", "")).strip()
        policy = dict(stage.get("execution_policy", {}) or {})
        gate = dict(stage_gate_policy.get(stage_name, {}) or {})
        policy["complex_task_controller"] = True
        policy["require_stage_artifacts_before_complete"] = True
        policy["required_artifact_keys"] = list(gate.get("required_artifact_keys", []))
        policy["require_summary_nonempty"] = bool(gate.get("require_summary_nonempty", True))
        if stage_name == "execute":
            policy["require_evidence_refs_for_completion"] = bool(gate.get("require_evidence_refs", True))
            policy["require_verifier_before_complete"] = True
        stage["execution_policy"] = policy
        if stage_name in {"understand", "plan", "execute"}:
            stage["verifier"] = {
                "type": "task_stage_artifacts_ready",
                "task_id": task_id,
                "stage": stage_name,
            }
        elif stage_name == "verify":
            existing_checks = list(((stage.get("verifier", {}) or {}).get("checks", []) or []))
            artifact_checks = [
                {"type": "task_stage_artifacts_ready", "task_id": task_id, "stage": "understand"},
                {"type": "task_stage_artifacts_ready", "task_id": task_id, "stage": "plan"},
                {"type": "task_stage_artifacts_ready", "task_id": task_id, "stage": "execute"},
            ]
            stage["verifier"] = {
                "type": "all",
                "checks": [*existing_checks, *artifact_checks],
            }
            stage["goal"] = "Verify the goal is actually satisfied, tests/acceptance evidence are real, and the staged deliverables are consistent."
            stage["expected_output"] = "verification report, acceptance decision, remaining risk digest"
            stage["acceptance_check"] = "verification must confirm prior stage artifacts, execute evidence, and a truthful acceptance decision before release"
        if stage_name == "understand":
            stage["goal"] = "Understand the complex mission deeply enough to define scope, target users, constraints, and what counts as a real finished delivery."
            stage["expected_output"] = "mission brief, scope constraints, and success definition"
            stage["acceptance_check"] = "the mission brief clearly defines user goal, constraints, and done definition in a way later stages can execute against"
        elif stage_name == "plan":
            stage["goal"] = "Produce a buildable complex-task plan with module breakdown, implementation order, testing strategy, and release gate."
            stage["expected_output"] = "execution plan, module breakdown, and test strategy"
            stage["acceptance_check"] = "the plan names build order, testing path, and what evidence each stage must produce before moving on"
        elif stage_name == "execute":
            stage["goal"] = f"Build the complex delivery in a controlled way: {selected_plan.get('summary', '')}"
            stage["expected_output"] = "implementation delta, delivery evidence, and test signal"
            stage["acceptance_check"] = "execute cannot close until implementation evidence and a truthful test signal are both recorded"
        elif stage_name == "learn":
            stage["goal"] = "Write a true postmortem and reusable rule set before allowing the complex task to close."
            stage["expected_output"] = "postmortem, reusable rule, and follow-up risk digest"
            stage["acceptance_check"] = "learn only passes when postmortem and reusable lessons are written successfully"
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
    goal_guardian = _derive_goal_guardian(goal, intent, mission_profile, coding_methodology)
    complex_task_controller = _derive_complex_task_controller(goal, intent, mission_profile, coding_methodology)
    doctor_strategy_hints = load_doctor_strategy_rules()[:8]
    strict_continuation_required = _goal_requires_strict_continuation(goal, intent, mission_profile)
    task_milestones = _derive_task_milestones(task_id, goal, intent, mission_profile)
    if mission_profile.get("matched"):
        intent["done_definition"] = str(mission_profile.get("done_definition", intent.get("done_definition", "")))
    # 下面这一串 builder / judge / scorer 就是 control center 的“大脑装配线”：
    # 它们分别负责能力盘点、候选方案生成、方案评分、审批、风险审计和研究路径规划。
    capabilities = build_capability_registry()
    blueprint = build_workflow_blueprint(intent, capabilities)
    judgment = judge_proposals(intent, capabilities, blueprint["candidate_plans"])
    tool_scores = score_external_options(task_id, intent, blueprint["candidate_plans"], capabilities)
    reselection = reselect_plan(task_id, intent, blueprint["candidate_plans"], judgment, tool_scores)
    selected_plan = reselection["final_selected_plan"]
    scored_by_id = {str(item.get("plan_id", "")): item for item in judgment.get("scores", [])}
    judgment["final_selected_plan"] = selected_plan
    judgment["final_selected_score"] = scored_by_id.get(str(selected_plan.get("plan_id", "")), judgment.get("selected_score", {}))
    approval = review_plan(task_id, selected_plan)
    tool_score_map = {str(item.get("plan_id", "")): item for item in tool_scores.get("scores", [])}
    adoption_flow = build_adoption_flow(task_id, selected_plan, approval, tool_score_map.get(str(selected_plan.get("plan_id", "")), {}))
    domain_profile = build_domain_profile(task_id, intent)
    challenge = classify_challenge(task_id, [], {"status": "planning", "current_stage": "understand"})
    authorized_session = build_authorized_session_plan(task_id, intent, challenge)
    human_checkpoint = build_human_checkpoint(task_id, challenge)
    fetch_route = build_fetch_route(task_id, intent, selected_plan, domain_profile, challenge)
    crawler = build_crawler_plan(task_id, intent, selected_plan, domain_profile, fetch_route, challenge)
    business_verification_requirements = derive_business_verification_requirements(intent)
    topology = build_topology(intent, selected_plan)
    fractal = build_fractal_loops(intent, selected_plan, topology)
    htn = build_htn_tree(intent, selected_plan, topology, fractal)
    initial_htn_focus = select_htn_focus(htn, "understand", 0)
    stpa = audit_mission(intent, selected_plan, topology, approval)
    scout = build_resource_scout_brief(intent, selected_plan, domain_profile, fetch_route)
    arbitration = arbitrate_solution_path(intent, selected_plan, approval, capabilities)
    initial_bdi = build_bdi_state(intent, selected_plan, approval, {"current_stage": "understand", "status": "planning", "blockers": []}, initial_htn_focus, arbitration)
    # `mission` 是控制中心的完整中间态快照：
    # 一方面会单独落到 missions/<task_id>.json，另一方面其中最关键的部分会被压回 contract metadata。
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
        "business_verification_requirements": business_verification_requirements,
        "resource_scout": scout,
        "arbitration": arbitration,
        "adoption_flow": adoption_flow,
        "mission_profile": mission_profile,
        "coding_methodology": coding_methodology,
        "goal_guardian": goal_guardian,
        "complex_task_controller": complex_task_controller,
        "doctor_strategy_hints": doctor_strategy_hints,
        "strict_continuation_required": strict_continuation_required,
        "task_milestones": task_milestones,
    }
    should_clone_capability = selected_plan.get("plan_id") == "in_house_capability_rebuild"
    if should_clone_capability:
        clone_event = publish_event("capability.clone_requested", {"task_id": task_id, "mission": mission})
        mission["capability_clone"] = clone_event.get("emitted_hooks", [{}])[0].get("clone", {}) if clone_event.get("emitted_hooks") else {}
    _write_json(MISSIONS_ROOT / f"{task_id}.json", mission)
    publish_event("mission.built", {"task_id": task_id, "mission": mission})
    if reselection.get("switched"):
        publish_event("plan.reselected", {"task_id": task_id, "mission": mission, "reselection": reselection})
    # metadata.control_center 是 runtime 后续所有阶段最常用的“结构化任务上下文”；
    # context_builder、mission_loop、doctor、snapshot 都会从这里继续取数。
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
            "domain_profile": domain_profile,
            "challenge": challenge,
            "authorized_session": authorized_session,
            "human_checkpoint": human_checkpoint,
            "fetch_route": fetch_route,
            "crawler": crawler,
            "business_verification_requirements": business_verification_requirements,
            "strict_continuation_required": strict_continuation_required,
            "task_milestones": task_milestones,
            "resource_scout": scout,
            "arbitration": arbitration,
            "adoption_flow": adoption_flow,
            "capability_clone": mission.get("capability_clone", {}),
            "mission_profile_id": mission_profile.get("profile_id", ""),
            "mission_profile": mission_profile,
            "coding_methodology": coding_methodology,
            "goal_guardian": goal_guardian,
            "complex_task_controller": complex_task_controller,
            "doctor_strategy_hints": doctor_strategy_hints,
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
        "allowed_tools": _derive_allowed_tools({**blueprint, "intent": intent, "selected_plan": selected_plan}),
        "stages": _derive_stage_contracts(task_id, {**blueprint, "approval": approval, "intent": intent, "selected_plan": selected_plan, "mission_profile": mission_profile, "strict_continuation_required": strict_continuation_required, "crawler": crawler, "complex_task_controller": complex_task_controller}),
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
