#!/usr/bin/env python3

from __future__ import annotations

import re
from typing import Any, Dict


def summarize_governance_attention(governance: Dict[str, Any]) -> Dict[str, Any]:
    governance = governance or {}
    permission = (governance.get("permission_decision", {}) or {}) if isinstance(governance, dict) else {}
    project_control = (governance.get("project_control", {}) or {}) if isinstance(governance, dict) else {}
    crawler_project = (governance.get("crawler_project", {}) or {}) if isinstance(governance, dict) else {}
    return {
        "permission_overall_status": str(permission.get("overall_status", "")).strip() or "unknown",
        "permission_primary_reason": str(permission.get("primary_reason", "")).strip() or "unknown",
        "permission_blocked_total": int(permission.get("blocked_total", 0) or 0),
        "crawler_health_status": str(crawler_project.get("health_status", "")).strip() or "unknown",
        "project_feedback_status": str(((project_control.get("summary", {}) or {}).get("crawler_feedback_coverage_status", ""))).strip() or "unknown",
        "scheduler_modes": dict(project_control.get("scheduler_modes", {}) or {}),
    }


def summarize_snapshot_governance(snapshot: Dict[str, Any]) -> Dict[str, Any]:
    governance = (snapshot.get("governance", {}) or {}) if isinstance(snapshot, dict) else {}
    return summarize_governance_attention(governance)


def governance_attention_flags(snapshot: Dict[str, Any]) -> Dict[str, bool]:
    governance = snapshot.get("governance", {}) or {}
    policy = governance.get("policy", {}) or {}
    memory = governance.get("memory", {}) or snapshot.get("memory", {}) or {}
    risk = str(policy.get("risk", "")).strip().lower()
    pending = policy.get("pending_approvals", []) or []
    matched_rules = memory.get("matched_promoted_rules", []) or []
    matched_recurrence = memory.get("matched_error_recurrence", []) or []
    return {
        "high_risk": risk in {"high", "critical"},
        "approval_pending": bool(pending),
        "memory_guidance_present": bool(matched_rules or matched_recurrence),
    }


def is_lightweight_followup_prompt(text: str, intent: Dict[str, object]) -> bool:
    normalized = re.sub(r"\s+", "", text.strip().lower())
    if not normalized:
        return False
    lightweight_tokens = {
        "继续",
        "继续吧",
        "接着",
        "开始吧",
        "开始",
        "可以",
        "好的",
        "同意",
        "继续推进",
        "继续。",
        "continue",
        "goon",
        "start",
    }
    if normalized in lightweight_tokens:
        return True
    if len(normalized) <= 12 and looks_like_followup_goal(text, intent):
        return True
    return False


def looks_like_followup_goal(text: str, intent: Dict[str, object]) -> bool:
    lowered = text.strip().lower()
    if not lowered:
        return False
    normalized = re.sub(r"\s+", "", lowered)
    follow_up_action_patterns = (
        "继续",
        "继续推进",
        "接着",
        "下一步",
        "后续",
        "剩下",
        "把这",
        "把剩下",
        "补到",
        "补齐",
        "提审",
        "提交审核",
        "排到",
        "排到前",
        "搞定",
        "完成剩余",
        "不要停止",
        "直到",
        "做完",
        "finish",
        "remaining",
        "follow-up",
        "followup",
        "continue",
    )
    if any(token in normalized for token in follow_up_action_patterns):
        return True
    if any(intent.get(key) for key in ("needs_browser", "needs_verification", "requires_external_information")):
        return True
    return intent.get("task_types", ["general"]) != ["general"]


def task_depends_on_external_crawling(mission: Dict[str, object], context_packet: Dict[str, object]) -> bool:
    intent = mission.get("intent", {}) or {}
    if any(bool(intent.get(key)) for key in ("requires_external_information", "needs_browser")):
        return True
    task_types = {str(item).strip().lower() for item in (intent.get("task_types", []) or []) if str(item).strip()}
    if task_types & {"marketplace", "web", "research", "crawler", "browser"}:
        return True
    allowed_tools = {str(item).strip().lower() for item in (context_packet.get("allowed_tools", []) or []) if str(item).strip()}
    external_tools = {
        "web",
        "search",
        "crawl4ai",
        "browser",
        "agent-browser",
        "playwright",
        "playwright_stealth",
        "httpx",
        "curl_cffi",
        "scrapy",
        "selectolax",
    }
    return bool(allowed_tools & external_tools)


