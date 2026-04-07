#!/usr/bin/env python3

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path


def _read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _utc_marker() -> str:
    return datetime.now(timezone.utc).isoformat()


def main() -> int:
    parser = argparse.ArgumentParser(description="Build a feedback-events template from an execution queue.")
    parser.add_argument("--execution-queue", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--limit", type=int, default=100)
    args = parser.parse_args()

    payload = _read_json(Path(args.execution_queue).expanduser())
    items = payload.get("items", [])
    queued_items = [item for item in items if item.get("status") == "queued"][: args.limit]

    template_items = []
    for index, item in enumerate(queued_items, start=1):
        template_items.append(
            {
                "feedback_id": f"feedback-template-{index}",
                "task_id": item.get("outreach_task_id", ""),
                "account_id": item.get("account_id", ""),
                "contact_id": item.get("contact_id"),
                "channel": item.get("channel", ""),
                "outcome_type": "",
                "classification": "",
                "evidence": "",
                "evidence_excerpt": "",
                "operator_notes": "",
                "captured_at": "",
                "template_status": "awaiting_operator_input",
            }
        )

    _write_json(
        Path(args.output).expanduser(),
        {
            "items": template_items,
            "meta": {
                "generated_at": _utc_marker(),
                "source_execution_queue": str(Path(args.execution_queue).expanduser()),
                "queued_item_count": len(queued_items),
            },
        },
    )
    print(
        json.dumps(
            {
                "status": "ok",
                "template_count": len(template_items),
                "output": str(Path(args.output).expanduser()),
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
