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
import shutil
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

from memory_writeback_runtime import load_memory_writeback, record_memory_writeback
from paths import (
    ARCHIVED_TASK_REGISTRY_PATH,
    AUTONOMY_ARCHIVE_LINKS_ROOT,
    AUTONOMY_ARCHIVE_MANIFESTS_ROOT,
    AUTONOMY_ARCHIVE_STATUS_ROOT,
    AUTONOMY_ARCHIVE_TASKS_ROOT,
    AUTONOMY_RUNTIME_ROOT,
    OPENMOSS_ROOT,
    TASK_RETENTION_LAST_RUN_PATH,
    TASK_STATUS_ROOT,
)
from progress_evidence import build_progress_evidence
from task_status_snapshot import build_task_status_snapshot


AUTONOMY_MODULE_ROOT = OPENMOSS_ROOT / "autonomy"
if str(AUTONOMY_MODULE_ROOT) not in sys.path:
    sys.path.append(str(AUTONOMY_MODULE_ROOT))

from learning_engine import record_learning

AUTONOMY_TASKS_ROOT = AUTONOMY_RUNTIME_ROOT / "tasks"
AUTONOMY_LINKS_ROOT = AUTONOMY_RUNTIME_ROOT / "links"
LEARNING_ROOT = AUTONOMY_RUNTIME_ROOT / "learning"
TASK_SUMMARIES_ROOT = LEARNING_ROOT / "task_summaries"
TERMINAL_TASK_STATUSES = {"completed", "failed", "cancelled", "lost"}
DEFAULT_TERMINAL_IDLE_SECONDS = 6 * 60 * 60
DEFAULT_ZOMBIE_IDLE_SECONDS = 3 * 24 * 60 * 60


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _seconds_since(iso_text: str) -> float:
    text = str(iso_text or "").strip()
    if not text:
        return 10**9
    try:
        dt = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return 10**9
    return max(0.0, (datetime.now(timezone.utc) - dt).total_seconds())


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


def _task_state(task_id: str) -> Dict[str, Any]:
    return _read_json(AUTONOMY_TASKS_ROOT / task_id / "state.json", {}) or {}


def _task_contract(task_id: str) -> Dict[str, Any]:
    return _read_json(AUTONOMY_TASKS_ROOT / task_id / "contract.json", {}) or {}


def _task_summary(task_id: str) -> Dict[str, Any]:
    return _read_json(TASK_SUMMARIES_ROOT / f"{task_id}.json", {}) or {}


def _task_created_at(task_id: str, state: Dict[str, Any], contract: Dict[str, Any]) -> str:
    contract_metadata = (contract.get("metadata", {}) or {}) if isinstance(contract, dict) else {}
    state_metadata = (state.get("metadata", {}) or {}) if isinstance(state, dict) else {}
    for value in (
        contract_metadata.get("created_at"),
        contract.get("created_at"),
        state_metadata.get("created_at"),
        state.get("created_at"),
    ):
        text = str(value or "").strip()
        if text:
            return text
    return ""


def _resolve_root_task_id(task_id: str, contracts: Dict[str, Dict[str, Any]]) -> str:
    current = task_id
    seen: set[str] = set()
    while current and current not in seen:
        seen.add(current)
        metadata = ((contracts.get(current, {}) or {}).get("metadata", {}) or {})
        lineage_root = str(metadata.get("lineage_root_task_id", "")).strip()
        if lineage_root and lineage_root in contracts:
            return lineage_root
        predecessor = str(metadata.get("predecessor_task_id", "")).strip()
        if not predecessor or predecessor not in contracts:
            return current
        current = predecessor
    return task_id


def _group_tasks() -> Dict[str, List[Dict[str, Any]]]:
    states: Dict[str, Dict[str, Any]] = {}
    contracts: Dict[str, Dict[str, Any]] = {}
    for task_dir in sorted((path for path in AUTONOMY_TASKS_ROOT.iterdir() if path.is_dir()), key=lambda path: path.name):
        task_id = task_dir.name
        states[task_id] = _task_state(task_id)
        contracts[task_id] = _task_contract(task_id)

    groups: Dict[str, List[Dict[str, Any]]] = {}
    for task_id in contracts:
        root_task_id = _resolve_root_task_id(task_id, contracts)
        groups.setdefault(root_task_id, []).append(
            {
                "task_id": task_id,
                "state": states.get(task_id, {}) or {},
                "contract": contracts.get(task_id, {}) or {},
            }
        )

    for root_task_id, items in groups.items():
        items.sort(
            key=lambda item: (
                _task_created_at(str(item.get("task_id", "")), item.get("state", {}) or {}, item.get("contract", {}) or {}) or "9999-12-31T23:59:59+00:00",
                str(item.get("task_id", "")),
            )
        )
    return groups


