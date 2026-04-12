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
- 文件路径：`tools/openmoss/control_center/stpa_auditor.py`
- 文件作用：负责控制中心中与 `stpa_auditor` 相关的编排、分析或决策逻辑。
- 顶层函数：audit_mission、evaluate_stage_gate、main。
- 顶层类：无顶层类。
- 阅读建议：先看模块说明，再按函数/类 docstring 顺着主流程理解调用关系。
"""
from __future__ import annotations

import json
from typing import Dict, List

from security_policy import default_security_policy


def audit_mission(intent: Dict[str, object], selected_plan: Dict[str, object], topology: Dict[str, object], approval: Dict[str, object]) -> Dict[str, object]:
    """
    中文注解：
    - 功能：实现 `audit_mission` 对应的处理逻辑。
    - 角色：属于本模块中的对外可见逻辑；私有函数通常服务同文件主流程，公共函数通常作为跨模块入口或能力接口。
    - 调用关系：建议结合本文件的模块说明、调用方以及同名相关辅助函数一起阅读。
    """
    policy = default_security_policy()
    pending_approvals = approval.get("pending", [])
    external_actions = selected_plan.get("external_actions", [])
    hazards: List[Dict[str, object]] = []
    unsafe_control_actions: List[Dict[str, object]] = []

    if pending_approvals:
        hazards.append(
            {
                "hazard_id": "unapproved_external_change",
                "severity": "high",
                "detail": "The mission still requires external changes that have not been fully approved.",
            }
        )
        unsafe_control_actions.append(
            {
                "control_id": "approval_before_external_change",
                "stage": "execute",
                "required": True,
                "satisfied": False,
                "detail": "Do not download, install, or execute external artifacts before approval is complete.",
            }
        )

    if topology.get("risk_nodes"):
        unsafe_control_actions.append(
            {
                "control_id": "risk_nodes_tracked",
                "stage": "plan",
                "required": True,
                "satisfied": True,
                "detail": "The topology includes explicit risk nodes that should be reviewed before execution.",
            }
        )

    if any(action.get("type") == "public_read" for action in external_actions):
        hazards.append(
            {
                "hazard_id": "untrusted_external_content",
                "severity": "medium",
                "detail": "Public sources may contain incomplete or misleading implementation guidance.",
            }
        )
        unsafe_control_actions.append(
            {
                "control_id": "source_trust_before_use",
                "stage": "execute",
                "required": True,
                "satisfied": True,
                "detail": "Prefer official docs and repositories before weaker public commentary.",
            }
        )

    unsafe_control_actions.append(
        {
            "control_id": "workspace_write_boundary",
            "stage": "execute",
            "required": True,
            "satisfied": True,
            "detail": "Any writes must stay inside approved workspace/output paths and preserve device safety.",
        }
    )

    unresolved = [item for item in unsafe_control_actions if item.get("required") and not item.get("satisfied")]
    return {
        "policy_principle": policy.get("principle", ""),
        "hazards": hazards,
        "unsafe_control_actions": unsafe_control_actions,
        "unresolved_controls": unresolved,
        "stage_gate": {
            "execute": not any(item.get("stage") == "execute" for item in unresolved),
            "plan": not any(item.get("stage") == "plan" for item in unresolved),
        },
    }


def evaluate_stage_gate(stpa: Dict[str, object], stage_name: str) -> Dict[str, object]:
    """
    中文注解：
    - 功能：实现 `evaluate_stage_gate` 对应的处理逻辑。
    - 角色：属于本模块中的对外可见逻辑；私有函数通常服务同文件主流程，公共函数通常作为跨模块入口或能力接口。
    - 调用关系：建议结合本文件的模块说明、调用方以及同名相关辅助函数一起阅读。
    """
    if stage_name not in {"plan", "execute", "verify"}:
        return {"ok": True, "status": "stpa_not_required_for_stage"}
    unresolved = [item for item in stpa.get("unresolved_controls", []) if item.get("stage") in {stage_name, "execute"}]
    if unresolved:
        return {
            "ok": False,
            "status": "stpa_control_gap",
            "unresolved_controls": unresolved,
        }
    return {"ok": True, "status": "stpa_stage_gate_passed"}


def main() -> int:
    """
    中文注解：
    - 功能：实现 `main` 对应的处理逻辑。
    - 角色：属于本模块中的对外可见逻辑；私有函数通常服务同文件主流程，公共函数通常作为跨模块入口或能力接口。
    - 调用关系：建议结合本文件的模块说明、调用方以及同名相关辅助函数一起阅读。
    """
    import argparse

    parser = argparse.ArgumentParser(description="Run a lightweight STPA-style control audit for a mission")
    parser.add_argument("--intent-json", required=True)
    parser.add_argument("--plan-json", required=True)
    parser.add_argument("--topology-json", required=True)
    parser.add_argument("--approval-json", required=True)
    parser.add_argument("--stage-name", default="")
    args = parser.parse_args()
    stpa = audit_mission(
        json.loads(args.intent_json),
        json.loads(args.plan_json),
        json.loads(args.topology_json),
        json.loads(args.approval_json),
    )
    payload = {"stpa": stpa}
    if args.stage_name:
        payload["stage_gate"] = evaluate_stage_gate(stpa, args.stage_name)
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
