#!/usr/bin/env python3

from __future__ import annotations

import json
from typing import Dict, List


def extract_behavior_model(task_id: str, mission: Dict[str, object]) -> Dict[str, object]:
    selected_plan = mission.get("selected_plan", {})
    adoption_flow = mission.get("adoption_flow", {})
    resource_scout = mission.get("resource_scout", {})
    challenge = mission.get("challenge", {})
    return {
        "task_id": task_id,
        "source_plan_id": selected_plan.get("plan_id", ""),
        "behavior_goals": selected_plan.get("steps", []),
        "useful_external_behaviors": [
            "structured acquisition ladder",
            "verified evidence collection",
            "safe fallback routing",
        ],
        "external_touchpoints": selected_plan.get("external_actions", []),
        "challenge_model": {
            "type": challenge.get("challenge_type", "none"),
            "route": challenge.get("recommended_route", "continue"),
        },
        "trust_model": {
            "trusted_sources": resource_scout.get("trusted_source_types", []),
            "adoption_mode": adoption_flow.get("adoption_mode", "local_or_read_only"),
        },
    }


def main() -> int:
    import argparse

    parser = argparse.ArgumentParser(description="Extract a behavior model from a mission for local capability cloning")
    parser.add_argument("--task-id", required=True)
    parser.add_argument("--mission-json", required=True)
    args = parser.parse_args()
    print(json.dumps(extract_behavior_model(args.task_id, json.loads(args.mission_json)), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
