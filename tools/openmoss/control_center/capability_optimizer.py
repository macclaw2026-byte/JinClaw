#!/usr/bin/env python3

from __future__ import annotations

import json
from typing import Dict


def optimize_capability(task_id: str, spec: Dict[str, object], rebuild: Dict[str, object]) -> Dict[str, object]:
    return {
        "task_id": task_id,
        "capability_name": spec.get("capability_name", ""),
        "optimized_from": rebuild.get("capability_name", ""),
        "optimizations": [
            "prefer structured outputs over raw text",
            "reduce token usage with minimal context packets",
            "add explicit verification and rollback readiness",
            "keep only the useful behavior surface from the external pattern",
        ],
        "strengthened_properties": [
            "auditability",
            "local control",
            "safety boundary preservation",
            "reusability",
        ],
    }


def main() -> int:
    import argparse

    parser = argparse.ArgumentParser(description="Apply local-first optimizations to a rebuilt capability")
    parser.add_argument("--task-id", required=True)
    parser.add_argument("--spec-json", required=True)
    parser.add_argument("--rebuild-json", required=True)
    args = parser.parse_args()
    print(json.dumps(optimize_capability(args.task_id, json.loads(args.spec_json), json.loads(args.rebuild_json)), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