def _task_links(task_ids: List[str], root_task_id: str) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    if not AUTONOMY_LINKS_ROOT.exists():
        return rows
    refs = set(task_ids)
    refs.add(root_task_id)
    for path in sorted(AUTONOMY_LINKS_ROOT.glob("*.json")):
        payload = _read_json(path, {}) or {}
        if not payload:
            continue
        values = {
            str(payload.get("task_id", "")).strip(),
            str(payload.get("lineage_root_task_id", "")).strip(),
            str(payload.get("predecessor_task_id", "")).strip(),
        }
        if refs.isdisjoint({value for value in values if value}):
            continue
        rows.append({"path": str(path), "payload": payload})
    return rows


def _has_active_execution(state: Dict[str, Any]) -> bool:
    metadata = (state.get("metadata", {}) or {}) if isinstance(state, dict) else {}
    active_execution = metadata.get("active_execution", {}) or {}
    return bool(str(active_execution.get("run_id", "")).strip())


def _archive_flag(state: Dict[str, Any]) -> bool:
    metadata = (state.get("metadata", {}) or {}) if isinstance(state, dict) else {}
    return bool(
        metadata.get("archive_approved")
        or ((metadata.get("task_retention", {}) or {}).get("archive_approved"))
        or ((metadata.get("lifecycle", {}) or {}).get("archive_approved"))
    )


def _superseded(state: Dict[str, Any]) -> bool:
    metadata = (state.get("metadata", {}) or {}) if isinstance(state, dict) else {}
    next_action = str(state.get("next_action", "")).strip()
    return bool(str(metadata.get("superseded_by_task_id", "")).strip() or next_action.startswith("superseded_by:") or next_action.startswith("rerooted_to:"))


def _retention_idle_seconds(state: Dict[str, Any], evidence: Dict[str, Any]) -> float:
    last_progress_at = str(state.get("last_progress_at", "")).strip()
    last_success_at = str(state.get("last_success_at", "")).strip()
    last_update_at = str(state.get("last_update_at", "")).strip()
    if last_progress_at:
        return _seconds_since(last_progress_at)
    if last_success_at:
        return _seconds_since(last_success_at)
    if last_update_at:
        return _seconds_since(last_update_at)
    return float(evidence.get("idle_seconds", 0) or 0)


def _is_ephemeral_task(task_id: str, contract: Dict[str, Any]) -> bool:
    lowered_task_id = str(task_id or "").strip().lower()
    goal = str((contract or {}).get("user_goal", "")).strip().lower()
    return (
        lowered_task_id.startswith("system-")
        or lowered_task_id.startswith("read-heartbeat")
        or "smoke" in lowered_task_id
        or goal.startswith("system:")
        or "read heartbeat.md" in goal
    )


def _candidate_for_member(task_id: str, state: Dict[str, Any], contract: Dict[str, Any], *, terminal_idle_seconds: int, zombie_idle_seconds: int) -> Dict[str, Any]:
    status = str(state.get("status", "unknown")).strip() or "unknown"
    evidence = build_progress_evidence(task_id, stale_after_seconds=max(300, min(terminal_idle_seconds, zombie_idle_seconds)))
    idle_seconds = _retention_idle_seconds(state, evidence)
    if status in TERMINAL_TASK_STATUSES and idle_seconds >= terminal_idle_seconds:
        return {"archivable": True, "classification": "terminal", "idle_seconds": idle_seconds}
    if _archive_flag(state) and idle_seconds >= min(terminal_idle_seconds, zombie_idle_seconds):
        return {"archivable": True, "classification": "approved_zombie", "idle_seconds": idle_seconds}
    if _superseded(state) and not _has_active_execution(state) and idle_seconds >= zombie_idle_seconds:
        return {"archivable": True, "classification": "superseded_zombie", "idle_seconds": idle_seconds}
    if _is_ephemeral_task(task_id, contract) and not _has_active_execution(state) and idle_seconds >= zombie_idle_seconds:
        return {"archivable": True, "classification": "ephemeral_zombie", "idle_seconds": idle_seconds}
    return {"archivable": False, "classification": "", "idle_seconds": idle_seconds}


