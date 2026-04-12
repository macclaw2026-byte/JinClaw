#!/usr/bin/env python3
# RULES-FIRST NOTICE:
# Before modifying this file, first read:
# - `JINCLAW_CONSTITUTION.md`
# - `AI_OPTIMIZATION_FRAMEWORK.md`
# Follow the constitution and framework:
# brain-first, one-doctor, fail-closed, evidence-over-narration,
# validate locally, then use the required PR workflow.
from __future__ import annotations

import json
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

from paths import TASK_ALIAS_REGISTRY_PATH


AUTONOMY_TASKS_ROOT = Path("/Users/mac_claw/.openclaw/workspace/tools/openmoss/runtime/autonomy/tasks")
TERMINAL_TASK_STATUSES = {"completed", "failed", "cancelled", "lost"}
DEFAULT_GROUP_SEQUENCE_START = 10001


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _read_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return default


def _write_json(path: Path, payload: Any) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = path.with_name(f"{path.name}.{os.getpid()}.{uuid.uuid4().hex}.tmp")
    temp_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    temp_path.replace(path)
    return str(path)


def _normalized_iso(value: Any) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00")).astimezone(timezone.utc).isoformat()
    except ValueError:
        return text


def _fallback_created_at(task_dir: Path) -> str:
    try:
        timestamp = task_dir.stat().st_mtime
    except OSError:
        return ""
    return datetime.fromtimestamp(timestamp, tz=timezone.utc).isoformat()


def _task_payloads() -> Dict[str, Dict[str, Any]]:
    payloads: Dict[str, Dict[str, Any]] = {}
    if not AUTONOMY_TASKS_ROOT.exists():
        return payloads
    for task_dir in sorted((path for path in AUTONOMY_TASKS_ROOT.iterdir() if path.is_dir()), key=lambda path: path.name):
        task_id = task_dir.name
        contract = _read_json(task_dir / "contract.json", {}) or {}
        state = _read_json(task_dir / "state.json", {}) or {}
        contract_metadata = (contract.get("metadata", {}) or {}) if isinstance(contract, dict) else {}
        state_metadata = (state.get("metadata", {}) or {}) if isinstance(state, dict) else {}
        created_at = (
            _normalized_iso(contract_metadata.get("created_at"))
            or _normalized_iso(contract.get("created_at"))
            or _normalized_iso(state_metadata.get("created_at"))
            or _normalized_iso(state.get("created_at"))
            or _fallback_created_at(task_dir)
        )
        payloads[task_id] = {
            "task_id": task_id,
            "task_dir": str(task_dir),
            "goal": str(contract.get("user_goal", "")).strip(),
            "status": str(state.get("status", "unknown")).strip() or "unknown",
            "current_stage": str(state.get("current_stage", "")).strip(),
            "next_action": str(state.get("next_action", "")).strip(),
            "created_at": created_at,
            "predecessor_task_id": str(contract_metadata.get("predecessor_task_id", "")).strip()
            or str(state_metadata.get("predecessor_task_id", "")).strip(),
            "lineage_root_task_id": str(contract_metadata.get("lineage_root_task_id", "")).strip()
            or str(state_metadata.get("lineage_root_task_id", "")).strip(),
            "superseded_by_task_id": str(state_metadata.get("superseded_by_task_id", "")).strip(),
        }
    return payloads


def _resolve_root_task_id(task_id: str, payloads: Dict[str, Dict[str, Any]]) -> str:
    current = task_id
    seen: set[str] = set()
    while current and current not in seen:
        seen.add(current)
        payload = payloads.get(current, {}) or {}
        lineage_root = str(payload.get("lineage_root_task_id", "")).strip()
        if lineage_root and lineage_root in payloads:
            return lineage_root
        predecessor = str(payload.get("predecessor_task_id", "")).strip()
        if not predecessor or predecessor not in payloads:
            return current
        current = predecessor
    return task_id


def _task_sort_key(task_id: str, payloads: Dict[str, Dict[str, Any]]) -> tuple[str, str]:
    created_at = str((payloads.get(task_id, {}) or {}).get("created_at", "")).strip()
    return (created_at or "9999-12-31T23:59:59+00:00", task_id)


def _select_group_current_task_id(task_ids: List[str], payloads: Dict[str, Dict[str, Any]]) -> str:
    active_candidates: List[str] = []
    for task_id in task_ids:
        payload = payloads.get(task_id, {}) or {}
        status = str(payload.get("status", "")).strip().lower()
        successor_task_id = str(payload.get("superseded_by_task_id", "")).strip()
        if successor_task_id and _resolve_root_task_id(successor_task_id, payloads) == _resolve_root_task_id(task_id, payloads):
            continue
        if status in TERMINAL_TASK_STATUSES:
            continue
        active_candidates.append(task_id)
    if active_candidates:
        return sorted(active_candidates, key=lambda item: _task_sort_key(item, payloads))[-1]
    if task_ids:
        return sorted(task_ids, key=lambda item: _task_sort_key(item, payloads))[-1]
    return ""


