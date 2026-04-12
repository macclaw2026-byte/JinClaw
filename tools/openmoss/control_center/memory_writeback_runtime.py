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
- 文件路径：`tools/openmoss/control_center/memory_writeback_runtime.py`
- 文件作用：定义 memory pipeline 的显式写回策略，并持久化 layer-specific writeback journal。
- 顶层函数：build_memory_writeback_policy、record_memory_writeback。
- 顶层类：无顶层类。
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

from paths import MEMORY_WRITEBACK_ROOT


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


def build_memory_writeback_policy(task_id: str, state: Dict[str, Any], mission: Dict[str, Any]) -> Dict[str, Any]:
    metadata = state.get("metadata", {}) or {}
    return {
        "task_id": task_id,
        "rules": {
            "session": {
                "sources": ["conversation_link_update", "route_persisted", "receipt_delivery"],
                "writes": ["active_link_count", "latest_link", "session_key"],
            },
            "project": {
                "sources": ["crawler_remediation_cycle", "crawler_profile_refresh", "promotion"],
                "writes": ["crawler_health", "crawler_priority_actions", "remediation_totals"],
            },
            "task": {
                "sources": ["task_summary_refresh", "verification", "plan_history", "business_outcome"],
                "writes": ["task_summary", "matched_promoted_rules", "matched_error_recurrence", "plan_history_profile"],
            },
            "runtime": {
                "sources": ["hook_effects", "preflight", "runtime_dispatch", "doctor_takeover"],
                "writes": ["blockers", "active_execution", "waiting_external", "hook_warnings", "hook_errors", "hook_next_actions"],
            },
        },
        "current_focus": {
            "current_stage": state.get("current_stage", ""),
            "status": state.get("status", ""),
            "has_active_execution": bool((metadata.get("active_execution", {}) or {}).get("run_id")),
            "has_waiting_external": bool(metadata.get("waiting_external")),
            "mission_task_types": ((mission.get("intent", {}) or {}).get("task_types", []) or [])[:5],
        },
    }


def _targets_for_source(source: str) -> List[str]:
    lowered = str(source or "").strip().lower()
    if lowered.startswith("preflight") or lowered.startswith("runtime") or lowered.startswith("doctor"):
        return ["runtime"]
    if lowered.startswith("receipt") or lowered.startswith("route") or lowered.startswith("conversation"):
        return ["session"]
    if lowered.startswith("crawler") or lowered.startswith("promotion"):
        return ["project"]
    if lowered.startswith("verification") or lowered.startswith("task_summary") or lowered.startswith("business_outcome"):
        return ["task"]
    return ["runtime"]


def _normalize_targets(summary: Dict[str, Any], source: str) -> List[str]:
    explicit = [str(item).strip() for item in summary.get("memory_targets", []) or [] if str(item).strip()]
    if explicit:
        return sorted(set(explicit))
    return _targets_for_source(source)


def record_memory_writeback(task_id: str, *, source: str, summary: Dict[str, Any]) -> Dict[str, Any]:
    path = MEMORY_WRITEBACK_ROOT / f"{task_id}.json"
    payload = _read_json(path, {"task_id": task_id, "updated_at": "", "entries": []}) or {"task_id": task_id, "updated_at": "", "entries": []}
    entry = {
        "at": _utc_now_iso(),
        "source": source,
        "targets": _normalize_targets(summary, source),
        "state_patch_keys": sorted((summary.get("state_patch", {}) or {}).keys()),
        "governance_patch_keys": sorted((summary.get("governance_patch", {}) or {}).keys()),
        "next_actions": list(summary.get("next_actions", []) or []),
        "warnings": list(summary.get("warnings", []) or []),
        "errors": list(summary.get("errors", []) or []),
        "decisions": list(summary.get("decisions", []) or []),
        "memory_reasons": list(summary.get("memory_reasons", []) or []),
        "attention_required": bool(summary.get("attention_required")),
    }
    entries = list(payload.get("entries", []) or [])
    entries.append(entry)
    payload["updated_at"] = _utc_now_iso()
    payload["entries"] = entries[-20:]
    _write_json(path, payload)
    return {
        "path": str(path),
        "last_entry": entry,
        "entries_total": len(payload["entries"]),
    }


def load_memory_writeback(task_id: str) -> Dict[str, Any]:
    path = MEMORY_WRITEBACK_ROOT / f"{task_id}.json"
    payload = _read_json(path, {"entries": []}) or {"entries": []}
    entries = list(payload.get("entries", []) or [])
    last_entry = entries[-1] if entries else {}
    return {
        "path": str(path),
        "last_entry": last_entry,
        "entries_total": len(entries),
    }


def summarize_project_memory_writebacks(*, limit: int = 20) -> Dict[str, Any]:
    items: List[Dict[str, Any]] = []
    target_counts: Dict[str, int] = {}
    reason_counts: Dict[str, int] = {}
    source_counts: Dict[str, int] = {}
    if MEMORY_WRITEBACK_ROOT.exists():
        for path in sorted(MEMORY_WRITEBACK_ROOT.glob("*.json")):
            payload = _read_json(path, {"entries": []}) or {"entries": []}
            entries = list(payload.get("entries", []) or [])
            if not entries:
                continue
            last_entry = entries[-1] if entries else {}
            task_id = path.stem
            items.append(
                {
                    "task_id": task_id,
                    "path": str(path),
                    "entries_total": len(entries),
                    "last_entry": last_entry,
                }
            )
            for target in last_entry.get("targets", []) or []:
                key = str(target).strip()
                if key:
                    target_counts[key] = target_counts.get(key, 0) + 1
            for reason in last_entry.get("memory_reasons", []) or []:
                key = str(reason).strip()
                if key:
                    reason_counts[key] = reason_counts.get(key, 0) + 1
            source = str(last_entry.get("source", "")).strip()
            if source:
                source_counts[source] = source_counts.get(source, 0) + 1
    items.sort(key=lambda item: str((item.get("last_entry", {}) or {}).get("at", "")), reverse=True)
    return {
        "generated_at": _utc_now_iso(),
        "tasks_total": len(items),
        "recent_items": items[:limit],
        "target_counts": target_counts,
        "reason_counts": reason_counts,
        "source_counts": source_counts,
    }
