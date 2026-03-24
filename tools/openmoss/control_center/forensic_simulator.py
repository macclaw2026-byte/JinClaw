#!/usr/bin/env python3

from __future__ import annotations

import json
from pathlib import Path
from typing import Dict, List

from fractal_decomposer import build_fractal_loops, select_loop_focus
from htn_planner import build_htn_tree, select_htn_focus_by_cursor
from paths import ADVISORIES_ROOT, MISSIONS_ROOT
from topology_mapper import build_topology


def _load_json(path: Path) -> Dict[str, object]:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def reconstruct_trace(task_id: str, state: Dict[str, object]) -> Dict[str, object]:
    mission = _load_json(MISSIONS_ROOT / f"{task_id}.json")
    advisory = _load_json(ADVISORIES_ROOT / f"{task_id}.json")
    control_center = mission.get("selected_plan", {})
    topology = mission.get("topology", {}) or build_topology(mission.get("intent", {}), control_center)
    fractal = mission.get("fractal_loops", {}) or build_fractal_loops(mission.get("intent", {}), control_center, topology)
    htn = mission.get("htn", {}) or build_htn_tree(mission.get("intent", {}), control_center, topology, fractal)
    stage_name = str(state.get("current_stage", ""))
    stage_attempts = int(state.get("stages", {}).get(stage_name, {}).get("attempts", 0) or 0)
    subtask_cursor = int(state.get("stages", {}).get(stage_name, {}).get("subtask_cursor", max(stage_attempts - 1, 0)) or 0)
    fractal_focus = select_loop_focus(fractal, stage_name, stage_attempts)
    htn_focus = select_htn_focus_by_cursor(htn, stage_name, subtask_cursor)
    trace: List[Dict[str, object]] = [
        {"phase": "intent", "detail": mission.get("intent", {}).get("goal", "")},
        {"phase": "plan_selection", "detail": control_center.get("plan_id", "")},
        {"phase": "topology", "detail": ",".join(topology.get("critical_dimensions", []))},
        {"phase": "current_stage", "detail": state.get("current_stage", "")},
        {"phase": "status", "detail": state.get("status", "")},
    ]
    return {
        "task_id": task_id,
        "trace": trace,
        "current_blockers": state.get("blockers", []),
        "fractal_focus": fractal_focus,
        "htn_focus": htn_focus,
        "topology_summary": {
            "dependency_nodes": topology.get("dependency_nodes", []),
            "verification_nodes": topology.get("verification_nodes", []),
            "risk_nodes": topology.get("risk_nodes", []),
            "coverage_goal": topology.get("coverage_goal", ""),
        },
        "advisory_recommendations": advisory.get("recommendations", []),
        "reconstruction_goal": "explain why the system is in its current state and what decision path led here",
    }


def main() -> int:
    import argparse

    parser = argparse.ArgumentParser(description="Reconstruct a lightweight forensic trace for a task")
    parser.add_argument("--task-id", required=True)
    parser.add_argument("--state-json", required=True)
    args = parser.parse_args()
    print(json.dumps(reconstruct_trace(args.task_id, json.loads(args.state_json)), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
