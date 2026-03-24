#!/usr/bin/env python3

from __future__ import annotations

import re
from pathlib import Path
from typing import Dict

from learning_engine import get_error_recurrence
from promotion_engine import resolve_rule_for_error


def classify_failure(error_text: str) -> str:
    error = error_text.lower()
    if "timeout" in error or "temporarily" in error:
        return "transient_error"
    if "permission" in error or "denied" in error:
        return "permission_error"
    if "missing" in error or "not found" in error:
        return "missing_dependency"
    if "auth" in error or "token" in error or "unauthorized" in error:
        return "auth_or_config_error"
    if "captcha" in error or "blocked" in error or "rate limit" in error:
        return "anti_automation_or_rate_limit"
    return "general_failure"


def propose_recovery(error_text: str, attempts: int) -> Dict[str, str]:
    classification = classify_failure(error_text)
    recurrence = get_error_recurrence(error_text)
    promoted_rule = resolve_rule_for_error(error_text)
    if classification == "transient_error":
        action = "retry_same_stage_with_fresh_evidence"
    elif classification == "permission_error":
        action = "inspect_permissions_then_retry"
    elif classification == "missing_dependency":
        action = "repair_missing_path_or_dependency"
    elif classification == "auth_or_config_error":
        action = "repair_credentials_or_configuration"
    elif classification == "anti_automation_or_rate_limit":
        action = "switch_tool_path_or_slow_down"
    else:
        action = "run_root_cause_review_before_retry"

    if attempts >= 3:
        action = "escalate_to_runtime_review"
    if recurrence.get("count", 0) >= 2:
        action = "install_preflight_guard_and_targeted_recovery"
    if promoted_rule and promoted_rule.get("preferred_action"):
        action = str(promoted_rule["preferred_action"])

    return {
        "classification": classification,
        "action": action,
        "recurrence_count": str(recurrence.get("count", 0)),
        "durable_rule": str(bool(promoted_rule)).lower(),
    }


def _extract_path(error_text: str) -> Path | None:
    matches = re.findall(r"(/Users/[^\s:'\"]+|/tmp/[^\s:'\"]+|\.[/\w\-.]+)", error_text)
    if not matches:
        return None
    return Path(matches[0]).expanduser()


def apply_recovery_action(action: str, error_text: str) -> Dict[str, str]:
    if action == "retry_same_stage_with_fresh_evidence":
        return {"ok": "true", "status": "state_reset_only", "note": "stage can be retried immediately"}

    if action == "inspect_permissions_then_retry":
        path = _extract_path(error_text)
        if path and path.exists():
            mode = path.stat().st_mode | 0o100
            path.chmod(mode)
            return {"ok": "true", "status": "chmod_applied", "path": str(path)}
        return {"ok": "false", "status": "path_not_found_for_permission_fix"}

    if action == "repair_missing_path_or_dependency":
        path = _extract_path(error_text)
        if path:
            target = path if path.suffix == "" else path.parent
            target.mkdir(parents=True, exist_ok=True)
            return {"ok": "true", "status": "path_created", "path": str(target)}
        return {"ok": "false", "status": "no_path_detected"}

    if action == "repair_credentials_or_configuration":
        return {"ok": "false", "status": "needs_external_secret_or_config"}

    if action == "switch_tool_path_or_slow_down":
        return {"ok": "true", "status": "tool_switch_recommended", "note": "requires alternate execution path"}

    if action == "install_preflight_guard_and_targeted_recovery":
        classification = classify_failure(error_text)
        path = _extract_path(error_text)
        if classification == "permission_error" and path and path.exists():
            mode = path.stat().st_mode | 0o100
            path.chmod(mode)
            return {"ok": "true", "status": "durable_permission_guard_applied", "path": str(path)}
        if classification == "missing_dependency" and path:
            target = path if path.suffix == "" else path.parent
            target.mkdir(parents=True, exist_ok=True)
            return {"ok": "true", "status": "durable_path_guard_applied", "path": str(target)}
        if classification == "anti_automation_or_rate_limit":
            return {"ok": "true", "status": "durable_slowdown_policy_requested", "note": "future executions should back off earlier"}
        return {"ok": "true", "status": "durable_review_rule_requested"}

    if action in {"run_root_cause_review_before_retry", "escalate_to_runtime_review"}:
        return {"ok": "true", "status": "review_required"}

    if action == "repair_verification_failure":
        return {"ok": "true", "status": "verification_repair_requested"}

    return {"ok": "false", "status": "unknown_action"}
