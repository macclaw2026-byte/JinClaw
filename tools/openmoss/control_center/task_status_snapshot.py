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
- 文件路径：`tools/openmoss/control_center/task_status_snapshot.py`
- 文件作用：负责为回复与诊断生成权威任务状态快照。
- 顶层函数：_read_json、_write_json、_load_task_state、_load_task_contract、_load_browser_signals、_recent_events、_build_authoritative_summary、build_task_status_snapshot、main。
- 顶层类：无顶层类。
- 阅读建议：先看模块说明，再按函数/类 docstring 顺着主流程理解调用关系。
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List

from canonical_active_task import resolve_canonical_active_task
from control_center_schemas import (
    build_acquisition_response_handoff_schema,
    build_capability_gap_schema,
    build_execution_handoff_schema,
    build_goal_continuation_schema,
)
from conversation_context import load_conversation_focus
from execution_governor import classify_blocked_runtime_state
from governance_runtime import build_governance_bundle
from paths import BROWSER_SIGNALS_ROOT, OPENMOSS_ROOT, TASK_STATUS_ROOT, WORKSPACE_ROOT
from progress_evidence import build_progress_evidence
from run_liveness_verifier import build_run_liveness


AUTONOMY_TASKS_ROOT = OPENMOSS_ROOT / "runtime/autonomy/tasks"
LINKS_ROOT = OPENMOSS_ROOT / "runtime/autonomy/links"
ATTACHMENT_SUFFIXES = {
    ".md",
    ".markdown",
    ".txt",
    ".csv",
    ".tsv",
    ".xlsx",
    ".xls",
    ".json",
    ".html",
    ".pdf",
    ".docx",
    ".pptx",
    ".png",
    ".jpg",
    ".jpeg",
    ".gif",
    ".webp",
}
INTERNAL_ARTIFACT_NAMES = {
    "contract.json",
    "state.json",
    "events.jsonl",
}


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


