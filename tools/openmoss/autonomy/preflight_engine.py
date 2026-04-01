#!/usr/bin/env python3

"""
中文说明：
- 文件路径：`tools/openmoss/autonomy/preflight_engine.py`
- 文件作用：负责执行前检查、风险门控与历史 guard 套用。
- 顶层函数：_normalize_path、_resolve_command_path、_extract_path、_extract_missing_command、_run_permission_guard、_run_path_guard、_run_dependency_guard、_run_required_commands_guard、_run_required_paths_guard、_run_writable_paths_guard、_run_contract_guards、_run_stpa_guard、_run_stage_specific_guard、run_stage_preflight。
- 顶层类：无顶层类。
- 阅读建议：先看模块说明，再按函数/类 docstring 顺着主流程理解调用关系。
"""
from __future__ import annotations

import os
import re
import shutil
import json
from pathlib import Path
from typing import Dict

from learning_engine import load_task_summary
from manager import load_contract, load_state
from promotion_engine import resolve_rule_for_error
from recovery_engine import apply_recovery_action, classify_failure
import sys

CONTROL_CENTER_DIR = Path("/Users/mac_claw/.openclaw/workspace/tools/openmoss/control_center")
if str(CONTROL_CENTER_DIR) not in sys.path:
    sys.path.insert(0, str(CONTROL_CENTER_DIR))

from stpa_auditor import audit_mission, evaluate_stage_gate
from topology_mapper import build_topology
from event_bus import publish_event
from governance_runtime import build_governance_bundle


NON_BLOCKING_PREFLIGHT_STATUSES = {
    "durable_permission_guard_applied",
    "durable_path_guard_applied",
    "durable_slowdown_policy_requested",
    "state_reset_only",
    "tool_switch_recommended",
    "permission_guard_verified",
    "path_guard_verified",
    "dependency_guard_verified",
}

APPROVALS_ROOT = Path("/Users/mac_claw/.openclaw/workspace/tools/openmoss/runtime/control_center/approvals")
MISSIONS_ROOT = Path("/Users/mac_claw/.openclaw/workspace/tools/openmoss/runtime/control_center/missions")
COMMAND_FALLBACKS = {
    "openclaw": [
        "/opt/homebrew/bin/openclaw",
        "/usr/local/bin/openclaw",
    ],
    "rg": [
        "/opt/homebrew/bin/rg",
        "/usr/local/bin/rg",
        "/Users/mac_claw/.vscode/extensions/openai.chatgpt-26.318.11754-darwin-arm64/bin/macos-aarch64/rg",
    ],
}


def _normalize_path(raw: str) -> Path:
    """
    中文注解：
    - 功能：实现 `_normalize_path` 对应的处理逻辑。
    - 角色：属于本模块中的内部辅助逻辑；私有函数通常服务同文件主流程，公共函数通常作为跨模块入口或能力接口。
    - 调用关系：建议结合本文件的模块说明、调用方以及同名相关辅助函数一起阅读。
    """
    return Path(raw).expanduser()


def _resolve_command_path(command: str) -> str:
    """
    中文注解：
    - 功能：实现 `_resolve_command_path` 对应的处理逻辑。
    - 角色：属于本模块中的内部辅助逻辑；私有函数通常服务同文件主流程，公共函数通常作为跨模块入口或能力接口。
    - 调用关系：建议结合本文件的模块说明、调用方以及同名相关辅助函数一起阅读。
    """
    if not command:
        return ""
    if "/" in command:
        candidate = str(Path(command).expanduser())
        return candidate if Path(candidate).exists() else ""
    resolved = shutil.which(command)
    if resolved:
        return resolved
    for candidate in COMMAND_FALLBACKS.get(command, []):
        expanded = str(Path(candidate).expanduser())
        if Path(expanded).exists():
            return expanded
    return ""


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


