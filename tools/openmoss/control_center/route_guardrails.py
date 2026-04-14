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
- 文件路径：`tools/openmoss/control_center/route_guardrails.py`
- 文件作用：负责路由守卫、切根与主题纠偏。
- 顶层函数：persist_route、_normalize_set、_normalize_goal、_looks_like_status_query、_safe_contract、_extract_current_intent、_topic_diverged、_next_root_task_id、_build_task、reroot_route_if_needed。
- 顶层类：无顶层类。
- 阅读建议：先看模块说明，再按函数/类 docstring 顺着主流程理解调用关系。
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from typing import Dict, Set

from intent_analyzer import analyze_intent
from goal_sanitizer import sanitize_goal_text
from orchestrator import build_control_center_package
from conversation_context import conversation_focus_path, record_conversation_context
from paths import BRAIN_ROUTES_ROOT
from task_status_snapshot import build_task_status_snapshot
AUTONOMY_DIR = Path("/Users/mac_claw/.openclaw/workspace/tools/openmoss/autonomy")
if str(AUTONOMY_DIR) not in sys.path:
    sys.path.insert(0, str(AUTONOMY_DIR))

from manager import build_args, contract_path, create_task, load_contract, load_state, log_event, save_state, utc_now_iso, write_link
from task_ingress import slugify


def persist_route(provider: str, conversation_id: str, route: Dict[str, object]) -> str:
    """
    中文注解：
    - 功能：实现 `persist_route` 对应的处理逻辑。
    - 角色：属于本模块中的对外可见逻辑；私有函数通常服务同文件主流程，公共函数通常作为跨模块入口或能力接口。
    - 调用关系：建议结合本文件的模块说明、调用方以及同名相关辅助函数一起阅读。
    """
    path = BRAIN_ROUTES_ROOT / provider / f"{conversation_id}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(route, ensure_ascii=False, indent=2), encoding="utf-8")
    return str(path)


def _normalize_set(values) -> Set[str]:
    """
    中文注解：
    - 功能：实现 `_normalize_set` 对应的处理逻辑。
    - 角色：属于本模块中的内部辅助逻辑；私有函数通常服务同文件主流程，公共函数通常作为跨模块入口或能力接口。
    - 调用关系：建议结合本文件的模块说明、调用方以及同名相关辅助函数一起阅读。
    """
    return {str(item).strip().lower() for item in (values or []) if str(item).strip()}


def _normalize_goal(text: str) -> str:
    """
    中文注解：
    - 功能：实现 `_normalize_goal` 对应的处理逻辑。
    - 角色：属于本模块中的内部辅助逻辑；私有函数通常服务同文件主流程，公共函数通常作为跨模块入口或能力接口。
    - 调用关系：建议结合本文件的模块说明、调用方以及同名相关辅助函数一起阅读。
    """
    return re.sub(r"\s+", "", str(text or "").strip().lower())


def _looks_like_status_query(text: str) -> bool:
    """
    中文注解：
    - 功能：实现 `_looks_like_status_query` 对应的处理逻辑。
    - 角色：属于本模块中的内部辅助逻辑；私有函数通常服务同文件主流程，公共函数通常作为跨模块入口或能力接口。
    - 调用关系：建议结合本文件的模块说明、调用方以及同名相关辅助函数一起阅读。
    """
    normalized = _normalize_goal(text)
    patterns = (
        "进展",
        "进度",
        "状态",
        "结果",
        "做的怎么样",
        "做得怎么样",
        "到什么阶段",
        "什么阶段",
        "搞定了吗",
        "完成了吗",
        "解决了吗",
        "跑通了吗",
        "情况",
    )
    return any(token in normalized for token in patterns)


