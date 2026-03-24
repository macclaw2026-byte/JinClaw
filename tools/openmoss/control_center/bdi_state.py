#!/usr/bin/env python3

from __future__ import annotations

import json
from typing import Dict, List


def build_bdi_state(
    intent: Dict[str, object],
    selected_plan: Dict[str, object],
    approval: Dict[str, object],
    state: Dict[str, object],
    htn_focus: Dict[str, object],
    arbitration: Dict[str, object] | None = None,
) -> Dict[str, object]:
    pending_approvals = approval.get("pending", [])
    arbitration = arbitration or {}
    necessity_proof = arbitration.get("necessity_proof", {})
    plan_id = str(selected_plan.get("plan_id", ""))
    beliefs = {
        "task_types": intent.get("task_types", []),
        "risk_level": intent.get("risk_level", "unknown"),
        "current_stage": state.get("current_stage", ""),
        "task_status": state.get("status", ""),
        "pending_approvals": pending_approvals,
        "selected_plan_id": selected_plan.get("plan_id", ""),
        "blockers": state.get("blockers", []),
    }
    desires: List[str] = [
        "satisfy_user_goal",
        "preserve_security_boundaries",
        "leave verifiable evidence",
    ]
    if intent.get("needs_verification"):
        desires.append("complete_verified_closure")
    if pending_approvals:
        intentions = ["obtain_or_wait_for_required_approvals"]
    elif (
        plan_id == "audited_external_extension"
        and not necessity_proof.get("required", True)
        and selected_plan.get("external_actions")
    ):
        intentions = ["prove_necessity_before_switching"]
    elif state.get("status") == "recovering":
        intentions = ["repair_blocker_and_resume"]
    elif state.get("status") == "verifying":
        intentions = ["complete_verification"]
    elif state.get("current_stage") == "execute" and htn_focus.get("focus_node", {}).get("node_id"):
        intentions = [f"advance_{htn_focus['focus_node']['node_id']}"]
    else:
        intentions = [f"advance_{state.get('current_stage', 'task')}"]
    focus_node = htn_focus.get("focus_node", {})
    return {
        "beliefs": beliefs,
        "desires": desires,
        "intentions": intentions,
        "current_intention": intentions[0] if intentions else "monitor",
        "focus_node": {
            "node_id": focus_node.get("node_id", ""),
            "goal": focus_node.get("goal", ""),
        },
    }


def main() -> int:
    import argparse

    parser = argparse.ArgumentParser(description="Build a lightweight BDI state for the current mission cycle")
    parser.add_argument("--intent-json", required=True)
    parser.add_argument("--plan-json", required=True)
    parser.add_argument("--approval-json", required=True)
    parser.add_argument("--state-json", required=True)
    parser.add_argument("--htn-focus-json", required=True)
    args = parser.parse_args()
    print(
        json.dumps(
            build_bdi_state(
                json.loads(args.intent_json),
                json.loads(args.plan_json),
                json.loads(args.approval_json),
                json.loads(args.state_json),
                json.loads(args.htn_focus_json),
            ),
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
