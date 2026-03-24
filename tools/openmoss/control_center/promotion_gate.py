#!/usr/bin/env python3

from __future__ import annotations

import json
from pathlib import Path
from typing import Dict

from paths import PROMOTED_CAPABILITIES_ROOT


def _write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def promote_capability(task_id: str, spec: Dict[str, object], rebuild: Dict[str, object], verification: Dict[str, object], optimization: Dict[str, object]) -> Dict[str, object]:
    promoted = bool(verification.get("passed", False))
    payload = {
        "task_id": task_id,
        "capability_name": spec.get("capability_name", ""),
        "promoted": promoted,
        "rebuild_root": rebuild.get("root", ""),
        "verification": verification,
        "optimization": optimization,
        "status": "promoted" if promoted else "blocked",
    }
    _write_json(PROMOTED_CAPABILITIES_ROOT / f"{task_id}.json", payload)
    return payload


def main() -> int:
    import argparse

    parser = argparse.ArgumentParser(description="Promote a verified local capability into the registry")
    parser.add_argument("--task-id", required=True)
    parser.add_argument("--spec-json", required=True)
    parser.add_argument("--rebuild-json", required=True)
    parser.add_argument("--verification-json", required=True)
    parser.add_argument("--optimization-json", required=True)
    args = parser.parse_args()
    print(
        json.dumps(
            promote_capability(
                args.task_id,
                json.loads(args.spec_json),
                json.loads(args.rebuild_json),
                json.loads(args.verification_json),
                json.loads(args.optimization_json),
            ),
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