def _build_lineage_distillation(root_task_id: str, members: List[Dict[str, Any]], links: List[Dict[str, Any]], classification: str) -> Dict[str, Any]:
    latest = members[-1]
    latest_task_id = str(latest.get("task_id", "")).strip()
    root = next((item for item in members if str(item.get("task_id", "")).strip() == root_task_id), members[0])
    root_contract = root.get("contract", {}) or {}
    root_state = root.get("state", {}) or {}
    latest_state = latest.get("state", {}) or {}
    snapshot = build_task_status_snapshot(latest_task_id)
    recent_events = snapshot.get("recent_events", []) or []
    summary = _task_summary(latest_task_id)
    writeback = load_memory_writeback(latest_task_id)
    milestone = snapshot.get("milestone_progress", {}) or {}
    milestone_stats = milestone.get("stats", {}) or {}
    business = snapshot.get("business_outcome", {}) or {}
    learning_notes = list(summary.get("notes", []) or [])
    learning_backlog = list(latest_state.get("learning_backlog", []) or [])

    distilled = {
        "archived_at": _utc_now_iso(),
        "classification": classification,
        "lineage_root_task_id": root_task_id,
        "task_ids": [str(item.get("task_id", "")).strip() for item in members],
        "latest_task_id": latest_task_id,
        "goal": str(root_contract.get("user_goal", "")).strip() or str(snapshot.get("goal", "")).strip(),
        "done_definition": str(root_contract.get("done_definition", "")).strip(),
        "latest_status": str(snapshot.get("status", "")).strip() or str(latest_state.get("status", "")).strip(),
        "latest_stage": str(snapshot.get("current_stage", "")).strip() or str(latest_state.get("current_stage", "")).strip(),
        "latest_next_action": str(snapshot.get("next_action", "")).strip() or str(latest_state.get("next_action", "")).strip(),
        "authoritative_summary": str(snapshot.get("authoritative_summary", "")).strip(),
        "proof_summary": str(business.get("proof_summary", "")).strip(),
        "business_outcome": business,
        "milestone_stats": milestone_stats,
        "completed_stages": list(summary.get("completed_stages", []) or []),
        "last_completed_stage": str(summary.get("last_completed_stage", "")).strip(),
        "blockers": list(latest_state.get("blockers", []) or []),
        "learning_backlog": learning_backlog,
        "learning_notes": learning_notes,
        "memory_writeback": writeback,
        "conversation_links_archived": [
            {
                "provider": str((row.get("payload", {}) or {}).get("provider", "")).strip(),
                "conversation_id": str((row.get("payload", {}) or {}).get("conversation_id", "")).strip(),
                "path": str(row.get("path", "")).strip(),
            }
            for row in links
        ],
        "recent_events": recent_events[-8:],
        "stage_artifacts": ((latest_state.get("metadata", {}) or {}).get("stage_artifacts", {}) or {}),
        "root_last_progress_at": str(root_state.get("last_progress_at", "")).strip(),
        "latest_last_progress_at": str(latest_state.get("last_progress_at", "")).strip(),
        "latest_last_update_at": str(latest_state.get("last_update_at", "")).strip(),
    }
    distilled["distilled_learning"] = [
        item
        for item in [
            str(distilled.get("proof_summary", "")).strip(),
            str(distilled.get("authoritative_summary", "")).strip(),
            f"completed_stages={','.join(distilled.get('completed_stages', []) or [])}" if distilled.get("completed_stages") else "",
            f"blockers={'; '.join(distilled.get('blockers', []) or [])}" if distilled.get("blockers") else "",
            f"learning_backlog={'; '.join(learning_backlog)}" if learning_backlog else "",
        ]
        if item
    ]
    return distilled


def _archive_path_for_link(link_path: str) -> Path:
    name = Path(link_path).name
    return AUTONOMY_ARCHIVE_LINKS_ROOT / name


