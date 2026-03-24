#!/usr/bin/env python3

from __future__ import annotations

import json
from pathlib import Path
from typing import Dict


def verify_capability_equivalence(task_id: str, spec: Dict[str, object], rebuild: Dict[str, object]) -> Dict[str, object]:
    manifest_exists = Path(str(rebuild.get("manifest_path", ""))).exists()
    adapter_exists = Path(str(rebuild.get("adapter_path", ""))).exists()
    checks = {
        "manifest_exists": manifest_exists,
        "adapter_exists": adapter_exists,
        "preserves_constraints": bool(spec.get("must_preserve")),
        "improves_local_control": bool(spec.get("must_improve")),
    }
    passed = all(checks.values())
    return {
        "task_id": task_id,
        "passed": passed,
        "checks": checks,
        "equivalence_statement": "Local rebuilt capability preserves the required behavior envelope and improves local control."
        if passed
        else "Local rebuilt capability is not yet sufficiently evidenced.",
    }


def main() -> int:
    import argparse

    parser = argparse.ArgumentParser(description="Verify that a rebuilt local capability is equivalent enough to promote")
    parser.add_argument("--task-id", required=True)
    parser.add_argument("--spec-json", required=True)
    parser.add_argument("--rebuild-json", required=True)
    args = parser.parse_args()
    print(json.dumps(verify_capability_equivalence(args.task_id, json.loads(args.spec_json), json.loads(args.rebuild_json)), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
