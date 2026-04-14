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
- 文件路径：`tools/openmoss/control_center/system_doctor.py`
- 文件作用：系统任务级“医生”。当任务没有按预期推进时，这里负责诊断卡点、尝试修复，并在必要时向聊天窗口升级告警。
- 顶层函数：_utc_now_iso、_write_json、_seconds_since、_progress_age_seconds、diagnose_task、repair_task_if_possible、run_system_doctor。
- 顶层类：无顶层类。
- 主流程定位：
  1. 读取 control plane 和 task state；
  2. 判断任务是否真的 stuck；
  3. 如果能修，就直接把 state 拉回 planning/start_stage；
  4. 如果超过升级阈值，就通过 receipt engine 把真实诊断回给用户。
"""
from __future__ import annotations

import json
import re
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

from adaptive_fetch_router import build_fetch_route
from acquisition_adapter_registry import build_acquisition_adapter_registry
from control_plane_builder import build_control_plane
from execution_governor import build_project_crawler_gate, classify_blocked_runtime_state, summarize_governance_attention
from paths import CONTROL_CENTER_RUNTIME_ROOT, FETCH_ROUTES_ROOT
from mission_supervisor import run_mission_supervisor
from progress_evidence import build_progress_evidence
from brain_router import route_instruction
from response_policy_engine import build_route_receipt_text, build_supervisor_status_text
from research_loop import prepare_research_package
from route_guardrails import persist_route, reroot_route_if_needed
from problem_solver import solve_problem
from task_receipt_engine import emit_route_receipt
from task_status_snapshot import build_task_status_snapshot
from capability_registry import build_capability_registry
from memory_writeback_runtime import record_memory_writeback
from governance_runtime import _build_doctor_coverage_bundle
from orchestrator import build_control_center_package

AUTONOMY_DIR = Path("/Users/mac_claw/.openclaw/workspace/tools/openmoss/autonomy")
if str(AUTONOMY_DIR) not in sys.path:
    sys.path.insert(0, str(AUTONOMY_DIR))

from manager import LINKS_ROOT, TASKS_ROOT, create_task_from_contract, ensure_autonomy_root_mission_link, events_path, find_link_by_task_id, load_contract, load_state, log_event, save_contract, save_state, task_dir
from learning_engine import load_task_summary, record_error, record_learning, update_task_summary
from promotion_engine import promote_doctor_strategy, resolve_doctor_strategy, resolve_rule_for_error
from task_contract import TaskContract
from memory_writeback_runtime import load_memory_writeback

DOCTOR_ROOT = CONTROL_CENTER_RUNTIME_ROOT / "doctor"
DOCTOR_HEARTBEATS_ROOT = DOCTOR_ROOT / "heartbeats"
DOCTOR_PROCESS_INCIDENTS_ROOT = DOCTOR_ROOT / "process_incidents"
DOCTOR_TASK_INCIDENTS_ROOT = DOCTOR_ROOT / "task_incidents"
DOCTOR_RESOLUTIONS_ROOT = DOCTOR_ROOT / "resolutions"
WORKSPACE_ROOT = Path("/Users/mac_claw/.openclaw/workspace")
CONTROL_CENTER_ROOT = WORKSPACE_ROOT / "tools/openmoss/control_center"
GSTACK_REQUIRED_FILES = [
    WORKSPACE_ROOT / 'compat/gstack/README.md',
    WORKSPACE_ROOT / 'compat/gstack/intake-assessment.md',
    WORKSPACE_ROOT / 'compat/gstack/capability-map.md',
    WORKSPACE_ROOT / 'compat/gstack/routing-policy.md',
    WORKSPACE_ROOT / 'compat/gstack/prompts/jinclaw-gstack-lite.md',
    WORKSPACE_ROOT / 'compat/gstack/prompts/jinclaw-gstack-plan.md',
    WORKSPACE_ROOT / 'compat/gstack/adapters/planning.md',
    WORKSPACE_ROOT / 'compat/gstack/adapters/review.md',
    WORKSPACE_ROOT / 'compat/gstack/adapters/verification.md',
    WORKSPACE_ROOT / 'compat/gstack/adapters/security-audit.md',
    WORKSPACE_ROOT / 'compat/gstack/adapters/acp-coding-session.md',
    WORKSPACE_ROOT / 'compat/gstack/adapters/acp-dispatch-request.md',
    WORKSPACE_ROOT / 'tools/bin/jinclaw-skill-factory',
    WORKSPACE_ROOT / 'tools/bin/jinclaw-skill-doctor',
    WORKSPACE_ROOT / 'tools/openmoss/control_center/coding_session_adapter.py',
    WORKSPACE_ROOT / 'tools/openmoss/control_center/acp_dispatch_builder.py',
]
ACQUISITION_REQUIRED_FILES = [
    WORKSPACE_ROOT / 'tools/openmoss/control_center/acquisition_hand_builder.py',
    WORKSPACE_ROOT / 'tools/openmoss/control_center/acquisition_adapter_registry.py',
    WORKSPACE_ROOT / 'tools/openmoss/control_center/acquisition_result_normalizer.py',
    WORKSPACE_ROOT / 'tools/openmoss/control_center/challenge_classifier.py',
    WORKSPACE_ROOT / 'tools/openmoss/control_center/crawler_probe_runner.py',
    WORKSPACE_ROOT / 'tools/openmoss/control_center/task_status_snapshot.py',
]
GSTACK_LIFECYCLE = ['think', 'plan', 'build', 'review', 'test', 'ship', 'reflect']
DOCTOR_RESOLUTION_REQUIRED_FIELDS = [
    "scope",
    "subject_id",
    "resolution_summary",
    "root_cause",
    "fix_summary",
    "verification_summary",
    "reusable_rule",
]

# Single-doctor architecture rule:
# JinClaw must have exactly one canonical whole-system doctor.
# Extend this file's coverage for new subsystems instead of introducing peer doctors.
# New files, features, skills, modules, bridges, schedulers, and verification paths
# should surface their health/evidence into this canonical doctor path.


def _utc_now_iso() -> str:
    """
    中文注解：
    - 功能：实现 `_utc_now_iso` 对应的处理逻辑。
    - 角色：属于本模块中的内部辅助逻辑；私有函数通常服务同文件主流程，公共函数通常作为跨模块入口或能力接口。
    - 调用关系：建议结合本文件的模块说明、调用方以及同名相关辅助函数一起阅读。
    """
    return datetime.now(timezone.utc).isoformat()


def _write_json(path: Path, payload: Dict[str, object]) -> None:
    """
    中文注解：
    - 功能：实现 `_write_json` 对应的处理逻辑。
    - 角色：属于本模块中的内部辅助逻辑；私有函数通常服务同文件主流程，公共函数通常作为跨模块入口或能力接口。
    - 调用关系：建议结合本文件的模块说明、调用方以及同名相关辅助函数一起阅读。
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _read_json(path: Path, default: Dict[str, object] | list | None = None):
    if not path.exists():
        return {} if default is None else default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {} if default is None else default


def _seconds_since(iso_text: str) -> float:
    """
    中文注解：
    - 功能：实现 `_seconds_since` 对应的处理逻辑。
    - 角色：属于本模块中的内部辅助逻辑；私有函数通常服务同文件主流程，公共函数通常作为跨模块入口或能力接口。
    - 调用关系：建议结合本文件的模块说明、调用方以及同名相关辅助函数一起阅读。
    """
    if not iso_text:
        return 10**9
    try:
        dt = datetime.fromisoformat(str(iso_text).replace("Z", "+00:00"))
    except ValueError:
        return 10**9
    return max(0.0, (datetime.now(timezone.utc) - dt).total_seconds())


def _slugify_runtime_identifier(value: str) -> str:
    slug = re.sub(r"[^a-zA-Z0-9]+", "-", str(value or "").strip().lower()).strip("-")
    return slug[:80] or "unknown"


def _tail_file(path_text: str, *, max_lines: int = 60, max_chars: int = 6000) -> Dict[str, object]:
    path = Path(str(path_text or "").strip())
    if not str(path):
        return {"path": "", "exists": False, "tail": ""}
    if not path.exists():
        return {"path": str(path), "exists": False, "tail": ""}
    try:
        tail = "\n".join(path.read_text(encoding="utf-8", errors="replace").splitlines()[-max_lines:])
    except OSError as exc:
        return {"path": str(path), "exists": True, "tail": "", "error": str(exc)}
    if len(tail) > max_chars:
        tail = tail[-max_chars:]
    return {"path": str(path), "exists": True, "tail": tail}


def _read_jsonl_tail(path: Path, *, max_items: int = 20) -> List[Dict[str, object]]:
    if not path.exists():
        return []
    try:
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return []
    items: List[Dict[str, object]] = []
    for raw in lines[-max_items:]:
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError:
            continue
        if isinstance(payload, dict):
            items.append(payload)
    return items


def _stage_snapshot(state) -> Dict[str, Dict[str, object]]:
    return {
        name: {
            "status": stage.status,
            "attempts": stage.attempts,
            "summary": stage.summary,
            "verification_status": stage.verification_status,
            "blocker": stage.blocker,
            "started_at": stage.started_at,
            "completed_at": stage.completed_at,
            "updated_at": stage.updated_at,
        }
        for name, stage in (state.stages or {}).items()
    }


def _append_task_summary_note(task_id: str, note: str, *, extra: Dict[str, object] | None = None) -> Dict[str, object]:
    text = str(note or "").strip()
    payload = dict(extra or {})
    if text:
        summary = load_task_summary(task_id)
        notes = [str(item).strip() for item in summary.get("notes", []) or [] if str(item).strip()]
        notes.append(text)
        payload["notes"] = notes[-20:]
    if not payload:
        return load_task_summary(task_id)
    return update_task_summary(task_id, payload)


def _process_incident_signature(incident: Dict[str, object]) -> str:
    parts = [
        str(incident.get("label", "")).strip(),
        str(incident.get("state", "")).strip(),
        str(incident.get("state_family", "")).strip(),
        str(incident.get("last_exit_code", "")).strip(),
        str(incident.get("runs", "")).strip(),
    ]
    return "|".join(parts)


def _process_incident_task_id(label: str) -> str:
    return f"doctor-process-watch-{_slugify_runtime_identifier(label)}"


def _task_incident_task_id(task_id: str) -> str:
    return f"doctor-task-watch-{_slugify_runtime_identifier(task_id)}"


def _task_incident_signature(task_id: str, diagnosis: Dict[str, object], repair: Dict[str, object]) -> str:
    blocked_runtime_state = diagnosis.get("blocked_runtime_state", {}) or {}
    parts = [
        task_id,
        str(diagnosis.get("status", "")).strip(),
        str(diagnosis.get("current_stage", "")).strip(),
        str(diagnosis.get("reason", "")).strip(),
        str(diagnosis.get("next_action", "")).strip(),
        str(blocked_runtime_state.get("category", "")).strip(),
        str(repair.get("reason", "")).strip(),
    ]
    return "|".join(parts)


def _task_incident_signal_text(task_id: str, diagnosis: Dict[str, object], state, recent_events: List[Dict[str, object]]) -> str:
    parts = [
        str(diagnosis.get("reason", "")).strip(),
        str(diagnosis.get("next_action", "")).strip(),
        " ".join(str(item).strip() for item in (state.blockers or []) if str(item).strip()),
    ]
    for stage in (state.stages or {}).values():
        if stage.summary:
            parts.append(stage.summary)
        if stage.blocker:
            parts.append(stage.blocker)
    for event in recent_events[-8:]:
        parts.extend(
            [
                str(event.get("event_type", "")).strip(),
                str(event.get("error", "")).strip(),
                str(event.get("summary", "")).strip(),
                str(event.get("diagnosis", "")).strip(),
            ]
        )
    return "\n".join(part for part in parts if part)


def _doctor_reusable_rule(scope: str, report: Dict[str, object]) -> str:
    diagnosis = report.get("diagnosis", {}) or {}
    reason = str(diagnosis.get("reason") or report.get("doctor_attention_reason") or "").strip()
    blocked_runtime_state = diagnosis.get("blocked_runtime_state", {}) or {}
    blocked_category = str(blocked_runtime_state.get("category", "")).strip()
    if reason in {"idle_without_active_execution", "waiting_external_without_active_execution", "stale_waiting_external"}:
        return "When execution becomes idle or stale without a live run, clear distorted runtime metadata and immediately restart the right stage instead of leaving the task parked."
    if blocked_category == "project_crawler_remediation":
        return "Only apply crawler remediation gates to routes that actually depend on the affected site capability, and auto-clear stale global gates."
    if blocked_category == "session_binding":
        return "Attach or recover a valid autonomy session link before letting a live task remain blocked on session binding."
    if "goal" in reason or "drift" in reason:
        return "When execution drifts away from the goal anchor, force a re-plan or reroot immediately before more work accumulates."
    if report.get("last_exit_code") not in {None, 0}:
        return "Install dependency and startup preflight guards for recurrent launchd crashes before re-running the same process again."
    return "When doctor cannot repair an anomaly locally, package the evidence, route it to an AI repair mission, and only close after verified recovery plus reusable learning."


def _doctor_evolution_suggestions(scope: str, report: Dict[str, object]) -> List[str]:
    diagnosis = report.get("diagnosis", {}) or {}
    reason = str(diagnosis.get("reason") or report.get("doctor_attention_reason") or "").strip()
    blocked_runtime_state = diagnosis.get("blocked_runtime_state", {}) or {}
    blocked_category = str(blocked_runtime_state.get("category", "")).strip()
    matched_rule = report.get("matched_durable_rule", {}) or {}
    suggestions: List[str] = []
    if reason in {"idle_without_active_execution", "waiting_external_without_active_execution", "stale_waiting_external"}:
        suggestions.append("add stronger liveness and stale-run guards so doctor can restart the exact stage before the task drifts further")
    if blocked_category == "project_crawler_remediation":
        suggestions.append("scope crawler remediation to route-relevant sites instead of applying a broad project-wide block")
    if blocked_category == "session_binding":
        suggestions.append("pre-bind a background autonomy session for root missions before they hit session-binding deadlocks")
    if "goal" in reason or "drift" in reason:
        suggestions.append("tighten goal-anchor verification and reroot mismatched execution earlier in the control loop")
    if report.get("last_exit_code") not in {None, 0}:
        suggestions.append("install dependency preflight checks and startup self-tests for launchd services before restart")
    if str(matched_rule.get("preferred_action", "")).strip():
        suggestions.append(f"promote durable runtime action: {matched_rule.get('preferred_action')}")
    suggestions.extend(
        [
            "persist a structured doctor resolution report so future repairs start from concrete evidence instead of rediscovery",
            "promote the resolved pattern into durable doctor and runtime guidance after verification passes",
        ]
    )
    deduped: List[str] = []
    for item in suggestions:
        text = str(item).strip()
        if text and text not in deduped:
            deduped.append(text)
    return deduped[:6]


