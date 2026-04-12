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
- 文件路径：`tools/openmoss/control_center/security_policy.py`
- 文件作用：负责控制中心中与 `security_policy` 相关的编排、分析或决策逻辑。
- 顶层函数：default_security_policy、classify_external_action、assess_plan_risk、main。
- 顶层类：无顶层类。
- 阅读建议：先看模块说明，再按函数/类 docstring 顺着主流程理解调用关系。
"""
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
    """
    中文注解：
    - 功能：实现 `default_security_policy` 对应的处理逻辑。
    - 角色：属于本模块中的对外可见逻辑；私有函数通常服务同文件主流程，公共函数通常作为跨模块入口或能力接口。
    - 调用关系：建议结合本文件的模块说明、调用方以及同名相关辅助函数一起阅读。
    """
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
    """
    中文注解：
    - 功能：实现 `classify_external_action` 对应的处理逻辑。
    - 角色：属于本模块中的对外可见逻辑；私有函数通常服务同文件主流程，公共函数通常作为跨模块入口或能力接口。
    - 调用关系：建议结合本文件的模块说明、调用方以及同名相关辅助函数一起阅读。
    """
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
    """
    中文注解：
    - 功能：实现 `assess_plan_risk` 对应的处理逻辑。
    - 角色：属于本模块中的对外可见逻辑；私有函数通常服务同文件主流程，公共函数通常作为跨模块入口或能力接口。
    - 调用关系：建议结合本文件的模块说明、调用方以及同名相关辅助函数一起阅读。
    """
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
    """
    中文注解：
    - 功能：实现 `main` 对应的处理逻辑。
    - 角色：属于本模块中的对外可见逻辑；私有函数通常服务同文件主流程，公共函数通常作为跨模块入口或能力接口。
    - 调用关系：建议结合本文件的模块说明、调用方以及同名相关辅助函数一起阅读。
    """
    print(json.dumps(default_security_policy(), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