def _governance_blocks_actionable_followup(snapshot: Dict[str, object]) -> bool:
    """
    中文注解：
    - 功能：判断当前任务是否处于“最好先回权威状态而不是继续吞入动作指令”的治理态。
    - 判定依据：待审批、以及 business 尚未完成但风险极高的状态。
    """
    governance = snapshot.get("governance", {}) or {}
    policy = governance.get("policy", {}) or {}
    pending = policy.get("pending_approvals", []) or []
    risk = str(policy.get("risk", "")).strip().lower()
    business = snapshot.get("business_outcome", {}) or {}
    if pending:
        return True
    if risk == "critical" and not business.get("goal_satisfied"):
        return True
    return False


def _safe_contract(task_id: str):
    """
    中文注解：
    - 功能：实现 `_safe_contract` 对应的处理逻辑。
    - 角色：属于本模块中的内部辅助逻辑；私有函数通常服务同文件主流程，公共函数通常作为跨模块入口或能力接口。
    - 调用关系：建议结合本文件的模块说明、调用方以及同名相关辅助函数一起阅读。
    """
    if not task_id or not contract_path(task_id).exists():
        return None
    try:
        return load_contract(task_id)
    except Exception:
        return None


def _extract_current_intent(task_id: str) -> Dict[str, object]:
    """
    中文注解：
    - 功能：实现 `_extract_current_intent` 对应的处理逻辑。
    - 角色：属于本模块中的内部辅助逻辑；私有函数通常服务同文件主流程，公共函数通常作为跨模块入口或能力接口。
    - 调用关系：建议结合本文件的模块说明、调用方以及同名相关辅助函数一起阅读。
    """
    contract = _safe_contract(task_id)
    if not contract:
        return {}
    control_center = contract.metadata.get("control_center", {}) or {}
    return (
        control_center.get("intent")
        or control_center.get("raw_intent")
        or control_center.get("inherited_intent")
        or analyze_intent(str(contract.user_goal), source="route_guardrails:fallback")
    )


def _topic_diverged(current_intent: Dict[str, object], new_intent: Dict[str, object], current_goal: str, new_goal: str) -> bool:
    """
    中文注解：
    - 功能：实现 `_topic_diverged` 对应的处理逻辑。
    - 角色：属于本模块中的内部辅助逻辑；私有函数通常服务同文件主流程，公共函数通常作为跨模块入口或能力接口。
    - 调用关系：建议结合本文件的模块说明、调用方以及同名相关辅助函数一起阅读。
    """
    current_types = _normalize_set(current_intent.get("task_types", []))
    new_types = _normalize_set(new_intent.get("task_types", []))
    current_domains = _normalize_set(current_intent.get("domains", [])) | _normalize_set(current_intent.get("likely_platforms", []))
    new_domains = _normalize_set(new_intent.get("domains", [])) | _normalize_set(new_intent.get("likely_platforms", []))
    current_keywords = _normalize_set(current_intent.get("keywords", []))
    new_keywords = _normalize_set(new_intent.get("keywords", []))

    type_disjoint = bool(current_types and new_types and current_types.isdisjoint(new_types))
    domain_disjoint = bool(current_domains and new_domains and current_domains.isdisjoint(new_domains))
    keyword_disjoint = bool(current_keywords and new_keywords and current_keywords.isdisjoint(new_keywords))
    browser_shift = bool(current_intent.get("needs_browser")) != bool(new_intent.get("needs_browser"))
    external_shift = bool(current_intent.get("requires_external_information")) != bool(new_intent.get("requires_external_information"))
    risk_shift = str(current_intent.get("risk_level", "")).strip() != str(new_intent.get("risk_level", "")).strip()

    current_norm = _normalize_goal(current_goal)
    new_norm = _normalize_goal(new_goal)
    textual_overlap = bool(current_norm and new_norm and (current_norm in new_norm or new_norm in current_norm))

    if textual_overlap:
        return False
    if type_disjoint and (domain_disjoint or browser_shift or external_shift):
        return True
    if type_disjoint and keyword_disjoint and risk_shift:
        return True
    if browser_shift and domain_disjoint and keyword_disjoint:
        return True
    return False