def _move_path(source: Path, target: Path) -> str:
    if not source.exists():
        return str(target) if target.exists() else ""
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists():
        target = target.with_name(f"{target.stem}-{uuid.uuid4().hex[:8]}{target.suffix}")
    shutil.move(str(source), str(target))
    return str(target)


def _append_archived_registry(entry: Dict[str, Any]) -> None:
    registry = _read_json(ARCHIVED_TASK_REGISTRY_PATH, {"generated_at": "", "items": []}) or {"generated_at": "", "items": []}
    items = list(registry.get("items", []) or [])
    items.append(entry)
    deduped: Dict[tuple[str, str, tuple[str, ...]], Dict[str, Any]] = {}
    for item in items:
        key = (
            str(item.get("lineage_root_task_id", "")).strip(),
            str(item.get("classification", "")).strip(),
            tuple(str(task_id).strip() for task_id in (item.get("task_ids", []) or []) if str(task_id).strip()),
        )
        deduped[key] = item
    registry["generated_at"] = _utc_now_iso()
    registry["items"] = sorted(
        deduped.values(),
        key=lambda item: (
            str(item.get("archived_at", "")).strip() or "0000-00-00T00:00:00+00:00",
            str(item.get("lineage_root_task_id", "")).strip(),
        ),
    )[-500:]
    _write_json(ARCHIVED_TASK_REGISTRY_PATH, registry)


def _persist_task_summary_distillation(task_id: str, distillation: Dict[str, Any]) -> None:
    path = TASK_SUMMARIES_ROOT / f"{task_id}.json"
    current = _read_json(path, {"task_id": task_id, "notes": []}) or {"task_id": task_id, "notes": []}
    notes = list(current.get("notes", []) or [])
    summary_line = str(distillation.get("authoritative_summary", "")).strip() or str(distillation.get("proof_summary", "")).strip()
    if summary_line and summary_line not in notes:
        notes.append(summary_line)
    current.update(
        {
            "task_id": task_id,
            "status": "archived",
            "archived_at": distillation.get("archived_at", ""),
            "archive_classification": distillation.get("classification", ""),
            "archive_lineage_root_task_id": distillation.get("lineage_root_task_id", ""),
            "distilled_learning": list(distillation.get("distilled_learning", []) or []),
            "notes": notes[-20:],
            "updated_at": _utc_now_iso(),
        }
    )
    _write_json(path, current)


def _archive_lineage(root_task_id: str, members: List[Dict[str, Any]], links: List[Dict[str, Any]], classification: str) -> Dict[str, Any]:
    distillation = _build_lineage_distillation(root_task_id, members, links, classification)
    manifest_path = AUTONOMY_ARCHIVE_MANIFESTS_ROOT / f"{root_task_id}.json"
    distillation["manifest_path"] = _write_json(manifest_path, distillation)

    archived_tasks: List[Dict[str, Any]] = []
    archived_links: List[Dict[str, Any]] = []
    archived_status_snapshots: List[Dict[str, Any]] = []

    for member in members:
        task_id = str(member.get("task_id", "")).strip()
        if not task_id:
            continue
        record_memory_writeback(
            task_id,
            source="task_retention_archive",
            summary={
                "memory_targets": ["task", "runtime"],
                "decisions": [f"archived:{classification}"],
                "memory_reasons": ["task_distilled_before_archive"],
                "next_actions": ["consult archive manifest if lineage needs to be reopened"],
            },
        )
        _persist_task_summary_distillation(task_id, distillation)
        contract = member.get("contract", {}) or {}
        goal = str(contract.get("user_goal", "")).strip()
        if goal:
            record_learning(task_id, f"Archived after distillation ({classification}): {goal[:160]}")
        archived_path = _move_path(AUTONOMY_TASKS_ROOT / task_id, AUTONOMY_ARCHIVE_TASKS_ROOT / task_id)
        if archived_path:
            archived_tasks.append({"task_id": task_id, "path": archived_path})
        status_path = _move_path(TASK_STATUS_ROOT / f"{task_id}.json", AUTONOMY_ARCHIVE_STATUS_ROOT / f"{task_id}.json")
        if status_path:
            archived_status_snapshots.append({"task_id": task_id, "path": status_path})

    for link in links:
        source = Path(str(link.get("path", "")).strip())
        target = _archive_path_for_link(str(source))
        archived_path = _move_path(source, target)
        if archived_path:
            archived_links.append({"path": archived_path})

    archive_entry = {
        "archived_at": distillation.get("archived_at", ""),
        "classification": classification,
        "lineage_root_task_id": root_task_id,
        "task_ids": [str(item.get("task_id", "")).strip() for item in members if str(item.get("task_id", "")).strip()],
        "manifest_path": distillation.get("manifest_path", ""),
        "archived_tasks": archived_tasks,
        "archived_links": archived_links,
        "archived_status_snapshots": archived_status_snapshots,
        "authoritative_summary": distillation.get("authoritative_summary", ""),
        "proof_summary": distillation.get("proof_summary", ""),
    }
    _append_archived_registry(archive_entry)
    return archive_entry


