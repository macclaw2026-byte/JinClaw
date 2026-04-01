#!/usr/bin/env python3

"""
中文说明：
- 文件路径：`tools/openmoss/autonomy/recovery_engine.py`
- 文件作用：负责失败分类、恢复动作生成与恢复执行。
- 顶层函数：classify_failure、propose_recovery、_extract_path、apply_recovery_action。
- 顶层类：无顶层类。
- 阅读建议：先看模块说明，再按函数/类 docstring 顺着主流程理解调用关系。
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Dict

from learning_engine import get_error_recurrence
from promotion_engine import resolve_rule_for_error

CONTROL_CENTER_DIR = Path("/Users/mac_claw/.openclaw/workspace/tools/openmoss/control_center")
if str(CONTROL_CENTER_DIR) not in __import__("sys").path:
    __import__("sys").path.insert(0, str(CONTROL_CENTER_DIR))

from browser_task_signals import collect_browser_task_signals
from browser_channel_recovery import recover_browser_channel
from event_bus import publish_event


def _emit_recovery_event(task_id: str, event_suffix: str, payload: Dict[str, str]) -> None:
    if not str(task_id or "").strip():
        return
    publish_event(
        f"recovery.{event_suffix}",
        {
            "task_id": task_id,
            **payload,
        },
    )


def _finish_recovery(task_id: str, action: str, result: Dict[str, str]) -> Dict[str, str]:
    _emit_recovery_event(
        task_id,
        "applied",
        {
            "action": action,
            "recovery": result,
            "blockers": [str(result.get("blocker", "")).strip()] if str(result.get("blocker", "")).strip() else [],
        },
    )
    return result


def classify_failure(error_text: str) -> str:
    """
    中文注解：
    - 功能：实现 `classify_failure` 对应的处理逻辑。
    - 角色：属于本模块中的对外可见逻辑；私有函数通常服务同文件主流程，公共函数通常作为跨模块入口或能力接口。
    - 调用关系：建议结合本文件的模块说明、调用方以及同名相关辅助函数一起阅读。
    """
    error = error_text.lower()
    if "upload_control_path_invalid" in error:
        return "upload_control_path_invalid"
    if "browser_control_channel_lost" in error or "tab not found" in error:
        return "browser_control_channel_lost"
    if "browser_relay_unattached" in error or "no attached chrome tabs" in error:
        return "browser_relay_unattached"
    if "stale_target_id" in error:
        return "stale_target_id"
    if "browser_channel_reacquired" in error:
        return "browser_channel_reacquired"
    if "frontend_binding_not_triggered" in error:
        return "frontend_binding_not_triggered"
    if "browser_form_validation_blocking_submit" in error:
        return "browser_form_validation_blocking_submit"
    if "upload_saved_successfully" in error:
        return "upload_saved_successfully"
    if "needs_network_request_level_debugging" in error:
        return "needs_network_request_level_debugging"
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
    """
    中文注解：
    - 功能：实现 `propose_recovery` 对应的处理逻辑。
    - 角色：属于本模块中的对外可见逻辑；私有函数通常服务同文件主流程，公共函数通常作为跨模块入口或能力接口。
    - 调用关系：建议结合本文件的模块说明、调用方以及同名相关辅助函数一起阅读。
    """
    classification = classify_failure(error_text)
    recurrence = get_error_recurrence(error_text)
    promoted_rule = resolve_rule_for_error(error_text)
    if classification == "transient_error":
        action = "retry_same_stage_with_fresh_evidence"
    elif classification == "permission_error":
        action = "inspect_permissions_then_retry"
    elif classification == "missing_dependency":
        action = "repair_missing_path_or_dependency"
    elif classification in {"browser_control_channel_lost", "stale_target_id"}:
        action = "reacquire_browser_channel"
    elif classification == "browser_relay_unattached":
        action = "await_relay_attach_checkpoint"
    elif classification == "auth_or_config_error":
        action = "repair_credentials_or_configuration"
    elif classification == "anti_automation_or_rate_limit":
        action = "switch_tool_path_or_slow_down"
    elif classification == "upload_control_path_invalid":
        action = "needs_network_request_level_debugging"
    elif classification == "frontend_binding_not_triggered":
        action = "investigate_frontend_binding_and_network_request_chain"
    elif classification == "browser_form_validation_blocking_submit":
        action = "normalize_invalid_numeric_fields_then_resubmit"
    elif classification == "upload_saved_successfully":
        action = "confirm_business_outcome_and_finalize"
    elif classification == "browser_channel_reacquired":
        action = "continue_current_plan"
    elif classification == "needs_network_request_level_debugging":
        action = "needs_network_request_level_debugging"
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
    """
    中文注解：
    - 功能：实现 `_extract_path` 对应的处理逻辑。
    - 角色：属于本模块中的内部辅助逻辑；私有函数通常服务同文件主流程，公共函数通常作为跨模块入口或能力接口。
    - 调用关系：建议结合本文件的模块说明、调用方以及同名相关辅助函数一起阅读。
    """
    matches = re.findall(r"(/Users/[^\s:'\"]+|/tmp/[^\s:'\"]+|\.[/\w\-.]+)", error_text)
    if not matches:
        return None
    return Path(matches[0]).expanduser()


def apply_recovery_action(action: str, error_text: str, task_id: str = "") -> Dict[str, str]:
    """
    中文注解：
    - 功能：实现 `apply_recovery_action` 对应的处理逻辑。
    - 角色：属于本模块中的对外可见逻辑；私有函数通常服务同文件主流程，公共函数通常作为跨模块入口或能力接口。
    - 调用关系：建议结合本文件的模块说明、调用方以及同名相关辅助函数一起阅读。
    """
    _emit_recovery_event(
        task_id,
        "requested",
        {
            "action": action,
            "error_text": error_text,
            "classification": classify_failure(error_text),
            "blockers": [str(error_text).strip()] if str(error_text).strip() else [],
        },
    )
    if action == "retry_same_stage_with_fresh_evidence":
        return _finish_recovery(task_id, action, {"ok": "true", "status": "state_reset_only", "note": "stage can be retried immediately"})

    if action == "inspect_permissions_then_retry":
        path = _extract_path(error_text)
        if path and path.exists():
            mode = path.stat().st_mode | 0o100
            path.chmod(mode)
            return _finish_recovery(task_id, action, {"ok": "true", "status": "chmod_applied", "path": str(path)})
        return _finish_recovery(task_id, action, {"ok": "false", "status": "path_not_found_for_permission_fix"})

    if action == "repair_missing_path_or_dependency":
        path = _extract_path(error_text)
        if path:
            target = path if path.suffix == "" else path.parent
            target.mkdir(parents=True, exist_ok=True)
            return _finish_recovery(task_id, action, {"ok": "true", "status": "path_created", "path": str(target)})
        return _finish_recovery(task_id, action, {"ok": "false", "status": "no_path_detected"})

    if action == "repair_credentials_or_configuration":
        return _finish_recovery(task_id, action, {"ok": "false", "status": "needs_external_secret_or_config"})

    if action == "switch_tool_path_or_slow_down":
        return _finish_recovery(task_id, action, {"ok": "true", "status": "tool_switch_recommended", "note": "requires alternate execution path"})

    if action == "reacquire_browser_channel":
        recovery = recover_browser_channel(task_id, expected_domains=["seller.neosgo.com"])
        if recovery.get("ok"):
            return _finish_recovery(task_id, action, {
                "ok": "true",
                "status": "browser_channel_recovered",
                "target_id": str(recovery.get("target_id", "")),
                "page_url": str(recovery.get("page_url", "")),
            })
        return _finish_recovery(task_id, action, {
            "ok": "false",
            "status": str(recovery.get("status", "browser_channel_recovery_failed")),
            "next_action": "reacquire_browser_channel",
            "blocker": str(recovery.get("status", "browser_channel_recovery_failed")),
        })

    if action == "await_relay_attach_checkpoint":
        return _finish_recovery(task_id, action, {
            "ok": "false",
            "status": "await_relay_attach_checkpoint",
            "next_action": "await_relay_attach_checkpoint",
            "blocker": "chrome-relay has no attached tabs",
        })

    if action == "install_preflight_guard_and_targeted_recovery":
        classification = classify_failure(error_text)
        path = _extract_path(error_text)
        if classification == "permission_error" and path and path.exists():
            mode = path.stat().st_mode | 0o100
            path.chmod(mode)
            return _finish_recovery(task_id, action, {"ok": "true", "status": "durable_permission_guard_applied", "path": str(path)})
        if classification == "missing_dependency" and path:
            target = path if path.suffix == "" else path.parent
            target.mkdir(parents=True, exist_ok=True)
            return _finish_recovery(task_id, action, {"ok": "true", "status": "durable_path_guard_applied", "path": str(target)})
        if classification == "anti_automation_or_rate_limit":
            return _finish_recovery(task_id, action, {"ok": "true", "status": "durable_slowdown_policy_requested", "note": "future executions should back off earlier"})
        return _finish_recovery(task_id, action, {"ok": "true", "status": "durable_review_rule_requested"})

    if action in {"run_root_cause_review_before_retry", "escalate_to_runtime_review"}:
        return _finish_recovery(task_id, action, {"ok": "true", "status": "review_required"})

    if action == "repair_verification_failure":
        signals = collect_browser_task_signals(task_id) if task_id else {"diagnosis": "none"}
        diagnosis = str(signals.get("diagnosis", "none"))
        if diagnosis == "upload_control_path_invalid":
            return _finish_recovery(task_id, action, {
                "ok": "false",
                "status": "upload_control_path_invalid",
                "next_action": "needs_network_request_level_debugging",
                "blocker": "upload_control_path_invalid",
            })
        if diagnosis == "frontend_binding_not_triggered":
            return _finish_recovery(task_id, action, {
                "ok": "false",
                "status": "frontend_binding_not_triggered",
                "next_action": "investigate_frontend_binding_and_network_request_chain",
                "blocker": "frontend_binding_not_triggered",
            })
        if diagnosis == "needs_network_request_level_debugging":
            return _finish_recovery(task_id, action, {
                "ok": "false",
                "status": "needs_network_request_level_debugging",
                "next_action": "needs_network_request_level_debugging",
                "blocker": "needs_network_request_level_debugging",
            })
        if diagnosis == "browser_form_validation_blocking_submit":
            return _finish_recovery(task_id, action, {
                "ok": "false",
                "status": "browser_form_validation_blocking_submit",
                "next_action": "normalize_invalid_numeric_fields_then_resubmit",
                "blocker": "browser_form_validation_blocking_submit",
            })
        if diagnosis == "upload_saved_successfully":
            return _finish_recovery(task_id, action, {
                "ok": "true",
                "status": "business_outcome_confirmed",
                "next_action": "confirm_business_outcome_and_finalize",
            })
        return _finish_recovery(task_id, action, {"ok": "true", "status": "verification_repair_requested"})

    if action in {
        "needs_network_request_level_debugging",
        "investigate_frontend_binding_and_network_request_chain",
        "normalize_invalid_numeric_fields_then_resubmit",
        "reacquire_browser_channel",
    }:
        return _finish_recovery(task_id, action, {"ok": "false", "status": action, "next_action": action, "blocker": action})

    if action == "confirm_business_outcome_and_finalize":
        return _finish_recovery(task_id, action, {"ok": "true", "status": "business_outcome_confirmed", "next_action": action})

    return _finish_recovery(task_id, action, {"ok": "false", "status": "unknown_action"})
