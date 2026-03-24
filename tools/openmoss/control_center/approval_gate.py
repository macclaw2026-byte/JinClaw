#!/usr/bin/env python3

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List

from paths import APPROVALS_ROOT
from security_policy import assess_plan_risk, default_security_policy


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _write_json(path: Path, payload) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _approval_path(task_id: str) -> Path:
    return APPROVALS_ROOT / f"{task_id}.json"


def _read_json(path: Path, default):
    if not path.exists():
        return default
    return json.loads(path.read_text(encoding="utf-8"))


def review_plan(task_id: str, selected_plan: Dict[str, object]) -> Dict[str, object]:
    policy = default_security_policy()
    assessed = assess_plan_risk(selected_plan)
    decisions: Dict[str, Dict[str, object]] = {}
    pending: List[str] = []
    approved: List[str] = []

    for index, action in enumerate(assessed["actions"], start=1):
        action_id = f"{task_id}:{action.get('type', 'external')}:{index}"
        mode = str(action.get("approval_mode", "manual_approval"))
        status = "approved" if mode == "auto_review" else "pending"
        record = {
            "id": action_id,
            "status": status,
            "type": action.get("type", ""),
            "reason": action.get("reason", ""),
            "risk": action.get("risk", "high"),
            "approval_mode": mode,
            "reviewed_at": _utc_now_iso(),
        }
        decisions[action_id] = record
        if status == "approved":
            approved.append(action_id)
        else:
            pending.append(action_id)

    payload = {
        "task_id": task_id,
        "reviewed_at": _utc_now_iso(),
        "security_policy": policy["principle"],
        "overall_risk": assessed["risk"],
        "decisions": decisions,
        "approved": approved,
        "pending": pending,
    }
    _write_json(_approval_path(task_id), payload)
    return payload


def approve_pending_action(task_id: str, approval_id: str, reviewer: str = "manual") -> Dict[str, object]:
    payload = _read_json(_approval_path(task_id), {})
    decisions = payload.get("decisions", {})
    if approval_id not in decisions:
        return {"ok": False, "status": "unknown_approval_id", "approval_id": approval_id}
    decisions[approval_id]["status"] = "approved"
    decisions[approval_id]["reviewed_at"] = _utc_now_iso()
    decisions[approval_id]["reviewer"] = reviewer
    payload["approved"] = sorted({*payload.get("approved", []), approval_id})
    payload["pending"] = [item for item in payload.get("pending", []) if item != approval_id]
    payload["decisions"] = decisions
    _write_json(_approval_path(task_id), payload)
    return {"ok": True, "status": "approved", "approval_id": approval_id, "payload": payload}


def main() -> int:
    import argparse

    parser = argparse.ArgumentParser(description="Review an execution plan and produce approval decisions")
    parser.add_argument("--task-id", required=True)
    parser.add_argument("--plan-json", default="")
    parser.add_argument("--approve-id", default="")
    parser.add_argument("--reviewer", default="manual")
    args = parser.parse_args()
    if args.approve_id:
        print(json.dumps(approve_pending_action(args.task_id, args.approve_id, reviewer=args.reviewer), ensure_ascii=False, indent=2))
        return 0
    if not args.plan_json:
        raise SystemExit("--plan-json is required unless --approve-id is used")
    print(json.dumps(review_plan(args.task_id, json.loads(args.plan_json)), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
