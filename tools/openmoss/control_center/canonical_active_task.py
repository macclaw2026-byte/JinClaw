#!/usr/bin/env python3

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List

from paths import OPENMOSS_ROOT


AUTONOMY_TASKS_ROOT = OPENMOSS_ROOT / "runtime/autonomy/tasks"


def _read_json(path: Path) -> Dict[str, Any]:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def _successor_from_state(task_id: str) -> str:
    state = _read_json(AUTONOMY_TASKS_ROOT / task_id / "state.json")
    next_action = str(state.get("next_action", "")).strip()
    if next_action.startswith("superseded_by:"):
        return next_action.split(":", 1)[1].strip()
    metadata = state.get("metadata", {}) or {}
    return str(metadata.get("superseded_by_task_id", "")).strip()


def resolve_canonical_active_task(task_id: str) -> Dict[str, Any]:
    current = str(task_id or "").strip()
    visited: List[str] = []
    while current and current not in visited:
        visited.append(current)
        successor = _successor_from_state(current)
        if not successor:
            break
        current = successor
    return {
        "requested_task_id": str(task_id or "").strip(),
        "canonical_task_id": current or str(task_id or "").strip(),
        "lineage": visited,
        "rerooted": bool(visited and current and visited[0] != current),
    }

