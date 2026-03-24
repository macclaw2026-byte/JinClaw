#!/usr/bin/env python3

from __future__ import annotations

import json
from typing import Dict, List

from security_policy import default_security_policy


def audit_mission(intent: Dict[str, object], selected_plan: Dict[str, object], topology: Dict[str, object], approval: Dict[str, object]) -> Dict[str, object]:
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
