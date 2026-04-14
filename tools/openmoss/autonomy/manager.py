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
- 文件路径：`tools/openmoss/autonomy/manager.py`
- 文件作用：自治 runtime 的基础状态库；负责 contract/state/link/event 的读写，以及常见生命周期动作的原子更新。
- 顶层函数：_plan_bucket、utc_now_iso、build_args、task_dir、read_json、write_json、append_jsonl、ingress_path、link_path、contract_path、state_path、events_path、checkpoints_dir、_refresh_task_summary、load_contract、load_state、save_contract、save_state、log_event、log_ingress、write_link、read_link、infer_link_session_key、find_link_by_task_id、parse_stage_args、parse_stage_payloads、create_task_from_contract、create_task、status_task、list_tasks、run_once、recover_task、apply_recovery、complete_stage、complete_stage_internal、_set_nested_dict_value、advance_execute_subtask、fail_stage、verify_task、checkpoint_task、set_stage_verifier、set_stage_execution_policy、set_task_metadata、write_business_outcome、evolve_task、build_parser、main。
- 顶层类：无顶层类。
- 主流程定位：
  1. orchestrator 产出结构化 package 后，这里把它真正写成 contract/state。
  2. runtime / executor / doctor 在推进任务时，最终都会落回这里更新 state、event 和 link。
  3. learning、recovery、plan_history 也都从这里被触发，是任务生命周期的“持久化总线”。
"""
from __future__ import annotations

import argparse
import json
import os
import time
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

from checkpoint_reporter import render_checkpoint, write_checkpoint
from learning_engine import get_error_recurrence, note_error_occurrence, record_error, record_learning, update_task_summary
from recovery_engine import apply_recovery_action, propose_recovery
from task_contract import StageContract, TaskContract, merge_execution_policy
from task_state import StageState, TaskState
from verifier_registry import run_verifier

CONTROL_CENTER_DIR = Path("/Users/mac_claw/.openclaw/workspace/tools/openmoss/control_center")
if str(CONTROL_CENTER_DIR) not in sys.path:
    sys.path.insert(0, str(CONTROL_CENTER_DIR))

from plan_history import record_plan_outcome
from goal_sanitizer import sanitize_goal_text


def _plan_bucket(contract: TaskContract) -> tuple[list[str], str]:
    """
    中文注解：
    - 功能：实现 `_plan_bucket` 对应的处理逻辑。
    - 角色：属于本模块中的内部辅助逻辑；私有函数通常服务同文件主流程，公共函数通常作为跨模块入口或能力接口。
    - 调用关系：建议结合本文件的模块说明、调用方以及同名相关辅助函数一起阅读。
    """
    intent = contract.metadata.get("control_center", {}).get("intent", {})
    return [str(item) for item in intent.get("task_types", [])], str(intent.get("risk_level", ""))


RUNTIME_ROOT = Path("/Users/mac_claw/.openclaw/workspace/tools/openmoss/runtime/autonomy")
TASKS_ROOT = RUNTIME_ROOT / "tasks"
INGRESS_ROOT = RUNTIME_ROOT / "ingress"
LINKS_ROOT = RUNTIME_ROOT / "links"
BACKGROUND_AUTONOMY_PROVIDER = "autonomy-runtime"
BACKGROUND_AUTONOMY_SESSION_KEY = "agent:main:main"


def utc_now_iso() -> str:
    """
    中文注解：
    - 功能：实现 `utc_now_iso` 对应的处理逻辑。
    - 角色：属于本模块中的对外可见逻辑；私有函数通常服务同文件主流程，公共函数通常作为跨模块入口或能力接口。
    - 调用关系：建议结合本文件的模块说明、调用方以及同名相关辅助函数一起阅读。
    """
    return datetime.now(timezone.utc).isoformat()


def build_args(**kwargs):
    """
    中文注解：
    - 功能：实现 `build_args` 对应的处理逻辑。
    - 角色：属于本模块中的对外可见逻辑；私有函数通常服务同文件主流程，公共函数通常作为跨模块入口或能力接口。
    - 调用关系：建议结合本文件的模块说明、调用方以及同名相关辅助函数一起阅读。
    """
    return argparse.Namespace(**kwargs)


def task_dir(task_id: str) -> Path:
    """
    中文注解：
    - 功能：实现 `task_dir` 对应的处理逻辑。
    - 角色：属于本模块中的对外可见逻辑；私有函数通常服务同文件主流程，公共函数通常作为跨模块入口或能力接口。
    - 调用关系：建议结合本文件的模块说明、调用方以及同名相关辅助函数一起阅读。
    """
    return TASKS_ROOT / task_id


def read_json(path: Path, default):
    """
    中文注解：
    - 功能：实现 `read_json` 对应的处理逻辑。
    - 角色：属于本模块中的对外可见逻辑；私有函数通常服务同文件主流程，公共函数通常作为跨模块入口或能力接口。
    - 调用关系：建议结合本文件的模块说明、调用方以及同名相关辅助函数一起阅读。
    """
    if not path.exists():
        return default
    attempts = 3
    for attempt in range(attempts):
        try:
            with path.open("r", encoding="utf-8") as fh:
                return json.load(fh)
        except json.JSONDecodeError:
            if attempt >= attempts - 1:
                raise
            time.sleep(0.05)


def write_json(path: Path, payload) -> None:
    """
    中文注解：
    - 功能：实现 `write_json` 对应的处理逻辑。
    - 角色：属于本模块中的对外可见逻辑；私有函数通常服务同文件主流程，公共函数通常作为跨模块入口或能力接口。
    - 调用关系：建议结合本文件的模块说明、调用方以及同名相关辅助函数一起阅读。
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    # 使用唯一 tmp 文件，避免 doctor/runtime 并发写同一任务状态时互相覆盖临时文件名。
    temp_path = path.with_name(f"{path.name}.{os.getpid()}.{uuid.uuid4().hex}.tmp")
    try:
        with temp_path.open("w", encoding="utf-8") as fh:
            json.dump(payload, fh, ensure_ascii=False, indent=2)
        temp_path.replace(path)
    finally:
        if temp_path.exists():
            temp_path.unlink()


