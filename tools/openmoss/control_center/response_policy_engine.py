#!/usr/bin/env python3

from __future__ import annotations

from typing import Any, Dict


def build_route_receipt_text(route: Dict[str, Any]) -> str:
    mode = str(route.get("mode", "instant_reply_only"))
    task_id = str(route.get("task_id", "")).strip()
    if mode == "authoritative_task_status":
        snapshot = route.get("authoritative_task_status", {}) or {}
        return str(snapshot.get("authoritative_summary", "")).strip() or f"当前任务状态已刷新，任务 ID: {task_id or 'unknown'}。"
    if mode in {"create_new_root_task", "create_or_attach"}:
        return f"已识别为新任务，任务 ID: {task_id}。我会先进入 understand 阶段，梳理目标、约束、交付物和执行条件，然后持续推进。"
    if mode in {"create_successor_task", "branch_from_active_task", "append_to_active_successor_task"}:
        return f"已识别为后续任务，任务 ID: {task_id}。我会沿当前任务链继续执行；如果遇到真实阻塞，会直接告诉你卡点而不是静默等待。"
    if mode == "append_to_existing_task":
        return f"已把这条新指令挂到当前任务 {task_id}，接下来会继续按现有任务链推进。"
    if mode == "doctor_diagnostic":
        snapshot = route.get("authoritative_task_status", {}) or {}
        return str(snapshot.get("authoritative_summary", "")).strip() or f"系统医生已接管任务 {task_id} 并开始诊断。"
    return f"已收到任务型指令。当前路由模式: {mode}。任务 ID: {task_id or '未创建'}。"


def build_supervisor_status_text(task_id: str, evidence: Dict[str, Any], repair: Dict[str, Any]) -> str:
    reason = str(evidence.get("reason", "unknown"))
    status = str(evidence.get("status", "unknown"))
    stage = str(evidence.get("current_stage", ""))
    next_action = str(evidence.get("next_action", ""))
    if repair.get("repaired"):
        return (
            f"系统医生检测到任务 {task_id} 处于 {status} / {stage or 'none'}，原因是 {reason}。"
            f" 已自动修复并重新拉回执行，下一步是 {repair.get('next_action', next_action or 'unknown')}。"
        )
    return (
        f"系统医生检测到任务 {task_id} 处于 {status} / {stage or 'none'}，原因是 {reason}。"
        f" 当前还没有自动修复成功，下一步卡在 {next_action or 'unknown'}。"
    )