def _record_doctor_resolution(
    *,
    scope: str,
    subject_id: str,
    watch_task_id: str,
    report: Dict[str, object],
    resolution_reason: str,
) -> Dict[str, object]:
    now = _utc_now_iso()
    reusable_rule = _doctor_reusable_rule(scope, report)
    evolution_payload = {
        "task_id": watch_task_id or subject_id,
        "subject_id": subject_id,
        "scope": scope,
        "proposed_at": now,
        "reason": resolution_reason,
        "current_blockers": list((report.get("blockers", []) or [])),
        "learning_backlog": list(((report.get("task_summary", {}) or {}).get("learning_backlog", []) or [])),
        "suggested_runtime_changes": _doctor_evolution_suggestions(scope, report),
        "reusable_rule": reusable_rule,
        "report_path": str(report.get("report_path", "")).strip(),
    }
    evolution_path = ""
    if watch_task_id and task_dir(watch_task_id).exists():
        evolution_path = str(task_dir(watch_task_id) / "runtime-evolution-proposal.json")
        _write_json(Path(evolution_path), evolution_payload)
        log_event(watch_task_id, "runtime_evolution_proposed", path=evolution_path, source="system_doctor_resolution")
    resolution_payload = {
        "written_at": now,
        "scope": scope,
        "subject_id": subject_id,
        "watch_task_id": watch_task_id,
        "resolution_reason": resolution_reason,
        "report_signature": str(report.get("signature", "")).strip(),
        "report_path": str(report.get("report_path", "")).strip(),
        "reusable_rule": reusable_rule,
        "evolution_proposal_path": evolution_path,
        "suggested_runtime_changes": evolution_payload.get("suggested_runtime_changes", []),
    }
    doctor_reason = str(((report.get("diagnosis", {}) or {}).get("reason") or report.get("doctor_attention_reason") or "")).strip()
    if doctor_reason:
        resolution_payload["promoted_rule"] = promote_doctor_strategy(
            doctor_reason=doctor_reason,
            preferred_repair=str(((report.get("repair", {}) or {}).get("reason") or resolution_reason)).strip() or resolution_reason,
            preferred_escalation_mode="ai_takeover",
            prevention_hint=reusable_rule,
            task_id=watch_task_id or subject_id,
            evidence={
                "status": str(report.get("status", "")).strip(),
                "current_stage": str(report.get("current_stage", "")).strip(),
                "scope": scope,
            },
        )
    resolution_slug = _slugify_runtime_identifier(f"{scope}-{subject_id}")
    resolution_path = DOCTOR_RESOLUTIONS_ROOT / f"{resolution_slug}.json"
    resolution_payload["path"] = str(resolution_path)
    _write_json(resolution_path, resolution_payload)

    learning_owner = watch_task_id if watch_task_id and task_dir(watch_task_id).exists() else subject_id
    record_learning(
        learning_owner,
        f"{scope} resolved for {subject_id}: {resolution_reason}. Reusable rule: {reusable_rule}",
    )
    _append_task_summary_note(
        learning_owner,
        f"Doctor resolved {scope} for {subject_id}: {resolution_reason}",
        extra={
            "doctor_last_resolution_path": str(resolution_path),
            "doctor_last_resolution_at": now,
            "doctor_evolution_proposal_path": evolution_path,
        },
    )
    if scope == "task_incident" and task_dir(subject_id).exists():
        _append_task_summary_note(
            subject_id,
            f"Doctor AI watch resolved the anomaly via {watch_task_id or 'doctor'}: {resolution_reason}",
            extra={
                "doctor_watch_task_id": watch_task_id,
                "doctor_last_resolution_path": str(resolution_path),
                "doctor_last_resolution_at": now,
                "doctor_evolution_proposal_path": evolution_path,
            },
        )
        state = load_state(subject_id)
        state.metadata["doctor_last_resolution"] = resolution_payload
        state.metadata["doctor_task_incident_active"] = False
        state.last_update_at = now
        save_state(state)
        record_memory_writeback(
            subject_id,
            source="doctor:ai_resolution",
            summary={
                "attention_required": False,
                "state_patch": {},
                "governance_patch": {},
                "next_actions": ["keep the reusable rule active in future doctor cycles"],
                "warnings": [],
                "errors": [],
                "decisions": ["doctor_ai_watch_resolved", "runtime_evolution_proposed"],
                "memory_targets": ["runtime", "task", "project"],
                "memory_reasons": ["doctor_resolution", "system_evolution"],
            },
        )
    if watch_task_id and task_dir(watch_task_id).exists():
        watch_state = load_state(watch_task_id)
        watch_state.metadata["doctor_watch_resolution"] = resolution_payload
        watch_state.metadata["doctor_watch_active"] = False
        watch_state.last_update_at = now
        save_state(watch_state)
        log_event(watch_task_id, "doctor_watch_resolved", resolution=resolution_payload)
    return resolution_payload


def _reopen_process_incident_task(task_id: str, incident_report: Dict[str, object]) -> str:
    state = load_state(task_id)
    history = list(state.metadata.get("doctor_process_incident_history", []) or [])
    history.append(
        {
            "at": str(incident_report.get("generated_at", "")).strip(),
            "signature": str(incident_report.get("signature", "")).strip(),
            "label": str(incident_report.get("label", "")).strip(),
            "reason": str(incident_report.get("doctor_attention_reason", "")).strip(),
            "last_exit_code": incident_report.get("last_exit_code"),
            "report_path": str(incident_report.get("report_path", "")).strip(),
        }
    )
    state.metadata["doctor_process_incident"] = incident_report
    state.metadata["doctor_process_incident_history"] = history[-12:]
    state.metadata["doctor_process_incident_active"] = True
    state.metadata["doctor_process_incident_last_report"] = str(incident_report.get("report_path", "")).strip()
    state.metadata["doctor_process_incident_last_seen_at"] = _utc_now_iso()
    state.metadata.pop("waiting_external", None)
    state.metadata.pop("active_execution", None)

    reopened = False
    if state.status in {"completed", "failed", "blocked"}:
        target_stage = "understand" if "understand" in state.stages else state.first_pending_stage() or state.current_stage or ""
        for stage_name in state.stage_order:
            stage = state.stages.get(stage_name)
            if not stage:
                continue
            stage.status = "pending"
            stage.summary = ""
            stage.blocker = ""
            stage.completed_at = ""
            stage.updated_at = _utc_now_iso()
        milestone_progress = dict(state.metadata.get("milestone_progress", {}) or {})
        for entry in milestone_progress.values():
            if not isinstance(entry, dict):
                continue
            entry["status"] = "pending"
            entry["completed_at"] = ""
            entry["summary"] = ""
        if milestone_progress:
            state.metadata["milestone_progress"] = milestone_progress
            stats = state.metadata.get("milestone_stats", {}) or {}
            stats["required_completed"] = 0
            stats["all_required_completed"] = False
            state.metadata["milestone_stats"] = stats
        state.status = "planning"
        state.current_stage = target_stage
        state.blockers = [f"doctor detected runtime incident for {incident_report.get('label', task_id)}"]
        state.next_action = f"start_stage:{target_stage}" if target_stage else "initialize"
        reopened = True
    state.last_update_at = _utc_now_iso()
    save_state(state)
    log_event(
        task_id,
        "doctor_process_incident_observed",
        incident_report=str(incident_report.get("report_path", "")).strip(),
        signature=str(incident_report.get("signature", "")).strip(),
        last_exit_code=incident_report.get("last_exit_code"),
        reopened=reopened,
    )
    return "reactivated" if reopened else "updated"


def _build_process_incident_goal(incident_report: Dict[str, object]) -> str:
    name = str(incident_report.get("name", "")).strip() or str(incident_report.get("label", "")).strip() or "runtime job"
    label = str(incident_report.get("label", "")).strip() or name
    description = str(incident_report.get("description", "")).strip()
    trigger = str(incident_report.get("trigger_summary", "")).strip()
    status_text = str(incident_report.get("status_text", "")).strip()
    reason = str(incident_report.get("doctor_attention_reason", "")).strip()
    report_path = str(incident_report.get("report_path", "")).strip()
    last_exit_code = incident_report.get("last_exit_code")
    lines = [
        f"持续监控并修复运行进程 incident：{name}（{label}）。",
        f"当前 doctor 检测到该进程异常，状态为 {status_text or incident_report.get('state', 'unknown')}，最近 exit code 为 {last_exit_code if last_exit_code is not None else 'unknown'}，触发原因是 {reason or 'runtime incident'}。",
    ]
    if description:
        lines.append(f"任务职责：{description}")
    if trigger:
        lines.append(f"触发方式：{trigger}")
    if report_path:
        lines.append(f"证据包：{report_path}")
    lines.append("请基于 launchctl 状态、stdout/stderr 日志尾部和历史规则先定位根因，再实施修复、验证恢复，并把结论写入学习与复盘。")
    return "\n".join(lines)


def _upsert_process_incident_task(incident_report: Dict[str, object]) -> Dict[str, object]:
    label = str(incident_report.get("label", "")).strip()
    task_id = _process_incident_task_id(label)
    created = False
    if not task_dir(task_id).exists():
        goal = _build_process_incident_goal(incident_report)
        package = build_control_center_package(task_id, goal, source="system_doctor:process_incident:root_mission")
        package["metadata"] = {
            **(package.get("metadata", {}) or {}),
            "root_mission": True,
            "doctor_process_incident_watch": True,
            "doctor_process_label": label,
            "doctor_process_incident": incident_report,
        }
        contract = TaskContract.from_dict(
            {
                "task_id": task_id,
                "user_goal": package.get("goal", goal),
                "done_definition": package.get("done_definition", ""),
                "hard_constraints": package.get("hard_constraints", []) or [],
                "soft_preferences": [],
                "allowed_tools": package.get("allowed_tools", []) or [],
                "forbidden_actions": package.get("forbidden_actions", []) or [],
                "stages": package.get("stages", []) or [],
                "metadata": package.get("metadata", {}) or {},
            }
        )
        create_task_from_contract(contract)
        log_event(
            task_id,
            "doctor_process_incident_task_created",
            incident_report=str(incident_report.get("report_path", "")).strip(),
            signature=str(incident_report.get("signature", "")).strip(),
            label=label,
        )
        task_action = "created"
        created = True
    else:
        task_action = _reopen_process_incident_task(task_id, incident_report)
    link = ensure_autonomy_root_mission_link(task_id)
    return {
        "task_id": task_id,
        "task_action": task_action,
        "created": created,
        "link_provider": str(link.get("provider", "")).strip(),
        "link_conversation_id": str(link.get("conversation_id", "")).strip(),
        "link_kind": str(link.get("link_kind", "")).strip(),
    }


def _task_incident_error_text(report: Dict[str, object]) -> str:
    diagnosis = report.get("diagnosis", {}) or {}
    recent_events = list(report.get("recent_events", []) or [])
    latest_signal = ""
    for event in reversed(recent_events):
        latest_signal = str(event.get("error", "")).strip() or str(event.get("summary", "")).strip()
        if latest_signal:
            break
    parts = [
        f"doctor_task_incident:{str(diagnosis.get('reason', '')).strip()}",
        str(report.get("next_action", "")).strip(),
        latest_signal,
    ]
    return " | ".join(part for part in parts if part)[:2000]


def _process_incident_error_text(report: Dict[str, object]) -> str:
    stderr_tail = (report.get("stderr_tail", {}) or {}).get("tail", "")
    last_tail_line = ""
    for line in reversed(str(stderr_tail or "").splitlines()):
        if line.strip():
            last_tail_line = line.strip()
            break
    parts = [
        f"doctor_process_incident:{str(report.get('label', '')).strip()}",
        str(report.get("doctor_attention_reason", "")).strip(),
        f"exit:{report.get('last_exit_code')}",
        last_tail_line,
    ]
    return " | ".join(part for part in parts if part)[:2000]


def _build_task_incident_goal(incident_report: Dict[str, object]) -> str:
    task_id = str(incident_report.get("watched_task_id", "")).strip() or "unknown-task"
    goal = str(incident_report.get("goal", "")).strip()
    diagnosis = incident_report.get("diagnosis", {}) or {}
    repair = incident_report.get("repair", {}) or {}
    lines = [
        f"持续监控并修复任务异常：{task_id}。",
        f"当前 doctor 检测到该任务异常，状态为 {incident_report.get('status', 'unknown')}，阶段为 {incident_report.get('current_stage', 'unknown')}，原因是 {diagnosis.get('reason', 'unknown')}。",
        f"doctor 一线修复结果：{repair.get('reason', 'not_attempted')}；若未真正恢复，请继续接管直到异常解除。",
    ]
    if goal:
        lines.append(f"任务目标：{goal}")
    if str(incident_report.get("next_action", "")).strip():
        lines.append(f"当前 next_action：{incident_report.get('next_action')}")
    if str(incident_report.get("report_path", "")).strip():
        lines.append(f"证据包：{incident_report.get('report_path')}")
    lines.append("请先看状态快照、阶段信息、最近事件和 durable rules，定位根因后实施修复、验证恢复，并在恢复后写出 root cause、reusable rule 与 runtime evolution proposal。")
    return "\n".join(lines)


def _reopen_task_incident_task(task_id: str, incident_report: Dict[str, object]) -> str:
    state = load_state(task_id)
    history = list(state.metadata.get("doctor_task_incident_history", []) or [])
    history.append(
        {
            "at": str(incident_report.get("generated_at", "")).strip(),
            "signature": str(incident_report.get("signature", "")).strip(),
            "watched_task_id": str(incident_report.get("watched_task_id", "")).strip(),
            "reason": str(((incident_report.get("diagnosis", {}) or {}).get("reason", ""))).strip(),
            "report_path": str(incident_report.get("report_path", "")).strip(),
        }
    )
    state.metadata["doctor_task_incident"] = incident_report
    state.metadata["doctor_task_incident_history"] = history[-12:]
    state.metadata["doctor_watch_active"] = True
    state.metadata["doctor_watched_task_id"] = str(incident_report.get("watched_task_id", "")).strip()
    state.metadata["doctor_task_incident_last_report"] = str(incident_report.get("report_path", "")).strip()
    state.metadata["doctor_task_incident_last_seen_at"] = _utc_now_iso()
    reopened = False
    if state.status in {"completed", "failed", "blocked"}:
        target_stage = "understand" if "understand" in state.stages else state.first_pending_stage() or state.current_stage or ""
        for stage_name in state.stage_order:
            stage = state.stages.get(stage_name)
            if not stage:
                continue
            stage.status = "pending"
            stage.summary = ""
            stage.blocker = ""
            stage.completed_at = ""
            stage.updated_at = _utc_now_iso()
        state.status = "planning"
        state.current_stage = target_stage
        state.blockers = [f"doctor detected unresolved anomaly for {incident_report.get('watched_task_id', task_id)}"]
        state.next_action = f"start_stage:{target_stage}" if target_stage else "initialize"
        reopened = True
    state.last_update_at = _utc_now_iso()
    save_state(state)
    log_event(
        task_id,
        "doctor_task_incident_observed",
        incident_report=str(incident_report.get("report_path", "")).strip(),
        signature=str(incident_report.get("signature", "")).strip(),
        watched_task_id=str(incident_report.get("watched_task_id", "")).strip(),
        reopened=reopened,
    )
    return "reactivated" if reopened else "updated"


