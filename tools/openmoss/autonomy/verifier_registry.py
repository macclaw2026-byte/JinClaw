#!/usr/bin/env python3

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any, Dict


TASKS_ROOT = Path("/Users/mac_claw/.openclaw/workspace/tools/openmoss/runtime/autonomy/tasks")


def verify_not_configured(spec: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "ok": False,
        "status": "not_configured",
        "reason": "no verifier configured",
    }


def verify_file_exists(spec: Dict[str, Any]) -> Dict[str, Any]:
    path = Path(str(spec.get("path", ""))).expanduser()
    return {
        "ok": path.exists(),
        "status": "ok" if path.exists() else "missing",
        "path": str(path),
    }


def verify_text_contains(spec: Dict[str, Any]) -> Dict[str, Any]:
    path = Path(str(spec.get("path", ""))).expanduser()
    needle = str(spec.get("contains", ""))
    if not path.exists():
        return {"ok": False, "status": "missing", "path": str(path)}
    text = path.read_text(encoding="utf-8")
    return {
        "ok": needle in text,
        "status": "ok" if needle in text else "not_found",
        "path": str(path),
        "needle": needle,
    }


def verify_json_field_equals(spec: Dict[str, Any]) -> Dict[str, Any]:
    path = Path(str(spec.get("path", ""))).expanduser()
    field = str(spec.get("field", ""))
    expected = spec.get("equals")
    if not path.exists():
        return {"ok": False, "status": "missing", "path": str(path)}
    payload = json.loads(path.read_text(encoding="utf-8"))
    current = payload
    for part in [p for p in field.split(".") if p]:
        if not isinstance(current, dict) or part not in current:
            return {"ok": False, "status": "field_missing", "path": str(path), "field": field}
        current = current[part]
    return {
        "ok": current == expected,
        "status": "ok" if current == expected else "mismatch",
        "path": str(path),
        "field": field,
        "current": current,
        "expected": expected,
    }


def _resolve_field(payload: Dict[str, Any], field: str) -> tuple[bool, Any]:
    parts = [p for p in field.split(".") if p]
    candidates = [payload]
    metadata = payload.get("metadata")
    if isinstance(metadata, dict):
        candidates.append(metadata)
    for candidate in candidates:
        current: Any = candidate
        found = True
        for part in parts:
            if not isinstance(current, dict) or part not in current:
                found = False
                break
            current = current[part]
        if found:
            return True, current
    return False, None


def _load_task_state_payload(task_id: str) -> tuple[Path, Dict[str, Any] | None]:
    path = TASKS_ROOT / task_id / "state.json"
    if not path.exists():
        return path, None
    return path, json.loads(path.read_text(encoding="utf-8"))


def verify_task_state_metadata_equals(spec: Dict[str, Any]) -> Dict[str, Any]:
    task_id = str(spec.get("task_id", "")).strip()
    field = str(spec.get("field", "")).strip()
    expected = spec.get("equals")
    path, payload = _load_task_state_payload(task_id)
    if payload is None:
        return {"ok": False, "status": "task_state_missing", "task_id": task_id, "path": str(path)}
    found, current = _resolve_field(payload, field)
    if not found:
        return {"ok": False, "status": "field_missing", "task_id": task_id, "path": str(path), "field": field}
    return {
        "ok": current == expected,
        "status": "ok" if current == expected else "mismatch",
        "task_id": task_id,
        "path": str(path),
        "field": field,
        "current": current,
        "expected": expected,
    }


def verify_task_state_metadata_nonempty(spec: Dict[str, Any]) -> Dict[str, Any]:
    task_id = str(spec.get("task_id", "")).strip()
    field = str(spec.get("field", "")).strip()
    path, payload = _load_task_state_payload(task_id)
    if payload is None:
        return {"ok": False, "status": "task_state_missing", "task_id": task_id, "path": str(path)}
    found, current = _resolve_field(payload, field)
    if not found:
        return {"ok": False, "status": "field_missing", "task_id": task_id, "path": str(path), "field": field}
    is_nonempty = current not in {"", None, [], {}}
    return {
        "ok": bool(is_nonempty),
        "status": "ok" if is_nonempty else "empty",
        "task_id": task_id,
        "path": str(path),
        "field": field,
        "current": current,
    }


def verify_command_exit_zero(spec: Dict[str, Any]) -> Dict[str, Any]:
    command = spec.get("command") or []
    if not isinstance(command, list) or not command:
        return {"ok": False, "status": "invalid_command"}
    timeout = int(spec.get("timeout_seconds", 30))
    completed = subprocess.run(command, capture_output=True, text=True, check=False, timeout=timeout)
    return {
        "ok": completed.returncode == 0,
        "status": "ok" if completed.returncode == 0 else "command_failed",
        "command": command,
        "returncode": completed.returncode,
        "stdout": completed.stdout[-1000:],
        "stderr": completed.stderr[-1000:],
    }


def verify_all(spec: Dict[str, Any]) -> Dict[str, Any]:
    checks = spec.get("checks") or []
    if not isinstance(checks, list) or not checks:
        return {"ok": False, "status": "invalid_checks"}
    results = []
    all_ok = True
    for check in checks:
        if not isinstance(check, dict):
            results.append({"ok": False, "status": "invalid_check"})
            all_ok = False
            continue
        verifier_type = str(check.get("type") or "none")
        verifier = VERIFIERS.get(verifier_type, verify_not_configured)
        result = verifier(check)
        result["verifier_type"] = verifier_type
        results.append(result)
        if not result.get("ok"):
            all_ok = False
    return {
        "ok": all_ok,
        "status": "ok" if all_ok else "check_failed",
        "results": results,
    }


VERIFIERS = {
    "none": verify_not_configured,
    "file_exists": verify_file_exists,
    "text_contains": verify_text_contains,
    "json_field_equals": verify_json_field_equals,
    "task_state_metadata_equals": verify_task_state_metadata_equals,
    "task_state_metadata_nonempty": verify_task_state_metadata_nonempty,
    "command_exit_zero": verify_command_exit_zero,
    "all": verify_all,
}


def run_verifier(spec: Dict[str, Any]) -> Dict[str, Any]:
    verifier_type = str(spec.get("type") or "none")
    verifier = VERIFIERS.get(verifier_type, verify_not_configured)
    result = verifier(spec)
    result["verifier_type"] = verifier_type
    return result