def _next_root_task_id(goal: str) -> str:
    """
    中文注解：
    - 功能：实现 `_next_root_task_id` 对应的处理逻辑。
    - 角色：属于本模块中的内部辅助逻辑；私有函数通常服务同文件主流程，公共函数通常作为跨模块入口或能力接口。
    - 调用关系：建议结合本文件的模块说明、调用方以及同名相关辅助函数一起阅读。
    """
    clean_goal = sanitize_goal_text(goal)
    base = slugify(clean_goal)
    if base == "autonomy-task":
        intent = analyze_intent(clean_goal, source="route_guardrails:slug")
        platforms = [str(item).strip().lower() for item in intent.get("likely_platforms", []) if str(item).strip()]
        task_types = [str(item).strip().lower() for item in intent.get("task_types", []) if str(item).strip() and str(item).strip().lower() != "general"]
        semantic_seed = "-".join(platforms[:2] + task_types[:3])
        base = slugify(semantic_seed) or "autonomy-task"
    candidate = base
    counter = 2
    while contract_path(candidate).exists():
        candidate = f"{base}-{counter}"
        counter += 1
    return candidate


def _build_task(task_id: str, goal: str, source: str, metadata_extra: Dict[str, object] | None = None) -> Dict[str, object]:
    """
    中文注解：
    - 功能：实现 `_build_task` 对应的处理逻辑。
    - 角色：属于本模块中的内部辅助逻辑；私有函数通常服务同文件主流程，公共函数通常作为跨模块入口或能力接口。
    - 调用关系：建议结合本文件的模块说明、调用方以及同名相关辅助函数一起阅读。
    """
    clean_goal = sanitize_goal_text(goal)
    package = build_control_center_package(task_id, clean_goal, source=source)
    metadata = dict(package["metadata"])
    if metadata_extra:
        metadata.update(metadata_extra)
    create_task(
        build_args(
            task_id=task_id,
            goal=clean_goal,
            done_definition=package["done_definition"],
            stage=[],
            stage_json=json.dumps(package["stages"], ensure_ascii=False),
            hard_constraint=package["hard_constraints"],
            soft_preference=[],
            allowed_tool=package["allowed_tools"],
            forbidden_action=[],
            metadata_json=json.dumps(metadata, ensure_ascii=False),
        )
    )
    return package


