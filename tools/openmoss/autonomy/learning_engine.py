#!/usr/bin/env python3

from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List


LEARNINGS_ROOT = Path("/Users/mac_claw/.openclaw/workspace/.learnings")
STRUCTURED_ROOT = Path("/Users/mac_claw/.openclaw/workspace/tools/openmoss/runtime/autonomy/learning")


def _append(path: Path, lines: List[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as fh:
        for line in lines:
            fh.write(line.rstrip() + "\n")


def _read_json(path: Path, default):
    if not path.exists():
        return default
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, payload) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _normalize_error(error_text: str) -> str:
    lowered = error_text.lower().strip()
    lowered = re.sub(r"^(understand|plan|execute|verify|learn)\s*:\s*", "", lowered)
    lowered = re.sub(r"^(auto-recovery failed for [^:]+:\s*)", "", lowered)
    lowered = re.sub(r"/users/[^\s]+", "/users/<path>", lowered)
    lowered = re.sub(r"/tmp/[^\s]+", "/tmp/<path>", lowered)
    lowered = re.sub(r"\b[0-9a-f]{8,}\b", "<id>", lowered)
    return lowered


def _recurrence_path() -> Path:
    return STRUCTURED_ROOT / "error_recurrence.json"


def _promotion_report_path(key: str) -> Path:
    safe = re.sub(r"[^a-zA-Z0-9]+", "-", key).strip("-")[:80] or "recurring-error"
    return STRUCTURED_ROOT / "reports" / f"{safe}.json"


def _task_summary_path(task_id: str) -> Path:
    return STRUCTURED_ROOT / "task_summaries" / f"{task_id}.json"


def record_learning(task_id: str, summary: str) -> str:
    path = LEARNINGS_ROOT / "LEARNINGS.md"
    _append(path, [f"- [{task_id}] {summary}"])
    return str(path)


def record_error(task_id: str, error_text: str) -> str:
    path = LEARNINGS_ROOT / "ERRORS.md"
    _append(path, [f"- [{task_id}] {error_text}"])
    note_error_occurrence(task_id, error_text)
    return str(path)


def note_error_occurrence(task_id: str, error_text: str) -> Dict[str, object]:
    path = _recurrence_path()
    payload = _read_json(path, {"errors": {}})
    key = _normalize_error(error_text)
    item = payload["errors"].get(
        key,
        {
            "count": 0,
            "tasks": [],
            "first_seen_task": task_id,
            "last_seen_task": task_id,
            "sample_error": error_text,
        },
    )
    item["count"] += 1
    item["last_seen_task"] = task_id
    if task_id not in item["tasks"]:
        item["tasks"].append(task_id)
    payload["errors"][key] = item
    _write_json(path, payload)
    if item["count"] >= 2:
        _write_json(
            _promotion_report_path(key),
            {
                "error_key": key,
                "count": item["count"],
                "tasks": item["tasks"],
                "recommended_action": "promote recurring fix into runtime guidance",
                "sample_error": item["sample_error"],
            },
        )
    return {"key": key, "count": item["count"], "tasks": item["tasks"]}


def get_error_recurrence(error_text: str) -> Dict[str, object]:
    payload = _read_json(_recurrence_path(), {"errors": {}})
    key = _normalize_error(error_text)
    item = payload["errors"].get(key, {"count": 0, "tasks": []})
    return {"key": key, "count": item.get("count", 0), "tasks": item.get("tasks", [])}


def update_task_summary(task_id: str, update: Dict[str, object]) -> Dict[str, object]:
    path = _task_summary_path(task_id)
    current = _read_json(
        path,
        {
            "task_id": task_id,
            "updated_at": "",
            "status": "unknown",
            "current_stage": "",
            "last_completed_stage": "",
            "last_failure": {},
            "learning_backlog": [],
            "verified_stages": [],
            "completed_stages": [],
            "notes": [],
        },
    )
    current.update({k: v for k, v in update.items() if v is not None})
    current["updated_at"] = _utc_now_iso()
    _write_json(path, current)
    return current


def load_task_summary(task_id: str) -> Dict[str, object]:
    return _read_json(_task_summary_path(task_id), {})