def _extract_missing_command(error_text: str) -> str:
    """
    中文注解：
    - 功能：实现 `_extract_missing_command` 对应的处理逻辑。
    - 角色：属于本模块中的内部辅助逻辑；私有函数通常服务同文件主流程，公共函数通常作为跨模块入口或能力接口。
    - 调用关系：建议结合本文件的模块说明、调用方以及同名相关辅助函数一起阅读。
    """
    match = re.search(r"command not found:\s*([A-Za-z0-9._/-]+)", error_text, re.IGNORECASE)
    return match.group(1).strip() if match else ""


def _run_permission_guard(error_text: str) -> Dict[str, object]:
    """
    中文注解：
    - 功能：实现 `_run_permission_guard` 对应的处理逻辑。
    - 角色：属于本模块中的内部辅助逻辑；私有函数通常服务同文件主流程，公共函数通常作为跨模块入口或能力接口。
    - 调用关系：建议结合本文件的模块说明、调用方以及同名相关辅助函数一起阅读。
    """
    path = _extract_path(error_text)
    if not path:
        return {"ok": False, "status": "permission_guard_missing_path"}
    if path.exists():
        try:
            mode = path.stat().st_mode | 0o100
            path.chmod(mode)
        except OSError as exc:
            return {"ok": False, "status": "permission_guard_failed", "error": str(exc), "path": str(path)}
        return {"ok": True, "status": "permission_guard_verified", "path": str(path)}
    parent = path.parent
    try:
        parent.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        return {"ok": False, "status": "permission_guard_parent_create_failed", "error": str(exc), "path": str(parent)}
    return {"ok": True, "status": "permission_guard_verified", "path": str(parent)}


def _run_path_guard(error_text: str) -> Dict[str, object]:
    """
    中文注解：
    - 功能：实现 `_run_path_guard` 对应的处理逻辑。
    - 角色：属于本模块中的内部辅助逻辑；私有函数通常服务同文件主流程，公共函数通常作为跨模块入口或能力接口。
    - 调用关系：建议结合本文件的模块说明、调用方以及同名相关辅助函数一起阅读。
    """
    path = _extract_path(error_text)
    if not path:
        return {"ok": False, "status": "path_guard_missing_path"}
    target = path if path.suffix == "" else path.parent
    try:
        target.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        return {"ok": False, "status": "path_guard_failed", "error": str(exc), "path": str(target)}
    return {"ok": True, "status": "path_guard_verified", "path": str(target)}


def _run_dependency_guard(error_text: str) -> Dict[str, object]:
    """
    中文注解：
    - 功能：实现 `_run_dependency_guard` 对应的处理逻辑。
    - 角色：属于本模块中的内部辅助逻辑；私有函数通常服务同文件主流程，公共函数通常作为跨模块入口或能力接口。
    - 调用关系：建议结合本文件的模块说明、调用方以及同名相关辅助函数一起阅读。
    """
    command = _extract_missing_command(error_text)
    if not command:
        return {"ok": False, "status": "dependency_guard_unknown_dependency"}
    if "/" in command:
        dependency_exists = Path(command).expanduser().exists()
    else:
        dependency_exists = shutil.which(command) is not None
    if dependency_exists:
        return {"ok": True, "status": "dependency_guard_verified", "dependency": command}
    return {"ok": False, "status": "dependency_missing", "dependency": command}


def _run_required_commands_guard(commands: list[str]) -> Dict[str, object]:
    """
    中文注解：
    - 功能：实现 `_run_required_commands_guard` 对应的处理逻辑。
    - 角色：属于本模块中的内部辅助逻辑；私有函数通常服务同文件主流程，公共函数通常作为跨模块入口或能力接口。
    - 调用关系：建议结合本文件的模块说明、调用方以及同名相关辅助函数一起阅读。
    """
    resolved = {command: _resolve_command_path(command) for command in commands if command}
    missing = [command for command, path in resolved.items() if not path]
    if missing:
        return {"ok": False, "status": "required_commands_missing", "missing_commands": missing}
    return {"ok": True, "status": "required_commands_verified", "commands": commands, "resolved_commands": resolved}


