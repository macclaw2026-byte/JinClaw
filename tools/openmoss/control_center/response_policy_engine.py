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
- 文件路径：`tools/openmoss/control_center/response_policy_engine.py`
- 文件作用：负责把内部状态翻译成对用户可见的真实回复。
- 顶层函数：build_route_receipt_text、build_supervisor_status_text。
- 顶层类：无顶层类。
- 阅读建议：先看模块说明，再按函数/类 docstring 顺着主流程理解调用关系。
"""
from __future__ import annotations

from typing import Any, Dict, List


def _milestone_fragment(snapshot: Dict[str, Any]) -> str:
    """
    中文注解：
    - 功能：把权威状态里的里程碑快照压缩成一小段可直接放进聊天回执的描述。
    - 角色：服务本模块的回复生成逻辑，避免每条状态回复都重复拼接同样的 milestone 文案。
    - 调用关系：由 `build_route_receipt_text(...)` 在状态类回复中调用。
    """
    milestone_progress = snapshot.get("milestone_progress", {}) or {}
    stats = milestone_progress.get("stats", {}) or {}
    required_total = int(stats.get("required_total", 0) or 0)
    required_completed = int(stats.get("required_completed", 0) or 0)
    next_pending = milestone_progress.get("next_pending", {}) or {}
    if required_total <= 0:
        return ""
    fragment = f" 当前里程碑进度 {required_completed}/{required_total}。"
    next_label = str(next_pending.get("label", "")).strip()
    next_stage = str(next_pending.get("stage", "")).strip()
    if next_label:
        if next_stage:
            fragment += f" 下一步是 {next_stage} 阶段的 {next_label}。"
        else:
            fragment += f" 下一步是 {next_label}。"
    return fragment


def _governance_fragment(snapshot: Dict[str, Any]) -> str:
    """
    中文注解：
    - 功能：把治理封包里用户最关心的少量信息压成一句补充说明。
    - 设计意图：避免用户回执只报状态，不解释“为什么现在这样做”“风险在哪”“系统依据了哪些历史经验”。
    """
    governance = snapshot.get("governance", {}) or {}
    security = governance.get("security", {}) or {}
    approval = governance.get("approval", {}) or {}
    authorized_session = governance.get("authorized_session", {}) or {}
    human_checkpoint = governance.get("human_checkpoint", {}) or {}
    crawler_project = governance.get("crawler_project", {}) or {}
    blocked_runtime_state = snapshot.get("blocked_runtime_state", {}) or {}
    policy = governance.get("policy", {}) or {}
    memory = governance.get("memory", {}) or snapshot.get("memory", {}) or {}
    risk = str(policy.get("risk", "")).strip()
    pending = policy.get("pending_approvals", []) or []
    matched_rules = memory.get("matched_promoted_rules", []) or []
    recurrence = memory.get("matched_error_recurrence", []) or []
    parts = []
    if risk:
        parts.append(f"治理风险级别 {risk}")
    if pending or approval.get("pending"):
        parts.append(f"待审批 {len(pending)} 项")
    if authorized_session.get("needs_authorized_session"):
        parts.append("需要授权态会话")
    if human_checkpoint.get("required"):
        parts.append("需要人工检查点")
    if matched_rules:
        parts.append(f"命中 durable rule {len(matched_rules)} 条")
    elif recurrence:
        parts.append(f"命中历史复发模式 {len(recurrence)} 条")
    crawler_health = str(crawler_project.get("health_status", "")).strip()
    crawler_summary = crawler_project.get("summary", {}) or {}
    if crawler_health in {"degraded", "critical"}:
        attention_sites = int(crawler_summary.get("sites_attention_required", 0) or 0)
        width_score = crawler_summary.get("width_score")
        depth_score = crawler_summary.get("depth_score")
        breadth_score = crawler_summary.get("breadth_score")
        stats = []
        if attention_sites:
            stats.append(f"{attention_sites} 个站点待加固")
        if width_score is not None:
            stats.append(f"宽度 {width_score}")
        if breadth_score is not None:
            stats.append(f"广度 {breadth_score}")
        if depth_score is not None:
            stats.append(f"深度 {depth_score}")
        suffix = f"（{'，'.join(stats)}）" if stats else ""
        parts.append(f"项目抓取能力 {crawler_health}{suffix}")
    blocked_category = str(blocked_runtime_state.get("category", "")).strip()
    blocked_reason = str(blocked_runtime_state.get("attention_reason", "")).strip()
    if blocked_category:
        blocked_text = f"运行时阻断 {blocked_category}"
        if blocked_reason:
            blocked_text += f"（{blocked_reason}）"
        parts.append(blocked_text)
    if not parts and security.get("overall_risk"):
        parts.append(f"治理风险级别 {security.get('overall_risk')}")
    if not parts:
        return ""
    return " 当前治理上下文：" + "，".join(parts) + "。"


def _acquisition_response_fragment(snapshot: Dict[str, Any]) -> str:
    """
    中文注解：
    - 功能：把 snapshot.reply_contract 中的 acquisition response 合同翻译成用户可见的简短回复片段。
    - 设计意图：让最终回执真正消费 acquisition-hand 的答案合同，而不是只停留在内部 metadata。
    """
    reply_contract = snapshot.get("reply_contract", {}) or {}
    acquisition_response = reply_contract.get("acquisition_response", {}) or {}
    if not bool(acquisition_response.get("enabled")):
        return ""
    mode = str(acquisition_response.get("response_mode", "")).strip() or "unknown"
    fragment = f" 当前数据回答模式是 {mode}。"
    preview_lines = [str(item).strip() for item in (acquisition_response.get("preview_lines", []) or []) if str(item).strip()]
    disclosure_lines = [str(item).strip() for item in (acquisition_response.get("disclosure_lines", []) or []) if str(item).strip()]
    blocker_reasons = [str(item).strip() for item in (acquisition_response.get("blocker_reasons", []) or []) if str(item).strip()]
    recommended_next_actions = [
        str(item).strip() for item in (acquisition_response.get("recommended_next_actions", []) or []) if str(item).strip()
    ]
    if preview_lines:
        fragment += " 当前可引用字段：" + "；".join(preview_lines[:2]) + "。"
    if bool(acquisition_response.get("requires_user_confirmation")):
        fragment += " 继续前需要你确认接受当前 guarded 证据级别。"
    elif bool(acquisition_response.get("requires_disclosure")) and disclosure_lines:
        fragment += " 使用当前结果时必须附带说明：" + "；".join(disclosure_lines[:2]) + "。"
    if mode in {"partial_answer_with_blockers", "pause_and_recapture"} and blocker_reasons:
        fragment += " 当前阻断：" + "，".join(blocker_reasons[:3]) + "。"
    elif mode in {"partial_answer_with_blockers", "pause_and_recapture"} and recommended_next_actions:
        fragment += " 下一步建议：" + "，".join(recommended_next_actions[:3]) + "。"
    return fragment


def _acquisition_response_details_fragment(snapshot: Dict[str, Any]) -> str:
    reply_contract = snapshot.get("reply_contract", {}) or {}
    acquisition_response = reply_contract.get("acquisition_response", {}) or {}
    if not bool(acquisition_response.get("enabled")):
        return ""
    fragment = ""
    preview_lines = [str(item).strip() for item in (acquisition_response.get("preview_lines", []) or []) if str(item).strip()]
    disclosure_lines = [str(item).strip() for item in (acquisition_response.get("disclosure_lines", []) or []) if str(item).strip()]
    blocker_reasons = [str(item).strip() for item in (acquisition_response.get("blocker_reasons", []) or []) if str(item).strip()]
    recommended_next_actions = [
        str(item).strip() for item in (acquisition_response.get("recommended_next_actions", []) or []) if str(item).strip()
    ]
    mode = str(acquisition_response.get("response_mode", "")).strip()
    if preview_lines:
        fragment += " 当前可引用字段：" + "；".join(preview_lines[:2]) + "。"
    if bool(acquisition_response.get("requires_user_confirmation")):
        fragment += " 继续前需要你确认接受当前 guarded 证据级别。"
    elif bool(acquisition_response.get("requires_disclosure")) and disclosure_lines:
        fragment += " 使用当前结果时必须附带说明：" + "；".join(disclosure_lines[:2]) + "。"
    if mode in {"partial_answer_with_blockers", "pause_and_recapture"} and blocker_reasons:
        fragment += " 当前阻断：" + "，".join(blocker_reasons[:3]) + "。"
    elif mode in {"partial_answer_with_blockers", "pause_and_recapture"} and recommended_next_actions:
        fragment += " 下一步建议：" + "，".join(recommended_next_actions[:3]) + "。"
    return fragment


def _merge_acquisition_response(summary: str, snapshot: Dict[str, Any]) -> str:
    text = str(summary or "").strip()
    if "Current data answer mode is" in text or "当前数据回答模式是" in text:
        return text + _acquisition_response_details_fragment(snapshot)
    return text + _acquisition_response_fragment(snapshot)


def _reply_flags(snapshot: Dict[str, Any]) -> Dict[str, Any]:
    """
    中文注解：
    - 功能：从权威快照里提炼会影响用户回复策略的显式标志。
    - 设计意图：让 reply projection 能把“需要确认/需要披露/当前回答模式”结构化暴露出来，后续 transport 只负责投影，不再各自猜测。
    """
    reply_contract = snapshot.get("reply_contract", {}) or {}
    acquisition_response = reply_contract.get("acquisition_response", {}) or {}
    return {
        "acquisition_enabled": bool(acquisition_response.get("enabled")),
        "response_mode": str(acquisition_response.get("response_mode", "")).strip(),
        "requires_user_confirmation": bool(acquisition_response.get("requires_user_confirmation")),
        "requires_disclosure": bool(acquisition_response.get("requires_disclosure")),
    }


def render_reply_projection(projection: Dict[str, Any]) -> str:
    """
    中文注解：
    - 功能：把结构化 reply projection 渲染成最终用户可见文本。
    - 设计意图：从本阶段开始，把“解释 route”与“输出文本”拆开；未来 Telegram / 直连 / 其它 transport 都应优先消费 projection，再做各自渲染。
    """
    segments = projection.get("segments", []) or []
    text = "".join(
        str(item.get("text", "")).strip() if str(item.get("glue", "")).strip() == "tight" else str(item.get("text", ""))
        for item in segments
        if str(item.get("text", "")).strip()
    )
    text = str(text).strip()
    if text:
        return text
    return str(projection.get("fallback_text", "")).strip()


def build_route_reply_projection(route: Dict[str, Any]) -> Dict[str, Any]:
    """
    中文注解：
    - 功能：把 route 与权威快照解释成结构化 reply projection。
    - 设计意图：让 task receipt、Telegram/chat transport、未来 UI 都消费同一份解释结果，避免一条 route 被多层重复翻译。
    """
    mode = str(route.get("mode", "instant_reply_only"))
    task_id = str(route.get("task_id", "")).strip()
    prompt_error = route.get("prompt_error", {}) or {}
    prompt_error_message = str(prompt_error.get("error", "")).strip()
    selection_updated = bool(route.get("selection_updated"))
    selected_task_group_alias = str(route.get("selected_task_group_alias", "")).strip()
    selected_task_alias = str(route.get("selected_task_alias", "")).strip()
    selection_label = selected_task_alias or selected_task_group_alias or task_id
    selection_prefix = f"已切换到任务 {selection_label}。 " if selection_updated and selection_label else ""
    snapshot = route.get("authoritative_task_status", {}) or {}
    flags = _reply_flags(snapshot)
    projection: Dict[str, Any] = {
        "projection_version": 1,
        "mode": mode,
        "task_id": task_id,
        "message_kind": "route_ack",
        "source_of_truth": "route",
        "selection_prefix": selection_prefix,
        "flags": {
            "selection_updated": selection_updated,
            **flags,
        },
        "segments": [],
        "fallback_text": f"已收到任务型指令。当前路由模式: {mode}。任务 ID: {task_id or '未创建'}。",
    }

    def add_segment(key: str, text: str) -> None:
        if not str(text or "").strip():
            return
        projection["segments"].append({"key": key, "text": text})

    if selection_prefix:
        add_segment("selection_prefix", selection_prefix)

    if mode == "heartbeat_probe":
        status = str(snapshot.get("status", "")).strip()
        if not snapshot or not task_id or status in {"completed", "failed"}:
            projection["message_kind"] = "heartbeat_ok"
            add_segment("summary", "HEARTBEAT_OK")
        else:
            projection["message_kind"] = "heartbeat_status"
            projection["source_of_truth"] = "authoritative_task_status"
            summary = str(snapshot.get("authoritative_summary", "")).strip() or f"任务 {task_id} 仍在推进中。"
            add_segment("summary", _merge_acquisition_response(summary, snapshot))
            add_segment("milestone", _milestone_fragment(snapshot))
            add_segment("governance", _governance_fragment(snapshot))
    elif mode == "explicit_task_not_found":
        projection["message_kind"] = "task_not_found"
        add_segment("summary", f"没有找到任务 {task_id or 'unknown'}。请先在任务面板确认任务 ID，然后再用 `[task:任务ID]` 或 `任务: 任务ID` 指定。")
    elif mode == "task_completed_notice":
        projection["message_kind"] = "task_completed"
        projection["source_of_truth"] = "authoritative_task_status"
        summary = str(snapshot.get("authoritative_summary", "")).strip()
        body = _merge_acquisition_response(summary or "完成状态已记录。", snapshot)
        add_segment("summary", f"任务 {task_id or snapshot.get('task_id', 'unknown')} 已完成。{body}")
        add_segment("milestone", _milestone_fragment(snapshot))
        add_segment("governance", _governance_fragment(snapshot))
    elif mode == "milestone_progress_notice":
        projection["message_kind"] = "milestone_progress"
        projection["source_of_truth"] = "authoritative_task_status"
        notice = route.get("milestone_notice", {}) or {}
        title = str(notice.get("title", "")).strip() or str(notice.get("milestone_id", "")).strip() or "一个关键步骤"
        summary = str(snapshot.get("authoritative_summary", "")).strip()
        prefix = f"任务 {task_id or snapshot.get('task_id', 'unknown')} 已推进里程碑：{title}。"
        if summary:
            prefix += summary
        add_segment("summary", _merge_acquisition_response(prefix, snapshot))
        add_segment("milestone", _milestone_fragment(snapshot))
        add_segment("governance", _governance_fragment(snapshot))
    elif mode == "failed_task_doctor_takeover":
        projection["message_kind"] = "doctor_takeover"
        projection["source_of_truth"] = "authoritative_task_status"
        summary = str(snapshot.get("authoritative_summary", "")).strip()
        body = _merge_acquisition_response(summary or '我会先分析并尝试修复，再决定是否升级报告。', snapshot)
        add_segment("summary", f"任务 {task_id or snapshot.get('task_id', 'unknown')} 刚进入失败态，系统医生已接管。{body}")
        add_segment("milestone", _milestone_fragment(snapshot))
        add_segment("governance", _governance_fragment(snapshot))
    elif mode == "authoritative_task_status":
        projection["message_kind"] = "task_status"
        projection["source_of_truth"] = "authoritative_task_status"
        canonical = snapshot.get("canonical_task", {}) or {}
        requested_task_id = str(snapshot.get("requested_task_id", "")).strip()
        canonical_task_id = str(snapshot.get("task_id", "")).strip()
        projection["requested_task_id"] = requested_task_id
        projection["canonical_task_id"] = canonical_task_id
        projection["canonical_task_label"] = str(canonical.get("task_id", "")).strip() or canonical_task_id
        summary = str(snapshot.get("authoritative_summary", "")).strip() or f"当前任务状态已刷新，任务 ID: {task_id or 'unknown'}。"
        summary = _merge_acquisition_response(summary, snapshot)
        summary += _milestone_fragment(snapshot)
        summary += _governance_fragment(snapshot)
        if requested_task_id and canonical_task_id and requested_task_id != canonical_task_id:
            summary = f"你询问的原任务 {requested_task_id} 已经切换到当前活跃任务 {canonical_task_id}。{summary}"
        if prompt_error_message:
            summary = f"主回复链刚刚发生异常（{prompt_error_message}），我已自动降级到权威状态回复。{summary}"
        add_segment("summary", summary)
    elif mode in {"create_new_root_task", "create_or_attach"}:
        projection["message_kind"] = "task_created"
        add_segment("summary", f"已识别为新任务，任务 ID: {task_id}。我会先进入 understand 阶段，梳理目标、约束、交付物和执行条件，然后持续推进。")
    elif mode in {"create_successor_task", "branch_from_active_task", "append_to_active_successor_task"}:
        projection["message_kind"] = "task_chain_append"
        projection["source_of_truth"] = "authoritative_task_status" if snapshot else "route"
        suffix = ""
        if route.get("state_attention_required"):
            status = str(snapshot.get("status", "")).strip()
            stage = str(snapshot.get("current_stage", "")).strip() or "none"
            next_action = str(snapshot.get("next_action", "")).strip() or "none"
            suffix = f" 当前主任务状态是 {status or 'unknown'} / {stage}，下一步是 {next_action}；我会在这个基础上继续推进，而不是只回内部状态。"
        add_segment("summary", f"已识别为后续任务，任务 ID: {task_id}。我会沿当前任务链继续执行；如果遇到真实阻塞，会直接告诉你卡点而不是静默等待。{suffix}")
    elif mode == "append_to_root_mission_task":
        projection["message_kind"] = "root_mission_append"
        projection["source_of_truth"] = "authoritative_task_status" if snapshot else "route"
        suffix = ""
        if route.get("state_attention_required"):
            status = str(snapshot.get("status", "")).strip()
            stage = str(snapshot.get("current_stage", "")).strip() or "none"
            next_action = str(snapshot.get("next_action", "")).strip() or "none"
            suffix = f" 当前 root mission 状态是 {status or 'unknown'} / {stage}，下一步是 {next_action}；我会直接接着往下做。"
        add_segment("summary", f"已把这条新指令并入当前 root mission {task_id}，接下来会按既定目标继续推进。{suffix}")
    elif mode == "append_to_existing_task":
        projection["message_kind"] = "task_chain_append"
        projection["source_of_truth"] = "authoritative_task_status" if snapshot else "route"
        suffix = ""
        if route.get("state_attention_required"):
            status = str(snapshot.get("status", "")).strip()
            stage = str(snapshot.get("current_stage", "")).strip() or "none"
            next_action = str(snapshot.get("next_action", "")).strip() or "none"
            suffix = f" 当前主任务状态是 {status or 'unknown'} / {stage}，下一步是 {next_action}；我会先恢复连续执行，再推进你刚才这条要求。"
        add_segment("summary", f"已把这条新指令挂到当前任务 {task_id}，接下来会继续按现有任务链推进。{suffix}")
    elif mode == "doctor_diagnostic":
        projection["message_kind"] = "doctor_diagnostic"
        projection["source_of_truth"] = "authoritative_task_status"
        summary = str(snapshot.get("authoritative_summary", "")).strip() or f"系统医生已接管任务 {task_id} 并开始诊断。"
        add_segment("summary", _merge_acquisition_response(summary, snapshot))
        add_segment("milestone", _milestone_fragment(snapshot))
        add_segment("governance", _governance_fragment(snapshot))
    else:
        add_segment("summary", projection["fallback_text"])

    projection["rendered_text"] = render_reply_projection(projection)
    return projection


def build_route_receipt_text(route: Dict[str, Any]) -> str:
    """
    中文注解：
    - 功能：实现 `build_route_receipt_text` 对应的处理逻辑。
    - 角色：属于本模块中的对外可见逻辑；私有函数通常服务同文件主流程，公共函数通常作为跨模块入口或能力接口。
    - 调用关系：建议结合本文件的模块说明、调用方以及同名相关辅助函数一起阅读。
    """
    return render_reply_projection(build_route_reply_projection(route))


def build_supervisor_status_text(task_id: str, evidence: Dict[str, Any], repair: Dict[str, Any], snapshot: Dict[str, Any] | None = None) -> str:
    """
    中文注解：
    - 功能：实现 `build_supervisor_status_text` 对应的处理逻辑。
    - 角色：属于本模块中的对外可见逻辑；私有函数通常服务同文件主流程，公共函数通常作为跨模块入口或能力接口。
    - 调用关系：建议结合本文件的模块说明、调用方以及同名相关辅助函数一起阅读。
    """
    reason = str(evidence.get("reason", "unknown"))
    status = str(evidence.get("status", "unknown"))
    stage = str(evidence.get("current_stage", ""))
    next_action = str(evidence.get("next_action", ""))
    run_liveness = evidence.get("run_liveness", {}) or {}
    waiting_reason = str(run_liveness.get("waiting_reason", "")).strip()
    wait_status = str(run_liveness.get("wait_status", "")).strip()
    milestone_stats = evidence.get("milestone_stats", {}) or {}
    milestone_fragment = ""
    if milestone_stats:
        milestone_fragment = (
            f" 当前里程碑进度 {int(milestone_stats.get('required_completed', 0) or 0)}/"
            f"{int(milestone_stats.get('required_total', 0) or 0)}。"
        )
    governance_fragment = _governance_fragment(snapshot or {})
    waiting_fragment = ""
    if status == "waiting_external":
        waiting_fragment = f" 当前等待原因是 {waiting_reason or 'unknown'}"
        if wait_status:
            waiting_fragment += f"，最近一次 wait 状态是 {wait_status}"
        waiting_fragment += "。"
    if repair.get("repaired"):
        return (
            f"系统医生检测到任务 {task_id} 处于 {status} / {stage or 'none'}，原因是 {reason}。"
            f"{milestone_fragment}{waiting_fragment}{governance_fragment} 已自动修复并重新拉回执行，下一步是 {repair.get('next_action', next_action or 'unknown')}。"
        )
    return (
        f"系统医生检测到任务 {task_id} 处于 {status} / {stage or 'none'}，原因是 {reason}。"
        f"{milestone_fragment}{waiting_fragment}{governance_fragment} 当前还没有自动修复成功，下一步卡在 {next_action or 'unknown'}。"
    )
