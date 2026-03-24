#!/usr/bin/env python3

from __future__ import annotations

import json
from typing import Dict


def distill_capability_spec(task_id: str, behavior_model: Dict[str, object]) -> Dict[str, object]:
    source_plan_id = str(behavior_model.get("source_plan_id", ""))
    capability_name = f"{task_id}-local-capability"
    return {
        "task_id": task_id,
        "capability_name": capability_name,
        "source_plan_id": source_plan_id,
        "purpose": "Replicate the useful external behavior locally with stronger safety, auditability, and verification.",
        "inputs": [
            "goal",
            "trusted_sources",
            "constraints",
        ],
        "outputs": [
            "verified_local_result",
            "structured_evidence",
            "safety_audit_log",
        ],
        "must_preserve": [
            "security boundaries",
            "verification-first execution",
            "rollback readiness",
        ],
        "must_improve": [
            "auditability",
            "local controllability",
            "token efficiency",
        ],
        "behavior_goals": behavior_model.get("behavior_goals", []),
        "challenge_model": behavior_model.get("challenge_model", {}),
        "trust_model": behavior_model.get("trust_model", {}),
    }


def main() -> int:
    import argparse

    parser = argparse.ArgumentParser(description="Distill a local capability specification from an extracted behavior model")
    parser.add_argument("--task-id", required=True)
    parser.add_argument("--behavior-json", required=True)
    args = parser.parse_args()
    print(json.dumps(distill_capability_spec(args.task_id, json.loads(args.behavior_json)), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