def _write_json(path: Path, payload: Dict[str, Any]) -> str:
    """
    中文注解：
    - 功能：实现 `_write_json` 对应的处理逻辑。
    - 角色：属于本模块中的内部辅助逻辑；私有函数通常服务同文件主流程，公共函数通常作为跨模块入口或能力接口。
    - 调用关系：建议结合本文件的模块说明、调用方以及同名相关辅助函数一起阅读。
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return str(path)


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


def _load_browser_signals(task_id: str) -> Dict[str, Any]:
    """
    中文注解：
    - 功能：实现 `_load_browser_signals` 对应的处理逻辑。
    - 角色：属于本模块中的内部辅助逻辑；私有函数通常服务同文件主流程，公共函数通常作为跨模块入口或能力接口。
    - 调用关系：建议结合本文件的模块说明、调用方以及同名相关辅助函数一起阅读。
    """
    return _read_json(BROWSER_SIGNALS_ROOT / f"{task_id}.json", {})


def _recent_events(task_id: str, limit: int = 8) -> List[Dict[str, Any]]:
    """
    中文注解：
    - 功能：实现 `_recent_events` 对应的处理逻辑。
    - 角色：属于本模块中的内部辅助逻辑；私有函数通常服务同文件主流程，公共函数通常作为跨模块入口或能力接口。
    - 调用关系：建议结合本文件的模块说明、调用方以及同名相关辅助函数一起阅读。
    """
    events_path = AUTONOMY_TASKS_ROOT / task_id / "events.jsonl"
    if not events_path.exists():
        return []
    rows: List[Dict[str, Any]] = []
    for line in events_path.read_text(encoding="utf-8", errors="ignore").splitlines()[-limit:]:
        try:
            rows.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return rows


def _iter_local_path_strings(payload: Any) -> List[str]:
    """
    中文注解：
    - 功能：从任意嵌套 dict/list 结构里递归提取看起来像本地绝对路径的字符串。
    - 设计意图：很多任务产物会散落在 business_outcome.evidence、metadata.attachments 等位置，这里先统一抽出候选路径，再交给后面的过滤逻辑判定是否真能对外发送。
    """
    values: List[str] = []
    if isinstance(payload, dict):
        for item in payload.values():
            values.extend(_iter_local_path_strings(item))
    elif isinstance(payload, list):
        for item in payload:
            values.extend(_iter_local_path_strings(item))
    elif isinstance(payload, str):
        text = payload.strip().strip("\"'")
        if text.startswith("/Users/mac_claw/"):
            values.append(text.rstrip("\\"))
    return values


def _normalize_attachment_path(candidate: str) -> Path | None:
    """
    中文注解：
    - 功能：把候选字符串规范成真正可发送的本地文件路径。
    - 过滤规则：
      - 必须是存在的文件；
      - 必须落在工作区下；
      - 不能是 secrets/internal runtime 工件；
      - 后缀必须是适合聊天附件直发的常见文档/图片格式。
    """
    raw = str(candidate or "").strip().strip("\"'")
    if not raw:
        return None
    path = Path(raw).expanduser()
    if not path.is_absolute() or not path.exists() or not path.is_file():
        return None
    try:
        resolved = path.resolve()
    except OSError:
        return None
    try:
        resolved.relative_to(WORKSPACE_ROOT)
    except ValueError:
        return None
    if ".openclaw/secrets" in str(resolved):
        return None
    if resolved.name in INTERNAL_ARTIFACT_NAMES:
        return None
    if resolved.suffix.lower() not in ATTACHMENT_SUFFIXES:
        return None
    return resolved


def _discover_output_attachments(task_id: str, state: Dict[str, Any], business: Dict[str, Any]) -> List[Dict[str, Any]]:
    """
    中文注解：
    - 功能：统一整理“任务产物文件”候选列表，供回执链决定是否把文件直接发到聊天窗口。
    - 数据来源：
      - business_outcome 及其 evidence；
      - metadata.delivery_artifacts / output_artifacts / attachments；
      - 任务目录中少量最近生成的用户可见文档。
    """
    metadata = state.get("metadata", {}) or {}
    seen: set[str] = set()
    attachments: List[Dict[str, Any]] = []

    def add_candidate(path_text: str, source: str) -> None:
        normalized = _normalize_attachment_path(path_text)
        if not normalized:
            return
        key = str(normalized)
        if key in seen:
            return
        seen.add(key)
        attachments.append(
            {
                "path": key,
                "name": normalized.name,
                "suffix": normalized.suffix.lower(),
                "source": source,
            }
        )

    sources = {
        "business_outcome": business,
        "business_evidence": business.get("evidence", {}) if isinstance(business, dict) else {},
        "delivery_artifacts": metadata.get("delivery_artifacts", {}),
        "output_artifacts": metadata.get("output_artifacts", {}),
        "attachments": metadata.get("attachments", {}),
    }
    for source, payload in sources.items():
        for item in _iter_local_path_strings(payload):
            add_candidate(item, source)

    task_root = AUTONOMY_TASKS_ROOT / task_id
    if task_root.exists():
        recent_candidates = sorted(
            [path for path in task_root.iterdir() if path.is_file()],
            key=lambda item: item.stat().st_mtime,
            reverse=True,
        )[:8]
        for path in recent_candidates:
            add_candidate(str(path), "task_root")

    return attachments[:5]


def _find_link_for_task(task_id: str) -> Dict[str, Any]:
    """
    中文注解：
    - 功能：为 snapshot 查找当前任务绑定的会话 link。
    - 设计意图：execution handoff 需要知道 transport/provider 和当前会话模式，不能只看 task state。
    """
    if not LINKS_ROOT.exists():
        return {}
    for path in sorted(LINKS_ROOT.glob("*.json")):
        payload = _read_json(path, {})
        if str((payload or {}).get("task_id", "")).strip() == str(task_id or "").strip():
            return payload if isinstance(payload, dict) else {}
    return {}


def _derive_business_outcome_from_workspace_guards(task_id: str, state: Dict[str, Any]) -> Dict[str, Any]:
    """
    中文注解：
    - 功能：当 runtime state 里的 `metadata.business_outcome` 尚未正确吸收时，
      从工作区中已经落盘的 final-state / runtime-handoff / proof / verification 守卫文件推导业务完成结果。
    - 设计意图：当前一些任务真实已经完成，但 authoritative snapshot 仍引用旧 state，
      导致 control-center 持续输出 planning / blocked / bind_session_link 等过期状态。
      这里优先做一个最小、可逆、只读工作区证据的止血层。
    """
    existing = (state.get("metadata", {}) or {}).get("business_outcome", {}) or {}
    if existing.get("goal_satisfied") is True and existing.get("user_visible_result_confirmed") is True:
        return existing

    output_root = WORKSPACE_ROOT / "data/output"
    candidates = {
        "final_state": output_root / f"{task_id}-final-state.txt",
        "runtime_handoff": output_root / f"{task_id}-runtime-handoff.txt",
        "proof_json": output_root / f"{task_id}-proof.json",
        "verification": output_root / f"{task_id}-verification.txt",
    }

    def read_text(path: Path) -> str:
        try:
            return path.read_text(encoding="utf-8", errors="ignore") if path.exists() else ""
        except OSError:
            return ""

    final_state_text = read_text(candidates["final_state"])
    runtime_handoff_text = read_text(candidates["runtime_handoff"])
    verification_text = read_text(candidates["verification"])
    proof = _read_json(candidates["proof_json"], {}) if candidates["proof_json"].exists() else {}

    proof_business = proof.get("business_outcome", {}) if isinstance(proof, dict) else {}
    proof_goal = proof_business.get("goal_satisfied") is True
    proof_visible = proof_business.get("user_visible_result_confirmed") is True
    proof_summary = str(proof_business.get("proof_summary", "")).strip()

    final_completed = "final_state=completed" in final_state_text
    handoff_done = "runtime_handoff=done" in runtime_handoff_text and "completed=true" in runtime_handoff_text
    do_not_requeue = "do-not-requeue" in runtime_handoff_text
    verification_confirmed = "goal_satisfied=True" in verification_text and "user_visible_result_confirmed=True" in verification_text

    if not ((final_completed and handoff_done) or (proof_goal and proof_visible) or (final_completed and verification_confirmed)):
        return existing

    summary = proof_summary
    if not summary:
        summary = (
            f"Workspace completion guards confirm {task_id} is already completed; "
            f"final-state/runtime-handoff evidence indicates later repeats are stale orchestration residue"
        )

    derived = dict(existing)
    derived.update(
        {
            "goal_satisfied": True,
            "user_visible_result_confirmed": True,
            "proof_summary": summary,
            "derived_from_workspace_guards": True,
            "workspace_guards": {
                "final_state": str(candidates["final_state"]),
                "runtime_handoff": str(candidates["runtime_handoff"]),
                "proof_json": str(candidates["proof_json"]),
                "verification": str(candidates["verification"]),
                "do_not_requeue": do_not_requeue,
            },
        }
    )
    return derived


def _milestone_snapshot(contract: Dict[str, Any], state: Dict[str, Any]) -> Dict[str, Any]:
    """
    中文注解：
    - 功能：从 contract/state 中提炼里程碑进度快照，给回执、状态问答和医生输出统一使用。
    - 角色：属于状态快照构建链中的辅助函数，负责把底层 `task_milestones` 与 `milestone_progress` 翻译成更适合展示的结构。
    - 调用关系：由 `build_task_status_snapshot(...)` 调用；输出结果会被 `response_policy_engine.py` 用于生成更可读的聊天回复。
    """
    control_center = (contract.get("metadata", {}) or {}).get("control_center", {}) or {}
    milestone_defs = control_center.get("task_milestones", []) or []
    progress = (state.get("metadata", {}) or {}).get("milestone_progress", {}) or {}
    stats = (state.get("metadata", {}) or {}).get("milestone_stats", {}) or {}
    pending: List[Dict[str, Any]] = []
    completed: List[Dict[str, Any]] = []
    current_stage = str(state.get("current_stage", "")).strip()
    for item in milestone_defs:
        milestone_id = str(item.get("id", "")).strip()
        if not milestone_id:
            continue
        progress_item = progress.get(milestone_id, {}) or {}
        row = {
            "id": milestone_id,
            "label": str(item.get("label", milestone_id)).strip() or milestone_id,
            "stage": str(item.get("stage", "")).strip(),
            "required": bool(item.get("required", True)),
            "status": str(progress_item.get("status", "pending")).strip() or "pending",
            "summary": str(progress_item.get("summary", "")).strip(),
        }
        if row["status"] == "completed":
            completed.append(row)
        else:
            pending.append(row)
    preferred_pending = next((row for row in pending if row.get("stage") == current_stage), pending[0] if pending else {})
    return {
        "strict_continuation_required": bool(control_center.get("strict_continuation_required")),
        "stats": stats,
        "next_pending": preferred_pending,
        "pending": pending[:8],
        "completed": completed[:8],
    }


def _build_acquisition_reply_contract(snapshot: Dict[str, Any]) -> Dict[str, Any]:
    """
    中文注解：
    - 功能：把 acquisition answer synthesis 压成回复层可直接消费的轻量合同。
    - 设计意图：回复链不应该自己逆向拼装 answer_synthesis，而应消费 snapshot 中的一份显式交付合同。
    """
    acquisition_hand = snapshot.get("acquisition_hand", {}) or {}
    answer_synthesis = acquisition_hand.get("answer_synthesis", {}) or {}
    release_governance = acquisition_hand.get("release_governance", {}) or {}
    delivery_requirements = acquisition_hand.get("delivery_requirements", {}) or {}
    if not isinstance(answer_synthesis, dict) or not answer_synthesis:
        return build_acquisition_response_handoff_schema(
            enabled=False,
            contract_source="",
            governance_mode=str(release_governance.get("mode", "")).strip(),
            required_fields_by_site=delivery_requirements.get("required_fields_by_site", {}) or {},
        )
    preview_lines: List[str] = []
    for site_answer in (answer_synthesis.get("site_answers", []) or [])[:2]:
        site = str(site_answer.get("site", "")).strip() or "current target"
        fields = []
        for row in (site_answer.get("required_fields", []) or [])[:3]:
            field_name = str((row or {}).get("field_name", "")).strip()
            value = str((row or {}).get("value", "")).strip()
            if field_name and value:
                fields.append(f"{field_name}={value}")
        if fields:
            preview_lines.append(f"{site}: {', '.join(fields)}")
    return build_acquisition_response_handoff_schema(
        enabled=True,
        contract_source="execution_answer_synthesis",
        status=str(answer_synthesis.get("status", "")).strip(),
        response_mode=str(answer_synthesis.get("response_mode", "")).strip(),
        governance_mode=str(release_governance.get("mode", "")).strip(),
        answerable=bool(answer_synthesis.get("answerable")),
        must_use_authoritative_snapshot=True,
        requires_disclosure=bool(answer_synthesis.get("requires_disclosure")),
        requires_user_confirmation=bool(answer_synthesis.get("requires_user_confirmation")),
        preview_lines=preview_lines,
        disclosure_lines=[
            str(item).strip()
            for item in (answer_synthesis.get("user_visible_lines", []) or [])[:3]
            if str(item).strip()
        ],
        blocker_reasons=[
            str(item).strip()
            for item in (answer_synthesis.get("blocker_reasons", []) or [])[:4]
            if str(item).strip()
        ],
        recommended_next_actions=[
            str(item).strip()
            for item in (answer_synthesis.get("recommended_next_actions", []) or [])[:4]
            if str(item).strip()
        ],
        required_fields_by_site=delivery_requirements.get("required_fields_by_site", {}) or {},
        answerable_site_total=int(answer_synthesis.get("answerable_site_total", 0) or 0),
    )


def _build_execution_handoff(snapshot: Dict[str, Any], state: Dict[str, Any]) -> Dict[str, Any]:
    """
    中文注解：
    - 功能：把 runtime dispatch/poll 的执行真相压成权威 snapshot 合同。
    - 设计意图：让 reply chain、doctor、ops 能看到“任务是否已经真正交给执行内核”，而不是只看 planning/status 字样。
    """
    metadata = state.get("metadata", {}) or {}
    active_execution = metadata.get("active_execution", {}) or {}
    waiting_external = metadata.get("waiting_external", {}) or {}
    status = str(state.get("status", "")).strip()
    if not active_execution and not waiting_external and status != "waiting_external":
        return build_execution_handoff_schema(enabled=False)
    task_id = str(snapshot.get("task_id", "")).strip()
    link = _find_link_for_task(task_id)
    provider = str((link or {}).get("provider", "")).strip()
    conversation_id = str((link or {}).get("conversation_id", "")).strip()
    focus = load_conversation_focus(provider, conversation_id) if provider and conversation_id else {}
    stage_name = str(active_execution.get("stage_name", "")).strip() or str(state.get("current_stage", "")).strip()
    linked_session_key = str((active_execution or {}).get("linked_session_key", "") or (link or {}).get("session_key", "")).strip()
    execution_session_key = str((active_execution or {}).get("session_key", "")).strip()
    runtime_mode = str((active_execution or {}).get("runtime_mode", "") or focus.get("resolved_mode", "") or focus.get("requested_mode", "")).strip()
    runtime_mode_reason = str(
        (active_execution or {}).get("runtime_mode_reason", "") or focus.get("resolved_mode_reason", "") or focus.get("requested_mode_reason", "")
    ).strip()
    execution_strategy = str((active_execution or {}).get("execution_session_strategy", "")).strip()
    execution_strategy_reason = str((active_execution or {}).get("execution_session_strategy_reason", "")).strip()
    if not execution_strategy and linked_session_key and execution_session_key:
        if execution_session_key == linked_session_key:
            execution_strategy = "linked_session"
            execution_strategy_reason = execution_strategy_reason or "derived_from_matching_session_key"
        elif execution_session_key == f"{linked_session_key}:autonomy:{task_id}":
            execution_strategy = "autonomy_derived_session"
            execution_strategy_reason = execution_strategy_reason or "derived_from_autonomy_session_suffix"
    handoff_status = (
        "waiting_external"
        if status == "waiting_external"
        else str((active_execution or {}).get("status", "")).strip() or status or "unknown"
    )
    return build_execution_handoff_schema(
        enabled=bool(provider and conversation_id),
        contract_source="authoritative_task_state",
        task_id=task_id,
        stage_name=stage_name,
        handoff_status=handoff_status,
        provider=provider,
        conversation_id=conversation_id,
        session_key=str(focus.get("session_key", "") or (link or {}).get("session_key", "")).strip(),
        linked_session_key=linked_session_key,
        execution_session_key=execution_session_key,
        execution_session_strategy=execution_strategy,
        execution_session_strategy_reason=execution_strategy_reason,
        run_id=str((active_execution or {}).get("run_id", "") or (waiting_external or {}).get("run_id", "")).strip(),
        runtime_mode=runtime_mode,
        runtime_mode_reason=runtime_mode_reason,
        next_action=str(state.get("next_action", "")).strip(),
        wait_status=str((waiting_external or {}).get("wait_status", "")).strip(),
        wait_error=str((waiting_external or {}).get("wait_error", "")).strip(),
        dispatched_at=str((active_execution or {}).get("dispatched_at", "")).strip(),
        updated_at=str(state.get("last_update_at", "")).strip(),
        conversation_focus_ready=bool(focus.get("context_ready")),
        must_use_authoritative_snapshot=True,
    )


def _build_goal_continuation(contract: Dict[str, Any], snapshot: Dict[str, Any], state: Dict[str, Any]) -> Dict[str, Any]:
    """
    中文注解：
    - 功能：生成“当前是否还必须继续推进”的权威 continuation 合同。
    - 设计意图：把 PR/测试通过/局部修复视为 milestone，而不是终点，避免 terminal status 被误读成真正完成。
    """
    control_center = (contract.get("metadata", {}) or {}).get("control_center", {}) or {}
    operating_discipline = control_center.get("operating_discipline", {}) or {}
    completion_guard = operating_discipline.get("completion_guard", {}) or {}
    strict = bool(control_center.get("strict_continuation_required"))
    business = snapshot.get("business_outcome", {}) or {}
    outcome_evaluation = snapshot.get("outcome_evaluation", {}) or {}
    proof_ready = bool(
        business.get("goal_satisfied") is True
        and business.get("user_visible_result_confirmed") is True
        and str(business.get("proof_summary", "")).strip()
    )
    goal_reached = proof_ready or str(outcome_evaluation.get("outcome_status", "")).strip() == "goal_reached"
    continuation_required = bool(strict and not goal_reached)
    non_terminal_reasons: List[str] = []
    if strict:
        non_terminal_reasons.append("strict_continuation_required")
    if strict and not proof_ready:
        non_terminal_reasons.append("goal_completion_proof_missing")
    if str(state.get("status", "")).strip() == "completed" and continuation_required:
        non_terminal_reasons.append("terminal_status_without_goal_proof")
    milestones = (completion_guard.get("non_terminal_milestones", []) or [])
    next_required_stage = str(state.get("current_stage", "")).strip()
    next_required_action = str(state.get("next_action", "")).strip()
    if continuation_required and str(state.get("status", "")).strip() == "completed":
        next_required_stage = "verify"
        next_required_action = "start_stage:verify"
    return build_goal_continuation_schema(
        enabled=bool(strict or completion_guard),
        strict_continuation_required=strict,
        continuation_required=continuation_required,
        goal_reached=goal_reached,
        proof_ready=proof_ready,
        stop_condition=str(completion_guard.get("default_stop_condition", "")).strip(),
        requires_goal_completion_proof=bool(completion_guard.get("requires_goal_completion_proof")),
        treat_pr_as_milestone_only=bool(completion_guard.get("treat_pr_as_milestone_only")),
        treat_round_as_milestone_only=bool(completion_guard.get("treat_round_as_milestone_only")),
        non_terminal_milestones=milestones,
        terminal_boundaries=completion_guard.get("terminal_boundaries", []) or [],
        non_terminal_reasons=non_terminal_reasons,
        next_required_stage=next_required_stage,
        next_required_action=next_required_action,
        contract_source="authoritative_task_state",
    )


def _build_capability_gap(snapshot: Dict[str, Any], state: Dict[str, Any]) -> Dict[str, Any]:
    """
    中文注解：
    - 功能：把 runtime 写入的 capability-gap 元数据标准化成权威快照合同。
    - 设计意图：让回复链、doctor 和 ops 都围绕同一份能力缺口结构工作，而不是各自从 blocker 文本里重猜。
    """
    payload = ((state.get("metadata", {}) or {}).get("capability_gap", {}) or {})
    if not isinstance(payload, dict) or not payload:
        return build_capability_gap_schema()
    return build_capability_gap_schema(
        enabled=bool(payload.get("enabled")),
        gap_detected=bool(payload.get("gap_detected")),
        task_id=str(payload.get("task_id", "")).strip() or str(snapshot.get("task_id", "")).strip(),
        target_stage=str(payload.get("target_stage", "")).strip() or str(snapshot.get("current_stage", "")).strip(),
        current_action=str(payload.get("current_action", "")).strip() or str(snapshot.get("next_action", "")).strip(),
        classification=str(payload.get("classification", "")).strip(),
        blocker=str(payload.get("blocker", "")).strip(),
        missing_dependency=str(payload.get("missing_dependency", "")).strip(),
        selected_path=str(payload.get("selected_path", "")).strip(),
        next_step=str(payload.get("next_step", "")).strip(),
        auto_continue=bool(payload.get("auto_continue")),
        requires_external_research=bool(payload.get("requires_external_research")),
        build_feasible=bool(payload.get("build_feasible")),
        requires_human_decision=bool(payload.get("requires_human_decision")),
        local_tool_candidates=list(payload.get("local_tool_candidates", []) or []),
        skill_candidates=list(payload.get("skill_candidates", []) or []),
        generated_capability_candidates=list(payload.get("generated_capability_candidates", []) or []),
        attempted_steps=list(payload.get("attempted_steps", []) or []),
        ladder_steps=list(payload.get("ladder_steps", []) or []),
        rationale=list(payload.get("rationale", []) or []),
        contract_source=str(payload.get("contract_source", "")).strip() or "runtime_service",
        checked_at=str(payload.get("checked_at", "")).strip(),
    )


def _build_authoritative_summary(task_id: str, snapshot: Dict[str, Any], state: Dict[str, Any], browser_signals: Dict[str, Any]) -> str:
    """
    中文注解：
    - 功能：实现 `_build_authoritative_summary` 对应的处理逻辑。
    - 角色：属于本模块中的内部辅助逻辑；私有函数通常服务同文件主流程，公共函数通常作为跨模块入口或能力接口。
    - 调用关系：建议结合本文件的模块说明、调用方以及同名相关辅助函数一起阅读。
    """
    business = _derive_business_outcome_from_workspace_guards(task_id, state)
    status = str(state.get("status", ""))
    current_stage = str(state.get("current_stage", ""))
    next_action = str(state.get("next_action", ""))
    diagnosis = str(browser_signals.get("diagnosis", "none"))
    acquisition_response = ((snapshot.get("reply_contract", {}) or {}).get("acquisition_response", {}) or {})
    execution_handoff = snapshot.get("execution_handoff", {}) or {}
    goal_continuation = snapshot.get("goal_continuation", {}) or {}
    capability_gap = snapshot.get("capability_gap", {}) or {}
    outcome_evaluation = snapshot.get("outcome_evaluation", {}) or {}
    reflection_report = snapshot.get("reflection_report", {}) or {}
    skill_action_plane = snapshot.get("skill_action_plane", {}) or {}
    execution_suffix = ""
    if bool(execution_handoff.get("enabled")):
        handoff_status = str(execution_handoff.get("handoff_status", "")).strip()
        runtime_mode = str(execution_handoff.get("runtime_mode", "")).strip() or "runtime"
        handoff_stage = str(execution_handoff.get("stage_name", "")).strip() or current_stage or "unknown"
        wait_status = str(execution_handoff.get("wait_status", "")).strip()
        if handoff_status in {"dispatched", "waiting_external", "completed", "preflight_blocked"}:
            execution_suffix = f" Execution handoff is {handoff_status} via {runtime_mode} for stage {handoff_stage}."
            strategy = str(execution_handoff.get("execution_session_strategy", "")).strip()
            if strategy:
                execution_suffix += f" Session strategy is {strategy}."
            if wait_status and handoff_status == "waiting_external":
                execution_suffix += f" External wait status is {wait_status}."
    acquisition_suffix = ""
    if acquisition_response.get("enabled"):
        mode = str(acquisition_response.get("response_mode", "")).strip()
        preview_lines = acquisition_response.get("preview_lines", []) or []
        blocker_reasons = acquisition_response.get("blocker_reasons", []) or []
        acquisition_suffix = f" Current data answer mode is {mode or 'unknown'}."
        if preview_lines:
            acquisition_suffix += " Answer preview: " + " | ".join(preview_lines[:2]) + "."
        elif blocker_reasons:
            acquisition_suffix += " Current blockers: " + ", ".join(blocker_reasons[:3]) + "."
        if acquisition_response.get("requires_user_confirmation"):
            acquisition_suffix += " User confirmation is required before guarded release."
        elif acquisition_response.get("requires_disclosure"):
            acquisition_suffix += " Guarded disclosure is required when using the current result."
    completion_suffix = ""
    if bool(outcome_evaluation.get("enabled")):
        completion_suffix += (
            f" Outcome evaluation is {str(outcome_evaluation.get('outcome_status', '')).strip() or 'unknown'}"
            f" with score {float(outcome_evaluation.get('completion_score', 0.0) or 0.0):.1f}."
        )
    if bool(reflection_report.get("enabled")):
        completion_suffix += (
            f" Reflection report has {len(reflection_report.get('optimization_proposals', []) or [])} optimization proposals."
        )
    continuation_suffix = ""
    if bool(goal_continuation.get("enabled")) and bool(goal_continuation.get("continuation_required")):
        continuation_suffix += (
            f" Continuation is still required because {', '.join(goal_continuation.get('non_terminal_reasons', []) or ['goal_not_reached'])}."
        )
        if str(goal_continuation.get("next_required_action", "")).strip():
            continuation_suffix += f" Next required action is {str(goal_continuation.get('next_required_action', '')).strip()}."
    capability_gap_suffix = ""
    if bool(capability_gap.get("enabled")) and bool(capability_gap.get("gap_detected")):
        capability_gap_suffix += (
            f" Capability-gap loop selected {str(capability_gap.get('selected_path', '')).strip() or 'observe_only'}"
            f" with next step {str(capability_gap.get('next_step', '')).strip() or 'continue_current_plan'}."
        )
        if str(capability_gap.get("missing_dependency", "")).strip():
            capability_gap_suffix += f" Missing dependency is {str(capability_gap.get('missing_dependency', '')).strip()}."
    skill_action_suffix = ""
    if bool(skill_action_plane.get("enabled")):
        skill_action_suffix += (
            f" Skill action plane prefers {str(skill_action_plane.get('preferred_action_id', '')).strip() or 'unknown_action'}"
            f" via {str(skill_action_plane.get('preferred_skill_name', '')).strip() or 'unknown_skill'}."
        )
    if business.get("goal_satisfied") is True and business.get("user_visible_result_confirmed") is True:
        return (
            f"Authoritative task state says {task_id} is completed. "
            f"Business outcome is confirmed: {business.get('proof_summary', '')}"
            f"{execution_suffix}"
            f"{acquisition_suffix}"
            f"{completion_suffix}"
            f"{continuation_suffix}"
            f"{capability_gap_suffix}"
            f"{skill_action_suffix}"
        ).strip()
    if diagnosis and diagnosis != "none":
        return (
            f"Authoritative task state says {task_id} is {status or 'unknown'} "
            f"at stage {current_stage or 'none'} with next action {next_action or 'none'}. "
            f"Latest browser diagnosis is {diagnosis}."
            f"{execution_suffix}"
            f"{acquisition_suffix}"
            f"{completion_suffix}"
            f"{continuation_suffix}"
            f"{capability_gap_suffix}"
            f"{skill_action_suffix}"
        ).strip()
    return (
        f"Authoritative task state says {task_id} is {status or 'unknown'} "
        f"at stage {current_stage or 'none'} with next action {next_action or 'none'}."
        f"{execution_suffix}"
        f"{acquisition_suffix}"
        f"{completion_suffix}"
        f"{continuation_suffix}"
        f"{capability_gap_suffix}"
        f"{skill_action_suffix}"
    ).strip()


def _normalized_blocked_runtime_state(state: Dict[str, Any]) -> Dict[str, Any]:
    if str(state.get("status", "")).strip() != "blocked":
        return {}
    inferred = classify_blocked_runtime_state(
        next_action=str(state.get("next_action", "")).strip(),
        blockers=[str(item).strip() for item in (state.get("blockers", []) or []) if str(item).strip()],
        governance_attention=((state.get("metadata", {}) or {}).get("last_governance_attention", {}) or {}),
    )
    if str(inferred.get("category", "")).strip():
        return inferred
    return (state.get("metadata", {}) or {}).get("blocked_runtime_state", {}) or {}


def build_task_status_snapshot(task_id: str) -> Dict[str, Any]:
    """
    中文注解：
    - 功能：实现 `build_task_status_snapshot` 对应的处理逻辑。
    - 角色：属于本模块中的对外可见逻辑；私有函数通常服务同文件主流程，公共函数通常作为跨模块入口或能力接口。
    - 调用关系：建议结合本文件的模块说明、调用方以及同名相关辅助函数一起阅读。
    """
    canonical = resolve_canonical_active_task(task_id)
    canonical_task_id = str(canonical.get("canonical_task_id", task_id)).strip() or task_id
    state = _load_task_state(canonical_task_id)
    contract = _load_task_contract(canonical_task_id)
    browser_signals = _load_browser_signals(canonical_task_id)
    business = _derive_business_outcome_from_workspace_guards(canonical_task_id, state)
    milestone_progress = _milestone_snapshot(contract, state)
    progress_evidence = build_progress_evidence(canonical_task_id)
    control_center = ((contract.get("metadata", {}) or {}).get("control_center", {}) or {})
    governance = build_governance_bundle(
        canonical_task_id,
        str(state.get("current_stage", "")).strip(),
        contract,
        state,
        {
            "selected_plan": control_center.get("selected_plan", {}),
            "intent": control_center.get("intent", {}),
            "approval": control_center.get("approval", {}),
        },
    )
    snapshot: Dict[str, Any] = {
        "requested_task_id": task_id,
        "task_id": canonical_task_id,
        "canonical_task": canonical,
        "goal": contract.get("user_goal", ""),
        "status": state.get("status", "unknown"),
        "current_stage": state.get("current_stage", ""),
        "next_action": state.get("next_action", ""),
        "blockers": state.get("blockers", []),
        "blocked_runtime_state": _normalized_blocked_runtime_state(state),
        "business_outcome": business,
        "milestone_progress": milestone_progress,
        "run_liveness": build_run_liveness(canonical_task_id),
        "goal_conformance": progress_evidence.get("goal_conformance", {}),
        "governance": governance,
        "control_center_governance": control_center.get("governance", {}),
        "protocol_pack": control_center.get("protocol_pack", {}),
        "skill_action_plane": control_center.get("skill_action_plane", {}) or {},
        "plan_reviews": control_center.get("plan_reviews", {}),
        "readiness_dashboard": control_center.get("readiness_dashboard", {}),
        "outcome_evaluation": ((state.get("metadata", {}) or {}).get("outcome_evaluation", {}) or {}),
        "reflection_report": ((state.get("metadata", {}) or {}).get("reflection_report", {}) or {}),
        "capability_gap": {},
        "acquisition_hand": {
            "enabled": bool((control_center.get("acquisition_hand", {}) or {}).get("enabled")),
            "mode": str((((control_center.get("acquisition_hand", {}) or {}).get("execution_strategy", {}) or {}).get("mode", ""))).strip(),
            "primary_route": (((control_center.get("acquisition_hand", {}) or {}).get("summary", {}) or {}).get("primary_route", {}) or {}),
            "validation_routes": (((control_center.get("acquisition_hand", {}) or {}).get("summary", {}) or {}).get("validation_routes", []) or []),
            "delivery_requirements": ((control_center.get("acquisition_hand", {}) or {}).get("delivery_requirements", {}) or {}),
            "release_governance": ((control_center.get("acquisition_hand", {}) or {}).get("release_governance", {}) or {}),
            "execution_summary_path": str(((state.get("metadata", {}) or {}).get("crawler_execution", {}) or {}).get("acquisition_summary_json_path", "")).strip(),
            "execution_consensus_status": str(((((state.get("metadata", {}) or {}).get("crawler_execution", {}) or {}).get("acquisition_summary", {}) or {}).get("overall_summary", {}) or {}).get("consensus_status", "")).strip(),
            "execution_synthesis_status": str(((((state.get("metadata", {}) or {}).get("crawler_execution", {}) or {}).get("acquisition_summary", {}) or {}).get("overall_summary", {}) or {}).get("synthesis_status", "")).strip(),
            "release_readiness_status": str(((((state.get("metadata", {}) or {}).get("crawler_execution", {}) or {}).get("acquisition_summary", {}) or {}).get("overall_summary", {}) or {}).get("release_readiness_status", "")).strip(),
            "trusted_release_status": str(((((state.get("metadata", {}) or {}).get("crawler_execution", {}) or {}).get("acquisition_summary", {}) or {}).get("overall_summary", {}) or {}).get("trusted_release_status", "")).strip(),
            "governed_release_status": str(((((state.get("metadata", {}) or {}).get("crawler_execution", {}) or {}).get("acquisition_summary", {}) or {}).get("overall_summary", {}) or {}).get("governed_release_status", "")).strip(),
            "requires_human_confirmation": bool(((((state.get("metadata", {}) or {}).get("crawler_execution", {}) or {}).get("acquisition_summary", {}) or {}).get("overall_summary", {}) or {}).get("requires_human_confirmation", False)),
            "release_disclosure": (((((state.get("metadata", {}) or {}).get("crawler_execution", {}) or {}).get("acquisition_summary", {}) or {}).get("overall_summary", {}) or {}).get("release_disclosure", {}) or {}),
            "answer_synthesis": (((((state.get("metadata", {}) or {}).get("crawler_execution", {}) or {}).get("acquisition_summary", {}) or {}).get("overall_summary", {}) or {}).get("answer_synthesis", {}) or {}),
            "validation_diversity_status": str(((((state.get("metadata", {}) or {}).get("crawler_execution", {}) or {}).get("acquisition_summary", {}) or {}).get("overall_summary", {}) or {}).get("validation_diversity_status", "")).strip(),
            "synthesized_sites_total": int(((((state.get("metadata", {}) or {}).get("crawler_execution", {}) or {}).get("acquisition_summary", {}) or {}).get("overall_summary", {}) or {}).get("synthesized_sites_total", 0) or 0),
            "required_field_gap_total": int(((((state.get("metadata", {}) or {}).get("crawler_execution", {}) or {}).get("acquisition_summary", {}) or {}).get("overall_summary", {}) or {}).get("required_field_gap_total", 0) or 0),
            "conflicted_field_total": int(((((state.get("metadata", {}) or {}).get("crawler_execution", {}) or {}).get("acquisition_summary", {}) or {}).get("overall_summary", {}) or {}).get("conflicted_field_total", 0) or 0),
            "planned_route_gaps": (((state.get("metadata", {}) or {}).get("crawler_execution", {}) or {}).get("acquisition_summary", {}) or {}).get("planned_but_not_executed_route_ids", []) or [],
        },
        "memory": governance.get("memory", {}),
        "browser_signals": {
            "diagnosis": browser_signals.get("diagnosis", "none"),
            "recommended_action": browser_signals.get("recommended_action", "continue_current_plan"),
            "live_product_image_count": browser_signals.get("live_product_image_count"),
            "save_request_succeeded": browser_signals.get("save_request_succeeded"),
            "live_last_images": browser_signals.get("live_last_images", []),
        },
        "recent_events": _recent_events(canonical_task_id),
    }
    snapshot["output_attachments"] = _discover_output_attachments(canonical_task_id, state, business)
    snapshot["execution_handoff"] = _build_execution_handoff(snapshot, state)
    snapshot["goal_continuation"] = _build_goal_continuation(contract, snapshot, state)
    snapshot["capability_gap"] = _build_capability_gap(snapshot, state)
    snapshot["reply_contract"] = {
        "must_use_authoritative_snapshot": True,
        "must_prefer_task_state_over_chat_memory": True,
        "forbid_outdated_failure_claims_when_business_outcome_confirmed": bool(
            business.get("goal_satisfied") and business.get("user_visible_result_confirmed")
        ),
        "acquisition_response": _build_acquisition_reply_contract(snapshot),
        "execution_handoff": snapshot.get("execution_handoff", {}),
        "goal_continuation": snapshot.get("goal_continuation", {}),
        "capability_gap": snapshot.get("capability_gap", {}),
        "skill_action_plane": snapshot.get("skill_action_plane", {}),
        "completion_reflection": {
            "outcome_evaluation_enabled": bool((snapshot.get("outcome_evaluation", {}) or {}).get("enabled")),
            "reflection_report_enabled": bool((snapshot.get("reflection_report", {}) or {}).get("enabled")),
            "completion_score": float((snapshot.get("outcome_evaluation", {}) or {}).get("completion_score", 0.0) or 0.0),
            "optimization_proposal_total": len((snapshot.get("reflection_report", {}) or {}).get("optimization_proposals", []) or []),
        },
    }
    snapshot["authoritative_summary"] = _build_authoritative_summary(canonical_task_id, snapshot, state, browser_signals)
    snapshot["snapshot_path"] = _write_json(TASK_STATUS_ROOT / f"{canonical_task_id}.json", snapshot)
    return snapshot


def main() -> int:
    """
    中文注解：
    - 功能：实现 `main` 对应的处理逻辑。
    - 角色：属于本模块中的对外可见逻辑；私有函数通常服务同文件主流程，公共函数通常作为跨模块入口或能力接口。
    - 调用关系：建议结合本文件的模块说明、调用方以及同名相关辅助函数一起阅读。
    """
    import argparse

    parser = argparse.ArgumentParser(description="Build an authoritative task status snapshot for response-time use")
    parser.add_argument("--task-id", required=True)
    args = parser.parse_args()
    print(json.dumps(build_task_status_snapshot(args.task_id), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
