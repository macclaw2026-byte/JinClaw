#!/usr/bin/env python3

from __future__ import annotations

import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

from canonical_active_task import resolve_canonical_active_task
from paths import (
    ALERTS_PATH,
    CONTROL_PLANE_ROOT,
    DOCTOR_QUEUE_PATH,
    OPS_REGISTRY_PATH,
    PROCESS_REGISTRY_PATH,
    SYSTEM_SNAPSHOT_PATH,
    TASK_REGISTRY_PATH,
    TASK_LIFECYCLE_PATH,
    WAITING_REGISTRY_PATH,
)
from progress_evidence import build_progress_evidence
from task_lifecycle import classify_task_lifecycle

OPS_DIR = Path("/Users/mac_claw/.openclaw/workspace/tools/openmoss/ops")
AUTONOMY_DIR = Path("/Users/mac_claw/.openclaw/workspace/tools/openmoss/autonomy")
if str(OPS_DIR) not in sys.path:
    sys.path.insert(0, str(OPS_DIR))
if str(AUTONOMY_DIR) not in sys.path:
    sys.path.insert(0, str(AUTONOMY_DIR))

from jinclaw_ops import doctor_payload
from learning_engine import get_error_recurrence, load_task_summary
from promotion_engine import resolve_rule_for_error


AUTONOMY_TASKS_ROOT = Path("/Users/mac_claw/.openclaw/workspace/tools/openmoss/runtime/autonomy/tasks")
LINKS_ROOT = Path("/Users/mac_claw/.openclaw/workspace/tools/openmoss/runtime/autonomy/links")

PROCESS_TARGETS = [
    {"label": "brain_enforcer", "launchd_label": "ai.openclaw.brain-enforcer"},
    {"label": "autonomy_runtime", "launchd_label": "ai.jinclaw.autonomy-runtime"},
]


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
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return str(path)


def _launchctl_status(launchd_label: str) -> Dict[str, Any]:
    domain = f"gui/{os.getuid()}/{launchd_label}"
    proc = subprocess.run(
        ["launchctl", "print", domain],
        capture_output=True,
        text=True,
        timeout=10,
    )
    output = (proc.stdout or "") + "\n" + (proc.stderr or "")
    state = "unknown"
    pid = 0
    for line in output.splitlines():
        stripped = line.strip()
        if stripped.startswith("state = "):
            state = stripped.split("=", 1)[1].strip()
        elif stripped.startswith("pid = "):
            try:
                pid = int(stripped.split("=", 1)[1].strip())
            except ValueError:
                pid = 0
    return {
        "launchd_label": launchd_label,
        "ok": proc.returncode == 0,
        "state": state,
        "pid": pid,
        "raw_excerpt": "\n".join(output.splitlines()[:20]),
    }


def build_process_registry() -> Dict[str, Any]:
    items = []
    for target in PROCESS_TARGETS:
        status = _launchctl_status(target["launchd_label"])
        status["label"] = target["label"]
        items.append(status)
    registry = {
        "generated_at": _utc_now_iso(),
        "items": items,
        "all_running": all(item.get("state") == "running" for item in items),
    }
    registry["path"] = _write_json(PROCESS_REGISTRY_PATH, registry)
    return registry


def build_ops_registry() -> Dict[str, Any]:
    registry = {
        "generated_at": _utc_now_iso(),
        "doctor": doctor_payload(),
    }
    registry["path"] = _write_json(OPS_REGISTRY_PATH, registry)
    return registry


def _load_task_state(task_id: str) -> Dict[str, Any]:
    return _read_json(AUTONOMY_TASKS_ROOT / task_id / "state.json", {})


def _load_task_contract(task_id: str) -> Dict[str, Any]:
    return _read_json(AUTONOMY_TASKS_ROOT / task_id / "contract.json", {})


def _conversation_links_for_task(task_id: str, canonical_task_id: str) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    if not LINKS_ROOT.exists():
        return rows
    for path in sorted(LINKS_ROOT.glob("*.json")):
        payload = _read_json(path, {})
        if not payload:
            continue
        if canonical_task_id not in {
            str(payload.get("task_id", "")).strip(),
            str(payload.get("lineage_root_task_id", "")).strip(),
            str(payload.get("predecessor_task_id", "")).strip(),
        } and task_id not in {
            str(payload.get("task_id", "")).strip(),
            str(payload.get("lineage_root_task_id", "")).strip(),
            str(payload.get("predecessor_task_id", "")).strip(),
        }:
            continue
        rows.append(
            {
                "path": str(path),
                "provider": payload.get("provider", ""),
                "conversation_id": payload.get("conversation_id", ""),
                "task_id": payload.get("task_id", ""),
                "lineage_root_task_id": payload.get("lineage_root_task_id", ""),
                "session_key": payload.get("session_key", ""),
                "updated_at": payload.get("updated_at", ""),
            }
        )
    return rows