def _upsert_task_incident_task(incident_report: Dict[str, object]) -> Dict[str, object]:
    watched_task_id = str(incident_report.get("watched_task_id", "")).strip()
    task_id = _task_incident_task_id(watched_task_id or "unknown-task")
    created = False
    if not task_dir(task_id).exists():
        goal = _build_task_incident_goal(incident_report)
        package = build_control_center_package(task_id, goal, source="system_doctor:task_incident:root_mission")
        package["metadata"] = {
            **(package.get("metadata", {}) or {}),
            "root_mission": True,
            "doctor_task_incident_watch": True,
            "doctor_watched_task_id": watched_task_id,
            "doctor_task_incident": incident_report,
        }
        contract = TaskContract.from_dict(
            {
                "task_id": task_id,
                "user_goal": package.get("goal", goal),
                "done_definition": package.get("done_definition", ""),
                "hard_constraints": package.get("hard_constraints", []) or [],
                "soft_preferences": [],
                "allowed_tools": package.get("allowed_tools", []) or [],
                "forbidden_actions": package.get("forbidden_actions", []) or [],
                "stages": package.get("stages", []) or [],
                "metadata": package.get("metadata", {}) or {},
            }
        )
        create_task_from_contract(contract)
        log_event(
            task_id,
            "doctor_task_incident_task_created",
            incident_report=str(incident_report.get("report_path", "")).strip(),
            signature=str(incident_report.get("signature", "")).strip(),
            watched_task_id=watched_task_id,
        )
        task_action = "created"
        created = True
    else:
        task_action = _reopen_task_incident_task(task_id, incident_report)
    link = ensure_autonomy_root_mission_link(task_id)
    return {
        "task_id": task_id,
        "task_action": task_action,
        "created": created,
        "link_provider": str(link.get("provider", "")).strip(),
        "link_conversation_id": str(link.get("conversation_id", "")).strip(),
        "link_kind": str(link.get("link_kind", "")).strip(),
    }


def _should_route_task_incident_to_ai(task_id: str, canonical_task_id: str, diagnosis: Dict[str, object], repair: Dict[str, object]) -> bool:
    if not diagnosis.get("stuck"):
        return False
    if task_id != canonical_task_id:
        return False
    if task_id.startswith("doctor-process-watch-") or task_id.startswith("doctor-task-watch-"):
        return False
    contract = load_contract(task_id)
    metadata = contract.metadata or {}
    if metadata.get("doctor_process_incident_watch") or metadata.get("doctor_task_incident_watch"):
        return False
    state = load_state(task_id)
    if str(state.metadata.get("superseded_by_task_id", "")).strip():
        return False
    blocked_category = str(((diagnosis.get("blocked_runtime_state", {}) or {}).get("category", ""))).strip()
    if blocked_category == "targeted_fix":
        return False
    if repair.get("repaired") and str(repair.get("reason", "")).strip() not in {"doctor_failure_takeover_started", "awaiting_human_guidance"}:
        return False
    return True


def _build_task_incident_report(candidate: Dict[str, object]) -> Dict[str, object]:
    task_id = str(candidate.get("task_id", "")).strip()
    diagnosis = dict(candidate.get("diagnosis", {}) or {})
    repair = dict(candidate.get("repair", {}) or {})
    state = load_state(task_id)
    contract = load_contract(task_id)
    summary = load_task_summary(task_id)
    recent_events = _read_jsonl_tail(events_path(task_id), max_items=20)
    signal_text = _task_incident_signal_text(task_id, diagnosis, state, recent_events)
    matched_rule = resolve_rule_for_error(signal_text) if signal_text else None
    status_snapshot = build_task_status_snapshot(task_id)
    report = {
        "generated_at": _utc_now_iso(),
        "last_seen_at": _utc_now_iso(),
        "active": True,
        "watched_task_id": task_id,
        "canonical_task_id": str(candidate.get("canonical_task_id", task_id)).strip() or task_id,
        "goal": contract.user_goal,
        "done_definition": contract.done_definition,
        "status": state.status,
        "current_stage": state.current_stage,
        "next_action": state.next_action,
        "blockers": list(state.blockers or []),
        "active_execution": state.metadata.get("active_execution", {}) or {},
        "waiting_external": state.metadata.get("waiting_external", {}) or {},
        "stage_snapshot": _stage_snapshot(state),
        "diagnosis": diagnosis,
        "repair": repair,
        "priority": dict(candidate.get("priority", {}) or {}),
        "task_summary": summary,
        "memory_writeback": load_memory_writeback(task_id),
        "recent_events": recent_events,
        "task_status_snapshot": {
            "governance": status_snapshot.get("governance", {}) or {},
            "authoritative_summary": status_snapshot.get("authoritative_summary", {}),
            "acquisition_hand": status_snapshot.get("acquisition_hand", {}) or {},
        },
        "signal_excerpt": signal_text[-4000:] if signal_text else "",
        "matched_durable_rule": {
            "error_key": str((matched_rule or {}).get("error_key", "")).strip(),
            "preferred_action": str((matched_rule or {}).get("preferred_action", "")).strip(),
            "preferred_guard": str((matched_rule or {}).get("preferred_guard", "")).strip(),
            "prevention_hint": str((matched_rule or {}).get("prevention_hint", "")).strip(),
        }
        if matched_rule
        else {},
    }
    report["signature"] = _task_incident_signature(task_id, diagnosis, repair)
    return report


def _reconcile_task_incidents(candidates: List[Dict[str, object]], *, idle_after_seconds: int) -> Dict[str, object]:
    now = _utc_now_iso()
    active_candidates = [item for item in candidates if str(item.get("task_id", "")).strip()]
    active_task_ids = {str(item.get("task_id", "")).strip() for item in active_candidates}
    resolved: List[Dict[str, object]] = []
    dispatched: List[Dict[str, object]] = []

    if DOCTOR_TASK_INCIDENTS_ROOT.exists():
        for path in sorted(DOCTOR_TASK_INCIDENTS_ROOT.glob("*.json")):
            payload = _read_json(path, {})
            if not isinstance(payload, dict):
                continue
            watched_task_id = str(payload.get("watched_task_id", "")).strip()
            if not watched_task_id or watched_task_id in active_task_ids:
                continue
            if task_dir(watched_task_id).exists():
                diagnosis = diagnose_task(watched_task_id, idle_after_seconds=idle_after_seconds)
                if diagnosis.get("stuck"):
                    continue
            if not payload.get("active") and payload.get("resolution"):
                continue
            payload["active"] = False
            payload["resolved_at"] = now
            payload["last_seen_at"] = now
            watch_task_id = str(((payload.get("brain_dispatch", {}) or {}).get("task_id", ""))).strip() or _task_incident_task_id(watched_task_id)
            payload["resolution"] = _record_doctor_resolution(
                scope="task_incident",
                subject_id=watched_task_id,
                watch_task_id=watch_task_id,
                report=payload,
                resolution_reason="task_no_longer_requires_doctor_intervention",
            )
            _write_json(path, payload)
            resolved.append(payload)

    for candidate in active_candidates:
        report = _build_task_incident_report(candidate)
        watched_task_id = str(report.get("watched_task_id", "")).strip()
        slug = _slugify_runtime_identifier(watched_task_id)
        report_path = DOCTOR_TASK_INCIDENTS_ROOT / f"{slug}.json"
        existing = _read_json(report_path, {})
        history = list(existing.get("history", []) or []) if isinstance(existing, dict) else []
        last_signature = str((existing or {}).get("last_dispatched_signature", "")).strip() if isinstance(existing, dict) else ""
        report["report_path"] = str(report_path)
        should_dispatch = report["signature"] != last_signature or not bool((existing or {}).get("active"))
        if should_dispatch:
            dispatch = _upsert_task_incident_task(report)
            report["brain_dispatch"] = dispatch
            report["last_dispatched_at"] = now
            report["last_dispatched_signature"] = report["signature"]
            history.append(
                {
                    "at": now,
                    "signature": report["signature"],
                    "reason": str(((report.get("diagnosis", {}) or {}).get("reason", ""))).strip(),
                    "task_id": str(dispatch.get("task_id", "")).strip(),
                    "task_action": str(dispatch.get("task_action", "")).strip(),
                }
            )
            record_error(watched_task_id, _task_incident_error_text(report))
            dispatched.append(report)
        else:
            report["brain_dispatch"] = dict((existing or {}).get("brain_dispatch", {}) or {})
            report["last_dispatched_at"] = str((existing or {}).get("last_dispatched_at", "")).strip()
            report["last_dispatched_signature"] = last_signature
        report["history"] = history[-12:]
        _write_json(report_path, report)

    return {
        "incident_total": len(active_candidates),
        "dispatched_total": len(dispatched),
        "resolved_total": len(resolved),
        "items": dispatched,
        "resolved": resolved[:20],
    }


def _reconcile_process_incidents(control_plane: Dict[str, object]) -> Dict[str, object]:
    incident_items = list(((control_plane.get("runtime_jobs_registry", {}) or {}).get("incidents", []) or []))
    now = _utc_now_iso()
    reports: list[Dict[str, object]] = []
    resolved_reports: list[Dict[str, object]] = []
    active_labels = {str(item.get("label", "")).strip() for item in incident_items if str(item.get("label", "")).strip()}

    if DOCTOR_PROCESS_INCIDENTS_ROOT.exists():
        for path in sorted(DOCTOR_PROCESS_INCIDENTS_ROOT.glob("*.json")):
            payload = _read_json(path, {})
            if not isinstance(payload, dict):
                continue
            label = str(payload.get("label", "")).strip()
            if label and label not in active_labels and (payload.get("active") or not payload.get("resolution")):
                payload["active"] = False
                payload["resolved_at"] = now
                payload["last_seen_at"] = now
                watch_task_id = str(((payload.get("brain_dispatch", {}) or {}).get("task_id", ""))).strip() or _process_incident_task_id(label)
                payload["resolution"] = _record_doctor_resolution(
                    scope="process_incident",
                    subject_id=label,
                    watch_task_id=watch_task_id,
                    report=payload,
                    resolution_reason="process_no_longer_reported_as_incident",
                )
                _write_json(path, payload)
                resolved_reports.append(payload)

    for incident in incident_items:
        label = str(incident.get("label", "")).strip()
        if not label:
            continue
        slug = _slugify_runtime_identifier(label)
        report_path = DOCTOR_PROCESS_INCIDENTS_ROOT / f"{slug}.json"
        existing = _read_json(report_path, {})
        stderr_tail = _tail_file(str(incident.get("stderr_path", "")).strip())
        stdout_tail = _tail_file(str(incident.get("stdout_path", "")).strip())
        signal_text = "\n".join(
            part
            for part in [
                str(incident.get("launchctl_excerpt", "")).strip(),
                str(stderr_tail.get("tail", "")).strip(),
                str(stdout_tail.get("tail", "")).strip(),
            ]
            if part
        )
        matched_rule = resolve_rule_for_error(signal_text) if signal_text else None
        signature = _process_incident_signature(incident)
        report = {
            "generated_at": now,
            "last_seen_at": now,
            "active": True,
            "signature": signature,
            **incident,
            "stderr_tail": stderr_tail,
            "stdout_tail": stdout_tail,
            "matched_durable_rule": {
                "error_key": str((matched_rule or {}).get("error_key", "")).strip(),
                "preferred_action": str((matched_rule or {}).get("preferred_action", "")).strip(),
                "preferred_guard": str((matched_rule or {}).get("preferred_guard", "")).strip(),
                "prevention_hint": str((matched_rule or {}).get("prevention_hint", "")).strip(),
            }
            if matched_rule
            else {},
        }
        history = list(existing.get("history", []) or []) if isinstance(existing, dict) else []
        last_signature = str((existing or {}).get("last_dispatched_signature", "")).strip() if isinstance(existing, dict) else ""
        report["report_path"] = str(report_path)

        if signature != last_signature or not bool((existing or {}).get("active")):
            dispatch = _upsert_process_incident_task(report)
            report["brain_dispatch"] = dispatch
            report["last_dispatched_at"] = now
            report["last_dispatched_signature"] = signature
            history.append(
                {
                    "at": now,
                    "signature": signature,
                    "reason": str(incident.get("doctor_attention_reason", "")).strip(),
                    "last_exit_code": incident.get("last_exit_code"),
                    "task_id": str(dispatch.get("task_id", "")).strip(),
                    "task_action": str(dispatch.get("task_action", "")).strip(),
                }
            )
            record_error(str(dispatch.get("task_id", "")).strip() or label, _process_incident_error_text(report))
            reports.append(report)
        else:
            report["brain_dispatch"] = dict((existing or {}).get("brain_dispatch", {}) or {})
            report["last_dispatched_at"] = str((existing or {}).get("last_dispatched_at", "")).strip()
            report["last_dispatched_signature"] = last_signature
        report["history"] = history[-12:]
        _write_json(report_path, report)
    return {
        "incident_total": len(incident_items),
        "dispatched_total": len(reports),
        "resolved_total": len(resolved_reports),
        "items": reports,
        "resolved": resolved_reports[:20],
    }


def _progress_age_seconds(*, status: str, next_action: str, last_progress_at: str, last_update_at: str) -> float:
    """
    中文注解：
    - 功能：实现 `_progress_age_seconds` 对应的处理逻辑。
    - 角色：属于本模块中的内部辅助逻辑；私有函数通常服务同文件主流程，公共函数通常作为跨模块入口或能力接口。
    - 调用关系：建议结合本文件的模块说明、调用方以及同名相关辅助函数一起阅读。
    """
    progress_age = _seconds_since(last_progress_at)
    update_age = _seconds_since(last_update_at)
    if status == "waiting_external" and next_action.startswith("poll_run:"):
        return progress_age
    if status == "blocked":
        return progress_age
    return min(progress_age, update_age)


def _clear_blocked_metadata(state) -> None:
    state.metadata.pop("blocked_runtime_state", None)
    state.metadata.pop("project_crawler_gate", None)


def _normalized_blocked_runtime_state(state) -> Dict[str, object]:
    if state.status != "blocked":
        return {}
    inferred = classify_blocked_runtime_state(
        next_action=state.next_action,
        blockers=list(state.blockers or []),
        governance_attention=state.metadata.get("last_governance_attention", {}) or {},
    )
    if str(inferred.get("category", "")).strip():
        return inferred
    return dict(state.metadata.get("blocked_runtime_state", {}) or {})


def _resolved_missing_commands(blockers: list[str]) -> list[str]:
    resolved: list[str] = []
    for blocker in blockers:
        text = str(blocker or "").strip()
        if not text.startswith("preflight_missing_commands:"):
            continue
        _, _, payload = text.partition(":")
        for command in [item.strip() for item in payload.split(",") if item.strip()]:
            if shutil.which(command):
                resolved.append(command)
    return sorted(set(resolved))


