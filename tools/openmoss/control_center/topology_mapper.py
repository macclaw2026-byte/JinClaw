#!/usr/bin/env python3

from __future__ import annotations

import json
from typing import Dict, List


def build_topology(intent: Dict[str, object], selected_plan: Dict[str, object]) -> Dict[str, object]:
    task_types = [str(item) for item in intent.get("task_types", [])]
    dependencies: List[str] = []
    verification_nodes: List[str] = ["verify_goal", "verify_security_boundary"]
    risk_nodes: List[str] = []
    semantic_anchor = {
        "goal": intent.get("goal", ""),
        "keywords": intent.get("keywords", [])[:12],
        "done_definition": intent.get("done_definition", ""),
        "hard_constraints": intent.get("hard_constraints", [])[:6],
    }
    critical_dimensions = ["goal_alignment", "verification", "security_boundary"]
    if "dependency" in task_types:
        dependencies.append("external_tool_candidate")
        verification_nodes.append("verify_approval_state")
        risk_nodes.append("third_party_artifact_risk")
        critical_dimensions.append("dependency_review")
    if "web" in task_types:
        dependencies.append("public_source_access")
        verification_nodes.append("verify_source_quality")
        risk_nodes.append("untrusted_external_content")
        critical_dimensions.append("source_trust")
    if "data" in task_types:
        dependencies.append("evidence_store")
        verification_nodes.append("verify_output_schema")
        critical_dimensions.append("output_integrity")
    covered_dimensions = sorted(set(critical_dimensions))
    return {
        "semantic_anchor": semantic_anchor,
        "task_types": task_types,
        "selected_plan_id": selected_plan.get("plan_id", ""),
        "dependency_nodes": dependencies,
        "verification_nodes": verification_nodes,
        "risk_nodes": risk_nodes,
        "critical_dimensions": covered_dimensions,
        "unmapped_dimensions": [],
        "coverage_matrix": {
            "dependencies": len(dependencies),
            "verification": len(verification_nodes),
            "risks": len(risk_nodes),
            "critical_dimensions": len(covered_dimensions),
        },
        "coverage_goal": "no_critical_dependency_or_verification_branch_left_unmapped",
    }


def main() -> int:
    import argparse

    parser = argparse.ArgumentParser(description="Build a task topology map for control-center missions")
    parser.add_argument("--intent-json", required=True)
    parser.add_argument("--plan-json", required=True)
    args = parser.parse_args()
    print(json.dumps(build_topology(json.loads(args.intent_json), json.loads(args.plan_json)), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