def _run_required_paths_guard(paths: list[str]) -> Dict[str, object]:
    """
    中文注解：
    - 功能：实现 `_run_required_paths_guard` 对应的处理逻辑。
    - 角色：属于本模块中的内部辅助逻辑；私有函数通常服务同文件主流程，公共函数通常作为跨模块入口或能力接口。
    - 调用关系：建议结合本文件的模块说明、调用方以及同名相关辅助函数一起阅读。
    """
    missing = [raw for raw in paths if raw and not _normalize_path(raw).exists()]
    if missing:
        return {"ok": False, "status": "required_paths_missing", "missing_paths": missing}
    return {"ok": True, "status": "required_paths_verified", "paths": paths}


def _run_writable_paths_guard(paths: list[str]) -> Dict[str, object]:
    """
    中文注解：
    - 功能：实现 `_run_writable_paths_guard` 对应的处理逻辑。
    - 角色：属于本模块中的内部辅助逻辑；私有函数通常服务同文件主流程，公共函数通常作为跨模块入口或能力接口。
    - 调用关系：建议结合本文件的模块说明、调用方以及同名相关辅助函数一起阅读。
    """
    verified = []
    for raw in paths:
        if not raw:
            continue
        path = _normalize_path(raw)
        target = path if path.exists() and path.is_dir() else path.parent if path.suffix else path
        try:
            target.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            return {"ok": False, "status": "writable_path_prepare_failed", "path": str(target), "error": str(exc)}
        if not target.exists():
            return {"ok": False, "status": "writable_path_missing_after_prepare", "path": str(target)}
        if not os.access(target, os.W_OK):
            return {"ok": False, "status": "writable_path_not_writable", "path": str(target)}
        verified.append(str(target))
    return {"ok": True, "status": "writable_paths_verified", "paths": verified}


def _run_contract_guards(task_id: str, stage_name: str) -> Dict[str, object]:
    """
    中文注解：
    - 功能：实现 `_run_contract_guards` 对应的处理逻辑。
    - 角色：属于本模块中的内部辅助逻辑；私有函数通常服务同文件主流程，公共函数通常作为跨模块入口或能力接口。
    - 调用关系：建议结合本文件的模块说明、调用方以及同名相关辅助函数一起阅读。
    """
    contract = load_contract(task_id)
    stage = next((item for item in contract.stages if item.name == stage_name), None)
    if not stage:
        return {"ok": True, "status": "no_stage_contract"}
    policy = stage.execution_policy or {}
    approval_requirements = [str(item).strip() for item in policy.get("approval_requirements", []) if str(item).strip()]
    approval_pending_ids = [str(item).strip() for item in policy.get("approval_pending_ids", []) if str(item).strip()]
    approval_payload = contract.metadata.get("approval", {})
    approval_path = APPROVALS_ROOT / f"{task_id}.json"
    if approval_path.exists():
        approval_payload = json.loads(approval_path.read_text(encoding="utf-8"))
    approval_decisions = approval_payload.get("decisions", {})
    commands = [str(item).strip() for item in policy.get("required_commands", []) if str(item).strip()]
    required_paths = [str(item).strip() for item in policy.get("required_paths", []) if str(item).strip()]
    writable_paths = [str(item).strip() for item in policy.get("writable_paths", []) if str(item).strip()]

    results = []
    if approval_requirements:
        unresolved = [
            item for item in approval_requirements
            if approval_decisions.get(item, {}).get("status") != "approved"
        ]
        if unresolved:
            return {
                "ok": False,
                "status": "approval_required",
                "results": [
                    {
                        "ok": False,
                        "status": "approval_pending",
                        "pending_ids": unresolved,
                        "declared_pending_ids": approval_pending_ids,
                    }
                ],
            }
        results.append({"ok": True, "status": "approval_verified", "approved_ids": approval_requirements})
    if commands:
        result = _run_required_commands_guard(commands)
        results.append(result)
        if not result.get("ok"):
            return {"ok": False, "status": "contract_preflight_blocked", "results": results}
    if required_paths:
        result = _run_required_paths_guard(required_paths)
        results.append(result)
        if not result.get("ok"):
            return {"ok": False, "status": "contract_preflight_blocked", "results": results}
    if writable_paths:
        result = _run_writable_paths_guard(writable_paths)
        results.append(result)
        if not result.get("ok"):
            return {"ok": False, "status": "contract_preflight_blocked", "results": results}
    if results:
        return {"ok": True, "status": "contract_preflight_applied", "results": results}
    return {"ok": True, "status": "no_contract_preflight_rules"}


