#!/usr/bin/env python3

from __future__ import annotations

import json
from pathlib import Path
from typing import Dict, List

from paths import HOOKS_ROOT


DEFAULT_HOOKS: Dict[str, List[str]] = {
    "mission.built": ["evaluate_clone_need"],
    "plan.reselected": ["audit_plan_switch"],
    "challenge.detected": ["route_challenge_response"],
    "capability.clone_requested": ["run_capability_clone_pipeline"],
    "capability.clone_verified": ["promote_cloned_capability"],
}


def _write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def get_registered_hooks(event_type: str) -> Dict[str, object]:
    hooks = DEFAULT_HOOKS.get(event_type, [])
    payload = {"event_type": event_type, "hooks": hooks}
    _write_json(HOOKS_ROOT / f"{event_type.replace('.', '_')}.json", payload)
    return payload


def main() -> int:
    import argparse

    parser = argparse.ArgumentParser(description="Inspect registered control-center hooks for an event")
    parser.add_argument("--event-type", required=True)
    args = parser.parse_args()
    print(json.dumps(get_registered_hooks(args.event_type), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
