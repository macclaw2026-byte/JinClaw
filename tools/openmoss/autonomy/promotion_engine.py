#!/usr/bin/env python3

from __future__ import annotations

import json
from pathlib import Path

from learning_engine import get_error_recurrence

LEARNING_ROOT = Path("/Users/mac_claw/.openclaw/workspace/tools/openmoss/runtime/autonomy/learning")
PROMOTED_RULES = LEARNING_ROOT / "promoted_rules.json"
RECURRENCE = LEARNING_ROOT / "error_recurrence.json"


def _read_json(path: Path, default):
    if not path.exists():
        return default
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, payload) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _classify_failure(error_text: str) -> str:
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


def load_promoted_rules() -> dict:
    return _read_json(PROMOTED_RULES, {"rules": []})


def resolve_rule_for_error(error_text: str) -> dict | None:
    recurrence = get_error_recurrence(error_text)
    promoted = load_promoted_rules()
    for rule in promoted.get("rules", []):
        if rule.get("error_key") == recurrence.get("key"):
            if not rule.get("preferred_guard"):
                rule["preferred_guard"] = _classify_failure(error_text)
            return rule
    return None


def promote_recurring_errors(min_count: int = 2) -> dict:
    recurrence = _read_json(RECURRENCE, {"errors": {}})
    promoted = _read_json(PROMOTED_RULES, {"rules": []})
    existing_keys = {rule["error_key"] for rule in promoted["rules"]}
    added = []
    for key, item in recurrence.get("errors", {}).items():
        if item.get("count", 0) < min_count or key in existing_keys:
            continue
        failure_kind = _classify_failure(key)
        rule = {
            "error_key": key,
            "count": item.get("count", 0),
            "recommended_fix": "install stronger verifier and recovery path",
            "preferred_action": "install_preflight_guard_and_targeted_recovery",
            "preferred_guard": failure_kind,
            "prevention_hint": "add a durable preflight check before re-running the same stage",
            "tasks": item.get("tasks", []),
            "promotion_type": "durable_runtime_rule",
            "source": "error_recurrence",
        }
        promoted["rules"].append(rule)
        added.append(rule)
    _write_json(PROMOTED_RULES, promoted)
    return {"added": added, "total_rules": len(promoted["rules"])}


if __name__ == "__main__":
    print(json.dumps(promote_recurring_errors(), ensure_ascii=False, indent=2))
