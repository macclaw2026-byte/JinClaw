#!/usr/bin/env python3

"""
中文说明：
- 文件路径：`tools/openmoss/control_center/control_plane_builder.py`
- 文件作用：负责统一控制平面的快照构建与多源状态汇总。
- 顶层函数：_utc_now_iso、_read_json、_write_json、_launchctl_status、build_process_registry、_load_task_state、_load_task_contract、_conversation_links_for_task、build_task_registry、build_control_plane、main。
- 顶层类：无顶层类。
- 阅读建议：先看模块说明，再按函数/类 docstring 顺着主流程理解调用关系。
"""
from __future__ import annotations

import json
import os
import subprocess
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

from canonical_active_task import resolve_canonical_active_task
from crawler_capability_profile import build_crawler_capability_profile
from crawler_remediation_planner import build_crawler_remediation_plan
from execution_governor import classify_blocked_runtime_state
from memory_writeback_runtime import summarize_project_memory_writebacks
from project_scheduler_policy import build_project_scheduler_policy
from paths import (
    ALERTS_PATH,
    DOCTOR_LAST_RUN_PATH,
    CROSS_MARKET_ARBITRAGE_SCHEDULER_STATE_PATH,
    CRAWLER_CAPABILITY_PROFILE_PATH,
    CRAWLER_REMEDIATION_EXECUTION_PATH,
    CRAWLER_REMEDIATION_PLAN_PATH,
    CRAWLER_REMEDIATION_QUEUE_PATH,
    CRAWLER_REMEDIATION_SCHEDULER_STATE_PATH,
    DOCTOR_QUEUE_PATH,
    PROCESS_REGISTRY_PATH,
    PROJECT_RESULT_FEEDBACK_HISTORY_PATH,
    SELLER_BULK_SCHEDULER_STATE_PATH,
    SYSTEM_SNAPSHOT_PATH,
    TASK_REGISTRY_PATH,
    WAITING_REGISTRY_PATH,
)
from progress_evidence import build_progress_evidence


AUTONOMY_TASKS_ROOT = Path("/Users/mac_claw/.openclaw/workspace/tools/openmoss/runtime/autonomy/tasks")
LINKS_ROOT = Path("/Users/mac_claw/.openclaw/workspace/tools/openmoss/runtime/autonomy/links")

PROCESS_TARGETS = [
    {"label": "brain_enforcer", "launchd_label": "ai.openclaw.brain-enforcer"},
    {"label": "autonomy_runtime", "launchd_label": "ai.jinclaw.autonomy-runtime"},
    {"label": "cross_market_arbitrage", "launchd_label": "ai.jinclaw.cross-market-arbitrage"},
    {"label": "crawler_remediation", "launchd_label": "ai.jinclaw.crawler-remediation"},
]


def _utc_now_iso() -> str:
    """
    中文注解：
    - 功能：实现 `_utc_now_iso` 对应的处理逻辑。
    - 角色：属于本模块中的内部辅助逻辑；私有函数通常服务同文件主流程，公共函数通常作为跨模块入口或能力接口。
    - 调用关系：建议结合本文件的模块说明、调用方以及同名相关辅助函数一起阅读。
    """
    return datetime.now(timezone.utc).isoformat()


def _read_json(path: Path, default: Any) -> Any:
    """
    中文注解：
    - 功能：实现 `_read_json` 对应的处理逻辑。
    - 角色：属于本模块中的内部辅助逻辑；私有函数通常服务同文件主流程，公共函数通常作为跨模块入口或能力接口。
    - 调用关系：建议结合本文件的模块说明、调用方以及同名相关辅助函数一起阅读。
    """
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return default


