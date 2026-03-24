#!/usr/bin/env python3

from __future__ import annotations

import json
from typing import Dict, List


def build_htn_tree(intent: Dict[str, object], selected_plan: Dict[str, object], topology: Dict[str, object], fractal: Dict[str, object]) -> Dict[str, object]:
    execute_children = []
    for loop in fractal.get("loops", []):
        execute_children.append(
            {
                "node_id": loop.get("loop_id", ""),
                "kind": "subtask",
                "goal": loop.get("goal", ""),
                "verify_with": loop.get("verify_with", []),
                "dependencies": loop.get("dependencies", []),
                "risk_checks": loop.get("risk_checks", []),
            }
        )
    root = {
        "node_id": "mission-root",
        "kind": "mission",
        "goal": intent.get("goal", ""),
        "selected_plan_id": selected_plan.get("plan_id", ""),
        "children": [
            {
                "node_id": "stage-understand",
                "kind": "stage",
                "goal": "anchor the goal, constraints, and success criteria",
                "children": [],
            },
            {
                "node_id": "stage-plan",
                "kind": "stage",
                "goal": "compare and select a safe execution path",
                "children": [],
            },
            {
                "node_id": "stage-execute",
                "kind": "stage",
                "goal": selected_plan.get("summary", ""),
                "children": execute_children,
            },
            {
                "node_id": "stage-verify",
                "kind": "stage",
                "goal": "verify the result and confirm the safety boundary held",
                "children": [],
            },
            {
                "node_id": "stage-learn",
                "kind": "stage",
                "goal": "persist durable lessons and reusable rules",
                "children": [],
            },
        ],
    }
    return {
        "mode": "hierarchical_task_network",
        "root": root,
        "node_count": 1 + len(root["children"]) + len(execute_children),
        "verification_nodes": topology.get("verification_nodes", []),
        "critical_dimensions": topology.get("critical_dimensions", []),
    }


def select_htn_focus(htn: Dict[str, object], stage_name: str, stage_attempts: int = 0) -> Dict[str, object]:
    return select_htn_focus_by_cursor(htn, stage_name, stage_attempts)


def select_htn_focus_by_cursor(htn: Dict[str, object], stage_name: str, subtask_cursor: int = 0) -> Dict[str, object]:
    children = htn.get("root", {}).get("children", [])
    stage_node = next((child for child in children if child.get("node_id") == f"stage-{stage_name}"), {})
    if not stage_node:
        return {
            "stage_name": stage_name,
            "focus_node": {},
            "focus_reason": "no_htn_stage_node",
        }
    if stage_name != "execute" or not stage_node.get("children"):
        return {
            "stage_name": stage_name,
            "focus_node": stage_node,
            "focus_reason": "stage-level_focus",
        }
    index = min(max(subtask_cursor, 0), len(stage_node["children"]) - 1)
    return {
        "stage_name": stage_name,
        "focus_node": stage_node["children"][index],
        "parent_node": stage_node.get("node_id", ""),
        "focus_reason": "execute-subtask_focus",
    }


def main() -> int:
    import argparse

    parser = argparse.ArgumentParser(description="Build and inspect a simple HTN tree for a mission")
    parser.add_argument("--intent-json", required=True)
    parser.add_argument("--plan-json", required=True)
    parser.add_argument("--topology-json", required=True)
    parser.add_argument("--fractal-json", required=True)
    parser.add_argument("--stage-name", default="")
    parser.add_argument("--stage-attempts", type=int, default=0)
    args = parser.parse_args()
    htn = build_htn_tree(
        json.loads(args.intent_json),
        json.loads(args.plan_json),
        json.loads(args.topology_json),
        json.loads(args.fractal_json),
    )
    payload = {"htn": htn}
    if args.stage_name:
        payload["focus"] = select_htn_focus(htn, args.stage_name, args.stage_attempts)
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
