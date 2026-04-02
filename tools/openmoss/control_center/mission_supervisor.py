#!/usr/bin/env python3

"""
中文说明：
- 文件路径：`tools/openmoss/control_center/mission_supervisor.py`
- 文件作用：负责任务监督、空转识别与推进纠偏。
- 顶层函数：_utc_now_iso、_write_json、_apply_repair、supervise_task、run_mission_supervisor。
- 顶层类：无顶层类。
- 阅读建议：先看模块说明，再按函数/类 docstring 顺着主流程理解调用关系。
"""
from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

from control_plane_builder import build_control_plane
from paths import CONTROL_CENTER_RUNTIME_ROOT
from progress_evidence import build_progress_evidence
from response_policy_engine import build_supervisor_status_text
from task_receipt_engine import emit_route_receipt
from task_status_snapshot import build_task_status_snapshot

AUTONOMY_DIR = Path("/Users/mac_claw/.openclaw/workspace/tools/openmoss/autonomy")
if str(AUTONOMY_DIR) not in sys.path:
    sys.path.insert(0, str(AUTONOMY_DIR))

from manager import LINKS_ROOT, TASKS_ROOT, load_state, log_event, save_state


SUPERVISOR_ROOT = CONTROL_CENTER_RUNTIME_ROOT / "supervisor"


def _utc_now_iso() -> str:
    """
    中文注解：
    - 功能：实现 `_utc_now_iso` 对应的处理逻辑。
    - 角色：属于本模块中的内部辅助逻辑；私有函数通常服务同文件主流程，公共函数通常作为跨模块入口或能力接口。
    - 调用关系：建议结合本文件的模块说明、调用方以及同名相关辅助函数一起阅读。
    """
    return datetime.now(timezone.utc).isoformat()


def _write_json(path: Path, payload: Dict[str, Any]) -> None:
    """
    中文注解：
    - 功能：实现 `_write_json` 对应的处理逻辑。
    - 角色：属于本模块中的内部辅助逻辑；私有函数通常服务同文件主流程，公共函数通常作为跨模块入口或能力接口。
    - 调用关系：建议结合本文件的模块说明、调用方以及同名相关辅助函数一起阅读。
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _apply_repair(task_id: str, evidence: Dict[str, Any]) -> Dict[str, Any]:
    """
    中文注解：
    - 功能：实现 `_apply_repair` 对应的处理逻辑。
    - 角色：属于本模块中的内部辅助逻辑；私有函数通常服务同文件主流程，公共函数通常作为跨模块入口或能力接口。
    - 调用关系：建议结合本文件的模块说明、调用方以及同名相关辅助函数一起阅读。
    """
    state = load_state(task_id)
    reason = str(evidence.get("reason", "unknown"))
    repaired = False
    new_next_action = str(state.next_action)
    if evidence.get("progress_state") in {"idle_without_execution", "stalled_waiting_external", "stalled_verification"}:
        state.status = "planning"
        state.blockers = []
        state.metadata.pop("active_execution", None)
        state.metadata.pop("last_dispatched_marker", None)
        state.metadata.pop("last_dispatch_at", None)
        if state.current_stage:
            state.next_action = f"start_stage:{state.current_stage}"
        else:
            state.next_action = "initialize"
        state.last_update_at = _utc_now_iso()
        save_state(state)
        log_event(task_id, "mission_supervisor_restarted_execution", reason=reason)
        repaired = True
        new_next_action = state.next_action
    return {
        "task_id": task_id,
        "repaired": repaired,
        "reason": reason,
        "next_action": new_next_action,
    }


def supervise_task(task_id: str, *, stale_after_seconds: int = 300, escalation_after_seconds: int = 900) -> Dict[str, Any]:
    """
    中文注解：
    - 功能：实现 `supervise_task` 对应的处理逻辑。
    - 角色：属于本模块中的对外可见逻辑；私有函数通常服务同文件主流程，公共函数通常作为跨模块入口或能力接口。
    - 调用关系：建议结合本文件的模块说明、调用方以及同名相关辅助函数一起阅读。
    """
    evidence = build_progress_evidence(task_id, stale_after_seconds=stale_after_seconds)
    repair = _apply_repair(task_id, evidence) if evidence.get("needs_intervention") else {"task_id": task_id, "repaired": False, "reason": "healthy"}
    report: Dict[str, Any] = {"evidence": evidence, "repair": repair}
    if evidence.get("needs_intervention") and float(evidence.get("idle_seconds", 0)) >= float(escalation_after_seconds):
        for link_path in LINKS_ROOT.glob("*.json"):
            try:
                payload = json.loads(link_path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue
            if payload.get("task_id") != task_id:
                continue
            snapshot = build_task_status_snapshot(task_id)
            snapshot["authoritative_summary"] = build_supervisor_status_text(task_id, evidence, repair, snapshot)
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
            log_event(task_id, "mission_supervisor_escalated_to_user", evidence=evidence, repair=repair)
            break
    return report


def run_mission_supervisor(*, stale_after_seconds: int = 300, escalation_after_seconds: int = 900) -> Dict[str, Any]:
    """
    中文注解：
    - 功能：实现 `run_mission_supervisor` 对应的处理逻辑。
    - 角色：属于本模块中的对外可见逻辑；私有函数通常服务同文件主流程，公共函数通常作为跨模块入口或能力接口。
    - 调用关系：建议结合本文件的模块说明、调用方以及同名相关辅助函数一起阅读。
    """
    reports: List[Dict[str, Any]] = []
    if not TASKS_ROOT.exists():
        return {"checked_at": _utc_now_iso(), "reports": reports}
    for task_root in sorted(TASKS_ROOT.iterdir()):
        if not task_root.is_dir():
            continue
        task_id = task_root.name
        reports.append(
            supervise_task(
                task_id,
                stale_after_seconds=stale_after_seconds,
                escalation_after_seconds=escalation_after_seconds,
            )
        )
    control_plane = build_control_plane(
        stale_after_seconds=stale_after_seconds,
        escalation_after_seconds=escalation_after_seconds,
    )
    result = {
        "checked_at": _utc_now_iso(),
        "crawler_feedback": (control_plane.get("crawler_capability_profile", {}) or {}).get("feedback", {}) or {},
        "crawler_remediation_queue": (control_plane.get("crawler_remediation_queue", {}) or {}),
        "crawler_remediation_plan": (control_plane.get("crawler_remediation_plan", {}) or {}),
        "project_repair_value": control_plane.get("project_repair_value", {}) or {},
        "project_repair_recommendations": (control_plane.get("project_repair_recommendations", []) or [])[:6],
        "blocked_summary": {
            "total": ((control_plane.get("system_snapshot", {}) or {}).get("summary", {}) or {}).get("blocked_total", 0),
            "project_crawler_remediation": ((control_plane.get("system_snapshot", {}) or {}).get("summary", {}) or {}).get("blocked_project_crawler_remediation_total", 0),
            "approval_or_contract": ((control_plane.get("system_snapshot", {}) or {}).get("summary", {}) or {}).get("blocked_approval_or_contract_total", 0),
        },
        "reports": reports,
    }
    _write_json(SUPERVISOR_ROOT / "last_run.json", result)
    return result