def build_task_registry(*, stale_after_seconds: int = 300, escalation_after_seconds: int = 900) -> Dict[str, Any]:
    tasks: List[Dict[str, Any]] = []
    waiting: List[Dict[str, Any]] = []
    doctor_queue: List[Dict[str, Any]] = []
    alerts: List[Dict[str, Any]] = []
    seen_canonical: set[str] = set()
    lifecycle_counts = {"active": 0, "warm": 0, "archive": 0, "quarantine": 0}

    if AUTONOMY_TASKS_ROOT.exists():
        for task_root in sorted(AUTONOMY_TASKS_ROOT.iterdir()):
            if not task_root.is_dir():
                continue
            task_id = task_root.name
            state = _load_task_state(task_id)
            contract = _load_task_contract(task_id)
            canonical = resolve_canonical_active_task(task_id)
            canonical_task_id = str(canonical.get("canonical_task_id", task_id)).strip() or task_id
            evidence = build_progress_evidence(canonical_task_id, stale_after_seconds=stale_after_seconds)
            links = _conversation_links_for_task(task_id, canonical_task_id)
            lifecycle = classify_task_lifecycle(state)
            lifecycle_counts[lifecycle["tier"]] = lifecycle_counts.get(lifecycle["tier"], 0) + 1
            summary = load_task_summary(canonical_task_id)
            last_failure = summary.get("last_failure", {}) or {}
            last_failure_error = str(last_failure.get("error", "")).strip()
            recurrence = get_error_recurrence(last_failure_error) if last_failure_error else {"count": 0, "tasks": []}
            promoted_rule = resolve_rule_for_error(last_failure_error) if last_failure_error else None
            entry = {
                "task_id": task_id,
                "canonical_task_id": canonical_task_id,
                "lineage_root_task_id": canonical.get("lineage_root_task_id", task_id),
                "goal": contract.get("user_goal", ""),
                "status": state.get("status", "unknown"),
                "current_stage": state.get("current_stage", ""),
                "next_action": state.get("next_action", ""),
                "last_progress_at": state.get("last_progress_at", ""),
                "last_update_at": state.get("last_update_at", ""),
                "progress_state": evidence.get("progress_state", "unknown"),
                "needs_intervention": bool(evidence.get("needs_intervention")),
                "idle_seconds": evidence.get("idle_seconds", 0),
                "active_execution": state.get("metadata", {}).get("active_execution", {}) or {},
                "waiting_external": state.get("metadata", {}).get("waiting_external", {}) or {},
                "run_liveness": evidence.get("run_liveness", {}),
                "lifecycle": lifecycle,
                "memory": {
                    "summary": summary,
                    "last_failure": last_failure,
                    "error_recurrence": recurrence,
                    "promoted_rule": promoted_rule,
                },
                "conversation_links": links,
                "canonical": canonical,
            }
            tasks.append(entry)
            if canonical_task_id == task_id and canonical_task_id not in seen_canonical:
                seen_canonical.add(canonical_task_id)
            if entry["waiting_external"] and lifecycle["tier"] == "active":
                waiting.append(
                    {
                        "task_id": task_id,
                        "canonical_task_id": canonical_task_id,
                        "current_stage": entry["current_stage"],
                        "next_action": entry["next_action"],
                        "waiting_external": entry["waiting_external"],
                        "run_liveness": entry["run_liveness"],
                    }
                )
            if entry["needs_intervention"] and lifecycle["tier"] == "active":
                doctor_entry = {
                    "task_id": task_id,
                    "canonical_task_id": canonical_task_id,
                    "reason": evidence.get("reason", "unknown"),
                    "progress_state": entry["progress_state"],
                    "status": entry["status"],
                    "current_stage": entry["current_stage"],
                    "next_action": entry["next_action"],
                    "idle_seconds": entry["idle_seconds"],
                    "lifecycle_tier": lifecycle["tier"],
                    "error_recurrence_count": recurrence.get("count", 0),
                    "has_promoted_rule": bool(promoted_rule),
                    "promoted_rule": promoted_rule or {},
                }
                doctor_queue.append(doctor_entry)
                if entry["idle_seconds"] >= escalation_after_seconds:
                    alerts.append(
                        {
                            **doctor_entry,
                            "severity": "high",
                            "escalated": True,
                        }
                    )

    task_registry = {
        "generated_at": _utc_now_iso(),
        "items": tasks,
        "canonical_active_tasks": sorted(seen_canonical),
    }
    lifecycle_registry = {
        "generated_at": task_registry["generated_at"],
        "counts": lifecycle_counts,
        "items": [
            {
                "task_id": item["task_id"],
                "canonical_task_id": item["canonical_task_id"],
                "tier": item["lifecycle"]["tier"],
                "reason": item["lifecycle"]["reason"],
                "status": item["status"],
                "current_stage": item["current_stage"],
            }
            for item in tasks
        ],
    }
    waiting_registry = {"generated_at": task_registry["generated_at"], "items": waiting}
    doctor_queue_registry = {"generated_at": task_registry["generated_at"], "items": doctor_queue}
    alerts_registry = {"generated_at": task_registry["generated_at"], "items": alerts}
    _write_json(TASK_REGISTRY_PATH, task_registry)
    _write_json(TASK_LIFECYCLE_PATH, lifecycle_registry)
    _write_json(WAITING_REGISTRY_PATH, waiting_registry)
    _write_json(DOCTOR_QUEUE_PATH, doctor_queue_registry)
    _write_json(ALERTS_PATH, alerts_registry)
    return {
        "task_registry": task_registry,
        "task_lifecycle": lifecycle_registry,
        "waiting_registry": waiting_registry,
        "doctor_queue": doctor_queue_registry,
        "alerts": alerts_registry,
    }