def reroot_route_if_needed(
    *,
    route: Dict[str, object],
    provider: str,
    conversation_id: str,
    conversation_type: str,
    goal: str,
    session_key: str,
) -> Dict[str, object]:
    """
    中文注解：
    - 功能：实现 `reroot_route_if_needed` 对应的处理逻辑。
    - 角色：属于本模块中的对外可见逻辑；私有函数通常服务同文件主流程，公共函数通常作为跨模块入口或能力接口。
    - 调用关系：建议结合本文件的模块说明、调用方以及同名相关辅助函数一起阅读。
    """
    def _finalize(updated_route: Dict[str, object]) -> Dict[str, object]:
        finalized = dict(updated_route)
        focus = record_conversation_context(
            finalized,
            provider=provider,
            conversation_id=conversation_id,
            conversation_type=conversation_type,
            session_key=session_key,
        )
        finalized["conversation_focus"] = focus
        finalized["conversation_focus_path"] = str(conversation_focus_path(provider, conversation_id))
        return finalized

    goal = sanitize_goal_text(goal)
    route_intent = route.get("intent", {}) or analyze_intent(goal, source="route_guardrails:actionability")
    actionable = (
        bool(goal)
        and not (len(str(goal).strip()) < 24 and route_intent.get("task_types", ["general"]) == ["general"] and not any(route_intent.get(key) for key in ("requires_external_information", "needs_browser", "may_download_artifacts", "may_execute_external_code")))
    )
    if route.get("task_id") and _looks_like_status_query(goal) and not actionable:
        snapshot = build_task_status_snapshot(str(route.get("task_id")))
        route = dict(route)
        route["mode"] = "authoritative_task_status"
        route["authoritative_task_status"] = snapshot
        route["created_task"] = False
        route["attached_existing"] = True
        return _finalize(route)

    existing_task_id = str(route.get("task_id", "")).strip()
    predecessor_task_id = str(route.get("predecessor_task_id", "")).strip()
    if not existing_task_id:
        return _finalize(route)

    snapshot = build_task_status_snapshot(existing_task_id)
    route = dict(route)
    route["authoritative_task_status"] = route.get("authoritative_task_status") or snapshot
    if _governance_blocks_actionable_followup(snapshot) and not actionable:
        route["mode"] = "authoritative_task_status"
        route["created_task"] = False
        route["attached_existing"] = True
        return _finalize(route)

    comparison_task_id = predecessor_task_id or existing_task_id
    current_intent = _extract_current_intent(comparison_task_id) or _extract_current_intent(str(route.get("lineage_root_task_id", "")).strip())
    new_intent = route.get("intent", {}) or analyze_intent(goal, source="route_guardrails")
    current_contract = _safe_contract(comparison_task_id)
    current_goal = str(current_contract.user_goal if current_contract else "")
    if not _topic_diverged(current_intent, new_intent, current_goal, goal):
        return _finalize(route)

    new_task_id = _next_root_task_id(goal)
    if predecessor_task_id:
        stale_state = load_state(existing_task_id)
        stale_state.status = "blocked"
        stale_state.next_action = f"rerooted_to:{new_task_id}"
        stale_state.blockers = [f"rerooted into a new root task {new_task_id} because the topic diverged from predecessor {predecessor_task_id}"]
        stale_state.metadata["superseded_by_task_id"] = new_task_id
        stale_state.last_update_at = utc_now_iso()
        save_state(stale_state)
        log_event(existing_task_id, "task_rerooted_out_of_lineage", new_root_task_id=new_task_id, predecessor_task_id=predecessor_task_id)
    else:
        # 当前会话直接绑在一个 root task 上时，如果用户已经明显切换主题，
        # 这里只需要把会话链改挂到新的 root task，不能把旧 root mission 误判成被 supersede。
        log_event(existing_task_id, "conversation_rerooted_to_new_root_task", new_root_task_id=new_task_id, conversation_id=conversation_id)
    _build_task(
        new_task_id,
        goal,
        source=f"{route.get('source', 'route_guardrails')}:rerooted",
        metadata_extra={
            "rerooted_from_task_id": comparison_task_id,
            "rerooted_from_route_task_id": existing_task_id,
            "rerooted_at": utc_now_iso(),
        },
    )
    payload = {
        "provider": provider,
        "conversation_id": conversation_id,
        "conversation_type": conversation_type,
        "task_id": new_task_id,
        "goal": goal,
        "updated_at": utc_now_iso(),
        "last_message_id": route.get("message_id", ""),
        "last_sender_id": route.get("sender_id", ""),
        "last_sender_name": route.get("sender_name", ""),
        "brain_source": route.get("source", ""),
        "rerooted_from_task_id": comparison_task_id,
    }
    if session_key:
        payload["session_key"] = session_key
    link_path = write_link(provider, conversation_id, payload)
    log_event(new_task_id, "task_rerooted_from_prior_topic", prior_task_id=comparison_task_id, prior_route_task_id=existing_task_id)
    route = dict(route)
    route["mode"] = "create_new_root_task"
    route["created_task"] = True
    route["attached_existing"] = False
    route["rerooted"] = True
    route["rerooted_from_task_id"] = comparison_task_id
    route["task_id"] = new_task_id
    route["lineage_root_task_id"] = new_task_id
    route["link_path"] = link_path
    return _finalize(route)