def _write_json(path: Path, payload: Any) -> str:
    """
    中文注解：
    - 功能：实现 `_write_json` 对应的处理逻辑。
    - 角色：属于本模块中的内部辅助逻辑；私有函数通常服务同文件主流程，公共函数通常作为跨模块入口或能力接口。
    - 调用关系：建议结合本文件的模块说明、调用方以及同名相关辅助函数一起阅读。
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = path.with_name(f"{path.name}.{os.getpid()}.{uuid.uuid4().hex}.tmp")
    temp_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    temp_path.replace(path)
    return str(path)


def _launchctl_status(launchd_label: str) -> Dict[str, Any]:
    """
    中文注解：
    - 功能：实现 `_launchctl_status` 对应的处理逻辑。
    - 角色：属于本模块中的内部辅助逻辑；私有函数通常服务同文件主流程，公共函数通常作为跨模块入口或能力接口。
    - 调用关系：建议结合本文件的模块说明、调用方以及同名相关辅助函数一起阅读。
    """
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
    """
    中文注解：
    - 功能：实现 `build_process_registry` 对应的处理逻辑。
    - 角色：属于本模块中的对外可见逻辑；私有函数通常服务同文件主流程，公共函数通常作为跨模块入口或能力接口。
    - 调用关系：建议结合本文件的模块说明、调用方以及同名相关辅助函数一起阅读。
    """
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


def _load_task_state(task_id: str) -> Dict[str, Any]:
    """
    中文注解：
    - 功能：实现 `_load_task_state` 对应的处理逻辑。
    - 角色：属于本模块中的内部辅助逻辑；私有函数通常服务同文件主流程，公共函数通常作为跨模块入口或能力接口。
    - 调用关系：建议结合本文件的模块说明、调用方以及同名相关辅助函数一起阅读。
    """
    return _read_json(AUTONOMY_TASKS_ROOT / task_id / "state.json", {})


def _load_task_contract(task_id: str) -> Dict[str, Any]:
    """
    中文注解：
    - 功能：实现 `_load_task_contract` 对应的处理逻辑。
    - 角色：属于本模块中的内部辅助逻辑；私有函数通常服务同文件主流程，公共函数通常作为跨模块入口或能力接口。
    - 调用关系：建议结合本文件的模块说明、调用方以及同名相关辅助函数一起阅读。
    """
    return _read_json(AUTONOMY_TASKS_ROOT / task_id / "contract.json", {})


def _conversation_links_for_task(task_id: str, canonical_task_id: str) -> List[Dict[str, Any]]:
    """
    中文注解：
    - 功能：实现 `_conversation_links_for_task` 对应的处理逻辑。
    - 角色：属于本模块中的内部辅助逻辑；私有函数通常服务同文件主流程，公共函数通常作为跨模块入口或能力接口。
    - 调用关系：建议结合本文件的模块说明、调用方以及同名相关辅助函数一起阅读。
    """
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


def _normalized_blocked_runtime_state(state: Dict[str, Any]) -> Dict[str, Any]:
    metadata = (state.get("metadata", {}) or {}) if isinstance(state, dict) else {}
    blocked = dict(metadata.get("blocked_runtime_state", {}) or {})
    if blocked and str(blocked.get("category", "")).strip():
        return blocked
    if str(state.get("status", "")).strip() != "blocked":
        return blocked
    inferred = classify_blocked_runtime_state(
        next_action=str(state.get("next_action", "")).strip(),
        blockers=[str(item).strip() for item in (state.get("blockers", []) or []) if str(item).strip()],
        governance_attention={},
    )
    if not str(inferred.get("attention_reason", "")).strip():
        inferred["attention_reason"] = str(state.get("next_action", "")).strip() or "blocked_without_runtime_metadata"
    return inferred


def _doctor_priority_for_entry(entry: Dict[str, Any]) -> Dict[str, Any]:
    blocked = (entry.get("blocked_runtime_state", {}) or {}) if isinstance(entry, dict) else {}
    category = str(blocked.get("category", "")).strip() or "unknown"
    reason = str(entry.get("reason", "")).strip()
    status = str(entry.get("status", "")).strip()
    idle_seconds = float(entry.get("idle_seconds", 0) or 0)
    base_scores = {
        "project_crawler_remediation": 100,
        "approval_or_contract": 95,
        "authorized_session": 90,
        "human_checkpoint": 88,
        "runtime_or_contract_fix": 82,
        "runtime_failure": 80,
        "targeted_fix": 72,
        "necessity_proof": 66,
        "relay_attach": 60,
        "session_binding": 42,
        "unknown": 50,
    }
    score = int(base_scores.get(category, 50))
    if reason == "terminal_failure_requires_takeover":
        score = max(score, 110)
    elif reason == "latest_user_goal_mismatch_with_bound_task":
        score = max(score, 105)
    elif status == "failed":
        score = max(score, 108)
    elif status == "blocked" and category in {"project_crawler_remediation", "approval_or_contract"}:
        score += 6
    if idle_seconds >= 3600:
        score += 8
    elif idle_seconds >= 900:
        score += 4
    bucket = "low"
    if score >= 95:
        bucket = "critical"
    elif score >= 80:
        bucket = "high"
    elif score >= 60:
        bucket = "medium"
    priority_reason = category
    if category == "unknown" and reason:
        if reason == "latest_user_goal_mismatch_with_bound_task":
            priority_reason = "goal_mismatch"
        elif reason == "terminal_failure_requires_takeover":
            priority_reason = "terminal_failure"
        else:
            priority_reason = reason
    return {
        "priority_score": score,
        "priority_bucket": bucket,
        "priority_reason": priority_reason or "unknown",
    }


def build_task_registry(*, stale_after_seconds: int = 300, escalation_after_seconds: int = 900) -> Dict[str, Any]:
    """
    中文注解：
    - 功能：实现 `build_task_registry` 对应的处理逻辑。
    - 角色：属于本模块中的对外可见逻辑；私有函数通常服务同文件主流程，公共函数通常作为跨模块入口或能力接口。
    - 调用关系：建议结合本文件的模块说明、调用方以及同名相关辅助函数一起阅读。
    """
    tasks: List[Dict[str, Any]] = []
    waiting: List[Dict[str, Any]] = []
    doctor_queue: List[Dict[str, Any]] = []
    alerts: List[Dict[str, Any]] = []
    seen_canonical: set[str] = set()

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
            blocked_runtime_state = _normalized_blocked_runtime_state(state)
            entry = {
                "task_id": task_id,
                "canonical_task_id": canonical_task_id,
                "lineage_root_task_id": canonical.get("lineage_root_task_id", task_id),
                "goal": contract.get("user_goal", ""),
                "status": state.get("status", "unknown"),
                "current_stage": state.get("current_stage", ""),
                "next_action": state.get("next_action", ""),
                "blocked_runtime_state": blocked_runtime_state,
                "last_progress_at": state.get("last_progress_at", ""),
                "last_update_at": state.get("last_update_at", ""),
                "progress_state": evidence.get("progress_state", "unknown"),
                "needs_intervention": bool(evidence.get("needs_intervention")),
                "idle_seconds": evidence.get("idle_seconds", 0),
                "active_execution": state.get("metadata", {}).get("active_execution", {}) or {},
                "waiting_external": state.get("metadata", {}).get("waiting_external", {}) or {},
                "run_liveness": evidence.get("run_liveness", {}),
                "goal_conformance": evidence.get("goal_conformance", {}),
                "conversation_links": links,
                "canonical": canonical,
            }
            tasks.append(entry)
            if canonical_task_id == task_id and canonical_task_id not in seen_canonical:
                seen_canonical.add(canonical_task_id)
            if entry["waiting_external"]:
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
            if entry["needs_intervention"]:
                doctor_entry = {
                    "task_id": task_id,
                    "canonical_task_id": canonical_task_id,
                    "reason": evidence.get("reason", "unknown"),
                    "progress_state": entry["progress_state"],
                    "status": entry["status"],
                    "current_stage": entry["current_stage"],
                    "next_action": entry["next_action"],
                    "blocked_runtime_state": entry.get("blocked_runtime_state", {}) or {},
                    "idle_seconds": entry["idle_seconds"],
                    "goal_conformance": entry.get("goal_conformance", {}),
                }
                doctor_entry.update(_doctor_priority_for_entry(doctor_entry))
                doctor_queue.append(doctor_entry)
                if entry["idle_seconds"] >= escalation_after_seconds:
                    alerts.append({**doctor_entry, "severity": "high", "escalated": True})

    doctor_queue.sort(
        key=lambda item: (
            -int(item.get("priority_score", 0) or 0),
            -float(item.get("idle_seconds", 0) or 0),
            str(item.get("task_id", "")),
        )
    )
    alerts.sort(
        key=lambda item: (
            -int(item.get("priority_score", 0) or 0),
            -float(item.get("idle_seconds", 0) or 0),
            str(item.get("task_id", "")),
        )
    )

    task_registry = {
        "generated_at": _utc_now_iso(),
        "items": tasks,
        "canonical_active_tasks": sorted(seen_canonical),
    }
    waiting_registry = {"generated_at": task_registry["generated_at"], "items": waiting}
    doctor_queue_registry = {"generated_at": task_registry["generated_at"], "items": doctor_queue}
    alerts_registry = {"generated_at": task_registry["generated_at"], "items": alerts}
    _write_json(TASK_REGISTRY_PATH, task_registry)
    _write_json(WAITING_REGISTRY_PATH, waiting_registry)
    _write_json(DOCTOR_QUEUE_PATH, doctor_queue_registry)
    _write_json(ALERTS_PATH, alerts_registry)
    return {
        "task_registry": task_registry,
        "waiting_registry": waiting_registry,
        "doctor_queue": doctor_queue_registry,
        "alerts": alerts_registry,
    }


def build_crawler_remediation_queue(crawler_capability_profile: Dict[str, Any]) -> Dict[str, Any]:
    """
    中文注解：
    - 功能：把 crawler capability profile 里的优先修复建议整理成 control plane 可消费的项目级待办队列。
    - 设计意图：让系统不只知道“哪里弱”，还知道“下一步应该先修什么”，供医生、监督器和后续调度链共享。
    """
    items: List[Dict[str, Any]] = []
    for index, action in enumerate(crawler_capability_profile.get("priority_actions", []) or [], start=1):
        items.append(
            {
                "id": f"crawler-remediation-{index}",
                "priority": action.get("priority", "medium"),
                "action": action.get("action", ""),
                "site": action.get("site", ""),
                "reason": action.get("reason", ""),
                "status": "pending",
            }
        )
    queue = {
        "generated_at": _utc_now_iso(),
        "items": items,
    }
    _write_json(CRAWLER_REMEDIATION_QUEUE_PATH, queue)
    return queue


def _load_crawler_remediation_execution() -> Dict[str, Any]:
    return _read_json(CRAWLER_REMEDIATION_EXECUTION_PATH, {"items": []}) or {"items": []}


def _load_crawler_remediation_scheduler_state() -> Dict[str, Any]:
    return _read_json(CRAWLER_REMEDIATION_SCHEDULER_STATE_PATH, {}) or {}


def _load_seller_bulk_scheduler_state() -> Dict[str, Any]:
    return _read_json(SELLER_BULK_SCHEDULER_STATE_PATH, {}) or {}


def _load_cross_market_arbitrage_scheduler_state() -> Dict[str, Any]:
    return _read_json(CROSS_MARKET_ARBITRAGE_SCHEDULER_STATE_PATH, {}) or {}


def _blocked_category_counts(task_items: List[Dict[str, Any]]) -> Dict[str, int]:
    counts: Dict[str, int] = {}
    for item in task_items:
        if item.get("status") != "blocked":
            continue
        category = str(((item.get("blocked_runtime_state", {}) or {}).get("category", ""))).strip() or "unknown"
        counts[category] = counts.get(category, 0) + 1
    return dict(sorted(counts.items(), key=lambda kv: (-kv[1], kv[0])))


def _load_doctor_last_run() -> Dict[str, Any]:
    return _read_json(DOCTOR_LAST_RUN_PATH, {}) or {}


def _parse_iso(value: str) -> datetime | None:
    raw = str(value or "").strip()
    if not raw:
        return None
    try:
        return datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        return None


def _project_result_feedback_summary(
    memory_writeback_overview: Dict[str, Any],
    crawler_remediation_execution: Dict[str, Any],
    seller_bulk_scheduler_state: Dict[str, Any],
) -> Dict[str, Any]:
    now = datetime.now(timezone.utc)
    recent_items = memory_writeback_overview.get("recent_items", []) or []
    tracked = {
        "crawler_remediation_cycle": {
            "task_id": "project-crawler-remediation-cycle",
            "kind": "project_runtime_loop",
        },
        "seller_bulk_cycle": {
            "task_id": "project-neosgo-seller-bulk",
            "kind": "project_runtime_loop",
        },
    }
    for item in recent_items:
        task_id = str(item.get("task_id", "")).strip()
        last_entry = item.get("last_entry", {}) or {}
        source = str(last_entry.get("source", "")).strip()
        if source not in tracked:
            continue
        at = _parse_iso(last_entry.get("at"))
        age_seconds = int((now - at).total_seconds()) if at else None
        tracked[source].update(
            {
                "seen": True,
                "at": last_entry.get("at", ""),
                "age_seconds": age_seconds,
                "attention_required": bool(last_entry.get("attention_required")),
                "memory_reasons": list(last_entry.get("memory_reasons", []) or []),
                "task_id": task_id or tracked[source]["task_id"],
            }
        )
    remediation_items = crawler_remediation_execution.get("items", []) or []
    tracked["crawler_remediation_cycle"]["active_execution_total"] = sum(
        1
        for item in remediation_items
        if str(((item.get("task_state", {}) or {}).get("status", ""))).strip().lower() in {"running", "planning", "recovering", "blocked"}
    )
    tracked["seller_bulk_cycle"]["last_mode"] = str(seller_bulk_scheduler_state.get("last_mode", "")).strip()
    tracked["seller_bulk_cycle"]["last_batch_bias"] = str(seller_bulk_scheduler_state.get("last_batch_bias", "")).strip()
    tracked["seller_bulk_cycle"]["last_skip_reason"] = str(seller_bulk_scheduler_state.get("last_skip_reason", "")).strip()

    active_total = sum(1 for item in tracked.values() if item.get("seen"))
    recent_total = sum(1 for item in tracked.values() if item.get("seen") and (item.get("age_seconds") is None or item.get("age_seconds", 10**9) <= 6 * 3600))
    attention_total = sum(1 for item in tracked.values() if item.get("attention_required"))
    status = "thin"
    if recent_total >= 2:
        status = "strong"
    elif recent_total == 1:
        status = "partial"
    if attention_total > 0 and status == "strong":
        status = "watch"
    return {
        "status": status,
        "active_total": active_total,
        "recent_total": recent_total,
        "attention_total": attention_total,
        "loops": tracked,
    }


def _score_project_result_feedback(feedback: Dict[str, Any]) -> int:
    status = str(feedback.get("status", "")).strip().lower()
    base = {
        "strong": 100,
        "watch": 75,
        "partial": 55,
        "thin": 30,
    }.get(status, 40)
    recent_total = int(feedback.get("recent_total", 0) or 0)
    attention_total = int(feedback.get("attention_total", 0) or 0)
    score = base + min(10, recent_total * 3) - min(20, attention_total * 10)
    return max(0, min(100, score))


def _update_project_result_feedback_history(feedback: Dict[str, Any]) -> Dict[str, Any]:
    history = _read_json(PROJECT_RESULT_FEEDBACK_HISTORY_PATH, {"items": []}) or {"items": []}
    items = list(history.get("items", []) or [])
    current = {
        "at": _utc_now_iso(),
        "status": str(feedback.get("status", "")).strip() or "unknown",
        "score": _score_project_result_feedback(feedback),
        "recent_total": int(feedback.get("recent_total", 0) or 0),
        "attention_total": int(feedback.get("attention_total", 0) or 0),
    }
    items.append(current)
    items = items[-24:]
    history["items"] = items
    history["updated_at"] = current["at"]
    trend = "stable"
    delta = 0
    if len(items) >= 2:
        delta = int(items[-1].get("score", 0) or 0) - int(items[-2].get("score", 0) or 0)
        if delta >= 8:
            trend = "improving"
        elif delta <= -8:
            trend = "degrading"
    history["trend"] = {
        "direction": trend,
        "delta": delta,
        "latest_score": current["score"],
        "previous_score": int(items[-2].get("score", 0) or 0) if len(items) >= 2 else current["score"],
    }
    _write_json(PROJECT_RESULT_FEEDBACK_HISTORY_PATH, history)
    return history


def build_control_plane(*, stale_after_seconds: int = 300, escalation_after_seconds: int = 900) -> Dict[str, Any]:
    """
    中文注解：
    - 功能：实现 `build_control_plane` 对应的处理逻辑。
    - 角色：属于本模块中的对外可见逻辑；私有函数通常服务同文件主流程，公共函数通常作为跨模块入口或能力接口。
    - 调用关系：建议结合本文件的模块说明、调用方以及同名相关辅助函数一起阅读。
    """
    process_registry = build_process_registry()
    crawler_capability_profile = build_crawler_capability_profile()
    memory_writeback_overview = summarize_project_memory_writebacks()
    crawler_remediation_queue = build_crawler_remediation_queue(crawler_capability_profile)
    crawler_remediation_plan = build_crawler_remediation_plan()
    crawler_remediation_execution = _load_crawler_remediation_execution()
    crawler_remediation_scheduler_state = _load_crawler_remediation_scheduler_state()
    seller_bulk_scheduler_state = _load_seller_bulk_scheduler_state()
    cross_market_arbitrage_scheduler_state = _load_cross_market_arbitrage_scheduler_state()
    doctor_last_run = _load_doctor_last_run()
    project_result_feedback = _project_result_feedback_summary(
        memory_writeback_overview,
        crawler_remediation_execution,
        seller_bulk_scheduler_state,
    )
    project_result_feedback_history = _update_project_result_feedback_history(project_result_feedback)
    task_views = build_task_registry(
        stale_after_seconds=stale_after_seconds,
        escalation_after_seconds=escalation_after_seconds,
    )
    task_items = task_views["task_registry"].get("items", []) or []
    blocked_category_counts = _blocked_category_counts(task_items)
    top_blocked_category = next(iter(blocked_category_counts), "")
    doctor_cycle_stats = (doctor_last_run.get("doctor_cycle_stats", {}) or {}) if isinstance(doctor_last_run, dict) else {}
    doctor_strategy = (doctor_last_run.get("doctor_strategy", {}) or {}) if isinstance(doctor_last_run, dict) else {}
    processed_total = int(doctor_cycle_stats.get("processed_total", 0) or 0)
    skipped_total = int(doctor_cycle_stats.get("skipped_total", 0) or 0)
    attempted_total = processed_total + skipped_total
    recovery_efficiency_ratio = round((processed_total / attempted_total), 4) if attempted_total > 0 else 0.0
    snapshot = {
        "generated_at": _utc_now_iso(),
        "process_registry_path": process_registry.get("path"),
        "crawler_capability_profile_path": str(CRAWLER_CAPABILITY_PROFILE_PATH),
        "crawler_remediation_queue_path": str(CRAWLER_REMEDIATION_QUEUE_PATH),
        "crawler_remediation_plan_path": str(CRAWLER_REMEDIATION_PLAN_PATH),
        "crawler_remediation_execution_path": str(CRAWLER_REMEDIATION_EXECUTION_PATH),
        "task_registry_path": str(TASK_REGISTRY_PATH),
        "waiting_registry_path": str(WAITING_REGISTRY_PATH),
        "doctor_queue_path": str(DOCTOR_QUEUE_PATH),
        "alerts_path": str(ALERTS_PATH),
        "summary": {
            "processes_running": sum(1 for item in process_registry.get("items", []) if item.get("state") == "running"),
            "processes_total": len(process_registry.get("items", [])),
            "crawler_sites_total": crawler_capability_profile.get("summary", {}).get("sites_total", 0),
            "crawler_sites_ready": crawler_capability_profile.get("summary", {}).get("sites_production_ready", 0),
            "crawler_width_score": crawler_capability_profile.get("summary", {}).get("width_score", 0),
            "crawler_breadth_score": crawler_capability_profile.get("summary", {}).get("breadth_score", 0),
            "crawler_depth_score": crawler_capability_profile.get("summary", {}).get("depth_score", 0),
            "crawler_stability_score": crawler_capability_profile.get("summary", {}).get("stability_score", 0),
            "crawler_trend_direction": crawler_capability_profile.get("trend", {}).get("direction", "unknown"),
            "crawler_feedback_coverage_status": crawler_capability_profile.get("feedback", {}).get("coverage_status", "unknown"),
            "crawler_remediation_total": len(crawler_remediation_queue.get("items", [])),
            "crawler_remediation_plan_total": len(crawler_remediation_plan.get("items", [])),
            "crawler_remediation_execution_total": len(crawler_remediation_execution.get("items", [])),
            "crawler_remediation_last_mode": crawler_remediation_scheduler_state.get("last_mode", ""),
            "seller_bulk_last_mode": seller_bulk_scheduler_state.get("last_mode", ""),
            "cross_market_arbitrage_last_mode": cross_market_arbitrage_scheduler_state.get("last_mode", ""),
            "memory_writeback_tasks_total": memory_writeback_overview.get("tasks_total", 0),
            "project_result_feedback_status": project_result_feedback.get("status", "unknown"),
            "project_result_feedback_recent_total": project_result_feedback.get("recent_total", 0),
            "project_result_feedback_attention_total": project_result_feedback.get("attention_total", 0),
            "project_result_feedback_trend": ((project_result_feedback_history.get("trend", {}) or {}).get("direction", "unknown")),
            "project_result_feedback_score": ((project_result_feedback_history.get("trend", {}) or {}).get("latest_score", 0)),
            "doctor_priority_focus": str(doctor_strategy.get("priority_focus", "")).strip() or "unknown",
            "doctor_repair_mode": str(doctor_strategy.get("repair_mode", "")).strip() or "unknown",
            "doctor_processed_total": processed_total,
            "doctor_skipped_total": skipped_total,
            "recovery_efficiency_ratio": recovery_efficiency_ratio,
            "tasks_total": len(task_items),
            "blocked_total": sum(1 for item in task_items if item.get("status") == "blocked"),
            "blocked_project_crawler_remediation_total": blocked_category_counts.get("project_crawler_remediation", 0),
            "blocked_approval_or_contract_total": blocked_category_counts.get("approval_or_contract", 0),
            "blocked_authorized_session_total": blocked_category_counts.get("authorized_session", 0),
            "blocked_human_checkpoint_total": blocked_category_counts.get("human_checkpoint", 0),
            "blocked_targeted_fix_total": blocked_category_counts.get("targeted_fix", 0),
            "blocked_categories": blocked_category_counts,
            "top_blocked_category": top_blocked_category,
            "waiting_total": len(task_views["waiting_registry"].get("items", [])),
            "doctor_queue_total": len(task_views["doctor_queue"].get("items", [])),
            "alerts_total": len(task_views["alerts"].get("items", [])),
        },
    }
    project_scheduler_policy = build_project_scheduler_policy(
        crawler_profile=crawler_capability_profile,
        remediation_execution=crawler_remediation_execution,
        system_summary=snapshot.get("summary", {}) or {},
        project_result_feedback=project_result_feedback,
    )
    snapshot["project_scheduler_policy"] = project_scheduler_policy
    snapshot["scheduler_states"] = {
        "crawler_remediation": crawler_remediation_scheduler_state,
        "seller_bulk": seller_bulk_scheduler_state,
        "cross_market_arbitrage": cross_market_arbitrage_scheduler_state,
    }
    snapshot["path"] = _write_json(SYSTEM_SNAPSHOT_PATH, snapshot)
    return {
        "process_registry": process_registry,
        "crawler_capability_profile": crawler_capability_profile,
        "memory_writeback_overview": memory_writeback_overview,
        "project_result_feedback": project_result_feedback,
        "project_result_feedback_history": project_result_feedback_history,
        "crawler_remediation_queue": crawler_remediation_queue,
        "crawler_remediation_plan": crawler_remediation_plan,
        "crawler_remediation_execution": crawler_remediation_execution,
        "crawler_remediation_scheduler_state": crawler_remediation_scheduler_state,
        "seller_bulk_scheduler_state": seller_bulk_scheduler_state,
        "cross_market_arbitrage_scheduler_state": cross_market_arbitrage_scheduler_state,
        "doctor_last_run": doctor_last_run,
        "project_scheduler_policy": project_scheduler_policy,
        **task_views,
        "system_snapshot": snapshot,
    }


def main() -> int:
    """
    中文注解：
    - 功能：实现 `main` 对应的处理逻辑。
    - 角色：属于本模块中的对外可见逻辑；私有函数通常服务同文件主流程，公共函数通常作为跨模块入口或能力接口。
    - 调用关系：建议结合本文件的模块说明、调用方以及同名相关辅助函数一起阅读。
    """
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