def build_control_plane(*, stale_after_seconds: int = 300, escalation_after_seconds: int = 900) -> Dict[str, Any]:
    process_registry = build_process_registry()
    ops_registry = build_ops_registry()
    task_views = build_task_registry(
        stale_after_seconds=stale_after_seconds,
        escalation_after_seconds=escalation_after_seconds,
    )
    snapshot = {
        "generated_at": _utc_now_iso(),
        "process_registry_path": process_registry.get("path"),
        "ops_registry_path": ops_registry.get("path"),
        "task_registry_path": str(TASK_REGISTRY_PATH),
        "task_lifecycle_path": str(TASK_LIFECYCLE_PATH),
        "waiting_registry_path": str(WAITING_REGISTRY_PATH),
        "doctor_queue_path": str(DOCTOR_QUEUE_PATH),
        "alerts_path": str(ALERTS_PATH),
        "summary": {
            "processes_running": sum(1 for item in process_registry.get("items", []) if item.get("state") == "running"),
            "processes_total": len(process_registry.get("items", [])),
            "ops_doctor_ok": bool(ops_registry.get("doctor", {}).get("ok")),
            "tasks_total": len(task_views["task_registry"].get("items", [])),
            "tasks_active": int(task_views["task_lifecycle"].get("counts", {}).get("active", 0)),
            "tasks_warm": int(task_views["task_lifecycle"].get("counts", {}).get("warm", 0)),
            "tasks_archive": int(task_views["task_lifecycle"].get("counts", {}).get("archive", 0)),
            "tasks_quarantine": int(task_views["task_lifecycle"].get("counts", {}).get("quarantine", 0)),
            "waiting_total": len(task_views["waiting_registry"].get("items", [])),
            "doctor_queue_total": len(task_views["doctor_queue"].get("items", [])),
            "alerts_total": len(task_views["alerts"].get("items", [])),
        },
    }
    snapshot["path"] = _write_json(SYSTEM_SNAPSHOT_PATH, snapshot)
    return {
        "process_registry": process_registry,
        "ops_registry": ops_registry,
        **task_views,
        "system_snapshot": snapshot,
    }


def main() -> int:
    import argparse

    parser = argparse.ArgumentParser(description="Build the unified control plane snapshot for JinClaw")
    parser.add_argument("--stale-after-seconds", type=int, default=300)
    parser.add_argument("--escalation-after-seconds", type=int, default=900)
    args = parser.parse_args()
    print(
        json.dumps(
            build_control_plane(
                stale_after_seconds=args.stale_after_seconds,
                escalation_after_seconds=args.escalation_after_seconds,
            ),
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