def _load_or_build_fetch_route(task_id: str) -> Dict[str, object]:
    fetch_route_path = FETCH_ROUTES_ROOT / f"{task_id}.json"
    if fetch_route_path.exists():
        try:
            return json.loads(fetch_route_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            pass
    contract = load_contract(task_id)
    control_center = contract.metadata.get("control_center", {}) or {}
    return build_fetch_route(
        task_id,
        control_center.get("intent", {}) or {},
        control_center.get("selected_plan", {}) or {},
        control_center.get("domain_profile", {}) or {},
        {},
    )


def _project_crawler_gate_still_applies(task_id: str, state) -> Dict[str, object] | None:
    contract = load_contract(task_id)
    control_center = contract.metadata.get("control_center", {}) or {}
    snapshot = build_task_status_snapshot(task_id)
    governance = snapshot.get("governance", {}) or {}
    mission = {
        "intent": control_center.get("intent", {}) or {},
        "fetch_route": _load_or_build_fetch_route(task_id),
    }
    return build_project_crawler_gate(
        mission,
        {"governance": governance},
        summarize_governance_attention(governance),
        str(state.current_stage or "").strip(),
    )


def _restart_after_block_repair(task_id: str, state, *, repair_reason: str, event_name: str, extra: Dict[str, object] | None = None) -> Dict[str, object]:
    state.status = "planning"
    state.blockers = []
    state.metadata.pop("waiting_external", None)
    state.metadata.pop("active_execution", None)
    state.metadata.pop("last_dispatched_marker", None)
    state.metadata.pop("last_dispatch_at", None)
    state.metadata["last_blocked_repair"] = {
        "reason": repair_reason,
        "repaired_at": _utc_now_iso(),
        "details": extra or {},
    }
    _clear_blocked_metadata(state)
    state.next_action = f"start_stage:{state.current_stage}" if state.current_stage else "initialize"
    state.last_update_at = _utc_now_iso()
    save_state(state)
    log_event(task_id, event_name, repair_reason=repair_reason, details=extra or {})
    return {
        "task_id": task_id,
        "repaired": True,
        "reason": repair_reason,
        "details": extra or {},
    }


def _semantic_tokens(text: str) -> set[str]:
    return {
        token.lower()
        for token in re.findall(r"[A-Za-z][A-Za-z0-9_-]{2,}|[\u4e00-\u9fff]{2,}", str(text or ""))
        if token.strip()
    }


def _drift_and_consistency_status(task_id: str) -> Dict[str, object]:
    """
    中文注解：
    - 功能：检查任务是否出现目标漂移或前后不一致。
    - 设计意图：
      1. 不只在“彻底卡死”时才介入；
      2. 一旦任务开始偏题、自相矛盾，就让医生提前纠偏。
    """
    contract = load_contract(task_id)
    state = load_state(task_id)
    task_summary = load_task_summary(task_id)
    goal_tokens = _semantic_tokens(contract.user_goal)
    signal_parts = [state.next_action, " ".join(state.blockers or [])]
    for stage_name in state.stage_order:
        stage = state.stages.get(stage_name)
        if not stage:
            continue
        signal_parts.append(stage.summary or "")
        signal_parts.append(stage.blocker or "")
    signal_parts.extend([str(item) for item in task_summary.get("notes", []) or [] if str(item).strip()])
    signal_text = " ".join(part for part in signal_parts if str(part).strip())
    signal_tokens = _semantic_tokens(signal_text)
    overlap = goal_tokens & signal_tokens

    inconsistency_reasons = []
    incomplete = [name for name in state.stage_order if state.stages.get(name) and state.stages[name].status != "completed"]
    milestone_stats = state.metadata.get("milestone_stats", {}) or {}
    if state.status == "completed" and incomplete:
        inconsistency_reasons.append(f"completed_with_incomplete_stages:{','.join(incomplete)}")
    if state.status == "completed" and milestone_stats and milestone_stats.get("all_required_completed") is False:
        inconsistency_reasons.append("completed_with_incomplete_required_milestones")
    if state.current_stage and state.current_stage not in state.stage_order and state.status not in {"completed", "failed"}:
        inconsistency_reasons.append("current_stage_not_in_stage_order")
    if (
        state.current_stage == "verify"
        and state.stages.get("verify")
        and state.stages["verify"].status == "completed"
        and str(state.stages["verify"].verification_status).strip() not in {"passed", "verified", "ok"}
    ):
        inconsistency_reasons.append("verify_completed_without_passed_verification_status")

    drift_detected = False
    drift_reason = ""
    if (
        len(goal_tokens) >= 2
        and len(signal_tokens) >= 4
        and not overlap
        and state.status in {"planning", "running", "recovering"}
        and state.current_stage in {"plan", "execute", "verify"}
    ):
        drift_detected = True
        drift_reason = "goal_tokens_have_no_overlap_with_current_execution_signals"

    return {
        "goal_tokens": sorted(goal_tokens),
        "signal_tokens": sorted(signal_tokens),
        "overlap": sorted(overlap),
        "drift_detected": drift_detected,
        "drift_reason": drift_reason,
        "inconsistency_detected": bool(inconsistency_reasons),
        "inconsistency_reasons": inconsistency_reasons,
    }


def _goal_guardian_status(task_id: str, diagnosis: Dict[str, object]) -> Dict[str, object]:
    """
    中文注解：
    - 功能：汇总任务的目标守护状态。
    - 设计意图：让医生能明确知道“任务是否还在目标约束下继续推进，以及复盘是否已经落盘”。
    """
    contract = load_contract(task_id)
    control_center = (contract.metadata.get("control_center", {}) or {})
    guardian = control_center.get("goal_guardian", {}) or {}
    task_summary = load_task_summary(task_id)
    state = load_state(task_id)
    postmortem = state.metadata.get("postmortem", {}) or {}
    postmortem_written = bool(
        postmortem.get("written")
        or task_summary.get("postmortem_written")
        or str(task_summary.get("postmortem_path", "")).strip()
    )
    goal_conformance = diagnosis.get("goal_conformance", {}) or {}
    return {
        "enabled": bool(guardian.get("enabled")),
        "guardian_process": str(guardian.get("guardian_process", "system_doctor")).strip() or "system_doctor",
        "strict_continuation_required": bool(guardian.get("strict_continuation_required")),
        "require_postmortem_before_completion": bool(guardian.get("require_postmortem_before_completion")),
        "postmortem_written": postmortem_written,
        "postmortem_path": str(postmortem.get("path") or task_summary.get("postmortem_path", "") or "").strip(),
        "latest_user_goal": str(goal_conformance.get("latest_user_goal", "")).strip(),
        "bound_goal": str(goal_conformance.get("bound_goal", "")).strip(),
        "matches_latest_goal": goal_conformance.get("matches_latest_goal"),
    }


def _stuck_escalation_plan(task_id: str, diagnosis: Dict[str, object]) -> Dict[str, object]:
    """
    中文注解：
    - 功能：在任务卡壳时，为医生生成“继续研究还是请求人工”的升级方案。
    """
    contract = load_contract(task_id)
    state = load_state(task_id)
    control_center = (contract.metadata.get("control_center", {}) or {})
    intent = control_center.get("intent", {}) or {}
    approval = contract.metadata.get("approval", {}) or {}
    arbitration = control_center.get("arbitration", {}) or {}
    scout = control_center.get("resource_scout", {}) or {}
    blocker_list = list(state.blockers or [])
    problem = solve_problem(task_id, blocker_list, arbitration, approval)
    research_package = prepare_research_package(task_id, scout, intent)
    recommended_action = str(problem.get("recommended_action", "")).strip()
    learned_rule = resolve_doctor_strategy(str(diagnosis.get("reason", "")).strip())
    ask_user_actions = {
        "wait_for_or_request_approval",
        "await_human_verification_checkpoint",
        "request_authorized_configuration",
        "request_authorized_session",
    }
    deep_research_actions = {
        "research_alternative_solution",
        "needs_network_request_level_debugging",
        "investigate_frontend_binding_and_network_request_chain",
        "repair_and_retry",
        "browser_render",
        "official_source_or_authorized_session",
        "slow_down_and_switch_to_structured_source",
    }
    if learned_rule:
        mode = str(learned_rule.get("preferred_escalation_mode", "")).strip() or "continue"
    elif recommended_action in ask_user_actions:
        mode = "ask_user"
    elif (
        recommended_action in deep_research_actions
        or bool(research_package.get("enabled"))
        or bool(intent.get("requires_external_information"))
    ):
        mode = "deep_research"
    else:
        mode = "continue"
    return {
        "mode": mode,
        "recommended_action": recommended_action or "continue_current_plan",
        "learned_rule": learned_rule or {},
        "problem_analysis": problem,
        "research_package": research_package,
    }


def _record_doctor_rule(task_id: str, diagnosis: Dict[str, object], repair_reason: str, escalation_mode: str) -> Dict[str, object] | None:
    """
    中文注解：
    - 功能：把本次医生诊断与成功修复沉淀成 durable doctor rule。
    """
    doctor_reason = str(diagnosis.get("reason", "")).strip()
    if not doctor_reason or not repair_reason:
        return None
    consistency = diagnosis.get("consistency", {}) or {}
    prevention_hint = "keep goal anchor, verify every stage, and reopen the right phase instead of silently terminating"
    if doctor_reason == "goal_tokens_have_no_overlap_with_current_execution_signals":
        prevention_hint = "when execution signals no longer overlap the goal anchor, force a re-plan before continuing"
    elif doctor_reason == "completed_without_postmortem":
        prevention_hint = "do not allow completed status before learn/reflect artifacts and postmortem are written"
    elif consistency.get("inconsistency_detected"):
        prevention_hint = "when task state becomes self-contradictory, reopen verification or learning instead of trusting terminal status"
    return promote_doctor_strategy(
        doctor_reason=doctor_reason,
        preferred_repair=repair_reason,
        preferred_escalation_mode=escalation_mode,
        prevention_hint=prevention_hint,
        task_id=task_id,
        evidence={
            "idle_seconds": diagnosis.get("idle_seconds", 0),
            "current_stage": diagnosis.get("current_stage", ""),
            "status": diagnosis.get("status", ""),
        },
    )


def _goal_alignment_status(task_id: str, evidence: Dict[str, object], consistency: Dict[str, object]) -> Dict[str, object]:
    goal_conformance = evidence.get("goal_conformance", {}) or {}
    latest_user_goal = str(goal_conformance.get("latest_user_goal", "")).strip()
    bound_goal = str(goal_conformance.get("bound_goal", "")).strip()
    matched = goal_conformance.get("matches_latest_goal")
    overlap_count = len(consistency.get("overlap", []) or [])
    goal_count = len(consistency.get("goal_tokens", []) or [])
    signal_count = len(consistency.get("signal_tokens", []) or [])
    ratio = round((overlap_count / max(goal_count, 1)), 3) if goal_count else 1.0
    if goal_conformance.get("ok") is False:
        status = "mismatch"
    elif consistency.get("drift_detected"):
        status = "drifting"
    elif overlap_count:
        status = "aligned"
    elif signal_count >= 4 and goal_count >= 2:
        status = "weak_alignment"
    else:
        status = "insufficient_signal"
    return {
        "status": status,
        "matches_latest_goal": matched,
        "bound_goal": bound_goal,
        "latest_user_goal": latest_user_goal,
        "semantic_overlap_tokens": consistency.get("overlap", []),
        "semantic_overlap_ratio": ratio,
        "evidence_reason": str(goal_conformance.get("reason", "")).strip() or "goal_conformance_ok",
    }


def _stage_consistency_status(state, consistency: Dict[str, object]) -> Dict[str, object]:
    current_stage = str(state.current_stage or "").strip()
    stage_order = list(state.stage_order or [])
    pending = [name for name in stage_order if state.stages.get(name) and state.stages[name].status != "completed"]
    consistency_reasons = list(consistency.get("inconsistency_reasons", []) or [])
    if consistency_reasons:
        status = "inconsistent"
    elif current_stage and current_stage not in stage_order and state.status not in {"completed", "failed"}:
        status = "unknown_stage"
    elif pending:
        status = "active"
    else:
        status = "complete_or_ready_for_completion"
    return {
        "status": status,
        "current_stage": current_stage,
        "stage_order": stage_order,
        "pending_stages": pending,
        "inconsistency_reasons": consistency_reasons,
    }


def _completion_gate_status(task_id: str, state, diagnosis: Dict[str, object]) -> Dict[str, object]:
    guardian = diagnosis.get("goal_guardian", {}) or {}
    milestone_stats = state.metadata.get("milestone_stats", {}) or {}
    all_required_completed = milestone_stats.get("all_required_completed")
    if not guardian.get("enabled"):
        gate_status = "not_applicable"
    elif state.status != "completed":
        gate_status = "open"
    elif guardian.get("require_postmortem_before_completion") and not guardian.get("postmortem_written"):
        gate_status = "blocked_by_missing_postmortem"
    elif all_required_completed is False:
        gate_status = "blocked_by_required_milestones"
    else:
        gate_status = "satisfied"
    return {
        "status": gate_status,
        "goal_guardian_enabled": bool(guardian.get("enabled")),
        "postmortem_required": bool(guardian.get("require_postmortem_before_completion")),
        "postmortem_written": bool(guardian.get("postmortem_written")),
        "all_required_milestones_completed": all_required_completed,
        "task_status": state.status,
    }


def _build_doctor_heartbeat(task_id: str, *, idle_after_seconds: int) -> Dict[str, object]:
    state = load_state(task_id)
    evidence = build_progress_evidence(task_id, stale_after_seconds=max(60, idle_after_seconds))
    diagnosis = {
        "goal_conformance": evidence.get("goal_conformance", {}),
    }
    diagnosis["goal_guardian"] = _goal_guardian_status(task_id, diagnosis)
    consistency = _drift_and_consistency_status(task_id)
    diagnosis["consistency"] = consistency
    goal_alignment = _goal_alignment_status(task_id, evidence, consistency)
    stage_consistency = _stage_consistency_status(state, consistency)
    drift_score = round(1.0 - float(goal_alignment.get("semantic_overlap_ratio", 0.0) or 0.0), 3)
    heartbeat = {
        "task_id": task_id,
        "written_at": _utc_now_iso(),
        "task_status": state.status,
        "current_stage": state.current_stage,
        "goal_alignment": goal_alignment,
        "stage_consistency": stage_consistency,
        "drift_score": drift_score,
        "drift_detected": bool(consistency.get("drift_detected")),
        "completion_gate_status": _completion_gate_status(task_id, state, diagnosis),
        "progress_evidence": {
            "progress_state": evidence.get("progress_state", ""),
            "needs_intervention": bool(evidence.get("needs_intervention")),
            "reason": evidence.get("reason", ""),
            "idle_seconds": float(evidence.get("idle_seconds", 0) or 0),
        },
    }
    _write_json(DOCTOR_HEARTBEATS_ROOT / f"{task_id}.json", heartbeat)
    state.metadata["doctor_heartbeat"] = {
        "written_at": heartbeat["written_at"],
        "goal_alignment_status": str((goal_alignment or {}).get("status", "")).strip(),
        "stage_consistency_status": str((stage_consistency or {}).get("status", "")).strip(),
        "drift_score": float(drift_score),
        "drift_detected": bool(consistency.get("drift_detected")),
        "completion_gate_status": str(((heartbeat.get("completion_gate_status", {}) or {}).get("status", ""))).strip(),
        "progress_state": str(((heartbeat.get("progress_evidence", {}) or {}).get("progress_state", ""))).strip(),
        "needs_intervention": bool((heartbeat.get("progress_evidence", {}) or {}).get("needs_intervention")),
        "heartbeat_path": str(DOCTOR_HEARTBEATS_ROOT / f"{task_id}.json"),
    }
    state.last_update_at = heartbeat["written_at"]
    save_state(state)
    return heartbeat


def _write_doctor_heartbeats(control_plane: Dict[str, object], *, idle_after_seconds: int) -> Dict[str, object]:
    eligible_statuses = {"running", "planning", "recovering", "blocked", "verifying"}
    registry_items = list(((control_plane.get("task_registry", {}) or {}).get("items", []) or []))
    heartbeats = []
    errors = []
    for item in registry_items:
        task_id = str(item.get("canonical_task_id") or item.get("task_id") or "").strip()
        status = str(item.get("status", "")).strip()
        if not task_id or status not in eligible_statuses:
            continue
        try:
            heartbeats.append(_build_doctor_heartbeat(task_id, idle_after_seconds=idle_after_seconds))
        except Exception as exc:
            errors.append({"task_id": task_id, "error": str(exc)})
    summary = {
        "written_at": _utc_now_iso(),
        "eligible_statuses": sorted(eligible_statuses),
        "count": len(heartbeats),
        "error_count": len(errors),
        "items": heartbeats,
        "errors": errors[:20],
    }
    _write_json(DOCTOR_HEARTBEATS_ROOT / "last_cycle.json", summary)
    return summary


def _heartbeat_stability_overview(heartbeat_summary: Dict[str, object]) -> Dict[str, object]:
    items = list(heartbeat_summary.get("items", []) or [])
    goal_alignment_counts: Dict[str, int] = {}
    stage_consistency_counts: Dict[str, int] = {}
    completion_gate_counts: Dict[str, int] = {}
    intervention_total = 0
    drift_detected_total = 0
    drift_scores = []
    for item in items:
        goal_status = str(((item.get("goal_alignment", {}) or {}).get("status", ""))).strip() or "unknown"
        stage_status = str(((item.get("stage_consistency", {}) or {}).get("status", ""))).strip() or "unknown"
        gate_status = str(((item.get("completion_gate_status", {}) or {}).get("status", ""))).strip() or "unknown"
        goal_alignment_counts[goal_status] = goal_alignment_counts.get(goal_status, 0) + 1
        stage_consistency_counts[stage_status] = stage_consistency_counts.get(stage_status, 0) + 1
        completion_gate_counts[gate_status] = completion_gate_counts.get(gate_status, 0) + 1
        if bool(((item.get("progress_evidence", {}) or {}).get("needs_intervention"))):
            intervention_total += 1
        if bool(item.get("drift_detected")):
            drift_detected_total += 1
        drift_scores.append(float(item.get("drift_score", 0.0) or 0.0))
    return {
        "heartbeat_total": len(items),
        "goal_alignment_counts": goal_alignment_counts,
        "stage_consistency_counts": stage_consistency_counts,
        "completion_gate_counts": completion_gate_counts,
        "needs_intervention_total": intervention_total,
        "drift_detected_total": drift_detected_total,
        "average_drift_score": round(sum(drift_scores) / max(1, len(drift_scores)), 3),
    }


def _doctor_cycle_strategy(control_plane: Dict[str, object]) -> Dict[str, object]:
    summary = ((control_plane.get("system_snapshot", {}) or {}).get("summary", {}) or {}) if isinstance(control_plane, dict) else {}
    blocked_categories = summary.get("blocked_categories", {}) or {}
    top_blocked_category = str(summary.get("top_blocked_category", "")).strip()
    project_result_feedback_status = str(summary.get("project_result_feedback_status", "")).strip().lower()
    project_result_feedback_attention_total = int(summary.get("project_result_feedback_attention_total", 0) or 0)
    project_result_feedback_trend = str(summary.get("project_result_feedback_trend", "")).strip().lower()
    project_repair_value_status = str(summary.get("project_repair_value_status", "")).strip().lower()
    project_repair_value_trend = str(summary.get("project_repair_value_trend", "")).strip().lower()
    strategy = {
        "top_blocked_category": top_blocked_category,
        "blocked_categories": blocked_categories,
        "priority_focus": "general",
        "repair_mode": "balanced",
        "max_repairs_per_cycle": 12,
        "allowed_buckets": ["critical", "high", "medium", "low"],
    }
    if top_blocked_category in {"project_crawler_remediation", "approval_or_contract", "authorized_session", "human_checkpoint"}:
        strategy.update(
            {
                "priority_focus": "governance_blockers",
                "repair_mode": "governance_first",
                "max_repairs_per_cycle": 10,
                "allowed_buckets": ["critical", "high"],
            }
        )
    elif top_blocked_category in {"targeted_fix", "runtime_failure", "runtime_or_contract_fix"}:
        strategy.update(
            {
                "priority_focus": "repair_blockers",
                "repair_mode": "repair_first",
                "max_repairs_per_cycle": 16,
                "allowed_buckets": ["critical", "high", "medium"],
            }
        )
    elif top_blocked_category in {"session_binding", "relay_attach"}:
        strategy.update(
            {
                "priority_focus": "linkage_blockers",
                "repair_mode": "linkage_first",
                "max_repairs_per_cycle": 20,
                "allowed_buckets": ["critical", "high", "medium", "low"],
            }
        )
    if project_result_feedback_status in {"thin", "partial"} and strategy["priority_focus"] == "general":
        strategy.update(
            {
                "priority_focus": "feedback_rebuild",
                "repair_mode": "feedback_first",
                "max_repairs_per_cycle": 14,
                "allowed_buckets": ["critical", "high", "medium"],
            }
        )
    if project_result_feedback_attention_total > 0:
        strategy["repair_mode"] = "feedback_attention_first"
        strategy["max_repairs_per_cycle"] = min(int(strategy.get("max_repairs_per_cycle", 12) or 12), 10)
    elif project_result_feedback_trend == "degrading" and strategy["priority_focus"] == "general":
        strategy.update(
            {
                "priority_focus": "feedback_watch",
                "repair_mode": "feedback_trend_watch",
                "max_repairs_per_cycle": 12,
                "allowed_buckets": ["critical", "high", "medium"],
            }
        )
    if project_repair_value_status == "weak":
        strategy.update(
            {
                "priority_focus": "repair_value_rebuild",
                "repair_mode": "repair_value_first",
                "max_repairs_per_cycle": 10,
                "allowed_buckets": ["critical", "high", "medium"],
            }
        )
    elif project_repair_value_trend == "degrading" and strategy["priority_focus"] == "general":
        strategy.update(
            {
                "priority_focus": "repair_value_watch",
                "repair_mode": "repair_value_watch",
                "max_repairs_per_cycle": 12,
                "allowed_buckets": ["critical", "high", "medium"],
            }
        )
    return strategy


def _should_process_doctor_item(item: Dict[str, object], strategy: Dict[str, object], processed_total: int) -> tuple[bool, str]:
    if processed_total >= int(strategy.get("max_repairs_per_cycle", 0) or 0):
        return False, "cycle_capacity_reached"
    bucket = str(item.get("priority_bucket", "")).strip() or "low"
    allowed = {str(v).strip() for v in (strategy.get("allowed_buckets", []) or []) if str(v).strip()}
    if allowed and bucket not in allowed:
        return False, f"bucket_filtered:{bucket}"
    return True, "selected"


def diagnose_task(task_id: str, *, idle_after_seconds: int = 180) -> Dict[str, object]:
    """
    中文注解：
    - 功能：对单个任务做“是不是卡住了”的诊断。
    - 判断依据：
      - status / next_action
      - active_execution 是否存在
      - last_progress_at 到现在的时间
    - 输出：一个 diagnosis dict，供 repair 和用户回执复用。
    """
    state = load_state(task_id)
    age = _progress_age_seconds(
        status=state.status,
        next_action=state.next_action,
        last_progress_at=state.last_progress_at,
        last_update_at=state.last_update_at,
    )
    active_execution = state.metadata.get("active_execution", {}) or {}
    has_active_execution = bool(active_execution.get("run_id"))
    milestone_stats = state.metadata.get("milestone_stats", {}) or {}
    blocked_runtime_state = _normalized_blocked_runtime_state(state)
    diagnosis = {
        "task_id": task_id,
        "status": state.status,
        "current_stage": state.current_stage,
        "next_action": state.next_action,
        "blocked_runtime_state": blocked_runtime_state,
        "idle_seconds": age,
        "has_active_execution": has_active_execution,
        "milestone_stats": milestone_stats,
        "stuck": False,
        "reason": "healthy_or_recently_updated",
    }
    evidence = build_progress_evidence(task_id, stale_after_seconds=max(60, idle_after_seconds))
    diagnosis["goal_conformance"] = evidence.get("goal_conformance", {})
    diagnosis["goal_guardian"] = _goal_guardian_status(task_id, diagnosis)
    diagnosis["consistency"] = _drift_and_consistency_status(task_id)
    # terminal completed 不需要医生继续介入；failed 则需要医生接管而不是直接放弃。
    if state.status == "completed":
        guardian = diagnosis.get("goal_guardian", {}) or {}
        if guardian.get("enabled") and guardian.get("require_postmortem_before_completion") and not guardian.get("postmortem_written"):
            diagnosis["stuck"] = True
            diagnosis["reason"] = "completed_without_postmortem"
            diagnosis["stuck_escalation"] = _stuck_escalation_plan(task_id, diagnosis)
            return diagnosis
        diagnosis["reason"] = "terminal"
        return diagnosis
    if state.status == "failed":
        diagnosis["stuck"] = True
        diagnosis["reason"] = "terminal_failure_requires_takeover"
        return diagnosis
    if evidence.get("reason") == "latest_user_goal_mismatch_with_bound_task":
        diagnosis["stuck"] = True
        diagnosis["reason"] = "latest_user_goal_mismatch_with_bound_task"
        return diagnosis
    if evidence.get("progress_state") == "reanimated_completed_task":
        diagnosis["stuck"] = True
        diagnosis["reason"] = "reanimated_completed_task"
        diagnosis["stuck_escalation"] = _stuck_escalation_plan(task_id, diagnosis)
        return diagnosis
    if evidence.get("progress_state") == "satisfied_without_live_execution":
        diagnosis["stuck"] = True
        diagnosis["reason"] = "satisfied_without_live_execution"
        diagnosis["stuck_escalation"] = _stuck_escalation_plan(task_id, diagnosis)
        return diagnosis
    if evidence.get("progress_state") == "satisfied_waiting_residue":
        diagnosis["stuck"] = True
        diagnosis["reason"] = "satisfied_waiting_residue"
        diagnosis["stuck_escalation"] = _stuck_escalation_plan(task_id, diagnosis)
        return diagnosis
    if evidence.get("progress_state") == "satisfied_redundant_dispatch":
        diagnosis["stuck"] = True
        diagnosis["reason"] = "satisfied_redundant_dispatch"
        diagnosis["stuck_escalation"] = _stuck_escalation_plan(task_id, diagnosis)
        return diagnosis
    consistency = diagnosis.get("consistency", {}) or {}
    if consistency.get("inconsistency_detected"):
        diagnosis["stuck"] = True
        diagnosis["reason"] = str((consistency.get("inconsistency_reasons") or ["state_inconsistency_detected"])[0])
        diagnosis["stuck_escalation"] = _stuck_escalation_plan(task_id, diagnosis)
        return diagnosis
    if consistency.get("drift_detected"):
        diagnosis["stuck"] = True
        diagnosis["reason"] = str(consistency.get("drift_reason") or "goal_drift_detected")
        diagnosis["stuck_escalation"] = _stuck_escalation_plan(task_id, diagnosis)
        return diagnosis
    if age < idle_after_seconds:
        return diagnosis
    if not has_active_execution and state.status in {"planning", "running", "recovering"}:
        diagnosis["stuck"] = True
        diagnosis["reason"] = "idle_without_active_execution"
    elif state.status == "waiting_external" and not has_active_execution:
        diagnosis["stuck"] = True
        diagnosis["reason"] = "waiting_external_without_active_execution"
    elif state.status == "blocked":
        diagnosis["stuck"] = True
        blocked_category = str(blocked_runtime_state.get("category", "")).strip()
        diagnosis["reason"] = f"blocked:{blocked_category or state.next_action or 'unknown'}"
    elif state.next_action.startswith("poll_run:") and age >= idle_after_seconds:
        diagnosis["stuck"] = True
        diagnosis["reason"] = "stale_waiting_external"
    if diagnosis.get("stuck"):
        diagnosis["stuck_escalation"] = _stuck_escalation_plan(task_id, diagnosis)
    return diagnosis


def repair_task_if_possible(task_id: str, diagnosis: Dict[str, object]) -> Dict[str, object]:
    """
    中文注解：
    - 功能：对已确认 stuck 的任务尝试做最小代价修复。
    - 典型修复动作：
      - 清理失效的 active_execution / waiting_external
      - 把状态重新拉回 planning
      - 在 failed 时切成 doctor takeover
    - 调用关系：run_system_doctor 先诊断，再调用这里决定是否真的“动刀”。
    """
    if not diagnosis.get("stuck"):
        return {"task_id": task_id, "repaired": False, "reason": "not_stuck"}
    state = load_state(task_id)
    # 这些修复策略的共同思路是：
    # 先清掉失真的运行态，再把任务送回一个 runtime 能重新推进的安全状态。
    if diagnosis.get("reason") == "idle_without_active_execution":
        state.status = "planning"
        state.blockers = []
        state.metadata.pop("active_execution", None)
        state.metadata.pop("last_dispatched_marker", None)
        state.metadata.pop("last_dispatch_at", None)
        state.next_action = f"start_stage:{state.current_stage}" if state.current_stage else "initialize"
        state.last_update_at = _utc_now_iso()
        save_state(state)
        log_event(task_id, "system_doctor_repaired_idle_execution_gap", diagnosis=diagnosis)
        return {"task_id": task_id, "repaired": True, "reason": "restarted_stage_execution"}
    if diagnosis.get("reason") == "waiting_external_without_active_execution":
        state.status = "planning"
        state.blockers = []
        state.metadata.pop("waiting_external", None)
        state.metadata.pop("active_execution", None)
        state.metadata.pop("last_dispatched_marker", None)
        state.metadata.pop("last_dispatch_at", None)
        state.next_action = f"start_stage:{state.current_stage}" if state.current_stage else "initialize"
        state.last_update_at = _utc_now_iso()
        save_state(state)
        log_event(task_id, "system_doctor_repaired_waiting_external_without_execution", diagnosis=diagnosis)
        return {"task_id": task_id, "repaired": True, "reason": "restarted_after_waiting_external_without_execution"}
    if diagnosis.get("reason") == "stale_waiting_external":
        state.status = "planning"
        state.blockers = []
        state.metadata.pop("waiting_external", None)
        state.metadata.pop("active_execution", None)
        state.metadata.pop("last_dispatched_marker", None)
        state.metadata.pop("last_dispatch_at", None)
        state.next_action = f"start_stage:{state.current_stage}" if state.current_stage else "initialize"
        state.last_update_at = _utc_now_iso()
        save_state(state)
        log_event(task_id, "system_doctor_repaired_stale_waiting_external", diagnosis=diagnosis)
        return {"task_id": task_id, "repaired": True, "reason": "restarted_after_stale_waiting_external"}
    if diagnosis.get("reason") in {"reanimated_completed_task", "satisfied_without_live_execution", "satisfied_waiting_residue", "satisfied_redundant_dispatch"}:
        state.status = "completed"
        state.blockers = []
        state.metadata.pop("waiting_external", None)
        state.metadata.pop("active_execution", None)
        state.metadata.pop("last_dispatched_marker", None)
        state.metadata.pop("last_dispatch_at", None)
        state.metadata["doctor_reanimated_completed_repair"] = {
            "repaired_at": _utc_now_iso(),
            "reason": (
                "completed_summary_and_workspace_guards_conflict_with_live_runtime_state"
                if diagnosis.get("reason") == "reanimated_completed_task"
                else (
                    "business_outcome_satisfied_and_confirmed_without_live_runtime_execution"
                    if diagnosis.get("reason") == "satisfied_without_live_execution"
                    else (
                        "waiting_external_residue_with_satisfied_business_outcome"
                        if diagnosis.get("reason") == "satisfied_waiting_residue"
                        else "business_outcome_already_satisfied_but_plan_stage_re_dispatched"
                    )
                )
            ),
        }
        state.next_action = ""
        state.last_update_at = _utc_now_iso()
        save_state(state)
        log_event(task_id, "system_doctor_closed_reanimated_completed_task", diagnosis=diagnosis)
        return {
            "task_id": task_id,
            "repaired": True,
            "reason": (
                "closed_reanimated_completed_task"
                if diagnosis.get("reason") == "reanimated_completed_task"
                else (
                    "closed_satisfied_without_live_execution_task"
                    if diagnosis.get("reason") == "satisfied_without_live_execution"
                    else (
                        "closed_satisfied_waiting_residue_task"
                        if diagnosis.get("reason") == "satisfied_waiting_residue"
                        else "closed_satisfied_redundant_dispatch_task"
                    )
                )
            ),
        }
    if diagnosis.get("reason") == "terminal_failure_requires_takeover":
        state.status = "recovering"
        state.blockers = list(dict.fromkeys([*state.blockers, "terminal_failure_detected"]))
        state.metadata.pop("active_execution", None)
        state.metadata.pop("waiting_external", None)
        state.metadata["doctor_takeover"] = {
            "active": True,
            "reason": "terminal_failure_requires_takeover",
            "taken_over_at": _utc_now_iso(),
        }
        state.next_action = "doctor_investigating_failure"
        state.last_update_at = _utc_now_iso()
        save_state(state)
        log_event(task_id, "system_doctor_took_over_failed_task", diagnosis=diagnosis)
        return {"task_id": task_id, "repaired": True, "reason": "doctor_failure_takeover_started"}
    if diagnosis.get("reason") == "completed_without_postmortem":
        learn_stage = state.stages.get("learn")
        if learn_stage:
            learn_stage.status = "pending"
            learn_stage.summary = ""
            learn_stage.verification_status = "not-run"
            learn_stage.blocker = ""
            learn_stage.completed_at = ""
            learn_stage.updated_at = _utc_now_iso()
        state.status = "planning"
        state.current_stage = "learn" if learn_stage else state.current_stage
        state.blockers = ["goal guardian requires written postmortem before completion"]
        state.next_action = f"start_stage:{state.current_stage}" if state.current_stage else "initialize"
        state.metadata.pop("completion_notice_sent", None)
        state.last_update_at = _utc_now_iso()
        save_state(state)
        log_event(task_id, "system_doctor_reopened_task_for_postmortem", diagnosis=diagnosis)
        promoted_rule = _record_doctor_rule(task_id, diagnosis, "reopened_for_postmortem", "continue")
        return {"task_id": task_id, "repaired": True, "reason": "reopened_for_postmortem", "promoted_rule": promoted_rule}
    if diagnosis.get("reason") == "goal_tokens_have_no_overlap_with_current_execution_signals":
        state.status = "planning"
        state.current_stage = "plan"
        state.blockers = ["doctor detected goal drift and forced a re-plan against the original goal anchor"]
        state.metadata["last_drift_repair"] = diagnosis.get("consistency", {})
        state.next_action = "start_stage:plan"
        state.last_update_at = _utc_now_iso()
        save_state(state)
        log_event(task_id, "system_doctor_repaired_goal_drift", diagnosis=diagnosis)
        promoted_rule = _record_doctor_rule(task_id, diagnosis, "replanned_after_goal_drift", "continue")
        return {"task_id": task_id, "repaired": True, "reason": "replanned_after_goal_drift", "promoted_rule": promoted_rule}
    if str(diagnosis.get("reason", "")).startswith("completed_with_") or str(diagnosis.get("reason", "")).startswith("verify_completed_") or diagnosis.get("reason") == "current_stage_not_in_stage_order":
        target_stage = "verify" if state.stages.get("verify") else state.first_pending_stage() or state.current_stage or "plan"
        state.status = "planning"
        state.current_stage = target_stage
        state.blockers = ["doctor detected state inconsistency and reopened the task for reconciliation"]
        state.metadata["last_consistency_repair"] = diagnosis.get("consistency", {})
        state.next_action = f"start_stage:{target_stage}"
        state.last_update_at = _utc_now_iso()
        save_state(state)
        log_event(task_id, "system_doctor_repaired_state_inconsistency", diagnosis=diagnosis)
        promoted_rule = _record_doctor_rule(task_id, diagnosis, "reopened_after_state_inconsistency", "continue")
        return {"task_id": task_id, "repaired": True, "reason": "reopened_after_state_inconsistency", "promoted_rule": promoted_rule}
    if diagnosis.get("reason") == "latest_user_goal_mismatch_with_bound_task":
        conformance = diagnosis.get("goal_conformance", {}) or {}
        provider = str(conformance.get("provider", "")).strip()
        conversation_id = str(conformance.get("conversation_id", "")).strip()
        conversation_type = str(conformance.get("conversation_type", "")).strip() or "direct"
        latest_goal = str(conformance.get("latest_user_goal", "")).strip()
        session_key = str(conformance.get("session_key", "")).strip()
        message_id = str(conformance.get("latest_user_message_id", "")).strip()
        if not provider or not conversation_id or not latest_goal:
            return {"task_id": task_id, "repaired": False, "reason": "goal_mismatch_missing_rebind_context"}
        route = route_instruction(
            provider=provider,
            conversation_id=conversation_id,
            conversation_type=conversation_type,
            text=latest_goal,
            source="system_doctor:goal_realign",
            sender_id="user",
            sender_name="doctor-goal-realign",
            message_id=message_id,
            session_key=session_key,
        )
        route = reroot_route_if_needed(
            route=route,
            provider=provider,
            conversation_id=conversation_id,
            conversation_type=conversation_type,
            goal=str(route.get("goal") or latest_goal),
            session_key=session_key,
        )
        persist_route(provider, conversation_id, route)
        new_task_id = str(route.get("task_id", "")).strip()
        if not new_task_id or new_task_id == task_id:
            return {
                "task_id": task_id,
                "repaired": False,
                "reason": "goal_mismatch_route_did_not_realign",
                "route_mode": route.get("mode", ""),
            }
        state.status = "blocked"
        state.blockers = [f"latest user goal was reassigned to {new_task_id}"]
        state.metadata.pop("active_execution", None)
        state.metadata.pop("waiting_external", None)
        state.metadata["superseded_by_task_id"] = new_task_id
        state.next_action = f"superseded_by:{new_task_id}"
        state.last_update_at = _utc_now_iso()
        save_state(state)
        log_event(
            task_id,
            "system_doctor_repaired_goal_execution_mismatch",
            diagnosis=diagnosis,
            new_task_id=new_task_id,
            route_mode=route.get("mode", ""),
        )
        return {
            "task_id": task_id,
            "repaired": True,
            "reason": "goal_mismatch_rebound_to_latest_goal",
            "new_task_id": new_task_id,
            "route_mode": route.get("mode", ""),
        }
    if str(diagnosis.get("reason", "")).startswith("blocked:"):
        blocked_runtime_state = diagnosis.get("blocked_runtime_state", {}) or {}
        blocked_category = str(blocked_runtime_state.get("category", "")).strip()
        if blocked_category == "session_binding":
            link = find_link_by_task_id(task_id) or ensure_autonomy_root_mission_link(task_id)
            if link:
                return _restart_after_block_repair(
                    task_id,
                    state,
                    repair_reason="session_binding_recovered",
                    event_name="system_doctor_repaired_session_binding",
                    extra={
                        "provider": str(link.get("provider", "")).strip(),
                        "conversation_id": str(link.get("conversation_id", "")).strip(),
                        "session_key": str(link.get("session_key", "")).strip(),
                        "link_kind": str(link.get("link_kind", "")).strip(),
                    },
                )
        if blocked_category == "project_crawler_remediation":
            recomputed_gate = _project_crawler_gate_still_applies(task_id, state)
            if not recomputed_gate:
                return _restart_after_block_repair(
                    task_id,
                    state,
                    repair_reason="stale_project_crawler_gate_cleared",
                    event_name="system_doctor_cleared_stale_project_crawler_gate",
                    extra={
                        "previous_next_action": state.next_action,
                        "blocked_runtime_state": blocked_runtime_state,
                    },
                )
        if blocked_category == "runtime_or_contract_fix":
            resolved_commands = _resolved_missing_commands(list(state.blockers or []))
            if resolved_commands:
                return _restart_after_block_repair(
                    task_id,
                    state,
                    repair_reason="runtime_dependencies_restored",
                    event_name="system_doctor_repaired_runtime_dependencies",
                    extra={
                        "resolved_commands": resolved_commands,
                        "previous_next_action": state.next_action,
                    },
                )
    escalation = diagnosis.get("stuck_escalation", {}) or {}
    if escalation.get("mode") == "deep_research":
        state.status = "planning"
        state.blockers = []
        state.metadata["last_stuck_escalation"] = escalation
        state.next_action = f"start_stage:{state.current_stage}" if state.current_stage else "initialize"
        state.last_update_at = _utc_now_iso()
        save_state(state)
        log_event(task_id, "system_doctor_restarted_with_deep_research", diagnosis=diagnosis, escalation=escalation)
        promoted_rule = _record_doctor_rule(task_id, diagnosis, "restarted_with_deep_research", "deep_research")
        return {"task_id": task_id, "repaired": True, "reason": "restarted_with_deep_research", "promoted_rule": promoted_rule}
    if escalation.get("mode") == "ask_user":
        state.status = "blocked"
        state.metadata["last_stuck_escalation"] = escalation
        state.next_action = "doctor_request_human_guidance"
        state.last_update_at = _utc_now_iso()
        save_state(state)
        log_event(task_id, "system_doctor_marked_human_guidance_required", diagnosis=diagnosis, escalation=escalation)
        promoted_rule = _record_doctor_rule(task_id, diagnosis, "awaiting_human_guidance", "ask_user")
        return {"task_id": task_id, "repaired": True, "reason": "awaiting_human_guidance", "promoted_rule": promoted_rule}
    return {"task_id": task_id, "repaired": False, "reason": diagnosis.get("reason", "unhandled")}


def _run_gstack_integration_checks() -> Dict[str, object]:
    errors = []
    for path in GSTACK_REQUIRED_FILES:
        if not path.exists():
            errors.append(f'missing_required_file:{path}')
    prompt_path = WORKSPACE_ROOT / 'compat/gstack/prompts/jinclaw-gstack-lite.md'
    if prompt_path.exists():
        prompt_text = prompt_path.read_text(encoding='utf-8')
        for stage in GSTACK_LIFECYCLE:
            if stage not in prompt_text:
                errors.append(f'prompt_missing_lifecycle_stage:{stage}')
        if '## Reporting contract' not in prompt_text:
            errors.append('prompt_missing_reporting_contract')
    else:
        errors.append(f'missing_required_file:{prompt_path}')

    if str(CONTROL_CENTER_ROOT) not in sys.path:
        sys.path.insert(0, str(CONTROL_CENTER_ROOT))
    from orchestrator import build_control_center_package
    from context_builder import build_stage_context
    from coding_session_adapter import build_coding_session_payload
    from acp_dispatch_builder import build_acp_dispatch_request
    from task_contract import TaskContract
    from action_executor import _dispatch_prompt

    def _run_case(task_id: str, goal: str, expect_coding: bool) -> None:
        task_path = task_dir(task_id)
        if task_path.exists():
            shutil.rmtree(task_path)
        try:
            package = build_control_center_package(task_id, goal, source='system-doctor')
            contract = TaskContract.from_dict({
                'task_id': task_id,
                'user_goal': package['goal'],
                'done_definition': package['done_definition'],
                'allowed_tools': package.get('allowed_tools', []),
                'forbidden_actions': package.get('forbidden_actions', []),
                'stages': package['stages'],
                'metadata': package['metadata'],
            })
            create_task_from_contract(contract)
            methodology = (package.get('metadata', {}) or {}).get('control_center', {}).get('coding_methodology', {}) or {}
            state = {
                'current_stage': 'execute',
                'status': 'running',
                'next_action': 'start_stage:execute',
                'blockers': [],
                'stages': {'execute': {'attempts': 1, 'completed_subtasks': []}},
                'metadata': {},
            }
            stage_context = build_stage_context(task_id, 'execute', contract.to_dict(), state)
            payload = build_coding_session_payload(contract.to_dict(), stage_context)
            request = build_acp_dispatch_request(contract.to_dict(), stage_context)
            runtime_prompt = _dispatch_prompt(task_id, 'execute')
            if expect_coding:
                if methodology.get('methodology') != 'jinclaw-gstack-lite':
                    errors.append('coding_chain_missing_methodology_in_package')
                if methodology.get('lifecycle') != GSTACK_LIFECYCLE:
                    errors.append('coding_chain_invalid_lifecycle_in_package')
                if not payload.get('requires_prompt_injection'):
                    errors.append('coding_chain_missing_prompt_injection_flag')
                if not request.get('prompt_components', {}).get('methodology_prompt_included'):
                    errors.append('coding_chain_dispatch_missing_methodology_marker')
                if '# JinClaw GStack-Lite Coding Discipline' not in runtime_prompt:
                    errors.append('coding_chain_runtime_prompt_missing_gstack_header')
            else:
                if methodology.get('enabled') is not False:
                    errors.append('noncoding_chain_should_not_enable_coding_methodology')
                if payload.get('requires_prompt_injection'):
                    errors.append('noncoding_chain_should_not_require_prompt_injection')
                if request.get('prompt_components', {}).get('methodology_prompt_included'):
                    errors.append('noncoding_chain_dispatch_should_not_include_methodology_marker')
                if '# JinClaw GStack-Lite Coding Discipline' in runtime_prompt:
                    errors.append('noncoding_chain_runtime_prompt_should_remain_native')
        finally:
            if task_path.exists():
                shutil.rmtree(task_path)

    _run_case('doctor-coding-chain', 'Implement a code fix and add regression tests for integration doctor coverage', True)
    _run_case('doctor-optimization-chain', '优化 JinClaw 的目标守护与测试闭环，确保复杂任务更稳定', True)
    _run_case('doctor-noncoding-chain', 'Research marketplace competitors and produce a structured report', False)
    return {
        'single_doctor_rule': True,
        'authoritative_doctor': 'tools/openmoss/control_center/system_doctor.py',
        'registered_integrations': _build_doctor_coverage_bundle().get('registered_integrations', []),
        'required_files_checked': len(GSTACK_REQUIRED_FILES),
        'lifecycle': GSTACK_LIFECYCLE,
        'coding_chain': 'ok' if not any(err.startswith('coding_chain_') for err in errors) else 'error',
        'noncoding_chain': 'ok' if not any(err.startswith('noncoding_chain_') for err in errors) else 'error',
        'errors': errors,
        'ok': not errors,
    }


def _run_acquisition_integration_checks() -> Dict[str, object]:
    """
    中文注解：
    - 功能：校验 acquisition hand 是否已经被 canonical doctor 监控到位。
    - 输入角色：直接消费 acquisition hand 的合同、上下文、dispatch 与状态快照链路。
    - 输出角色：返回给 `run_system_doctor` 的 integration health，作为医生是否真的看得到抓取之手的证据。
    """
    errors = []
    for path in ACQUISITION_REQUIRED_FILES:
        if not path.exists():
            errors.append(f'missing_required_file:{path}')

    if str(CONTROL_CENTER_ROOT) not in sys.path:
        sys.path.insert(0, str(CONTROL_CENTER_ROOT))
    from orchestrator import build_control_center_package
    from context_builder import build_stage_context
    from coding_session_adapter import build_coding_session_payload
    from acp_dispatch_builder import build_acp_dispatch_request
    from crawler_probe_runner import _derive_probe_execution_plan
    from acquisition_result_normalizer import build_acquisition_execution_summary
    from crawler_capability_profile import build_crawler_capability_profile
    from task_contract import TaskContract
    from action_executor import _dispatch_prompt

    def _run_case(task_id: str, goal: str) -> None:
        task_path = task_dir(task_id)
        if task_path.exists():
            shutil.rmtree(task_path)
        try:
            package = build_control_center_package(task_id, goal, source='system-doctor')
            control_center = (package.get('metadata', {}) or {}).get('control_center', {}) or {}
            acquisition_hand = control_center.get('acquisition_hand', {}) or {}
            if not acquisition_hand.get('enabled'):
                errors.append('acquisition_chain_disabled_in_package')
            if not acquisition_hand.get('route_candidates'):
                errors.append('acquisition_chain_missing_route_candidates')
            if not ((acquisition_hand.get('execution_strategy', {}) or {}).get('primary_route_id')):
                errors.append('acquisition_chain_missing_primary_route')
            enabled_adapters = [
                item
                for item in ((acquisition_hand.get('adapter_registry', {}) or {}).get('adapters', []) or [])
                if bool((item or {}).get('enabled'))
            ]
            browser_enabled_adapters = [
                item for item in enabled_adapters if str((item or {}).get('route_type', '')).strip() == 'browser_render'
            ]
            validation_families = sorted(
                {
                    str((item or {}).get('validation_family', '')).strip()
                    for item in enabled_adapters
                    if str((item or {}).get('validation_family', '')).strip()
                }
            )
            if enabled_adapters and not any(str((item or {}).get('execution_tool_id', '')).strip() for item in enabled_adapters):
                errors.append('acquisition_chain_missing_execution_binding_registry')
            if browser_enabled_adapters and not any(str((item or {}).get('execution_profile', '')).strip() for item in browser_enabled_adapters):
                errors.append('acquisition_chain_missing_browser_execution_profiles')
            if enabled_adapters and not validation_families:
                errors.append('acquisition_chain_missing_validation_families')
            probe_plan = _derive_probe_execution_plan(
                goal,
                control_center.get('crawler', {}) or {},
                acquisition_hand,
            )
            if not [str(item).strip() for item in probe_plan.get('tool_ids', []) or [] if str(item).strip()]:
                errors.append('acquisition_chain_missing_local_probe_plan')
            delivery_requirements = acquisition_hand.get('delivery_requirements', {}) or {}
            if not (delivery_requirements.get('required_fields_by_site', {}) or {}):
                errors.append('acquisition_chain_missing_delivery_requirements')
            if not (acquisition_hand.get('release_governance', {}) or {}).get('mode'):
                errors.append('acquisition_chain_missing_release_governance')
            sample_tool_labels = [
                str(item.get('tool_label', '')).strip()
                for item in (probe_plan.get('route_plan', []) or [])[:2]
                if str(item.get('tool_label', '')).strip()
            ]
            if sample_tool_labels:
                sample_report = {
                    'generated_at': _utc_now_iso(),
                    'planned_execution': probe_plan,
                    'sites': [
                        {
                            'site': 'amazon',
                            'url': 'https://www.amazon.com/s?k=doctor+acquisition+probe',
                            'tool_results': [
                                {
                                    'tool': tool_label,
                                    'status': 'usable',
                                    'arbitration_score': 80 - index * 3,
                                    'normalized_task_output': {
                                        'field_completeness': 0.75,
                                        'populated_fields': ['title', 'price', 'link'],
                                        'fields': {
                                            'title': 'Doctor Probe Item',
                                            'price': '19.99',
                                            'link': '/dp/DOCTORCHECK',
                                        },
                                    },
                                    'false_positive': {'reasons': []},
                                }
                                for index, tool_label in enumerate(sample_tool_labels)
                            ],
                        }
                    ],
                }
                sample_summary = build_acquisition_execution_summary(
                    task_id,
                    goal,
                    sample_report,
                    acquisition_hand,
                    report_path='/tmp/doctor-acquisition-sample.json',
                )
                if not (sample_summary.get('site_synthesized_outputs', []) or []):
                    errors.append('acquisition_chain_missing_site_synthesis_summary')
                if not str((sample_summary.get('overall_summary', {}) or {}).get('synthesis_status', '')).strip():
                    errors.append('acquisition_chain_missing_synthesis_status')
                answer_synthesis = (sample_summary.get('overall_summary', {}) or {}).get('answer_synthesis', {})
                if not isinstance(answer_synthesis, dict):
                    errors.append('acquisition_chain_missing_answer_synthesis')
                elif bool(answer_synthesis.get('answerable')) and not str(answer_synthesis.get('response_mode', '')).strip():
                    errors.append('acquisition_chain_missing_answer_response_mode')
                if not str((sample_summary.get('overall_summary', {}) or {}).get('validation_diversity_status', '')).strip():
                    errors.append('acquisition_chain_missing_validation_diversity_status')
                if not str((sample_summary.get('overall_summary', {}) or {}).get('release_readiness_status', '')).strip():
                    errors.append('acquisition_chain_missing_release_readiness_status')
                if not str((sample_summary.get('overall_summary', {}) or {}).get('trusted_release_status', '')).strip():
                    errors.append('acquisition_chain_missing_trusted_release_status')
                if not str((sample_summary.get('overall_summary', {}) or {}).get('governed_release_status', '')).strip():
                    errors.append('acquisition_chain_missing_governed_release_status')
                site_answers = [
                    item.get('answer_synthesis', {}) or {}
                    for item in (sample_summary.get('site_synthesized_outputs', []) or [])
                ]
                if site_answers and not all(isinstance(item, dict) and str(item.get('status', '')).strip() for item in site_answers):
                    errors.append('acquisition_chain_site_answer_synthesis_incomplete')
                release_disclosure = (sample_summary.get('overall_summary', {}) or {}).get('release_disclosure', {})
                governed_release_status = str((sample_summary.get('overall_summary', {}) or {}).get('governed_release_status', '')).strip()
                if not isinstance(release_disclosure, dict):
                    errors.append('acquisition_chain_missing_release_disclosure')
                elif governed_release_status != 'auto_release_allowed' and not (release_disclosure or {}).get('headline'):
                    errors.append('acquisition_chain_release_disclosure_missing_headline')

            contract = TaskContract.from_dict({
                'task_id': task_id,
                'user_goal': package['goal'],
                'done_definition': package['done_definition'],
                'allowed_tools': package.get('allowed_tools', []),
                'forbidden_actions': package.get('forbidden_actions', []),
                'stages': package['stages'],
                'metadata': package['metadata'],
            })
            create_task_from_contract(contract)
            state = {
                'current_stage': 'execute',
                'status': 'running',
                'next_action': 'start_stage:execute',
                'blockers': [],
                'stages': {'execute': {'attempts': 1, 'completed_subtasks': []}},
                'metadata': {},
            }
            stage_context = build_stage_context(task_id, 'execute', contract.to_dict(), state)
            if not ((stage_context.get('acquisition_hand', {}) or {}).get('enabled')):
                errors.append('acquisition_chain_missing_stage_context')
            response_handoff = stage_context.get('response_handoff', {}) or {}
            if not str(response_handoff.get('status', '')).strip():
                errors.append('acquisition_chain_missing_response_handoff_status')
            if bool((stage_context.get('acquisition_hand', {}) or {}).get('enabled')) and not str(
                response_handoff.get('response_mode', '')
            ).strip():
                errors.append('acquisition_chain_missing_response_handoff_mode')
            payload = build_coding_session_payload(contract.to_dict(), stage_context)
            if 'Acquisition hand:' not in str(payload.get('base_prompt', '')):
                errors.append('acquisition_chain_runtime_prompt_missing_summary')
            if 'Response handoff:' not in str(payload.get('base_prompt', '')):
                errors.append('acquisition_chain_runtime_prompt_missing_response_handoff')
            request = build_acp_dispatch_request(contract.to_dict(), stage_context)
            if not ((request.get('metadata', {}) or {}).get('acquisition_enabled')):
                errors.append('acquisition_chain_dispatch_missing_enable_marker')
            if not str((request.get('metadata', {}) or {}).get('response_handoff_status', '')).strip():
                errors.append('acquisition_chain_dispatch_missing_response_handoff_status')
            runtime_prompt = _dispatch_prompt(task_id, 'execute')
            if 'response_handoff:' not in runtime_prompt:
                errors.append('acquisition_chain_runtime_dispatch_missing_response_handoff')
            snapshot = build_task_status_snapshot(task_id)
            snapshot_hand = snapshot.get('acquisition_hand', {}) or {}
            if not snapshot_hand.get('enabled'):
                errors.append('acquisition_chain_snapshot_missing_enable_marker')
            if not snapshot_hand.get('primary_route'):
                errors.append('acquisition_chain_snapshot_missing_primary_route')
            answer_response = ((snapshot.get('reply_contract', {}) or {}).get('acquisition_response', {}) or {})
            if (snapshot_hand.get('answer_synthesis', {}) or {}) and not str(answer_response.get('response_mode', '')).strip():
                errors.append('acquisition_chain_snapshot_missing_answer_response_mode')
            authoritative_summary = str(snapshot.get('authoritative_summary', '')).strip()
            if bool(answer_response.get('enabled')) and 'Current data answer mode is' not in authoritative_summary:
                errors.append('acquisition_chain_authoritative_summary_missing_answer_mode')
            receipt_text = build_route_receipt_text(
                {
                    'mode': 'authoritative_task_status',
                    'task_id': task_id,
                    'authoritative_task_status': snapshot,
                }
            )
            if bool(answer_response.get('enabled')) and not any(
                marker in receipt_text for marker in ['当前数据回答模式是', 'Current data answer mode is']
            ):
                errors.append('acquisition_chain_receipt_missing_answer_mode')
        finally:
            if task_path.exists():
                shutil.rmtree(task_path)

    _run_case(
        'doctor-acquisition-chain',
        'Collect current public marketplace pricing data, compare multiple sources, and return structured evidence with citations',
    )
    crawler_profile = build_crawler_capability_profile()
    crawler_summary = crawler_profile.get('summary', {}) or {}
    if 'sites_with_evidence_drift' not in crawler_summary:
        errors.append('acquisition_chain_missing_execution_truth_drift_summary')
    if 'evidence_alignment_score' not in crawler_summary:
        errors.append('acquisition_chain_missing_evidence_alignment_score')
    return {
        'single_doctor_rule': True,
        'authoritative_doctor': 'tools/openmoss/control_center/system_doctor.py',
        'required_files_checked': len(ACQUISITION_REQUIRED_FILES),
        'required_files': [str(path.relative_to(WORKSPACE_ROOT)) for path in ACQUISITION_REQUIRED_FILES],
        'field_synthesis_contract': not any(
            item in {'acquisition_chain_missing_site_synthesis_summary', 'acquisition_chain_missing_synthesis_status'}
            for item in errors
        ),
        'delivery_requirements_contract': not any(
            item in {'acquisition_chain_missing_delivery_requirements', 'acquisition_chain_missing_release_readiness_status'}
            for item in errors
        ),
        'source_trust_contract': not any(
            item in {'acquisition_chain_missing_trusted_release_status'}
            for item in errors
        ),
        'release_governance_contract': not any(
            item in {'acquisition_chain_missing_release_governance', 'acquisition_chain_missing_governed_release_status'}
            for item in errors
        ),
        'release_disclosure_contract': not any(
            item in {'acquisition_chain_missing_release_disclosure', 'acquisition_chain_release_disclosure_missing_headline'}
            for item in errors
        ),
        'answer_synthesis_contract': not any(
            item in {
                'acquisition_chain_missing_answer_synthesis',
                'acquisition_chain_missing_answer_response_mode',
                'acquisition_chain_site_answer_synthesis_incomplete',
            }
            for item in errors
        ),
        'answer_response_contract': not any(
            item in {
                'acquisition_chain_snapshot_missing_answer_response_mode',
                'acquisition_chain_authoritative_summary_missing_answer_mode',
                'acquisition_chain_receipt_missing_answer_mode',
            }
            for item in errors
        ),
        'response_handoff_contract': not any(
            item in {
                'acquisition_chain_missing_response_handoff_status',
                'acquisition_chain_missing_response_handoff_mode',
                'acquisition_chain_runtime_prompt_missing_response_handoff',
                'acquisition_chain_dispatch_missing_response_handoff_status',
                'acquisition_chain_runtime_dispatch_missing_response_handoff',
            }
            for item in errors
        ),
        'browser_execution_contract': not any(
            item in {'acquisition_chain_missing_browser_execution_profiles'}
            for item in errors
        ),
        'validation_family_contract': not any(
            item in {'acquisition_chain_missing_validation_families', 'acquisition_chain_missing_validation_diversity_status'}
            for item in errors
        ),
        'execution_truth_contract': not any(
            item in {'acquisition_chain_missing_execution_truth_drift_summary', 'acquisition_chain_missing_evidence_alignment_score'}
            for item in errors
        ),
        'acquisition_chain': 'ok' if not errors else 'error',
        'errors': errors,
        'ok': not errors,
    }


def _run_integration_health_checks() -> Dict[str, object]:
    """
    中文注解：
    - 功能：聚合所有已注册集成的 doctor 健康检查结果，继续保持 single-doctor 结构。
    - 输入角色：消费 gstack 与 acquisition hand 两条集成检查。
    - 输出角色：供 system doctor 与 ops doctor 统一展示。
    """
    gstack = _run_gstack_integration_checks()
    acquisition_hand = _run_acquisition_integration_checks()
    errors = list(gstack.get('errors', []) or []) + list(acquisition_hand.get('errors', []) or [])
    return {
        'single_doctor_rule': True,
        'authoritative_doctor': 'tools/openmoss/control_center/system_doctor.py',
        'registered_integrations': _build_doctor_coverage_bundle().get('registered_integrations', []),
        'required_files_checked': int(gstack.get('required_files_checked', 0) or 0)
        + int(acquisition_hand.get('required_files_checked', 0) or 0),
        'lifecycle': GSTACK_LIFECYCLE,
        'gstack': gstack,
        'acquisition_hand': acquisition_hand,
        'coding_chain': gstack.get('coding_chain', 'unknown'),
        'noncoding_chain': gstack.get('noncoding_chain', 'unknown'),
        'acquisition_chain': acquisition_hand.get('acquisition_chain', 'unknown'),
        'errors': errors,
        'ok': bool(gstack.get('ok')) and bool(acquisition_hand.get('ok')),
    }


def run_system_doctor(*, idle_after_seconds: int = 180, escalation_after_seconds: int = 600) -> Dict[str, object]:
    """
    中文注解：
    - 功能：执行一轮医生巡诊。
    - 主步骤：
      1. 先读取 control plane，拿到 doctor queue；
      2. 对每个待处理任务做 diagnose + repair；
      3. 超过升级阈值的任务，向聊天窗口发 doctor diagnostic receipt；
      4. 同时运行 mission_supervisor，补充更高层的监督结果。
    - 输出：会写 `doctor/last_run.json`，也会把结果返回给 runtime 或人工检查。
    """
    control_plane = build_control_plane(
        stale_after_seconds=max(120, idle_after_seconds),
        escalation_after_seconds=max(300, escalation_after_seconds),
    )
    heartbeat_summary = _write_doctor_heartbeats(control_plane, idle_after_seconds=idle_after_seconds)
    heartbeat_overview = _heartbeat_stability_overview(heartbeat_summary)
    process_incidents = _reconcile_process_incidents(control_plane)
    reports = []
    doctor_items = list(control_plane.get("doctor_queue", {}).get("items", []) or [])
    doctor_strategy = _doctor_cycle_strategy(control_plane)
    task_incident_candidates: List[Dict[str, object]] = []
    seen_task_ids = set()
    processed_total = 0
    skipped_reports = []
    # doctor_queue 是 control plane 给医生的统一待办清单；
    # 医生不再自己到处翻日志，而是集中读这份汇总视图。
    for item in doctor_items:
        task_id = str(item.get("task_id", "")).strip()
        if not task_id or task_id in seen_task_ids:
            continue
        seen_task_ids.add(task_id)
        try:
            should_process, decision_reason = _should_process_doctor_item(item, doctor_strategy, processed_total)
            if not should_process:
                skipped_reports.append(
                    {
                        "task_id": task_id,
                        "priority": {
                            "score": int(item.get("priority_score", 0) or 0),
                            "bucket": str(item.get("priority_bucket", "")).strip() or "unknown",
                            "reason": str(item.get("priority_reason", "")).strip() or "unknown",
                        },
                        "skip_reason": decision_reason,
                    }
                )
                continue
            diagnosis = diagnose_task(task_id, idle_after_seconds=idle_after_seconds)
            repair = repair_task_if_possible(task_id, diagnosis)
            processed_total += 1
            writeback_summary = {
                "attention_required": bool(diagnosis.get("stuck")),
                "state_patch": {},
                "governance_patch": {},
                "next_actions": [str(repair.get("reason", "")).strip()] if str(repair.get("reason", "")).strip() and repair.get("repaired") else [],
                "warnings": [str(diagnosis.get("reason", "")).strip()] if diagnosis.get("stuck") else [],
                "errors": [],
                "decisions": [
                    "doctor_diagnosis_completed",
                    "doctor_repair_applied" if repair.get("repaired") else "doctor_repair_not_applied",
                ],
                "memory_targets": ["runtime", "task"] if diagnosis.get("stuck") else ["runtime"],
                "memory_reasons": ["doctor_diagnosis", "doctor_repair"] if repair.get("repaired") else ["doctor_diagnosis"],
            }
            writeback = record_memory_writeback(task_id, source="doctor:diagnosis_cycle", summary=writeback_summary)
            state = load_state(task_id)
            state.metadata["memory_writeback"] = writeback
            state.last_update_at = _utc_now_iso()
            save_state(state)
            report = {"diagnosis": diagnosis, "repair": repair}
            report["memory_writeback"] = writeback
            report["priority"] = {
                "score": int(item.get("priority_score", 0) or 0),
                "bucket": str(item.get("priority_bucket", "")).strip() or "unknown",
                "reason": str(item.get("priority_reason", "")).strip() or "unknown",
            }
            if _should_route_task_incident_to_ai(
                task_id,
                str(item.get("canonical_task_id", task_id)).strip() or task_id,
                diagnosis,
                repair,
            ):
                task_incident_candidates.append(
                    {
                        "task_id": task_id,
                        "canonical_task_id": str(item.get("canonical_task_id", task_id)).strip() or task_id,
                        "diagnosis": diagnosis,
                        "repair": repair,
                        "priority": report["priority"],
                    }
                )
            if diagnosis.get("stuck"):
                report["governance"] = (build_task_status_snapshot(task_id).get("governance", {}) or {})
            if diagnosis.get("stuck") and diagnosis.get("idle_seconds", 0) >= escalation_after_seconds:
                for link_path in LINKS_ROOT.glob("*.json"):
                    try:
                        payload = json.loads(link_path.read_text(encoding="utf-8"))
                    except (OSError, json.JSONDecodeError):
                        continue
                    if payload.get("task_id") != task_id:
                        continue
                    snapshot = build_task_status_snapshot(task_id)
                    snapshot["authoritative_summary"] = build_supervisor_status_text(task_id, diagnosis, repair, snapshot)
                    route = {
                        "mode": "doctor_diagnostic",
                        "task_id": task_id,
                        "goal": payload.get("goal", ""),
                        "authoritative_task_status": snapshot,
                    }
                    receipt = emit_route_receipt(
                        route,
                        provider=str(payload.get("provider", "openclaw-main")),
                        conversation_id=str(payload.get("conversation_id", "")),
                        session_key=str(payload.get("session_key", "")),
                    )
                    report["receipt"] = receipt
                    log_event(task_id, "system_doctor_escalated_to_user", diagnosis=diagnosis, repair=repair)
                    break
            reports.append(report)
        except Exception as exc:
            reports.append(
                {
                    "task_id": task_id,
                    "doctor_internal_error": True,
                    "error": str(exc),
                    "priority": {
                        "score": int(item.get("priority_score", 0) or 0),
                        "bucket": str(item.get("priority_bucket", "")).strip() or "unknown",
                        "reason": str(item.get("priority_reason", "")).strip() or "unknown",
                    },
                }
            )
    supervisor = run_mission_supervisor(
        stale_after_seconds=max(120, idle_after_seconds),
        escalation_after_seconds=max(300, escalation_after_seconds),
    )
    task_incidents = _reconcile_task_incidents(task_incident_candidates, idle_after_seconds=idle_after_seconds)
    integration_health = _run_integration_health_checks()
    crawler_profile = control_plane.get("crawler_capability_profile", {}) or {}
    crawler_summary = crawler_profile.get("summary", {}) or {}
    acquisition_market = build_acquisition_adapter_registry(build_capability_registry())
    browser_adapters = [
        item
        for item in (acquisition_market.get("adapters", []) or [])
        if str((item or {}).get("route_type", "")).strip() == "browser_render"
    ]
    browser_runtime_ready = [item for item in browser_adapters if bool((item or {}).get("runtime_ready"))]
    browser_profiles = sorted(
        {
            str((item or {}).get("execution_profile", "")).strip()
            for item in browser_runtime_ready
            if str((item or {}).get("execution_profile", "")).strip()
        }
    )
    validation_families = sorted(
        {
            str((item or {}).get("validation_family", "")).strip()
            for item in (acquisition_market.get("adapters", []) or [])
            if str((item or {}).get("validation_family", "")).strip()
        }
    )
    source_trust_tiers = sorted(
        {
            str((item or {}).get("source_trust_tier", "")).strip()
            for item in (acquisition_market.get("adapters", []) or [])
            if str((item or {}).get("source_trust_tier", "")).strip()
        }
    )
    crawler_attention_sites = [
        {
            "site": site.get("site", ""),
            "readiness": site.get("readiness", ""),
            "primary_limitations": site.get("primary_limitations", []),
            "evidence_alignment": (site.get("evidence_alignment", {}) or {}).get("status", ""),
        }
        for site in (crawler_profile.get("sites", []) or [])
        if site.get("readiness") == "attention_required"
    ][:5]
    result = {
        "checked_at": _utc_now_iso(),
        "control_plane": {
            "system_snapshot": control_plane.get("system_snapshot", {}),
            "doctor_queue_count": len(control_plane.get("doctor_queue", {}).get("items", [])),
            "alerts_count": len(control_plane.get("alerts", {}).get("items", [])),
            "crawler_remediation_queue_count": len(control_plane.get("crawler_remediation_queue", {}).get("items", [])),
            "crawler_remediation_plan_count": len(control_plane.get("crawler_remediation_plan", {}).get("items", [])),
            "crawler_remediation_execution_count": len(control_plane.get("crawler_remediation_execution", {}).get("items", [])),
        },
        "crawler_health": {
            "summary": crawler_summary,
            "trend": crawler_profile.get("trend", {}) or {},
            "feedback": crawler_profile.get("feedback", {}) or {},
            "memory_writeback_overview": crawler_profile.get("memory_writeback_overview", {}) or {},
            "attention_sites": crawler_attention_sites,
            "recommended_project_actions": (crawler_profile.get("recommended_project_actions", []) or [])[:5],
            "priority_actions": (crawler_profile.get("priority_actions", []) or [])[:6],
            "remediation_queue": (control_plane.get("crawler_remediation_queue", {}).get("items", []) or [])[:6],
            "remediation_plan": (control_plane.get("crawler_remediation_plan", {}).get("items", []) or [])[:6],
            "remediation_execution": (control_plane.get("crawler_remediation_execution", {}).get("items", []) or [])[:6],
        },
        "acquisition_health": {
            "enabled": True,
            "summary": crawler_summary,
            "adapter_coverage": {
                "sites_total": int(crawler_summary.get("sites_total", 0) or 0),
                "sites_production_ready": int(crawler_summary.get("sites_production_ready", 0) or 0),
                "sites_attention_required": int(crawler_summary.get("sites_attention_required", 0) or 0),
                "sites_governed_ready": int(crawler_summary.get("sites_governed_ready", 0) or 0),
                "sites_authorized_session_ready": int(crawler_summary.get("sites_authorized_session_ready", 0) or 0),
                "sites_with_evidence_drift": int(crawler_summary.get("sites_with_evidence_drift", 0) or 0),
                "governed_width_score": float(crawler_summary.get("governed_width_score", 0.0) or 0.0),
                "evidence_alignment_score": float(crawler_summary.get("evidence_alignment_score", 0.0) or 0.0),
                "stability_score": float(crawler_summary.get("stability_score", 0.0) or 0.0),
                "available_adapter_total": int(acquisition_market.get("available_adapter_total", 0) or 0),
                "observed_only_adapter_total": len(acquisition_market.get("observed_only_adapter_ids", []) or []),
                "validation_family_total": len(validation_families),
                "validation_families": validation_families[:8],
                "source_trust_tier_total": len(source_trust_tiers),
                "source_trust_tiers": source_trust_tiers[:8],
                "browser_adapter_total": len(browser_adapters),
                "browser_runtime_ready_total": len(browser_runtime_ready),
                "browser_execution_profiles": browser_profiles[:8],
                "available_adapter_ids": (acquisition_market.get("available_adapter_ids", []) or [])[:10],
            },
            "attention_sites": crawler_attention_sites,
            "priority_actions": (crawler_profile.get("priority_actions", []) or [])[:6],
            "feedback": crawler_profile.get("feedback", {}) or {},
        },
        "process_incidents": process_incidents,
        "task_incidents": task_incidents,
        "project_repair_value": control_plane.get("project_repair_value", {}) or {},
        "project_repair_history": (control_plane.get("project_repair_value_history", {}) or {}).get("trend", {}) or {},
        "project_repair_recommendations": (control_plane.get("project_repair_recommendations", []) or [])[:6],
        "doctor_strategy": doctor_strategy,
        "doctor_heartbeat": {
            "count": int(heartbeat_summary.get("count", 0) or 0),
            "error_count": int(heartbeat_summary.get("error_count", 0) or 0),
            "eligible_statuses": heartbeat_summary.get("eligible_statuses", []),
            "last_cycle_path": str(DOCTOR_HEARTBEATS_ROOT / "last_cycle.json"),
        },
        "stability_overview": heartbeat_overview,
        "doctor_cycle_stats": {
            "processed_total": processed_total,
            "skipped_total": len(skipped_reports),
            "max_repairs_per_cycle": int(doctor_strategy.get("max_repairs_per_cycle", 0) or 0),
        },
        "integration_health": integration_health,
        "skipped_reports": skipped_reports[:20],
        "heartbeat_sample": (heartbeat_summary.get("items", []) or [])[:10],
        "reports": reports,
        "mission_supervisor": supervisor,
    }
    try:
        from generate_doctor_dashboard import build_dashboard

        dashboard_path = DOCTOR_ROOT / "dashboard.html"
        dashboard_path.write_text(build_dashboard(), encoding="utf-8")
        result["dashboard"] = {
            "generated": True,
            "path": str(dashboard_path),
        }
    except Exception as exc:
        result["dashboard"] = {
            "generated": False,
            "error": str(exc),
        }
    _write_json(DOCTOR_ROOT / "last_run.json", result)
    return result