def _run_stpa_guard(task_id: str, stage_name: str) -> Dict[str, object]:
    """
    中文注解：
    - 功能：实现 `_run_stpa_guard` 对应的处理逻辑。
    - 角色：属于本模块中的内部辅助逻辑；私有函数通常服务同文件主流程，公共函数通常作为跨模块入口或能力接口。
    - 调用关系：建议结合本文件的模块说明、调用方以及同名相关辅助函数一起阅读。
    """
    mission_path = MISSIONS_ROOT / f"{task_id}.json"
    if not mission_path.exists():
        return {"ok": True, "status": "no_mission_for_stpa"}
    mission = json.loads(mission_path.read_text(encoding="utf-8"))
    approval_path = APPROVALS_ROOT / f"{task_id}.json"
    approval = mission.get("approval", {})
    if approval_path.exists():
        approval = json.loads(approval_path.read_text(encoding="utf-8"))
    topology = mission.get("topology", {}) or build_topology(mission.get("intent", {}), mission.get("selected_plan", {}))
    stpa = audit_mission(mission.get("intent", {}), mission.get("selected_plan", {}), topology, approval)
    gate = evaluate_stage_gate(stpa, stage_name)
    if gate.get("ok"):
        return {"ok": True, "status": "stpa_guard_passed", "stpa": stpa}
    return {"ok": False, "status": "stpa_guard_blocked", "stpa": stpa, "gate": gate}


def _run_stage_specific_guard(error_text: str, rule: Dict[str, object]) -> Dict[str, object]:
    """
    中文注解：
    - 功能：实现 `_run_stage_specific_guard` 对应的处理逻辑。
    - 角色：属于本模块中的内部辅助逻辑；私有函数通常服务同文件主流程，公共函数通常作为跨模块入口或能力接口。
    - 调用关系：建议结合本文件的模块说明、调用方以及同名相关辅助函数一起阅读。
    """
    classification = classify_failure(error_text)
    if classification == "permission_error":
        return _run_permission_guard(error_text)
    if classification == "missing_dependency":
        path = _extract_path(error_text)
        if path:
            return _run_path_guard(error_text)
        return _run_dependency_guard(error_text)
    if classification == "anti_automation_or_rate_limit":
        return {"ok": True, "status": "durable_slowdown_policy_requested", "note": rule.get("prevention_hint", "")}
    if classification == "auth_or_config_error":
        return {"ok": False, "status": "preflight_needs_secret_or_config"}
    return {"ok": False, "status": "no_stage_specific_guard"}