def append_jsonl(path: Path, payload: Dict) -> None:
    """
    中文注解：
    - 功能：实现 `append_jsonl` 对应的处理逻辑。
    - 角色：属于本模块中的对外可见逻辑；私有函数通常服务同文件主流程，公共函数通常作为跨模块入口或能力接口。
    - 调用关系：建议结合本文件的模块说明、调用方以及同名相关辅助函数一起阅读。
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(payload, ensure_ascii=False) + "\n")


def ingress_path(source: str) -> Path:
    """
    中文注解：
    - 功能：实现 `ingress_path` 对应的处理逻辑。
    - 角色：属于本模块中的对外可见逻辑；私有函数通常服务同文件主流程，公共函数通常作为跨模块入口或能力接口。
    - 调用关系：建议结合本文件的模块说明、调用方以及同名相关辅助函数一起阅读。
    """
    return INGRESS_ROOT / f"{source}.jsonl"


def link_path(provider: str, conversation_id: str) -> Path:
    """
    中文注解：
    - 功能：实现 `link_path` 对应的处理逻辑。
    - 角色：属于本模块中的对外可见逻辑；私有函数通常服务同文件主流程，公共函数通常作为跨模块入口或能力接口。
    - 调用关系：建议结合本文件的模块说明、调用方以及同名相关辅助函数一起阅读。
    """
    safe_provider = provider.replace("/", "-")
    safe_conversation = conversation_id.replace("/", "-")
    return LINKS_ROOT / f"{safe_provider}__{safe_conversation}.json"


def contract_path(task_id: str) -> Path:
    """
    中文注解：
    - 功能：实现 `contract_path` 对应的处理逻辑。
    - 角色：属于本模块中的对外可见逻辑；私有函数通常服务同文件主流程，公共函数通常作为跨模块入口或能力接口。
    - 调用关系：建议结合本文件的模块说明、调用方以及同名相关辅助函数一起阅读。
    """
    return task_dir(task_id) / "contract.json"


def state_path(task_id: str) -> Path:
    """
    中文注解：
    - 功能：实现 `state_path` 对应的处理逻辑。
    - 角色：属于本模块中的对外可见逻辑；私有函数通常服务同文件主流程，公共函数通常作为跨模块入口或能力接口。
    - 调用关系：建议结合本文件的模块说明、调用方以及同名相关辅助函数一起阅读。
    """
    return task_dir(task_id) / "state.json"


def events_path(task_id: str) -> Path:
    """
    中文注解：
    - 功能：实现 `events_path` 对应的处理逻辑。
    - 角色：属于本模块中的对外可见逻辑；私有函数通常服务同文件主流程，公共函数通常作为跨模块入口或能力接口。
    - 调用关系：建议结合本文件的模块说明、调用方以及同名相关辅助函数一起阅读。
    """
    return task_dir(task_id) / "events.jsonl"


def checkpoints_dir(task_id: str) -> Path:
    """
    中文注解：
    - 功能：实现 `checkpoints_dir` 对应的处理逻辑。
    - 角色：属于本模块中的对外可见逻辑；私有函数通常服务同文件主流程，公共函数通常作为跨模块入口或能力接口。
    - 调用关系：建议结合本文件的模块说明、调用方以及同名相关辅助函数一起阅读。
    """
    return task_dir(task_id) / "checkpoints"


def _refresh_task_summary(task_id: str, *, state: TaskState | None = None, extra: Dict | None = None) -> Dict:
    """
    中文注解：
    - 功能：实现 `_refresh_task_summary` 对应的处理逻辑。
    - 角色：属于本模块中的内部辅助逻辑；私有函数通常服务同文件主流程，公共函数通常作为跨模块入口或能力接口。
    - 调用关系：建议结合本文件的模块说明、调用方以及同名相关辅助函数一起阅读。
    """
    current = state or load_state(task_id)
    completed_stages = [name for name in current.stage_order if current.stages.get(name) and current.stages[name].status == "completed"]
    payload = {
        "status": current.status,
        "current_stage": current.current_stage,
        "learning_backlog": current.learning_backlog,
        "completed_stages": completed_stages,
        "last_completed_stage": completed_stages[-1] if completed_stages else "",
    }
    if extra:
        payload.update(extra)
    return update_task_summary(task_id, payload)


def _task_milestones(contract: TaskContract) -> List[Dict[str, Any]]:
    """
    中文注解：
    - 功能：读取 contract 中由 control center 推导出的 milestones 定义。
    - 设计意图：让 manager / verifier / doctor 都能围绕同一份 milestone 结构工作，而不是各自再猜一遍。
    """
    control_center = contract.metadata.get("control_center", {}) or {}
    milestones = control_center.get("task_milestones", []) or []
    return [dict(item) for item in milestones if isinstance(item, dict)]


def _record_stage_artifact(
    task_id: str,
    *,
    contract: TaskContract | None = None,
    state: TaskState | None = None,
    stage_name: str,
    summary: str = "",
    evidence_ref: str = "",
    extra: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    """
    中文注解：
    - 功能：把阶段完成时的关键产物写入 `state.metadata.stage_artifacts`。
    - 设计意图：让复杂任务后续能基于阶段产物做 verify、doctor 巡检和 release gate。
    """
    current_contract = contract or load_contract(task_id)
    current_state = state or load_state(task_id)
    stage = current_state.stages.get(stage_name)
    stage_contract = next((item for item in current_contract.stages if item.name == stage_name), None)
    artifacts = current_state.metadata.get("stage_artifacts", {}) or {}
    existing = dict(artifacts.get(stage_name, {}) or {})
    evidence_refs = list(existing.get("evidence_refs", []) or [])
    if stage:
        evidence_refs.extend([str(item) for item in stage.evidence_refs if str(item).strip()])
        verification_status = stage.verification_status
    else:
        verification_status = str(existing.get("verification_status", "not-run"))
    if evidence_ref and str(evidence_ref).strip():
        evidence_refs.append(str(evidence_ref).strip())
    payload = {
        "stage": stage_name,
        "written_at": utc_now_iso(),
        "summary": summary or (stage.summary if stage else str(existing.get("summary", ""))),
        "expected_output": stage_contract.expected_output if stage_contract else str(existing.get("expected_output", "")),
        "acceptance_check": stage_contract.acceptance_check if stage_contract else str(existing.get("acceptance_check", "")),
        "execution_policy": dict(stage_contract.execution_policy or {}) if stage_contract else dict(existing.get("execution_policy", {}) or {}),
        "verification_status": verification_status,
        "evidence_refs": sorted(dict.fromkeys([item for item in evidence_refs if item])),
        "completed_subtasks": list(stage.completed_subtasks) if stage else list(existing.get("completed_subtasks", []) or []),
        "artifact_status": "ready",
    }
    summary_text = str(payload.get("summary", "")).strip()
    if stage_name == "understand":
        payload.setdefault("mission_brief", summary_text)
        payload.setdefault("scope_constraints", list(current_contract.hard_constraints or []))
        payload.setdefault("success_definition", str(current_contract.done_definition or ""))
    elif stage_name == "plan":
        execute_titles = [
            str(item.get("title", "")).strip()
            for item in _task_milestones(current_contract)
            if str(item.get("stage", "")).strip() == "execute" and str(item.get("title", "")).strip()
        ]
        payload.setdefault("execution_plan", summary_text)
        payload.setdefault("module_breakdown", list(stage.completed_subtasks) if stage and stage.completed_subtasks else execute_titles)
        payload.setdefault("test_strategy", "verify buildability, stage acceptance, and release readiness before final delivery")
    elif stage_name == "execute":
        payload.setdefault("delivery_evidence", summary_text or "implementation evidence recorded")
        payload.setdefault("implementation_delta", summary_text or "implementation delta recorded")
        payload.setdefault("test_signal", "verification_pending" if verification_status == "not-run" else verification_status)
    elif stage_name == "learn":
        postmortem = current_state.metadata.get("postmortem", {}) or {}
        payload.setdefault("postmortem", str(postmortem.get("path", "")).strip())
        payload.setdefault("reusable_rule", "do not close a complex task before staged artifacts, verification, and postmortem are all present")
        payload.setdefault("followup_risks", list(current_state.learning_backlog or []))
    if extra:
        payload.update(extra)
    artifacts[stage_name] = payload
    current_state.metadata["stage_artifacts"] = artifacts
    return payload


def _initial_milestone_progress(contract: TaskContract) -> Dict[str, Dict[str, Any]]:
    """
    中文注解：
    - 功能：给新任务生成第一版 milestone 进度表。
    - 说明：每个 milestone 会带上 stage、title、required 和当前 status，后续 state.metadata.milestone_progress 会持续更新它。
    """
    payload: Dict[str, Dict[str, Any]] = {}
    for item in _task_milestones(contract):
        milestone_id = str(item.get("id", "")).strip()
        if not milestone_id:
            continue
        payload[milestone_id] = {
            "id": milestone_id,
            "title": str(item.get("title", milestone_id)),
            "stage": str(item.get("stage", "")).strip(),
            "required": bool(item.get("required", True)),
            "completion_mode": str(item.get("completion_mode", "stage_completion")).strip(),
            "status": "pending",
            "completed_at": "",
            "summary": "",
        }
    return payload


def _milestone_stats_from_state(contract: TaskContract, state: TaskState) -> Dict[str, Any]:
    milestones = _task_milestones(contract)
    progress = state.metadata.get("milestone_progress", {}) or {}
    required = [item for item in milestones if bool(item.get("required", True))]
    completed_required = [
        item for item in required if (progress.get(str(item.get("id", "")), {}) or {}).get("status") == "completed"
    ]
    return {
        "total": len(milestones),
        "required_total": len(required),
        "required_completed": len(completed_required),
        "all_required_completed": len(required) == len(completed_required) if required else True,
    }


def _sync_milestone_progress(task_id: str, *, contract: TaskContract | None = None, state: TaskState | None = None) -> Dict[str, Any]:
    """
    中文注解：
    - 功能：把 stage 生命周期变化同步到 milestone_progress。
    - 规则：
      - 非 execute 的阶段里程碑，随对应 stage completed 自动完成。
      - execute 的 stepwise milestones 由显式 `advance_execute_milestone` 推进。
    """
    current_contract = contract or load_contract(task_id)
    current_state = state or load_state(task_id)
    progress = current_state.metadata.get("milestone_progress", {}) or _initial_milestone_progress(current_contract)
    now = utc_now_iso()
    for item in _task_milestones(current_contract):
        milestone_id = str(item.get("id", "")).strip()
        stage_name = str(item.get("stage", "")).strip()
        completion_mode = str(item.get("completion_mode", "stage_completion")).strip()
        entry = progress.setdefault(
            milestone_id,
            {
                "id": milestone_id,
                "title": str(item.get("title", milestone_id)),
                "stage": stage_name,
                "required": bool(item.get("required", True)),
                "completion_mode": completion_mode,
                "status": "pending",
                "completed_at": "",
                "summary": "",
            },
        )
        stage_state = current_state.stages.get(stage_name)
        if completion_mode == "stage_completion" and stage_state and stage_state.status == "completed":
            if entry.get("status") != "completed":
                entry["status"] = "completed"
                entry["completed_at"] = now
                entry["summary"] = stage_state.summary or str(item.get("title", milestone_id))
    current_state.metadata["milestone_progress"] = progress
    current_state.metadata["milestone_stats"] = _milestone_stats_from_state(current_contract, current_state)
    return progress


def advance_execute_milestone(task_id: str, *, summary: str = "") -> Dict[str, Any]:
    """
    中文注解：
    - 功能：在 execute 阶段每取得一次有效外部执行结果后，推进下一个待完成的 execute milestone。
    - 设计意图：让多步骤任务在“每一轮 execute 成功”后继续自动滚动到下一个 deliverable，而不是一轮成功后就把整段 execute 当成完成。
    """
    contract = load_contract(task_id)
    state = load_state(task_id)
    _sync_milestone_progress(task_id, contract=contract, state=state)
    progress = state.metadata.get("milestone_progress", {}) or {}
    execute_milestones = [
        item
        for item in _task_milestones(contract)
        if str(item.get("stage", "")).strip() == "execute" and str(item.get("completion_mode", "")).strip() == "stepwise_progress"
    ]
    if not execute_milestones:
        stats = _milestone_stats_from_state(contract, state)
        state.metadata["milestone_stats"] = stats
        save_state(state)
        return {"task_id": task_id, "advanced": False, "stage_complete": True, "milestone_stats": stats}
    target = None
    for item in execute_milestones:
        milestone_id = str(item.get("id", "")).strip()
        entry = progress.get(milestone_id, {})
        if entry.get("status") != "completed":
            target = item
            break
    if not target:
        stats = _milestone_stats_from_state(contract, state)
        state.metadata["milestone_stats"] = stats
        save_state(state)
        return {"task_id": task_id, "advanced": False, "stage_complete": True, "milestone_stats": stats}
    milestone_id = str(target.get("id", "")).strip()
    progress[milestone_id]["status"] = "completed"
    progress[milestone_id]["completed_at"] = utc_now_iso()
    progress[milestone_id]["summary"] = summary or str(target.get("title", milestone_id))
    stats = _milestone_stats_from_state(contract, state)
    state.metadata["milestone_progress"] = progress
    state.metadata["milestone_stats"] = stats
    state.last_progress_at = utc_now_iso()
    state.last_update_at = utc_now_iso()
    save_state(state)
    log_event(task_id, "execute_milestone_advanced", milestone_id=milestone_id, title=str(target.get("title", "")), milestone_stats=stats)
    remaining = [item for item in execute_milestones if progress.get(str(item.get("id", "")), {}).get("status") != "completed"]
    return {
        "task_id": task_id,
        "advanced": True,
        "milestone_id": milestone_id,
        "title": str(target.get("title", "")),
        "remaining_execute_milestones": len(remaining),
        "stage_complete": len(remaining) == 0,
        "milestone_stats": stats,
    }


def complete_execute_milestones(task_id: str, *, summary: str = "") -> Dict[str, Any]:
    """
    中文注解：
    - 功能：把 execute 阶段的所有 stepwise milestones 一次性收口。
    - 使用场景：本地执行器已经完整跑完整个 execute 目标，需要在结束前把 milestone 状态与真实结果同步。
    """
    contract = load_contract(task_id)
    state = load_state(task_id)
    _sync_milestone_progress(task_id, contract=contract, state=state)
    progress = state.metadata.get("milestone_progress", {}) or {}
    now = utc_now_iso()
    completed_ids: List[str] = []
    for item in _task_milestones(contract):
        if str(item.get("stage", "")).strip() != "execute":
            continue
        if str(item.get("completion_mode", "")).strip() != "stepwise_progress":
            continue
        milestone_id = str(item.get("id", "")).strip()
        if not milestone_id:
            continue
        entry = progress.setdefault(milestone_id, {})
        if entry.get("status") == "completed":
            continue
        entry["id"] = milestone_id
        entry["title"] = str(item.get("title", milestone_id))
        entry["stage"] = "execute"
        entry["required"] = bool(item.get("required", True))
        entry["completion_mode"] = "stepwise_progress"
        entry["status"] = "completed"
        entry["completed_at"] = now
        entry["summary"] = summary or str(item.get("title", milestone_id))
        completed_ids.append(milestone_id)
    state.metadata["milestone_progress"] = progress
    state.metadata["milestone_stats"] = _milestone_stats_from_state(contract, state)
    state.last_progress_at = now
    state.last_update_at = now
    save_state(state)
    if completed_ids:
        log_event(task_id, "execute_milestones_completed_in_bulk", milestone_ids=completed_ids, summary=summary)
    return {
        "task_id": task_id,
        "completed_ids": completed_ids,
        "milestone_stats": state.metadata.get("milestone_stats", {}),
    }


def load_contract(task_id: str) -> TaskContract:
    """
    中文注解：
    - 功能：实现 `load_contract` 对应的处理逻辑。
    - 角色：属于本模块中的对外可见逻辑；私有函数通常服务同文件主流程，公共函数通常作为跨模块入口或能力接口。
    - 调用关系：建议结合本文件的模块说明、调用方以及同名相关辅助函数一起阅读。
    """
    payload = read_json(contract_path(task_id), {})
    if not isinstance(payload, dict):
        raise ValueError(f"invalid contract payload type for task {task_id}: {type(payload).__name__}")
    missing = [key for key in ("task_id", "user_goal", "done_definition") if not payload.get(key)]
    if missing:
        raise ValueError(f"invalid contract for task {task_id}: missing {', '.join(missing)}")
    return TaskContract.from_dict(payload)


def load_state(task_id: str) -> TaskState:
    """
    中文注解：
    - 功能：实现 `load_state` 对应的处理逻辑。
    - 角色：属于本模块中的对外可见逻辑；私有函数通常服务同文件主流程，公共函数通常作为跨模块入口或能力接口。
    - 调用关系：建议结合本文件的模块说明、调用方以及同名相关辅助函数一起阅读。
    """
    return TaskState.from_dict(read_json(state_path(task_id), {}))


def save_contract(contract: TaskContract) -> None:
    """
    中文注解：
    - 功能：实现 `save_contract` 对应的处理逻辑。
    - 角色：属于本模块中的对外可见逻辑；私有函数通常服务同文件主流程，公共函数通常作为跨模块入口或能力接口。
    - 调用关系：建议结合本文件的模块说明、调用方以及同名相关辅助函数一起阅读。
    """
    write_json(contract_path(contract.task_id), contract.to_dict())


def save_state(state: TaskState) -> None:
    """
    中文注解：
    - 功能：实现 `save_state` 对应的处理逻辑。
    - 角色：属于本模块中的对外可见逻辑；私有函数通常服务同文件主流程，公共函数通常作为跨模块入口或能力接口。
    - 调用关系：建议结合本文件的模块说明、调用方以及同名相关辅助函数一起阅读。
    """
    write_json(state_path(state.task_id), state.to_dict())


def log_event(task_id: str, event_type: str, **extra) -> None:
    """
    中文注解：
    - 功能：实现 `log_event` 对应的处理逻辑。
    - 角色：属于本模块中的对外可见逻辑；私有函数通常服务同文件主流程，公共函数通常作为跨模块入口或能力接口。
    - 调用关系：建议结合本文件的模块说明、调用方以及同名相关辅助函数一起阅读。
    """
    payload = {"at": utc_now_iso(), "type": event_type}
    payload.update(extra)
    append_jsonl(events_path(task_id), payload)


def log_ingress(source: str, payload: Dict) -> None:
    """
    中文注解：
    - 功能：实现 `log_ingress` 对应的处理逻辑。
    - 角色：属于本模块中的对外可见逻辑；私有函数通常服务同文件主流程，公共函数通常作为跨模块入口或能力接口。
    - 调用关系：建议结合本文件的模块说明、调用方以及同名相关辅助函数一起阅读。
    """
    data = {"at": utc_now_iso(), "source": source}
    data.update(payload)
    append_jsonl(ingress_path(source), data)


def write_link(provider: str, conversation_id: str, payload: Dict) -> str:
    """
    中文注解：
    - 功能：实现 `write_link` 对应的处理逻辑。
    - 角色：属于本模块中的对外可见逻辑；私有函数通常服务同文件主流程，公共函数通常作为跨模块入口或能力接口。
    - 调用关系：建议结合本文件的模块说明、调用方以及同名相关辅助函数一起阅读。
    """
    path = link_path(provider, conversation_id)
    write_json(path, payload)
    return str(path)


def read_link(provider: str, conversation_id: str) -> Dict:
    """
    中文注解：
    - 功能：实现 `read_link` 对应的处理逻辑。
    - 角色：属于本模块中的对外可见逻辑；私有函数通常服务同文件主流程，公共函数通常作为跨模块入口或能力接口。
    - 调用关系：建议结合本文件的模块说明、调用方以及同名相关辅助函数一起阅读。
    """
    return read_json(link_path(provider, conversation_id), {})


def infer_link_session_key(payload: Dict) -> str:
    """
    中文注解：
    - 功能：实现 `infer_link_session_key` 对应的处理逻辑。
    - 角色：属于本模块中的对外可见逻辑；私有函数通常服务同文件主流程，公共函数通常作为跨模块入口或能力接口。
    - 调用关系：建议结合本文件的模块说明、调用方以及同名相关辅助函数一起阅读。
    """
    session_key = str(payload.get("session_key", "")).strip()
    if session_key:
        return session_key
    provider = str(payload.get("provider", "")).strip().lower()
    conversation_id = str(payload.get("conversation_id", "")).strip()
    conversation_type = str(payload.get("conversation_type", "")).strip().lower() or "direct"
    if provider == "openclaw-main" and conversation_id == "main":
        return "agent:main:main"
    if provider == "telegram" and conversation_id:
        if conversation_id.startswith("-") or conversation_type == "group":
            return f"agent:main:telegram:group:{conversation_id}"
        return f"agent:main:telegram:direct:{conversation_id}"
    return ""


def find_link_by_task_id(task_id: str) -> Dict:
    """
    中文注解：
    - 功能：实现 `find_link_by_task_id` 对应的处理逻辑。
    - 角色：属于本模块中的对外可见逻辑；私有函数通常服务同文件主流程，公共函数通常作为跨模块入口或能力接口。
    - 调用关系：建议结合本文件的模块说明、调用方以及同名相关辅助函数一起阅读。
    """
    if not LINKS_ROOT.exists():
        return {}
    for path in sorted(LINKS_ROOT.glob("*.json")):
        payload = read_json(path, {})
        if payload.get("task_id") == task_id:
            inferred_session_key = infer_link_session_key(payload)
            if inferred_session_key and not str(payload.get("session_key", "")).strip():
                payload["session_key"] = inferred_session_key
                write_json(path, payload)
            payload["_path"] = str(path)
            return payload
    return {}


def ensure_autonomy_root_mission_link(task_id: str) -> Dict:
    """
    中文注解：
    - 功能：为没有显式会话绑定的 root mission 补一条后台自治 link。
    - 设计意图：
      1. root mission 是持续运行任务，不应该因为没有手动绑定聊天窗口而永久卡住；
      2. 这里绑定的是主会话派生出来的 autonomy session，不会污染主聊天焦点；
      3. 只有明确标记为 root mission 的任务才允许走这个兜底。
    """
    existing = find_link_by_task_id(task_id)
    if existing:
        return existing
    contract = load_contract(task_id)
    metadata = contract.metadata or {}
    control_center = metadata.get("control_center", {}) or {}
    intent = control_center.get("intent", {}) or {}
    source = str(intent.get("source", "")).strip()
    if not metadata.get("root_mission") and "root_mission" not in source:
        return {}
    provider = BACKGROUND_AUTONOMY_PROVIDER
    conversation_id = f"task-{task_id}"
    payload = {
        "provider": provider,
        "conversation_id": conversation_id,
        "conversation_type": "service",
        "task_id": task_id,
        "lineage_root_task_id": str(metadata.get("root_task_id") or task_id).strip() or task_id,
        "goal": contract.user_goal,
        "session_key": BACKGROUND_AUTONOMY_SESSION_KEY,
        "updated_at": utc_now_iso(),
        "link_kind": "root_mission_autonomy",
    }
    path = write_link(provider, conversation_id, payload)
    payload["_path"] = path
    return payload


def parse_stage_args(stage_args: List[str]) -> List[StageContract]:
    """
    中文注解：
    - 功能：实现 `parse_stage_args` 对应的处理逻辑。
    - 角色：属于本模块中的对外可见逻辑；私有函数通常服务同文件主流程，公共函数通常作为跨模块入口或能力接口。
    - 调用关系：建议结合本文件的模块说明、调用方以及同名相关辅助函数一起阅读。
    """
    stages: List[StageContract] = []
    for raw in stage_args:
        name, sep, goal = raw.partition("|")
        if not sep:
            raise ValueError(f"invalid stage format: {raw}")
        stages.append(StageContract(name=name.strip(), goal=goal.strip()))
    return stages


def parse_stage_payloads(stage_payloads: List[Dict]) -> List[StageContract]:
    """
    中文注解：
    - 功能：实现 `parse_stage_payloads` 对应的处理逻辑。
    - 角色：属于本模块中的对外可见逻辑；私有函数通常服务同文件主流程，公共函数通常作为跨模块入口或能力接口。
    - 调用关系：建议结合本文件的模块说明、调用方以及同名相关辅助函数一起阅读。
    """
    stages: List[StageContract] = []
    for payload in stage_payloads:
        stages.append(StageContract(**payload))
    return stages


def create_task_from_contract(contract: TaskContract) -> Dict[str, Dict]:
    """
    中文注解：
    - 功能：根据 TaskContract 生成任务的第一版 state，并把 contract/state 一起落盘。
    - 结果：
      - 写出 contract.json
      - 写出 state.json
      - 初始化 summary 和 task_created 事件
    - 调用关系：brain_router / task_ingress 最终都会走到这里，所以这是一个任务真正“出生”的地方。
    """
    contract.user_goal = sanitize_goal_text(str(contract.user_goal or ""))
    # state 是从 contract 反推出来的第一张状态卡：
    # 默认从第一阶段开始，next_action 也会被设置成 start_stage:<first_stage>。
    stages = contract.stages
    state = TaskState(
        task_id=contract.task_id,
        status="planning",
        current_stage=stages[0].name if stages else "",
        next_action=f"start_stage:{stages[0].name}" if stages else "noop",
        last_update_at=utc_now_iso(),
        stage_order=[stage.name for stage in stages],
        stages={stage.name: StageState(name=stage.name, updated_at=utc_now_iso()) for stage in stages},
        metadata={
            "contract_metadata": contract.metadata,
            "milestone_progress": _initial_milestone_progress(contract),
        },
    )
    _sync_milestone_progress(contract.task_id, contract=contract, state=state)
    save_contract(contract)
    save_state(state)
    _refresh_task_summary(contract.task_id, state=state, extra={"goal": contract.user_goal, "done_definition": contract.done_definition})
    log_event(contract.task_id, "task_created", goal=contract.user_goal, done_definition=contract.done_definition, metadata=contract.metadata)
    return {"contract": contract.to_dict(), "state": state.to_dict()}


def create_task(args: argparse.Namespace) -> int:
    """
    中文注解：
    - 功能：实现 `create_task` 对应的处理逻辑。
    - 角色：属于本模块中的对外可见逻辑；私有函数通常服务同文件主流程，公共函数通常作为跨模块入口或能力接口。
    - 调用关系：建议结合本文件的模块说明、调用方以及同名相关辅助函数一起阅读。
    """
    args.goal = sanitize_goal_text(str(getattr(args, "goal", "") or ""))
    if getattr(args, "stage_json", ""):
        stages = parse_stage_payloads(json.loads(args.stage_json))
    else:
        stages = parse_stage_args(args.stage)
    allowed_tools = args.allowed_tool or []
    for stage in stages:
        stage.execution_policy = merge_execution_policy(
            args.goal,
            stage.name,
            stage.execution_policy,
            allowed_tools=allowed_tools,
        )
    contract = TaskContract(
        task_id=args.task_id,
        user_goal=args.goal,
        done_definition=args.done_definition,
        hard_constraints=args.hard_constraint or [],
        soft_preferences=args.soft_preference or [],
        allowed_tools=allowed_tools,
        forbidden_actions=args.forbidden_action or [],
        stages=stages,
        metadata={
            "created_at": utc_now_iso(),
            **json.loads(getattr(args, "metadata_json", "") or "{}"),
        },
    )
    payload = create_task_from_contract(contract)
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


def status_task(args: argparse.Namespace) -> int:
    """
    中文注解：
    - 功能：实现 `status_task` 对应的处理逻辑。
    - 角色：属于本模块中的对外可见逻辑；私有函数通常服务同文件主流程，公共函数通常作为跨模块入口或能力接口。
    - 调用关系：建议结合本文件的模块说明、调用方以及同名相关辅助函数一起阅读。
    """
    contract = load_contract(args.task_id)
    state = load_state(args.task_id)
    payload = {
        "contract": contract.to_dict(),
        "state": state.to_dict(),
        "checkpoint_preview": render_checkpoint(state),
    }
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


def list_tasks(args: argparse.Namespace) -> int:
    """
    中文注解：
    - 功能：实现 `list_tasks` 对应的处理逻辑。
    - 角色：属于本模块中的对外可见逻辑；私有函数通常服务同文件主流程，公共函数通常作为跨模块入口或能力接口。
    - 调用关系：建议结合本文件的模块说明、调用方以及同名相关辅助函数一起阅读。
    """
    payload = []
    if not TASKS_ROOT.exists():
        print("[]")
        return 0
    for task_root in sorted(TASKS_ROOT.iterdir()):
        if not task_root.is_dir():
            continue
        state = load_state(task_root.name)
        payload.append(
            {
                "task_id": task_root.name,
                "status": state.status,
                "current_stage": state.current_stage,
                "next_action": state.next_action,
                "last_update_at": state.last_update_at,
            }
        )
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


def run_once(args: argparse.Namespace) -> int:
    """
    中文注解：
    - 功能：把任务推进到“当前阶段开始运行”的起点。
    - 这一步不会真正 dispatch 外部 agent，而是先做状态切换：
      - planning -> running
      - current_stage -> 某个待执行阶段
      - next_action -> execute_stage:<stage>
    - 调用关系：runtime_service 在需要开启一个阶段时会调用这里。
    """
    contract = load_contract(args.task_id)
    state = load_state(args.task_id)
    if state.status in {"completed", "failed"}:
        print(json.dumps({"status": state.status, "message": "task already terminal"}, ensure_ascii=False, indent=2))
        return 0

    stage_name = state.current_stage or state.first_pending_stage()
    if not stage_name:
        state.status = "verifying"
        state.next_action = "verify_done_definition"
        state.last_update_at = utc_now_iso()
        save_state(state)
        log_event(args.task_id, "entered_verifying")
        print(json.dumps({"status": "verifying", "next_action": state.next_action}, ensure_ascii=False, indent=2))
        return 0

    stage = state.stages[stage_name]
    stage.status = "running"
    stage.attempts += 1
    stage.started_at = stage.started_at or utc_now_iso()
    stage.updated_at = utc_now_iso()
    state.status = "running"
    state.current_stage = stage_name
    state.attempts += 1
    state.next_action = f"execute_stage:{stage_name}"
    state.last_progress_at = utc_now_iso()
    state.last_update_at = utc_now_iso()
    save_state(state)
    log_event(args.task_id, "stage_started", stage=stage_name, attempts=stage.attempts)
    print(
        json.dumps(
            {
                "status": "running",
                "current_stage": stage_name,
                "stage_goal": next((s.goal for s in contract.stages if s.name == stage_name), ""),
                "next_action": state.next_action,
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


def recover_task(args: argparse.Namespace) -> int:
    """
    中文注解：
    - 功能：实现 `recover_task` 对应的处理逻辑。
    - 角色：属于本模块中的对外可见逻辑；私有函数通常服务同文件主流程，公共函数通常作为跨模块入口或能力接口。
    - 调用关系：建议结合本文件的模块说明、调用方以及同名相关辅助函数一起阅读。
    """
    state = load_state(args.task_id)
    stage_name = args.stage or state.current_stage
    if not stage_name or stage_name not in state.stages:
        raise SystemExit("unknown stage")
    stage = state.stages[stage_name]
    stage.status = "pending"
    stage.blocker = ""
    stage.summary = args.summary
    stage.updated_at = utc_now_iso()
    state.status = "planning"
    state.current_stage = stage_name
    state.blockers = []
    state.next_action = f"start_stage:{stage_name}"
    state.last_update_at = utc_now_iso()
    save_state(state)
    log_event(args.task_id, "stage_recovered", stage=stage_name, summary=args.summary)
    record_learning(args.task_id, f"Recovery applied for {stage_name}: {args.summary}")
    _refresh_task_summary(args.task_id, state=state, extra={"last_recovery": {"stage": stage_name, "summary": args.summary}})
    print(json.dumps({"status": state.status, "next_action": state.next_action}, ensure_ascii=False, indent=2))
    return 0


def apply_recovery(args: argparse.Namespace) -> int:
    """
    中文注解：
    - 功能：实现 `apply_recovery` 对应的处理逻辑。
    - 角色：属于本模块中的对外可见逻辑；私有函数通常服务同文件主流程，公共函数通常作为跨模块入口或能力接口。
    - 调用关系：建议结合本文件的模块说明、调用方以及同名相关辅助函数一起阅读。
    """
    state = load_state(args.task_id)
    stage_name = args.stage or state.current_stage
    if not stage_name:
        for name in state.stage_order:
            stage = state.stages.get(name)
            if stage and stage.status == "failed":
                stage_name = name
                break
    if not stage_name or stage_name not in state.stages:
        raise SystemExit("unknown stage")
    stage = state.stages[stage_name]
    action = args.action or state.next_action
    result = apply_recovery_action(action, stage.blocker or " ".join(state.blockers), args.task_id)
    stage.updated_at = utc_now_iso()
    state.last_update_at = utc_now_iso()
    if result.get("ok") == "true":
        stage.status = "pending"
        stage.blocker = ""
        state.status = "planning"
        state.blockers = []
        state.next_action = f"start_stage:{stage_name}"
        record_learning(args.task_id, f"Auto-recovery succeeded for {stage_name}: {action}")
    else:
        blocker = str(result.get("blocker") or stage.blocker or " ".join(state.blockers) or result.get("status", "recovery_blocked"))
        stage.status = "failed"
        stage.blocker = blocker
        state.status = "blocked"
        state.blockers = [blocker]
        state.next_action = str(result.get("next_action") or action)
        record_error(args.task_id, f"Auto-recovery failed for {stage_name}: {action} -> {result.get('status')}")
    save_state(state)
    _refresh_task_summary(
        args.task_id,
        state=state,
        extra={"last_recovery": {"stage": stage_name, "action": action, "result": result}},
    )
    log_event(args.task_id, "recovery_applied", stage=stage_name, action=action, result=result)
    print(json.dumps({"task_id": args.task_id, "stage": stage_name, "action": action, "result": result, "status": state.status}, ensure_ascii=False, indent=2))
    return 0


def complete_stage(args: argparse.Namespace) -> int:
    """
    中文注解：
    - 功能：实现 `complete_stage` 对应的处理逻辑。
    - 角色：属于本模块中的对外可见逻辑；私有函数通常服务同文件主流程，公共函数通常作为跨模块入口或能力接口。
    - 调用关系：建议结合本文件的模块说明、调用方以及同名相关辅助函数一起阅读。
    """
    contract = load_contract(args.task_id)
    state = load_state(args.task_id)
    stage_name = args.stage or state.current_stage
    if not stage_name or stage_name not in state.stages:
        raise SystemExit("unknown stage")
    stage = state.stages[stage_name]
    stage.status = "completed"
    stage.summary = args.summary
    stage.completed_at = utc_now_iso()
    stage.updated_at = utc_now_iso()
    state.last_success_at = utc_now_iso()
    state.last_update_at = utc_now_iso()
    artifact = _record_stage_artifact(
        args.task_id,
        contract=contract,
        state=state,
        stage_name=stage_name,
        summary=args.summary,
    )
    next_stage = None
    for name in state.stage_order:
        if state.stages[name].status != "completed":
            next_stage = name
            break
    if next_stage is None:
        state.status = "verifying"
        state.current_stage = ""
        state.next_action = "verify_done_definition"
    else:
        state.status = "planning"
        state.current_stage = next_stage
        state.next_action = f"start_stage:{next_stage}"
    save_state(state)
    log_event(args.task_id, "stage_completed", stage=stage_name, summary=args.summary, artifact=artifact)
    record_learning(args.task_id, f"Stage {stage_name} completed: {args.summary}")
    _refresh_task_summary(args.task_id, state=state, extra={"last_completed_stage": stage_name})
    print(json.dumps({"status": state.status, "next_action": state.next_action}, ensure_ascii=False, indent=2))
    return 0


def complete_stage_internal(task_id: str, stage_name: str, summary: str, evidence_ref: str = "") -> Dict[str, str]:
    """
    中文注解：
    - 功能：实现 `complete_stage_internal` 对应的处理逻辑。
    - 角色：属于本模块中的对外可见逻辑；私有函数通常服务同文件主流程，公共函数通常作为跨模块入口或能力接口。
    - 调用关系：建议结合本文件的模块说明、调用方以及同名相关辅助函数一起阅读。
    """
    state = load_state(task_id)
    if stage_name not in state.stages:
        raise ValueError(f"unknown stage: {stage_name}")
    stage = state.stages[stage_name]
    stage.status = "completed"
    stage.summary = summary
    stage.completed_at = utc_now_iso()
    stage.updated_at = utc_now_iso()
    if evidence_ref:
        stage.evidence_refs.append(evidence_ref)
    state.last_success_at = utc_now_iso()
    state.last_update_at = utc_now_iso()
    contract = load_contract(task_id)
    artifact = _record_stage_artifact(
        task_id,
        contract=contract,
        state=state,
        stage_name=stage_name,
        summary=summary,
        evidence_ref=evidence_ref,
    )
    next_stage = None
    for name in state.stage_order:
        if state.stages[name].status != "completed":
            next_stage = name
            break
    if next_stage is None:
        state.status = "verifying"
        state.current_stage = ""
        state.next_action = "verify_done_definition"
    else:
        state.status = "planning"
        state.current_stage = next_stage
        state.next_action = f"start_stage:{next_stage}"
    save_state(state)
    log_event(task_id, "stage_completed", stage=stage_name, summary=summary, evidence_ref=evidence_ref, artifact=artifact)
    record_learning(task_id, f"Stage {stage_name} completed: {summary}")
    if stage_name == "execute":
        plan_id = str(contract.metadata.get("control_center", {}).get("selected_plan", {}).get("plan_id", ""))
        if plan_id:
            task_types, risk_level = _plan_bucket(contract)
            record_plan_outcome(plan_id, "success", task_types=task_types, risk_level=risk_level)
    _sync_milestone_progress(task_id, state=state)
    save_state(state)
    _refresh_task_summary(task_id, state=state, extra={"last_completed_stage": stage_name})
    return {"status": state.status, "next_action": state.next_action}


def _set_nested_dict_value(payload: Dict[str, Any], field: str, value: Any) -> None:
    """
    中文注解：
    - 功能：实现 `_set_nested_dict_value` 对应的处理逻辑。
    - 角色：属于本模块中的内部辅助逻辑；私有函数通常服务同文件主流程，公共函数通常作为跨模块入口或能力接口。
    - 调用关系：建议结合本文件的模块说明、调用方以及同名相关辅助函数一起阅读。
    """
    parts = [part for part in field.split(".") if part]
    if not parts:
        raise ValueError("field path is required")
    current = payload
    for part in parts[:-1]:
        next_value = current.get(part)
        if not isinstance(next_value, dict):
            next_value = {}
            current[part] = next_value
        current = next_value
    current[parts[-1]] = value


def _set_taskstate_field(state: TaskState, field: str, value: Any) -> None:
    parts = [part for part in str(field).split(".") if part]
    if not parts:
        return
    head = parts[0]
    if head == "metadata":
        _set_nested_dict_value(state.metadata, ".".join(parts[1:]), value)
        return
    if head == "stages" and len(parts) >= 3:
        stage = state.stages.get(parts[1])
        if not stage:
            return
        setattr(stage, parts[2], value)
        stage.updated_at = utc_now_iso()
        return
    if hasattr(state, head):
        setattr(state, head, value)


def apply_hook_effects(task_id: str, hook_event: Dict[str, Any] | None, *, source: str = "") -> Dict[str, Any]:
    """
    中文注解：
    - 功能：把 hook 总线产出的标准补丁统一落到 task state。
    - 支持：`state_patch`、`governance_patch`、`next_actions`、`warnings`。
    - 设计意图：避免 action_executor / runtime / doctor 各自手写一套 hook 结果翻译逻辑。
    """
    if not hook_event:
        return {"applied": False, "reason": "no_hook_event"}
    control_center_dir = Path("/Users/mac_claw/.openclaw/workspace/tools/openmoss/control_center")
    if str(control_center_dir) not in sys.path:
        sys.path.insert(0, str(control_center_dir))
    from event_bus import summarize_hook_effects
    from memory_writeback_runtime import record_memory_writeback

    summary = summarize_hook_effects(hook_event)
    if not any(
        [
            summary.get("state_patch"),
            summary.get("governance_patch"),
            summary.get("next_actions"),
            summary.get("warnings"),
            summary.get("errors"),
        ]
    ):
        return {"applied": False, "reason": "no_patch_content", "summary": summary}
    state = load_state(task_id)
    for field, value in (summary.get("state_patch", {}) or {}).items():
        _set_taskstate_field(state, str(field), value)
    if summary.get("governance_patch"):
        state.metadata.setdefault("governance_runtime", {})
        state.metadata["governance_runtime"].update(summary.get("governance_patch", {}) or {})
    if summary.get("warnings"):
        existing = [str(item) for item in state.metadata.get("hook_warnings", []) or [] if str(item).strip()]
        state.metadata["hook_warnings"] = sorted(set([*existing, *summary.get("warnings", [])]))
    if summary.get("errors"):
        existing = [str(item) for item in state.metadata.get("hook_errors", []) or [] if str(item).strip()]
        state.metadata["hook_errors"] = sorted(set([*existing, *summary.get("errors", [])]))
    if summary.get("next_actions"):
        state.metadata["hook_next_actions"] = list(summary.get("next_actions", []))
    if source:
        state.metadata.setdefault("last_hook_effects", {})
        state.metadata["last_hook_effects"][source] = summary
    writeback = record_memory_writeback(task_id, source=source or "hook_effects", summary=summary)
    state.metadata["memory_writeback"] = writeback
    state.last_update_at = utc_now_iso()
    save_state(state)
    log_event(task_id, "hook_effects_applied", source=source or "unknown", summary=summary)
    return {"applied": True, "summary": summary}


def advance_execute_subtask(task_id: str, subtask_id: str, summary: str = "") -> Dict[str, object]:
    """
    中文注解：
    - 功能：实现 `advance_execute_subtask` 对应的处理逻辑。
    - 角色：属于本模块中的对外可见逻辑；私有函数通常服务同文件主流程，公共函数通常作为跨模块入口或能力接口。
    - 调用关系：建议结合本文件的模块说明、调用方以及同名相关辅助函数一起阅读。
    """
    state = load_state(task_id)
    stage = state.stages.get("execute")
    if not stage:
        raise ValueError("execute stage not found")
    if subtask_id and subtask_id not in stage.completed_subtasks:
        stage.completed_subtasks.append(subtask_id)
    stage.subtask_cursor = len(stage.completed_subtasks)
    stage.updated_at = utc_now_iso()
    if summary:
        stage.summary = summary
    state.last_update_at = utc_now_iso()
    save_state(state)
    log_event(task_id, "execute_subtask_advanced", subtask_id=subtask_id, completed_subtasks=stage.completed_subtasks, subtask_cursor=stage.subtask_cursor)
    return {
        "task_id": task_id,
        "stage": "execute",
        "subtask_id": subtask_id,
        "completed_subtasks": stage.completed_subtasks,
        "subtask_cursor": stage.subtask_cursor,
    }


def fail_stage(args: argparse.Namespace) -> int:
    """
    中文注解：
    - 功能：实现 `fail_stage` 对应的处理逻辑。
    - 角色：属于本模块中的对外可见逻辑；私有函数通常服务同文件主流程，公共函数通常作为跨模块入口或能力接口。
    - 调用关系：建议结合本文件的模块说明、调用方以及同名相关辅助函数一起阅读。
    """
    state = load_state(args.task_id)
    stage_name = args.stage or state.current_stage
    if not stage_name or stage_name not in state.stages:
        raise SystemExit("unknown stage")
    stage = state.stages[stage_name]
    stage.status = "failed"
    stage.blocker = args.error
    stage.updated_at = utc_now_iso()
    state.status = "recovering"
    state.current_stage = stage_name
    state.blockers = [args.error]
    state.learning_backlog = list(dict.fromkeys([*state.learning_backlog, f"prevent_repeat:{stage_name}"]))
    state.last_update_at = utc_now_iso()
    recovery = propose_recovery(args.error, stage.attempts)
    state.next_action = recovery["action"]
    save_state(state)
    recurrence = note_error_occurrence(args.task_id, args.error)
    contract = load_contract(args.task_id)
    plan_id = str(contract.metadata.get("control_center", {}).get("selected_plan", {}).get("plan_id", ""))
    if plan_id:
        task_types, risk_level = _plan_bucket(contract)
        record_plan_outcome(plan_id, "failure", task_types=task_types, risk_level=risk_level)
    _refresh_task_summary(
        args.task_id,
        state=state,
        extra={
            "last_failure": {
                "stage": stage_name,
                "error": args.error,
                "recovery": recovery,
                "recurrence": recurrence,
            }
        },
    )
    log_event(args.task_id, "stage_failed", stage=stage_name, error=args.error, recovery=recovery, recurrence=recurrence)
    record_error(args.task_id, f"{stage_name}: {args.error}")
    print(json.dumps({"status": "recovering", "recovery": recovery, "recurrence": recurrence}, ensure_ascii=False, indent=2))
    return 0


def verify_task(args: argparse.Namespace) -> int:
    """
    中文注解：
    - 功能：运行 contract 中定义的结构化 verifier，并把结果折算回 task state。
    - 典型结果：
      - 全部通过 -> completed 或推进下一阶段
      - 任一失败 -> recovering + repair_verification_failure
    - 调用关系：runtime_service 在 verify 阶段和部分自动完成逻辑里都会调这里。
    """
    contract = load_contract(args.task_id)
    state = load_state(args.task_id)
    results = []
    all_ok = True
    verified_stages = []
    first_failed_stage = ""
    # verifier 是“任务真的完成了吗”的结构化证据链；
    # 它和聊天里的自然语言总结不同，主要供 runtime 和 doctor 做确定性判断。
    for stage_contract in contract.stages:
        if not stage_contract.verifier:
            continue
        result = run_verifier(stage_contract.verifier)
        results.append({"stage": stage_contract.name, "result": result})
        stage_state = state.stages[stage_contract.name]
        stage_state.verification_status = result["status"]
        stage_state.updated_at = utc_now_iso()
        if not result["ok"]:
            all_ok = False
            stage_state.status = "failed"
            stage_state.blocker = f"verification failed: {result['status']}"
            if not first_failed_stage:
                first_failed_stage = stage_contract.name
        else:
            verified_stages.append(stage_contract.name)
            if stage_state.status != "completed":
                stage_state.status = "completed"
                stage_state.summary = stage_state.summary or f"Verifier passed for {stage_contract.name}"
                stage_state.completed_at = utc_now_iso()
    crawler = contract.metadata.get("control_center", {}).get("crawler", {}) or {}
    if (
        all_ok
        and bool(crawler.get("enabled"))
        and bool((crawler.get("loop_contract", {}) or {}).get("retro_required"))
        and state.stages.get("learn")
        and state.stages["learn"].status == "completed"
    ):
        retro_result = run_verifier({"type": "crawler_retro_complete", "task_id": args.task_id})
        results.append({"stage": "learn", "result": retro_result})
        if not retro_result.get("ok"):
            all_ok = False
            first_failed_stage = first_failed_stage or "learn"
            learn_stage = state.stages["learn"]
            learn_stage.status = "failed"
            learn_stage.blocker = f"verification failed: {retro_result['status']}"
            learn_stage.updated_at = utc_now_iso()
    verification_artifact = {
        "results": results,
        "verified_stages": verified_stages,
        "verification_ok": all_ok,
        "acceptance_decision": "accepted" if all_ok else "rework_required",
        "remaining_risks": [] if all_ok else [f"verification_failure:{first_failed_stage or 'unknown'}"],
        "artifact_status": "ready" if all_ok else "failed",
    }
    _record_stage_artifact(
        args.task_id,
        contract=contract,
        state=state,
        stage_name="verify",
        summary="Verification passed and the task satisfied the current release gate." if all_ok else "Verification failed and the task must re-enter recovery.",
        extra=verification_artifact,
    )
    state.status = "completed" if all_ok else "recovering"
    state.next_action = "none" if all_ok else "repair_verification_failure"
    state.blockers = [] if all_ok else [f"verification_failure:{first_failed_stage or 'unknown'}"]
    if all_ok:
        next_stage = None
        for name in state.stage_order:
            if state.stages[name].status != "completed":
                next_stage = name
                break
        if next_stage:
            state.status = "planning"
            state.current_stage = next_stage
            state.next_action = f"start_stage:{next_stage}"
        else:
            state.current_stage = ""
    else:
        state.current_stage = first_failed_stage or state.current_stage
    state.last_update_at = utc_now_iso()
    save_state(state)
    plan_id = str(contract.metadata.get("control_center", {}).get("selected_plan", {}).get("plan_id", ""))
    if plan_id:
        task_types, risk_level = _plan_bucket(contract)
        record_plan_outcome(plan_id, "success" if all_ok else "failure", task_types=task_types, risk_level=risk_level)
    _sync_milestone_progress(args.task_id, contract=contract, state=state)
    save_state(state)
    _refresh_task_summary(
        args.task_id,
        state=state,
        extra={"verified_stages": verified_stages, "verification_results": results, "verification_ok": all_ok},
    )
    log_event(args.task_id, "verification_ran", ok=all_ok, results=results, verified_stages=verified_stages)
    print(json.dumps({"ok": all_ok, "results": results, "verified_stages": verified_stages, "status": state.status, "next_action": state.next_action}, ensure_ascii=False, indent=2))
    return 0


def checkpoint_task(args: argparse.Namespace) -> int:
    """
    中文注解：
    - 功能：实现 `checkpoint_task` 对应的处理逻辑。
    - 角色：属于本模块中的对外可见逻辑；私有函数通常服务同文件主流程，公共函数通常作为跨模块入口或能力接口。
    - 调用关系：建议结合本文件的模块说明、调用方以及同名相关辅助函数一起阅读。
    """
    state = load_state(args.task_id)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    path = checkpoints_dir(args.task_id) / f"{stamp}.txt"
    text = write_checkpoint(path, state)
    log_event(args.task_id, "checkpoint_written", path=str(path))
    print(json.dumps({"path": str(path), "text": text}, ensure_ascii=False, indent=2))
    return 0


def set_stage_verifier(args: argparse.Namespace) -> int:
    """
    中文注解：
    - 功能：实现 `set_stage_verifier` 对应的处理逻辑。
    - 角色：属于本模块中的对外可见逻辑；私有函数通常服务同文件主流程，公共函数通常作为跨模块入口或能力接口。
    - 调用关系：建议结合本文件的模块说明、调用方以及同名相关辅助函数一起阅读。
    """
    contract = load_contract(args.task_id)
    stage = next((item for item in contract.stages if item.name == args.stage), None)
    if not stage:
        raise SystemExit("unknown stage")
    stage.verifier = json.loads(args.verifier_json)
    save_contract(contract)
    log_event(args.task_id, "stage_verifier_updated", stage=args.stage, verifier=stage.verifier)
    print(json.dumps({"task_id": args.task_id, "stage": args.stage, "verifier": stage.verifier}, ensure_ascii=False, indent=2))
    return 0


def set_stage_execution_policy(args: argparse.Namespace) -> int:
    """
    中文注解：
    - 功能：实现 `set_stage_execution_policy` 对应的处理逻辑。
    - 角色：属于本模块中的对外可见逻辑；私有函数通常服务同文件主流程，公共函数通常作为跨模块入口或能力接口。
    - 调用关系：建议结合本文件的模块说明、调用方以及同名相关辅助函数一起阅读。
    """
    contract = load_contract(args.task_id)
    stage = next((item for item in contract.stages if item.name == args.stage), None)
    if not stage:
        raise SystemExit("unknown stage")
    stage.execution_policy = json.loads(args.execution_policy_json)
    save_contract(contract)
    log_event(args.task_id, "stage_execution_policy_updated", stage=args.stage, execution_policy=stage.execution_policy)
    print(json.dumps({"task_id": args.task_id, "stage": args.stage, "execution_policy": stage.execution_policy}, ensure_ascii=False, indent=2))
    return 0


def set_task_metadata(args: argparse.Namespace) -> int:
    """
    中文注解：
    - 功能：实现 `set_task_metadata` 对应的处理逻辑。
    - 角色：属于本模块中的对外可见逻辑；私有函数通常服务同文件主流程，公共函数通常作为跨模块入口或能力接口。
    - 调用关系：建议结合本文件的模块说明、调用方以及同名相关辅助函数一起阅读。
    """
    state = load_state(args.task_id)
    value = json.loads(args.value_json)
    _set_nested_dict_value(state.metadata, args.field, value)
    state.last_update_at = utc_now_iso()
    save_state(state)
    log_event(args.task_id, "task_metadata_updated", field=args.field, value=value)
    print(json.dumps({"task_id": args.task_id, "field": args.field, "value": value}, ensure_ascii=False, indent=2))
    return 0


def write_business_outcome(
    task_id: str,
    *,
    goal_satisfied: bool,
    user_visible_result_confirmed: bool,
    proof_summary: str,
    evidence: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    """
    中文注解：
    - 功能：把“业务层是否真的达成目标”的结论写入 task metadata。
    - 关键字段：
      - goal_satisfied
      - user_visible_result_confirmed
      - proof_summary
      - evidence
    - 调用关系：browser signals、live probe、runtime 自动同步和业务型 verifier 最终都会走到这里。
    """
    state = load_state(task_id)
    payload: Dict[str, Any] = {
        "goal_satisfied": goal_satisfied,
        "user_visible_result_confirmed": user_visible_result_confirmed,
        "proof_summary": proof_summary,
        "updated_at": utc_now_iso(),
    }
    if evidence:
        payload["evidence"] = evidence
    state.metadata["business_outcome"] = payload
    state.last_update_at = utc_now_iso()
    contract = load_contract(task_id)
    _sync_milestone_progress(task_id, contract=contract, state=state)
    save_state(state)
    _refresh_task_summary(task_id, state=state, extra={"business_outcome": payload})
    log_event(task_id, "business_outcome_recorded", business_outcome=payload)
    return payload


def evolve_task(args: argparse.Namespace) -> int:
    """
    中文注解：
    - 功能：实现 `evolve_task` 对应的处理逻辑。
    - 角色：属于本模块中的对外可见逻辑；私有函数通常服务同文件主流程，公共函数通常作为跨模块入口或能力接口。
    - 调用关系：建议结合本文件的模块说明、调用方以及同名相关辅助函数一起阅读。
    """
    state = load_state(args.task_id)
    proposal = {
        "task_id": args.task_id,
        "proposed_at": utc_now_iso(),
        "reason": args.reason,
        "current_blockers": state.blockers,
        "learning_backlog": state.learning_backlog,
        "suggested_runtime_changes": [
            "add stronger verifier",
            "add recovery branch",
            "promote recurring fix into durable guidance",
        ],
    }
    report_path = task_dir(args.task_id) / "runtime-evolution-proposal.json"
    write_json(report_path, proposal)
    log_event(args.task_id, "runtime_evolution_proposed", path=str(report_path))
    print(json.dumps({"path": str(report_path), "proposal": proposal}, ensure_ascii=False, indent=2))
    return 0


def build_parser() -> argparse.ArgumentParser:
    """
    中文注解：
    - 功能：实现 `build_parser` 对应的处理逻辑。
    - 角色：属于本模块中的对外可见逻辑；私有函数通常服务同文件主流程，公共函数通常作为跨模块入口或能力接口。
    - 调用关系：建议结合本文件的模块说明、调用方以及同名相关辅助函数一起阅读。
    """
    parser = argparse.ArgumentParser(description="General autonomy runtime for long-running OpenClaw tasks")
    sub = parser.add_subparsers(dest="cmd", required=True)

    create = sub.add_parser("create")
    create.add_argument("--task-id", required=True)
    create.add_argument("--goal", required=True)
    create.add_argument("--done-definition", required=True)
    create.add_argument("--stage", action="append", required=True, help="Format: name|goal")
    create.add_argument("--hard-constraint", action="append")
    create.add_argument("--soft-preference", action="append")
    create.add_argument("--allowed-tool", action="append")
    create.add_argument("--forbidden-action", action="append")

    status = sub.add_parser("status")
    status.add_argument("--task-id", required=True)

    sub.add_parser("list")

    run_once_cmd = sub.add_parser("run-once")
    run_once_cmd.add_argument("--task-id", required=True)

    recover = sub.add_parser("recover-stage")
    recover.add_argument("--task-id", required=True)
    recover.add_argument("--stage", default="")
    recover.add_argument("--summary", required=True)

    apply_recover = sub.add_parser("apply-recovery")
    apply_recover.add_argument("--task-id", required=True)
    apply_recover.add_argument("--stage", default="")
    apply_recover.add_argument("--action", default="")

    complete = sub.add_parser("complete-stage")
    complete.add_argument("--task-id", required=True)
    complete.add_argument("--stage", default="")
    complete.add_argument("--summary", required=True)

    fail = sub.add_parser("fail-stage")
    fail.add_argument("--task-id", required=True)
    fail.add_argument("--stage", default="")
    fail.add_argument("--error", required=True)

    verify = sub.add_parser("verify")
    verify.add_argument("--task-id", required=True)

    checkpoint = sub.add_parser("checkpoint")
    checkpoint.add_argument("--task-id", required=True)

    set_verifier = sub.add_parser("set-stage-verifier")
    set_verifier.add_argument("--task-id", required=True)
    set_verifier.add_argument("--stage", required=True)
    set_verifier.add_argument("--verifier-json", required=True)

    set_execution_policy = sub.add_parser("set-stage-execution-policy")
    set_execution_policy.add_argument("--task-id", required=True)
    set_execution_policy.add_argument("--stage", required=True)
    set_execution_policy.add_argument("--execution-policy-json", required=True)

    set_task_meta = sub.add_parser("set-task-metadata")
    set_task_meta.add_argument("--task-id", required=True)
    set_task_meta.add_argument("--field", required=True)
    set_task_meta.add_argument("--value-json", required=True)

    evolve = sub.add_parser("propose-evolution")
    evolve.add_argument("--task-id", required=True)
    evolve.add_argument("--reason", required=True)
    return parser


def main() -> int:
    """
    中文注解：
    - 功能：实现 `main` 对应的处理逻辑。
    - 角色：属于本模块中的对外可见逻辑；私有函数通常服务同文件主流程，公共函数通常作为跨模块入口或能力接口。
    - 调用关系：建议结合本文件的模块说明、调用方以及同名相关辅助函数一起阅读。
    """
    parser = build_parser()
    args = parser.parse_args()
    if args.cmd == "create":
        return create_task(args)
    if args.cmd == "status":
        return status_task(args)
    if args.cmd == "list":
        return list_tasks(args)
    if args.cmd == "run-once":
        return run_once(args)
    if args.cmd == "recover-stage":
        return recover_task(args)
    if args.cmd == "apply-recovery":
        return apply_recovery(args)
    if args.cmd == "complete-stage":
        return complete_stage(args)
    if args.cmd == "fail-stage":
        return fail_stage(args)
    if args.cmd == "verify":
        return verify_task(args)
    if args.cmd == "checkpoint":
        return checkpoint_task(args)
    if args.cmd == "set-stage-verifier":
        return set_stage_verifier(args)
    if args.cmd == "set-stage-execution-policy":
        return set_stage_execution_policy(args)
    if args.cmd == "set-task-metadata":
        return set_task_metadata(args)
    if args.cmd == "propose-evolution":
        return evolve_task(args)
    parser.error(f"unknown command: {args.cmd}")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
