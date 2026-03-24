#!/usr/bin/env python3

from __future__ import annotations

import json
from typing import Dict, List


def build_fractal_loops(intent: Dict[str, object], selected_plan: Dict[str, object], topology: Dict[str, object]) -> Dict[str, object]:
    steps = [str(item) for item in selected_plan.get("steps", [])]
    loops: List[Dict[str, object]] = []
    for index, step in enumerate(steps, start=1):
        loops.append(
            {
                "loop_id": f"loop-{index}",
                "goal": step,
                "verify_with": topology.get("verification_nodes", [])[:2],
                "dependencies": topology.get("dependency_nodes", []),
                "risk_checks": topology.get("risk_nodes", []),
            }
        )
    return {
        "mode": "recursive_verifiable_subloops",
        "loop_count": len(loops),
        "loops": loops,
        "decomposition_rule": "each plan step becomes a verifiable sub-loop with explicit dependencies and risk checks",
    }


def select_loop_focus(fractal: Dict[str, object], stage_name: str, stage_attempts: int = 0) -> Dict[str, object]:
    loops = fractal.get("loops", [])
    if not loops:
        return {
            "stage_name": stage_name,
            "loop_count": 0,
            "focus": {},
            "focus_reason": "no_fractal_loops_available",
        }
    if stage_name == "execute":
        index = min(max(stage_attempts - 1, 0), len(loops) - 1)
    elif stage_name == "verify":
        index = len(loops) - 1
    else:
        index = 0
    return {
        "stage_name": stage_name,
        "loop_count": len(loops),
        "focus": loops[index],
        "focus_reason": "stage-aligned_fractal_focus",
    }


def main() -> int:
    import argparse

    parser = argparse.ArgumentParser(description="Build fractal sub-loops for a selected plan")
    parser.add_argument("--intent-json", required=True)
    parser.add_argument("--plan-json", required=True)
    parser.add_argument("--topology-json", required=True)
    parser.add_argument("--stage-name", default="")
    parser.add_argument("--stage-attempts", type=int, default=0)
    args = parser.parse_args()
    fractal = build_fractal_loops(json.loads(args.intent_json), json.loads(args.plan_json), json.loads(args.topology_json))
    payload = {"fractal": fractal}
    if args.stage_name:
        payload["focus"] = select_loop_focus(fractal, args.stage_name, args.stage_attempts)
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
