#!/usr/bin/env python3
# RULES-FIRST NOTICE:
# Before modifying this file, first read:
# - `JINCLAW_CONSTITUTION.md`
# - `AI_OPTIMIZATION_FRAMEWORK.md`
# Follow the constitution and framework:
# brain-first, one-doctor, fail-closed, evidence-over-narration,
# validate locally, then use the required PR workflow.
"""
中文说明：
- 文件路径：`tools/openmoss/control_center/memory_pipeline_store.py`
- 文件作用：负责 memory pipeline 的压缩、持久化与项目级索引写回。
- 顶层函数：compact_memory_layers、persist_memory_pipeline。
- 顶层类：无顶层类。
"""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

from paths import MEMORY_PIPELINES_ROOT, MEMORY_PROJECT_INDEX_PATH


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _read_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return default


def _write_json(path: Path, payload: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _trim_list(values: List[Any], limit: int) -> List[Any]:
    return list(values or [])[:limit]


def compact_memory_layers(layers: Dict[str, Any]) -> Dict[str, Any]:
    session = dict(layers.get("session", {}) or {})
    project = dict(layers.get("project", {}) or {})
    task = dict(layers.get("task", {}) or {})
    runtime = dict(layers.get("runtime", {}) or {})

    session["links"] = _trim_list(session.get("links", []) or [], 3)
    project["crawler_priority_actions"] = _trim_list(project.get("crawler_priority_actions", []) or [], 5)
    task["matched_promoted_rules"] = _trim_list(task.get("matched_promoted_rules", []) or [], 5)
    task["matched_error_recurrence"] = _trim_list(task.get("matched_error_recurrence", []) or [], 5)

    plan_history = dict(task.get("plan_history_profile", {}) or {})
    sources = dict(plan_history.get("sources", {}) or {})
    if sources:
        for key, value in list(sources.items()):
            if isinstance(value, dict):
                sources[key] = {
                    "successes": value.get("successes", 0),
                    "failures": value.get("failures", 0),
                    "blocked": value.get("blocked", 0),
                    "last_result": value.get("last_result", ""),
                    "last_updated_at": value.get("last_updated_at", ""),
                }
        plan_history["sources"] = sources
        task["plan_history_profile"] = plan_history

    runtime["blockers"] = _trim_list(runtime.get("blockers", []) or [], 8)
    runtime["hook_warnings"] = _trim_list(runtime.get("hook_warnings", []) or [], 8)
    runtime["hook_errors"] = _trim_list(runtime.get("hook_errors", []) or [], 8)
    runtime["hook_next_actions"] = _trim_list(runtime.get("hook_next_actions", []) or [], 8)

    compacted = {
        "session": session,
        "project": project,
        "task": task,
        "runtime": runtime,
        "summary": dict(layers.get("summary", {}) or {}),
    }
    serialized = json.dumps(compacted, ensure_ascii=False, sort_keys=True)
    compacted["summary"]["fingerprint"] = hashlib.sha256(serialized.encode("utf-8")).hexdigest()[:16]
    compacted["summary"]["persisted_at"] = _utc_now_iso()
    return compacted


def persist_memory_pipeline(task_id: str, layers: Dict[str, Any]) -> Dict[str, Any]:
    compacted = compact_memory_layers(layers)
    pipeline_path = MEMORY_PIPELINES_ROOT / f"{task_id}.json"
    payload = {
        "task_id": task_id,
        "generated_at": _utc_now_iso(),
        "layers": compacted,
    }
    _write_json(pipeline_path, payload)

    project_index = _read_json(MEMORY_PROJECT_INDEX_PATH, {"updated_at": "", "items": {}}) or {"updated_at": "", "items": {}}
    project_index["updated_at"] = _utc_now_iso()
    project_index["items"][task_id] = {
        "path": str(pipeline_path),
        "fingerprint": compacted.get("summary", {}).get("fingerprint", ""),
        "summary": compacted.get("summary", {}),
    }
    _write_json(MEMORY_PROJECT_INDEX_PATH, project_index)
    return {
        "path": str(pipeline_path),
        "fingerprint": compacted.get("summary", {}).get("fingerprint", ""),
        "summary": compacted.get("summary", {}),
    }
