#!/usr/bin/env python3

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict

from capability_cloner import clone_capability
from hook_registry import get_registered_hooks
from paths import EVENTS_ROOT


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _append_jsonl(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(payload, ensure_ascii=False) + "\n")


def publish_event(event_type: str, payload: Dict[str, object]) -> Dict[str, object]:
    task_id = str(payload.get("task_id", "global"))
    record = {
        "at": _utc_now_iso(),
        "event_type": event_type,
        "task_id": task_id,
        "payload": payload,
    }
    _append_jsonl(EVENTS_ROOT / f"{task_id}.jsonl", record)
    registered = get_registered_hooks(event_type)
    emitted_hooks = []
    for hook_name in registered.get("hooks", []):
        hook_result: Dict[str, object] = {"hook_name": hook_name, "status": "observed"}
        if hook_name == "run_capability_clone_pipeline":
            mission = payload.get("mission", {})
            clone = clone_capability(task_id, mission)
            hook_result = {
                "hook_name": hook_name,
                "status": "completed",
                "clone": clone,
            }
            if clone.get("verification", {}).get("passed"):
                _append_jsonl(
                    EVENTS_ROOT / f"{task_id}.jsonl",
                    {
                        "at": _utc_now_iso(),
                        "event_type": "capability.clone_verified",
                        "task_id": task_id,
                        "payload": {"task_id": task_id, "clone": clone},
                    },
                )
        emitted_hooks.append(hook_result)
    record["emitted_hooks"] = emitted_hooks
    _append_jsonl(EVENTS_ROOT / f"{task_id}.jsonl", {"at": _utc_now_iso(), "event_type": f"{event_type}.hooks", "task_id": task_id, "emitted_hooks": emitted_hooks})
    return {"recorded": True, "event_type": event_type, "task_id": task_id, "emitted_hooks": emitted_hooks}


def main() -> int:
    import argparse

    parser = argparse.ArgumentParser(description="Publish a control-center event and trigger registered hooks")
    parser.add_argument("--event-type", required=True)
    parser.add_argument("--payload-json", required=True)
    args = parser.parse_args()
    print(json.dumps(publish_event(args.event_type, json.loads(args.payload_json)), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
