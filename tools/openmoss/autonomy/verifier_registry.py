#!/usr/bin/env python3

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any, Dict


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
    "command_exit_zero": verify_command_exit_zero,
    "all": verify_all,
}


def run_verifier(spec: Dict[str, Any]) -> Dict[str, Any]:
    verifier_type = str(spec.get("type") or "none")
    verifier = VERIFIERS.get(verifier_type, verify_not_configured)
    result = verifier(spec)
    result["verifier_type"] = verifier_type
    return result