def build_task_alias_registry(task_items: List[Dict[str, Any]] | None = None, *, sequence_start: int = DEFAULT_GROUP_SEQUENCE_START) -> Dict[str, Any]:
    payloads = _task_payloads()
    task_index = {
        str(item.get("task_id", "")).strip(): item
        for item in (task_items or [])
        if str(item.get("task_id", "")).strip()
    }
    groups: Dict[str, List[str]] = {}
    for task_id in payloads:
        root_task_id = _resolve_root_task_id(task_id, payloads)
        if root_task_id not in payloads:
            root_task_id = task_id
        groups.setdefault(root_task_id, []).append(task_id)

    ordered_group_ids = sorted(groups, key=lambda task_id: _task_sort_key(task_id, payloads))
    group_items: List[Dict[str, Any]] = []
    by_task_id: Dict[str, Dict[str, Any]] = {}
    alias_to_task_id: Dict[str, str] = {}
    group_alias_to_task_id: Dict[str, str] = {}
    task_id_to_alias: Dict[str, str] = {}
    task_id_to_group_alias: Dict[str, str] = {}

    for offset, root_task_id in enumerate(ordered_group_ids):
        group_sequence = sequence_start + offset
        group_alias = f"JC{group_sequence}"
        member_ids = sorted(groups[root_task_id], key=lambda task_id: _task_sort_key(task_id, payloads))
        current_task_id = _select_group_current_task_id(member_ids, payloads)
        group_alias_to_task_id[group_alias] = current_task_id or root_task_id
        alias_to_task_id[group_alias] = current_task_id or root_task_id

        member_rows: List[Dict[str, Any]] = []
        for node_index, task_id in enumerate(member_ids, start=1):
            payload = payloads.get(task_id, {}) or {}
            task_item = task_index.get(task_id, {}) or {}
            task_alias = f"{group_alias}-{node_index}"
            row = {
                "task_id": task_id,
                "task_alias": task_alias,
                "task_group_alias": group_alias,
                "task_sequence": group_sequence,
                "task_node_index": node_index,
                "lineage_root_task_id": root_task_id,
                "is_group_root": task_id == root_task_id,
                "is_group_current": task_id == current_task_id,
                "created_at": str(payload.get("created_at", "")).strip(),
                "status": str(task_item.get("status", payload.get("status", "unknown"))).strip() or "unknown",
                "current_stage": str(task_item.get("current_stage", payload.get("current_stage", ""))).strip(),
                "next_action": str(task_item.get("next_action", payload.get("next_action", ""))).strip(),
                "canonical_task_id": str(task_item.get("canonical_task_id", "")).strip() or task_id,
                "goal": str(task_item.get("goal", payload.get("goal", ""))).strip(),
            }
            member_rows.append(row)
            by_task_id[task_id] = row
            alias_to_task_id[task_alias] = task_id
            task_id_to_alias[task_id] = task_alias
            task_id_to_group_alias[task_id] = group_alias

        group_items.append(
            {
                "group_alias": group_alias,
                "group_sequence": group_sequence,
                "root_task_id": root_task_id,
                "current_task_id": current_task_id or root_task_id,
                "task_count": len(member_rows),
                "created_at": str((payloads.get(root_task_id, {}) or {}).get("created_at", "")).strip(),
                "items": member_rows,
            }
        )

    registry = {
        "generated_at": _utc_now_iso(),
        "sequence_start": sequence_start,
        "scheme": "JC{group_sequence}-{task_node_index}",
        "group_alias_semantics": "group_alias maps to the group's current active task when available",
        "items": group_items,
        "by_task_id": by_task_id,
        "alias_to_task_id": alias_to_task_id,
        "group_alias_to_task_id": group_alias_to_task_id,
        "task_id_to_alias": task_id_to_alias,
        "task_id_to_group_alias": task_id_to_group_alias,
    }
    registry["path"] = _write_json(TASK_ALIAS_REGISTRY_PATH, registry)
    return registry


def load_task_alias_registry() -> Dict[str, Any]:
    return _read_json(TASK_ALIAS_REGISTRY_PATH, {}) or {}


def resolve_task_selector(task_ref: str, *, alias_registry: Dict[str, Any] | None = None) -> Dict[str, str]:
    requested_ref = str(task_ref or "").strip()
    if not requested_ref:
        return {}
    registry = alias_registry or load_task_alias_registry()
    by_task_id = (registry.get("by_task_id", {}) or {}) if isinstance(registry, dict) else {}
    alias_to_task_id = (registry.get("alias_to_task_id", {}) or {}) if isinstance(registry, dict) else {}
    direct_task_entry = (by_task_id.get(requested_ref, {}) or {}) if isinstance(by_task_id, dict) else {}
    if direct_task_entry:
        return {
            "requested_ref": requested_ref,
            "resolved_task_id": requested_ref,
            "matched_by": "task_id",
            "task_alias": str(direct_task_entry.get("task_alias", "")).strip(),
            "task_group_alias": str(direct_task_entry.get("task_group_alias", "")).strip(),
        }

    resolved_task_id = str(alias_to_task_id.get(requested_ref, "")).strip()
    if not resolved_task_id and requested_ref.upper() != requested_ref:
        resolved_task_id = str(alias_to_task_id.get(requested_ref.upper(), "")).strip()
        requested_ref = requested_ref.upper() if resolved_task_id else requested_ref
    if not resolved_task_id:
        return {}
    resolved_entry = (by_task_id.get(resolved_task_id, {}) or {}) if isinstance(by_task_id, dict) else {}
    matched_by = "group_alias" if requested_ref == str(resolved_entry.get("task_group_alias", "")).strip() else "task_alias"
    return {
        "requested_ref": requested_ref,
        "resolved_task_id": resolved_task_id,
        "matched_by": matched_by,
        "task_alias": str(resolved_entry.get("task_alias", "")).strip(),
        "task_group_alias": str(resolved_entry.get("task_group_alias", "")).strip(),
    }
