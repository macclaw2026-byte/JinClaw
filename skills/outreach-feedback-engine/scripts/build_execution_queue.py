#!/usr/bin/env python3

from __future__ import annotations

import argparse
import json
from pathlib import Path


def _read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def main() -> int:
    parser = argparse.ArgumentParser(description="Build a controlled execution queue scaffold from strategy tasks.")
    parser.add_argument("--strategy-tasks", required=True)
    parser.add_argument("--feedback-events")
    parser.add_argument("--suppression-registry")
    parser.add_argument("--output", required=True)
    args = parser.parse_args()

    tasks = _read_json(Path(args.strategy_tasks).expanduser())
    items = tasks if isinstance(tasks, list) else tasks.get("items", [])
    feedback_items = []
    if args.feedback_events:
        feedback_items = _read_json(Path(args.feedback_events).expanduser()).get("items", [])
    suppression_items = []
    if args.suppression_registry:
        suppression_items = _read_json(Path(args.suppression_registry).expanduser()).get("items", [])

    stop_accounts = {
        item.get("account_id")
        for item in feedback_items
        if item.get("classification") in {"unsubscribe", "do_not_contact", "hard_bounce", "invalid_contact"}
    }
    stop_tasks = {
        item.get("task_id")
        for item in feedback_items
        if item.get("classification") in {"unsubscribe", "do_not_contact", "hard_bounce", "invalid_contact"}
    }
    stop_accounts.update(item.get("account_id") for item in suppression_items if item.get("account_id"))
    stop_tasks.update(item.get("task_id") for item in suppression_items if item.get("task_id"))
    queue = []
    for item in items:
        is_suppressed = item.get("account_id") in stop_accounts or item.get("outreach_task_id") in stop_tasks
        queue.append(
            {
                "outreach_task_id": item.get("outreach_task_id", ""),
                "account_id": item.get("account_id", ""),
                "contact_id": item.get("contact_id"),
                "channel": item.get("channel", ""),
                "strategy_id": item.get("strategy_id", ""),
                "risk_level": item.get("risk_level", "medium"),
                "approval_state": "awaiting_approval" if item.get("approval_required") else "approved",
                "status": "suppressed" if is_suppressed else "queued",
                "stop_conditions": item.get("stop_conditions", []),
                "suppressed_by_feedback": is_suppressed,
                "path_type": item.get("path_type"),
                "primary_angle": item.get("primary_angle"),
                "CTA": item.get("CTA"),
            }
        )
    out = Path(args.output).expanduser()
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(
        json.dumps(
            {
                "items": queue,
                "summary": {
                    "total": len(queue),
                    "queued": len([item for item in queue if item["status"] == "queued"]),
                    "suppressed": len([item for item in queue if item["status"] == "suppressed"]),
                },
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    print(
        json.dumps(
            {
                "output": str(out),
                "count": len(queue),
                "suppressed": len([item for item in queue if item["status"] == "suppressed"]),
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
