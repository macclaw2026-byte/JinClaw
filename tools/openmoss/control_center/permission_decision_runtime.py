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
- 文件路径：`tools/openmoss/control_center/permission_decision_runtime.py`
- 文件作用：把 security / approval / hooks / authorized_session / human_checkpoint 合成统一的权限决策流水线。
- 顶层函数：build_permission_decision_bundle。
- 顶层类：无顶层类。
"""
from __future__ import annotations

from typing import Any, Dict, List


def _decision_for_action(
    *,
    action: Dict[str, Any],
    action_id: str,
    security: Dict[str, Any],
    approval: Dict[str, Any],
    authorized_session: Dict[str, Any],
    human_checkpoint: Dict[str, Any],
) -> Dict[str, Any]:
    action_type = str(action.get("type", "")).strip()
    forbidden = set(str(item).strip() for item in (security.get("forbidden_actions", []) or []) if str(item).strip())
    pending = set(str(item).strip() for item in (approval.get("pending", []) or []) if str(item).strip())
    approved = set(str(item).strip() for item in (approval.get("approved", []) or []) if str(item).strip())
    review_levels = security.get("review_levels", {}) or {}
    approval_mode = str(action.get("approval_mode") or review_levels.get(action_type, "manual_approval")).strip()
    verdict = "allow"
    reason = "allowed_by_policy"
    if action_type in forbidden:
        verdict = "deny"
        reason = "forbidden_action_type"
    elif action_type == "authorized_session" and bool(authorized_session.get("needs_authorized_session")):
        if action_id in pending or bool(authorized_session.get("approval_required")):
            verdict = "needs_authorized_session_approval"
            reason = "authorized_session_pending_review"
        elif action_id not in approved and approval_mode != "auto_review":
            verdict = "needs_approval"
            reason = "authorized_session_missing_approval"
    elif action_type == "human_checkpoint" and bool(human_checkpoint.get("required")):
        verdict = "needs_human_checkpoint"
        reason = str(human_checkpoint.get("checkpoint_reason") or "human_checkpoint_required").strip()
    elif approval_mode != "auto_review" and action_id in pending:
        verdict = "needs_approval"
        reason = "manual_approval_pending"
    return {
        "action_id": action_id,
        "type": action_type,
        "tool": action.get("tool", ""),
        "risk": action.get("risk", ""),
        "approval_mode": approval_mode,
        "verdict": verdict,
        "reason": reason,
    }


def build_permission_decision_bundle(
    *,
    task_id: str,
    stage_name: str,
    security: Dict[str, Any],
    policy: Dict[str, Any],
    approval: Dict[str, Any],
    authorized_session: Dict[str, Any],
    human_checkpoint: Dict[str, Any],
    hooks: Dict[str, Any],
) -> Dict[str, Any]:
    action_decisions: List[Dict[str, Any]] = []
    blocking_hooks: List[str] = []
    for registered in hooks.get("registered", []) or []:
        for spec in registered.get("hook_specs", []) or []:
            if str(spec.get("phase", "")).strip() == "pre_execute" and bool(spec.get("blocking")):
                blocking_hooks.append(str(spec.get("name", "")).strip())
    actions = policy.get("actions", []) or []
    for index, action in enumerate(actions, start=1):
        action_id = str(action.get("action_id", "")).strip() or f"{task_id}:{action.get('type', 'external')}:{index}"
        action_decisions.append(
            _decision_for_action(
                action=action,
                action_id=action_id,
                security=security,
                approval=approval,
                authorized_session=authorized_session,
                human_checkpoint=human_checkpoint,
            )
        )
    blocking = [row for row in action_decisions if row.get("verdict") != "allow"]
    overall_status = "ready"
    primary_reason = "all_actions_allowed"
    if blocking:
        first = blocking[0]
        verdict = str(first.get("verdict", "")).strip()
        if verdict == "deny":
            overall_status = "blocked"
        elif verdict == "needs_human_checkpoint":
            overall_status = "needs_human_checkpoint"
        elif verdict == "needs_authorized_session_approval":
            overall_status = "needs_authorized_session"
        else:
            overall_status = "needs_approval"
        primary_reason = str(first.get("reason", "")).strip() or primary_reason
    return {
        "task_id": task_id,
        "stage_name": stage_name,
        "overall_status": overall_status,
        "primary_reason": primary_reason,
        "blocking_hooks": [item for item in blocking_hooks if item],
        "trace": action_decisions,
        "allowed_total": sum(1 for row in action_decisions if row.get("verdict") == "allow"),
        "blocked_total": sum(1 for row in action_decisions if row.get("verdict") != "allow"),
    }