def run_task_retention(
    *,
    terminal_idle_seconds: int = DEFAULT_TERMINAL_IDLE_SECONDS,
    zombie_idle_seconds: int = DEFAULT_ZOMBIE_IDLE_SECONDS,
    apply: bool = True,
) -> Dict[str, Any]:
    groups = _group_tasks()
    candidates: List[Dict[str, Any]] = []
    archived: List[Dict[str, Any]] = []
    skipped: List[Dict[str, Any]] = []

    for root_task_id, members in sorted(groups.items(), key=lambda item: item[0]):
        task_ids = [str(member.get("task_id", "")).strip() for member in members if str(member.get("task_id", "")).strip()]
        links = _task_links(task_ids, root_task_id)
        member_results = [
            _candidate_for_member(
                str(member.get("task_id", "")).strip(),
                member.get("state", {}) or {},
                member.get("contract", {}) or {},
                terminal_idle_seconds=terminal_idle_seconds,
                zombie_idle_seconds=zombie_idle_seconds,
            )
            for member in members
        ]
        if any(_has_active_execution(member.get("state", {}) or {}) for member in members):
            skipped.append({"lineage_root_task_id": root_task_id, "reason": "active_execution_present"})
            continue
        if not all(result.get("archivable") for result in member_results):
            skipped.append({"lineage_root_task_id": root_task_id, "reason": "lineage_not_fully_archivable"})
            continue
        latest_result = member_results[-1]
        classification = str(latest_result.get("classification", "")).strip() or "terminal"
        if links and classification == "terminal":
            skipped.append({"lineage_root_task_id": root_task_id, "reason": "conversation_link_present"})
            continue
        candidate = {
            "lineage_root_task_id": root_task_id,
            "task_ids": task_ids,
            "classification": classification,
            "latest_idle_seconds": float(latest_result.get("idle_seconds", 0) or 0),
            "link_count": len(links),
        }
        candidates.append(candidate)
        if apply:
            archived.append(_archive_lineage(root_task_id, members, links, classification))

    payload = {
        "generated_at": _utc_now_iso(),
        "terminal_idle_seconds": terminal_idle_seconds,
        "zombie_idle_seconds": zombie_idle_seconds,
        "apply": apply,
        "candidates_total": len(candidates),
        "archived_total": len(archived),
        "candidates": candidates[:200],
        "archived": archived[:200],
        "skipped_total": len(skipped),
        "skipped": skipped[:200],
    }
    payload["path"] = _write_json(TASK_RETENTION_LAST_RUN_PATH, payload)
    return payload


def load_archived_task_registry() -> Dict[str, Any]:
    return _read_json(ARCHIVED_TASK_REGISTRY_PATH, {"items": []}) or {"items": []}


def main() -> int:
    import argparse

    parser = argparse.ArgumentParser(description="Distill and archive completed or zombie task lineages")
    parser.add_argument("--terminal-idle-seconds", type=int, default=DEFAULT_TERMINAL_IDLE_SECONDS)
    parser.add_argument("--zombie-idle-seconds", type=int, default=DEFAULT_ZOMBIE_IDLE_SECONDS)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    print(
        json.dumps(
            run_task_retention(
                terminal_idle_seconds=args.terminal_idle_seconds,
                zombie_idle_seconds=args.zombie_idle_seconds,
                apply=not args.dry_run,
            ),
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