def _load_mission_payload(task_id: str, contract, state) -> Dict[str, object]:
    mission_path = MISSIONS_ROOT / f"{task_id}.json"
    if mission_path.exists():
        try:
            return json.loads(mission_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            pass
    return {
        "task_id": task_id,
        "selected_plan": (contract.metadata.get("control_center", {}) or {}).get("selected_plan", {}),
        "intent": (contract.metadata.get("control_center", {}) or {}).get("intent", {}),
        "challenge": state.metadata.get("last_challenge", {}) or {},
        "approval": contract.metadata.get("approval", {}) or {},
        "authorized_session": contract.metadata.get("authorized_session", {}) or {},
        "human_checkpoint": contract.metadata.get("human_checkpoint", {}) or {},
    }


def _emit_preflight_event(task_id: str, stage_name: str, event_suffix: str, payload: Dict[str, object]) -> Dict[str, object]:
    return publish_event(
        f"stage.{stage_name}.{event_suffix}",
        {
            "task_id": task_id,
            "stage_name": stage_name,
            **payload,
        },
    )


def run_stage_preflight(task_id: str, stage_name: str) -> Dict[str, object]:
    """
    中文注解：
    - 功能：实现 `run_stage_preflight` 对应的处理逻辑。
    - 角色：属于本模块中的对外可见逻辑；私有函数通常服务同文件主流程，公共函数通常作为跨模块入口或能力接口。
    - 调用关系：建议结合本文件的模块说明、调用方以及同名相关辅助函数一起阅读。
    """
    contract = load_contract(task_id)
    state_obj = load_state(task_id)
    mission = _load_mission_payload(task_id, contract, state_obj)
    governance = build_governance_bundle(task_id, stage_name, contract.to_dict(), state_obj.to_dict(), mission)
    pre_execute_event = _emit_preflight_event(
        task_id,
        stage_name,
        "pre_execute",
        {"mission": mission, "governance": governance},
    )
    contract_preflight = _run_contract_guards(task_id, stage_name)
    contract_applied = contract_preflight.get("status") not in {"no_stage_contract", "no_contract_preflight_rules"}
    if contract_applied and not contract_preflight.get("ok", False):
        response = {
            "ok": False,
            "status": "preflight_blocked",
            "guard_type": "contract",
            "action": "satisfy_stage_contract_preflight",
            "result": contract_preflight,
        }
        blocked_event = _emit_preflight_event(
            task_id,
            stage_name,
            "preflight_blocked",
            {"mission": mission, "governance": governance, "preflight": response},
        )
        response["hook_event"] = {"pre_execute": pre_execute_event, "terminal": blocked_event}
        return response
    stpa_preflight = _run_stpa_guard(task_id, stage_name)
    if not stpa_preflight.get("ok", False):
        response = {
            "ok": False,
            "status": "preflight_blocked",
            "guard_type": "stpa",
            "action": "resolve_stpa_control_gap",
            "result": stpa_preflight,
        }
        blocked_event = _emit_preflight_event(
            task_id,
            stage_name,
            "preflight_blocked",
            {"mission": mission, "governance": governance, "preflight": response},
        )
        response["hook_event"] = {"pre_execute": pre_execute_event, "terminal": blocked_event}
        return response

    summary = load_task_summary(task_id)
    last_failure = summary.get("last_failure") or {}
    if last_failure.get("stage") != stage_name:
        if contract_applied:
            response = {
                "ok": True,
                "status": "preflight_applied",
                "guard_type": "contract",
                "action": "stage_contract_preflight",
                "result": contract_preflight,
            }
            terminal_event = _emit_preflight_event(
                task_id,
                stage_name,
                "preflight_passed",
                {"mission": mission, "governance": governance, "preflight": response},
            )
            response["hook_event"] = {"pre_execute": pre_execute_event, "terminal": terminal_event}
            return response
        response = {"ok": True, "status": "no_preflight_needed"}
        terminal_event = _emit_preflight_event(
            task_id,
            stage_name,
            "preflight_passed",
            {"mission": mission, "governance": governance, "preflight": response},
        )
        response["hook_event"] = {"pre_execute": pre_execute_event, "terminal": terminal_event}
        return response
    error_text = str(last_failure.get("error") or "").strip()
    if not error_text:
        if contract_applied:
            response = {
                "ok": True,
                "status": "preflight_applied",
                "guard_type": "contract",
                "action": "stage_contract_preflight",
                "result": contract_preflight,
            }
            terminal_event = _emit_preflight_event(
                task_id,
                stage_name,
                "preflight_passed",
                {"mission": mission, "governance": governance, "preflight": response},
            )
            response["hook_event"] = {"pre_execute": pre_execute_event, "terminal": terminal_event}
            return response
        response = {"ok": True, "status": "no_preflight_needed"}
        terminal_event = _emit_preflight_event(
            task_id,
            stage_name,
            "preflight_passed",
            {"mission": mission, "governance": governance, "preflight": response},
        )
        response["hook_event"] = {"pre_execute": pre_execute_event, "terminal": terminal_event}
        return response

    rule = resolve_rule_for_error(error_text)
    if not rule:
        if contract_applied:
            response = {
                "ok": True,
                "status": "preflight_applied",
                "guard_type": "contract",
                "action": "stage_contract_preflight",
                "result": contract_preflight,
            }
            terminal_event = _emit_preflight_event(
                task_id,
                stage_name,
                "preflight_passed",
                {"mission": mission, "governance": governance, "preflight": response},
            )
            response["hook_event"] = {"pre_execute": pre_execute_event, "terminal": terminal_event}
            return response
        response = {"ok": True, "status": "no_promoted_rule"}
        terminal_event = _emit_preflight_event(
            task_id,
            stage_name,
            "preflight_passed",
            {"mission": mission, "governance": governance, "preflight": response},
        )
        response["hook_event"] = {"pre_execute": pre_execute_event, "terminal": terminal_event}
        return response

    action = str(rule.get("preferred_action") or "").strip()
    if not action:
        if contract_applied:
            response = {
                "ok": True,
                "status": "preflight_applied",
                "guard_type": "contract",
                "action": "stage_contract_preflight",
                "result": contract_preflight,
            }
            terminal_event = _emit_preflight_event(
                task_id,
                stage_name,
                "preflight_passed",
                {"mission": mission, "governance": governance, "preflight": response},
            )
            response["hook_event"] = {"pre_execute": pre_execute_event, "terminal": terminal_event}
            return response
        response = {"ok": True, "status": "no_preflight_action"}
        terminal_event = _emit_preflight_event(
            task_id,
            stage_name,
            "preflight_passed",
            {"mission": mission, "governance": governance, "preflight": response},
        )
        response["hook_event"] = {"pre_execute": pre_execute_event, "terminal": terminal_event}
        return response

    guard_result = _run_stage_specific_guard(error_text, rule)
    if guard_result.get("status") not in {"no_stage_specific_guard", "dependency_guard_unknown_dependency"}:
        continue_execution = bool(guard_result.get("ok"))
        response = {
            "ok": continue_execution,
            "status": "preflight_applied" if continue_execution else "preflight_blocked",
            "guard_type": "contract+learned" if contract_applied else classify_failure(error_text),
            "action": action,
            "result": {
                "contract_preflight": contract_preflight if contract_applied else None,
                "learned_preflight": guard_result,
            },
            "error_text": error_text,
            "rule": rule,
        }
        terminal_event = _emit_preflight_event(
            task_id,
            stage_name,
            "preflight_passed" if continue_execution else "preflight_blocked",
            {"mission": mission, "governance": governance, "preflight": response},
        )
        response["hook_event"] = {"pre_execute": pre_execute_event, "terminal": terminal_event}
        return response

    result = apply_recovery_action(action, error_text, task_id=task_id)
    continue_execution = result.get("status") in NON_BLOCKING_PREFLIGHT_STATUSES
    response = {
        "ok": continue_execution,
        "status": "preflight_applied" if continue_execution else "preflight_blocked",
        "guard_type": "contract+generic" if contract_applied else "generic",
        "action": action,
        "result": {
            "contract_preflight": contract_preflight if contract_applied else None,
            "learned_preflight": result,
        },
        "error_text": error_text,
        "rule": rule,
    }
    terminal_event = _emit_preflight_event(
        task_id,
        stage_name,
        "preflight_passed" if continue_execution else "preflight_blocked",
        {"mission": mission, "governance": governance, "preflight": response},
    )
    response["hook_event"] = {"pre_execute": pre_execute_event, "terminal": terminal_event}
    return response
