#!/usr/bin/env python3

from __future__ import annotations

import json
from typing import Dict, List


DEFAULT_NETWORK_ALLOW_PATTERNS = [
    "github.com",
    "raw.githubusercontent.com",
    "docs.",
    "developer.",
    "api.",
]


def default_security_policy() -> Dict[str, object]:
    return {
        "principle": "solve_by_all_reasonable_means_without_crossing_security_boundaries",
        "data_security_first": True,
        "network_security_first": True,
        "device_security_first": True,
        "forbidden_actions": [
            "execute_untrusted_remote_code",
            "exfiltrate_local_sensitive_data",
            "bypass_authentication",
            "bypass_paywalls_or_access_controls",
            "disable_security_controls",
            "use_browser_auth_state_without_explicit_review",
        ],
        "network_allow_patterns": DEFAULT_NETWORK_ALLOW_PATTERNS,
        "review_levels": {
            "public_read": "auto_review",
            "public_download": "manual_approval",
            "dependency_install": "manual_approval",
            "external_code_execution": "manual_approval",
            "sensitive_browser_state": "manual_approval",
            "authorized_session": "manual_approval",
            "human_checkpoint": "manual_review",
        },
    }


def classify_external_action(action_type: str) -> Dict[str, object]:
    table = {
        "public_read": {"risk": "low", "approval_mode": "auto_review"},
        "public_download": {"risk": "medium", "approval_mode": "manual_approval"},
        "dependency_install": {"risk": "high", "approval_mode": "manual_approval"},
        "external_code_execution": {"risk": "critical", "approval_mode": "manual_approval"},
        "sensitive_browser_state": {"risk": "critical", "approval_mode": "manual_approval"},
        "authorized_session": {"risk": "high", "approval_mode": "manual_approval"},
        "human_checkpoint": {"risk": "medium", "approval_mode": "manual_review"},
    }
    return table.get(action_type, {"risk": "high", "approval_mode": "manual_approval"})


def assess_plan_risk(plan: Dict[str, object]) -> Dict[str, object]:
    required = plan.get("external_actions", [])
    assessed = []
    highest = "low"
    order = {"low": 0, "medium": 1, "high": 2, "critical": 3}
    for item in required:
        details = classify_external_action(str(item.get("type", "")))
        assessed.append({**item, **details})
        if order[details["risk"]] > order[highest]:
            highest = details["risk"]
    return {"risk": highest, "actions": assessed}


def main() -> int:
    print(json.dumps(default_security_policy(), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
