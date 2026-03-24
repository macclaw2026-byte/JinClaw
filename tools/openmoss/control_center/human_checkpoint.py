#!/usr/bin/env python3

from __future__ import annotations

import json
from pathlib import Path
from typing import Dict

from paths import HUMAN_CHECKPOINTS_ROOT


def _write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def build_human_checkpoint(task_id: str, challenge: Dict[str, object]) -> Dict[str, object]:
    needed = challenge.get("recommended_route") == "human_checkpoint" or challenge.get("challenge_type") == "human_verification_required"
    payload = {
        "task_id": task_id,
        "required": needed,
        "checkpoint_reason": challenge.get("challenge_type", "none"),
        "resume_condition": "human verification completed and execution can safely resume" if needed else "not_required",
        "instructions": [
            "Pause automated progression at the checkpoint.",
            "Let a human complete the verification or challenge step.",
            "Resume the task from the verified page or post-checkpoint state only.",
        ] if needed else [],
    }
    _write_json(HUMAN_CHECKPOINTS_ROOT / f"{task_id}.json", payload)
    return payload


def main() -> int:
    import argparse

    parser = argparse.ArgumentParser(description="Create a human checkpoint for challenge-gated tasks")
    parser.add_argument("--task-id", required=True)
    parser.add_argument("--challenge-json", required=True)
    args = parser.parse_args()
    print(json.dumps(build_human_checkpoint(args.task_id, json.loads(args.challenge_json)), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
