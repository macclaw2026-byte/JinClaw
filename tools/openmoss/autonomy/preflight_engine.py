#!/usr/bin/env python3

from __future__ import annotations

import os
import re
import shutil
import json
from pathlib import Path
from typing import Dict

from learning_engine import load_task_summary
from manager import load_contract
from promotion_engine import resolve_rule_for_error
from recovery_engine import apply_recovery_action, classify_failure
import sys

CONTROL_CENTER_DIR = Path("/Users/mac_claw/.openclaw/workspace/tools/openmoss/control_center")
if str(CONTROL_CENTER_DIR) not in sys.path:
    sys.path.insert(0, str(CONTROL_CENTER_DIR))

from stpa_auditor import audit_mission, evaluate_stage_gate
from topology_mapper import build_topology


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


def _normalize_path(raw: str) -> Path:
    return Path(raw).expanduser()


def _extract_path(error_text: str) -> Path | None:
    matches = re.findall(r"(/Users/[^\s:'\"]+|/tmp/[^\s:'\"]+|\.[/\w\-.]+)", error_text)
    if not matches:
        return None
    return Path(matches[0]).expanduser()


def _extract_missing_command(error_text: str) -> str:
    match = re.search(r"command not found:\s*([A-Za-z0-9._/-]+)", error_text, re.IGNORECASE)
    return match.group(1).strip() if match else ""


def _run_permission_guard(error_text: str) -> Dict[str, object]:
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
    missing = [command for command in commands if command and shutil.which(command) is None]
    if missing:
        return {"ok": False, "status": "required_commands_missing", "missing_commands": missing}
    return {"ok": True, "status": "required_commands_verified", "commands": commands}


def _run_required_paths_guard(paths: list[str]) -> Dict[str, object]:
    missing = [raw for raw in paths if raw and not _normalize_path(raw).exists()]
    if missing:
        return {"ok": False, "status": "required_paths_missing", "missing_paths": missing}
    return {"ok": True, "status": "required_paths_verified", "paths": paths}


def _run_writable_paths_guard(paths: list[str]) -> Dict[str, object]:
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


def run_stage_preflight(task_id: str, stage_name: str) -> Dict[str, object]:
    contract_preflight = _run_contract_guards(task_id, stage_name)
    contract_applied = contract_preflight.get("status") not in {"no_stage_contract", "no_contract_preflight_rules"}
    if contract_applied and not contract_preflight.get("ok", False):
        return {
            "ok": False,
            "status": "preflight_blocked",
            "guard_type": "contract",
            "action": "satisfy_stage_contract_preflight",
            "result": contract_preflight,
        }
    stpa_preflight = _run_stpa_guard(task_id, stage_name)
    if not stpa_preflight.get("ok", False):
        return {
            "ok": False,
            "status": "preflight_blocked",
            "guard_type": "stpa",
            "action": "resolve_stpa_control_gap",
            "result": stpa_preflight,
        }

    summary = load_task_summary(task_id)
    last_failure = summary.get("last_failure") or {}
    if last_failure.get("stage") != stage_name:
        if contract_applied:
            return {
                "ok": True,
                "status": "preflight_applied",
                "guard_type": "contract",
                "action": "stage_contract_preflight",
                "result": contract_preflight,
            }
        return {"ok": True, "status": "no_preflight_needed"}
    error_text = str(last_failure.get("error") or "").strip()
    if not error_text:
        if contract_applied:
            return {
                "ok": True,
                "status": "preflight_applied",
                "guard_type": "contract",
                "action": "stage_contract_preflight",
                "result": contract_preflight,
            }
        return {"ok": True, "status": "no_preflight_needed"}

    rule = resolve_rule_for_error(error_text)
    if not rule:
        if contract_applied:
            return {
                "ok": True,
                "status": "preflight_applied",
                "guard_type": "contract",
                "action": "stage_contract_preflight",
                "result": contract_preflight,
            }
        return {"ok": True, "status": "no_promoted_rule"}

    action = str(rule.get("preferred_action") or "").strip()
    if not action:
        if contract_applied:
            return {
                "ok": True,
                "status": "preflight_applied",
                "guard_type": "contract",
                "action": "stage_contract_preflight",
                "result": contract_preflight,
            }
        return {"ok": True, "status": "no_preflight_action"}

    guard_result = _run_stage_specific_guard(error_text, rule)
    if guard_result.get("status") not in {"no_stage_specific_guard", "dependency_guard_unknown_dependency"}:
        continue_execution = bool(guard_result.get("ok"))
        return {
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

    result = apply_recovery_action(action, error_text)
    continue_execution = result.get("status") in NON_BLOCKING_PREFLIGHT_STATUSES
    return {
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
