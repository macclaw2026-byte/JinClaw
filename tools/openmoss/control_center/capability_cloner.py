#!/usr/bin/env python3

from __future__ import annotations

import json
from pathlib import Path
from typing import Dict

from behavior_extractor import extract_behavior_model
from capability_distiller import distill_capability_spec
from capability_optimizer import optimize_capability
from equivalence_verifier import verify_capability_equivalence
from local_rebuilder import rebuild_local_capability
from paths import CAPABILITY_CLONES_ROOT
from promotion_gate import promote_capability


def _write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def clone_capability(task_id: str, mission: Dict[str, object]) -> Dict[str, object]:
    behavior = extract_behavior_model(task_id, mission)
    spec = distill_capability_spec(task_id, behavior)
    rebuild = rebuild_local_capability(task_id, spec)
    verification = verify_capability_equivalence(task_id, spec, rebuild)
    optimization = optimize_capability(task_id, spec, rebuild)
    promotion = promote_capability(task_id, spec, rebuild, verification, optimization)
    payload = {
        "task_id": task_id,
        "behavior_model": behavior,
        "spec": spec,
        "rebuild": rebuild,
        "verification": verification,
        "optimization": optimization,
        "promotion": promotion,
    }
    _write_json(CAPABILITY_CLONES_ROOT / f"{task_id}.json", payload)
    return payload


def main() -> int:
    import argparse

    parser = argparse.ArgumentParser(description="Clone a useful external or hybrid capability into a stronger local one")
    parser.add_argument("--task-id", required=True)
    parser.add_argument("--mission-json", required=True)
    args = parser.parse_args()
    print(json.dumps(clone_capability(args.task_id, json.loads(args.mission_json)), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
