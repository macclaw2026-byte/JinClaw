#!/usr/bin/env python3

from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Dict

from cache_store import cache_get, cache_put
from htn_planner import build_htn_tree, select_htn_focus_by_cursor
from topology_mapper import build_topology
from fractal_decomposer import select_loop_focus
from fractal_decomposer import build_fractal_loops
from paths import APPROVALS_ROOT, MISSIONS_ROOT, SUMMARIES_ROOT


def _load_json(path: Path) -> Dict[str, object]:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def build_stage_context(task_id: str, stage_name: str, contract: Dict[str, object], state: Dict[str, object]) -> Dict[str, object]:
    cache_key = f"{task_id}:{stage_name}"
    mission = _load_json(MISSIONS_ROOT / f"{task_id}.json")
    summary = _load_json(SUMMARIES_ROOT / f"{task_id}.json")
    live_approval = _load_json(APPROVALS_ROOT / f"{task_id}.json")
    selected_plan = mission.get("selected_plan", {})
    topology = mission.get("topology", {}) or build_topology(mission.get("intent", {}), selected_plan)
    fractal = mission.get("fractal_loops", {}) or build_fractal_loops(mission.get("intent", {}), selected_plan, topology)
    htn = mission.get("htn", {}) or build_htn_tree(mission.get("intent", {}), selected_plan, topology, fractal)
    stage_contract = next((item for item in contract.get("stages", []) if item.get("name") == stage_name), {})
    stage_state = state.get("stages", {}).get(stage_name, {})
    stage_attempts = int(stage_state.get("attempts", 0) or 0)
    subtask_cursor = int(stage_state.get("subtask_cursor", max(stage_attempts - 1, 0)) or 0)
    fractal_focus = select_loop_focus(fractal, stage_name, stage_attempts)
    htn_focus = select_htn_focus_by_cursor(htn, stage_name, subtask_cursor)
    signature = json.dumps(
        {
            "task_id": task_id,
            "stage_name": stage_name,
            "goal": contract.get("user_goal", ""),
            "done_definition": contract.get("done_definition", ""),
            "selected_plan": selected_plan,
            "topology": topology,
            "fractal_focus": fractal_focus,
            "htn_focus": htn_focus,
            "state": {
                "current_stage": state.get("current_stage", ""),
                "status": state.get("status", ""),
                "next_action": state.get("next_action", ""),
                "blockers": state.get("blockers", []),
            },
            "summary": {
                "current_stage": summary.get("current_stage", ""),
                "status": summary.get("status", ""),
                "next_action": summary.get("next_action", ""),
                "blockers": summary.get("blockers", []),
                "pending_approvals": summary.get("pending_approvals", live_approval.get("pending", mission.get("approval", {}).get("pending", []))),
            },
        },
        ensure_ascii=False,
        sort_keys=True,
    )
    cached = cache_get("stage_context", cache_key, {})
    if cached and cached.get("signature") == signature:
        cached["cache_hit"] = True
        return cached
    payload = {
        "task_id": task_id,
        "stage_name": stage_name,
        "goal": contract.get("user_goal", ""),
        "stage_goal": stage_contract.get("goal", ""),
        "done_definition": contract.get("done_definition", ""),
        "selected_plan": {
            "plan_id": selected_plan.get("plan_id", ""),
            "label": selected_plan.get("label", ""),
            "summary": selected_plan.get("summary", ""),
            "steps": selected_plan.get("steps", []),
        },
        "topology_focus": {
            "semantic_anchor": topology.get("semantic_anchor", {}),
            "dependency_nodes": topology.get("dependency_nodes", []),
            "verification_nodes": topology.get("verification_nodes", []),
            "risk_nodes": topology.get("risk_nodes", []),
            "coverage_goal": topology.get("coverage_goal", ""),
        },
        "fractal_focus": fractal_focus,
        "htn_focus": htn_focus,
        "subtask_progress": {
            "cursor": subtask_cursor,
            "completed_subtasks": stage_state.get("completed_subtasks", []),
        },
        "batch_focus": state.get("metadata", {}).get("batch_focus", {}),
        "summary": {
            "current_stage": state.get("current_stage", "") or summary.get("current_stage", ""),
            "status": state.get("status", "") or summary.get("status", ""),
            "next_action": state.get("next_action", "") or summary.get("next_action", ""),
            "blockers": state.get("blockers", []) or summary.get("blockers", []),
            "pending_approvals": summary.get("pending_approvals", live_approval.get("pending", mission.get("approval", {}).get("pending", []))),
        },
        "allowed_tools": contract.get("allowed_tools", []),
        "signature": signature,
        "cache_hit": False,
    }
    cache_put("stage_context", cache_key, payload)
    return payload


def main() -> int:
    import argparse

    parser = argparse.ArgumentParser(description="Build a minimal stage context packet for execution")
    parser.add_argument("--task-id", required=True)
    parser.add_argument("--stage-name", required=True)
    parser.add_argument("--contract-json", required=True)
    parser.add_argument("--state-json", required=True)
    args = parser.parse_args()
    print(json.dumps(build_stage_context(args.task_id, args.stage_name, json.loads(args.contract_json), json.loads(args.state_json)), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