def build_project_crawler_gate(
    mission: Dict[str, object],
    context_packet: Dict[str, object],
    governance_attention: Dict[str, object],
    current_stage: str,
) -> Dict[str, object] | None:
    if current_stage not in {"understand", "execute", "verify"}:
        return None
    if not task_depends_on_external_crawling(mission, context_packet):
        return None
    governance = (context_packet.get("governance", {}) or {}) if isinstance(context_packet, dict) else {}
    crawler_project = (governance.get("crawler_project", {}) or {}) if isinstance(governance, dict) else {}
    fetch_route = mission.get("fetch_route", {}) or {}
    route_ladder = [str(item).strip() for item in (fetch_route.get("route_ladder", []) or []) if str(item).strip()]
    current_route = str(fetch_route.get("current_route", "")).strip()
    high_risk_route = current_route in {"authorized_session", "human_checkpoint"} or (
        route_ladder and route_ladder[0] in {"authorized_session", "human_checkpoint"}
    )
    health_status = str(governance_attention.get("crawler_health_status", "")).strip().lower()
    feedback_status = str(governance_attention.get("project_feedback_status", "")).strip().lower()
    scheduler_modes = governance_attention.get("scheduler_modes", {}) or {}
    remediation_mode = str(scheduler_modes.get("crawler_remediation", "")).strip().lower()
    attention_sites = list(crawler_project.get("attention_sites", []) or [])
    recommended_actions = [str(item) for item in (crawler_project.get("recommended_project_actions", []) or []) if str(item).strip()]
    if health_status == "critical" and attention_sites:
        return {
            "action": "await_project_crawler_remediation",
            "reason": "project-level crawler health is critical for an externally dependent task, so execution should wait for remediation instead of forcing a fragile route",
            "auto_safe": True,
            "project_gate": {
                "health_status": health_status,
                "feedback_status": feedback_status,
                "remediation_mode": remediation_mode,
                "current_route": current_route,
                "attention_sites": attention_sites[:3],
                "recommended_project_actions": recommended_actions[:3],
            },
        }
    if feedback_status == "thin" and remediation_mode == "aggressive" and (attention_sites or high_risk_route):
        return {
            "action": "await_project_crawler_remediation",
            "reason": "project feedback coverage is still thin while remediation is in aggressive mode, so the task should pause before spending more effort on a low-confidence external route",
            "auto_safe": True,
            "project_gate": {
                "health_status": health_status or "unknown",
                "feedback_status": feedback_status,
                "remediation_mode": remediation_mode,
                "current_route": current_route,
                "attention_sites": attention_sites[:3],
                "recommended_project_actions": recommended_actions[:3],
            },
        }
    return None


def should_prefer_governance_status_reply(text: str, intent: Dict[str, object], snapshot: Dict[str, object]) -> bool:
    if not is_lightweight_followup_prompt(text, intent):
        return False
    if str(snapshot.get("status", "")).strip() != "blocked":
        return False
    next_action = str(snapshot.get("next_action", "")).strip()
    if next_action == "await_project_crawler_remediation":
        return True
    governance_attention = summarize_snapshot_governance(snapshot)
    permission_status = str(governance_attention.get("permission_overall_status", "")).strip().lower()
    crawler_health_status = str(governance_attention.get("crawler_health_status", "")).strip().lower()
    if permission_status == "blocked":
        return True
    if crawler_health_status == "critical" and next_action in {
        "request_authorized_session",
        "await_human_verification_checkpoint",
        "await_approval_or_contract_fix",
    }:
        return True
    return False


def classify_blocked_runtime_state(
    *,
    next_action: str,
    blockers: list[str] | None = None,
    governance_attention: Dict[str, Any] | None = None,
) -> Dict[str, str]:
    next_action = str(next_action or "").strip()
    blockers = [str(item).strip() for item in (blockers or []) if str(item).strip()]
    governance_attention = governance_attention or {}
    mapping = {
        "bind_session_link": {
            "category": "session_binding",
            "response_action": "awaiting_session_binding",
        },
        "await_project_crawler_remediation": {
            "category": "project_crawler_remediation",
            "response_action": "awaiting_project_crawler_remediation",
        },
        "await_approval_or_contract_fix": {
            "category": "approval_or_contract",
            "response_action": "awaiting_approval_by_control_center",
        },
        "prove_necessity_before_switching": {
            "category": "necessity_proof",
            "response_action": "awaiting_necessity_proof",
        },
        "request_authorized_session": {
            "category": "authorized_session",
            "response_action": "awaiting_authorized_session",
        },
        "await_relay_attach_checkpoint": {
            "category": "relay_attach",
            "response_action": "awaiting_relay_attach_checkpoint",
        },
        "await_human_verification_checkpoint": {
            "category": "human_checkpoint",
            "response_action": "awaiting_human_checkpoint",
        },
        "inspect_runtime_contract_or_environment": {
            "category": "runtime_or_contract_fix",
            "response_action": "awaiting_runtime_or_contract_fix",
        },
        "repair_runtime_failure": {
            "category": "runtime_failure",
            "response_action": "blocked_waiting_for_targeted_fix",
        },
    }
    details = dict(mapping.get(next_action, {}))
    if not details:
        details = {
            "category": "targeted_fix",
            "response_action": "blocked_waiting_for_targeted_fix",
        }
    permission_status = str((governance_attention or {}).get("permission_overall_status", "")).strip().lower()
    crawler_health_status = str((governance_attention or {}).get("crawler_health_status", "")).strip().lower()
    attention_reason = ""
    if details["category"] == "approval_or_contract" and permission_status == "blocked":
        attention_reason = "governance_permission_blocked"
    elif details["category"] == "project_crawler_remediation" and crawler_health_status in {"degraded", "critical"}:
        attention_reason = f"crawler_health_{crawler_health_status}"
    elif blockers:
        attention_reason = blockers[0]
    return {
        "category": details["category"],
        "response_action": details["response_action"],
        "attention_reason": attention_reason,
    }
