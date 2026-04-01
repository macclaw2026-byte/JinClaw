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
from memory_writeback_runtime import summarize_project_memory_writebacks
from project_scheduler_policy import build_project_scheduler_policy
from paths import (
    ALERTS_PATH,
    CROSS_MARKET_ARBITRAGE_SCHEDULER_STATE_PATH,
    CRAWLER_CAPABILITY_PROFILE_PATH,
    CRAWLER_REMEDIATION_EXECUTION_PATH,
    CRAWLER_REMEDIATION_PLAN_PATH,
    CRAWLER_REMEDIATION_QUEUE_PATH,
    CRAWLER_REMEDIATION_SCHEDULER_STATE_PATH,
    DOCTOR_QUEUE_PATH,
    PROCESS_REGISTRY_PATH,
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
                    "idle_seconds": entry["idle_seconds"],
                    "goal_conformance": entry.get("goal_conformance", {}),
                }
                doctor_queue.append(doctor_entry)
                if entry["idle_seconds"] >= escalation_after_seconds:
                    alerts.append({**doctor_entry, "severity": "high", "escalated": True})

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
    task_views = build_task_registry(
        stale_after_seconds=stale_after_seconds,
        escalation_after_seconds=escalation_after_seconds,
    )
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
            "tasks_total": len(task_views["task_registry"].get("items", [])),
            "waiting_total": len(task_views["waiting_registry"].get("items", [])),
            "doctor_queue_total": len(task_views["doctor_queue"].get("items", [])),
            "alerts_total": len(task_views["alerts"].get("items", [])),
        },
    }
    project_scheduler_policy = build_project_scheduler_policy(
        crawler_profile=crawler_capability_profile,
        remediation_execution=crawler_remediation_execution,
        system_summary=snapshot.get("summary", {}) or {},
    )
    snapshot["path"] = _write_json(SYSTEM_SNAPSHOT_PATH, snapshot)
    return {
        "process_registry": process_registry,
        "crawler_capability_profile": crawler_capability_profile,
        "memory_writeback_overview": memory_writeback_overview,
        "crawler_remediation_queue": crawler_remediation_queue,
        "crawler_remediation_plan": crawler_remediation_plan,
        "crawler_remediation_execution": crawler_remediation_execution,
        "crawler_remediation_scheduler_state": crawler_remediation_scheduler_state,
        "seller_bulk_scheduler_state": seller_bulk_scheduler_state,
        "cross_market_arbitrage_scheduler_state": cross_market_arbitrage_scheduler_state,
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
