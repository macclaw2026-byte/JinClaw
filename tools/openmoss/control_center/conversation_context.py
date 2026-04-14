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
- 文件路径：`tools/openmoss/control_center/conversation_context.py`
- 文件作用：为不同聊天入口提供统一的 instruction envelope 与 conversation focus 真源。
- 顶层函数：conversation_context_key、instruction_envelope_path、conversation_focus_path、load_conversation_focus、write_instruction_envelope、build_instruction_envelope、record_conversation_context、build_conversation_focus_registry。
- 顶层类：无顶层类。
- 阅读建议：先看 envelope 生成，再看 focus 回写，最后看 registry 汇总。
"""
from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

from paths import CONVERSATION_FOCUS_ROOT, INSTRUCTION_ENVELOPES_ROOT

STATUS_FOLLOWUP_TOKENS = {
    "然后呢",
    "接下来呢",
    "那现在呢",
    "现在呢",
    "下一步呢",
    "然后",
    "whatnext",
    "next",
    "next?",
}

CONTINUE_FOLLOWUP_TOKENS = {
    "继续",
    "继续吧",
    "继续推进",
    "接着",
    "开始",
    "开始吧",
    "可以",
    "好的",
    "同意",
    "不用停",
    "直到完成",
    "continue",
    "goon",
}

CONTEXTUAL_PREFIXES = (
    "还是",
    "改成",
    "换成",
    "用",
    "切到",
    "切换到",
    "按",
    "设成",
    "设为",
)

CONTEXTUAL_TOKENS = {
    "美国站",
    "英国站",
    "欧洲站",
    "三月",
    "四月",
    "五月",
    "六月",
    "今天",
    "昨天",
    "明天",
}

INTERACTIVE_MODE_HINTS = (
    "优化",
    "调试",
    "修复",
    "review",
    "代码",
    "架构",
    "为什么",
    "怎么回事",
    "排查",
    "系统",
    "框架",
)

MISSION_MODE_HINTS = (
    "浏览器",
    "店铺",
    "后台",
    "对账",
    "订单",
    "导出",
    "下载",
    "抓取",
    "google maps",
    "googlemaps",
    "地图",
    "定时",
    "周期",
    "监控",
    "持续运行",
    "报表",
)


def _utc_now_iso() -> str:
    """
    中文注解：
    - 功能：返回当前 UTC 时间字符串。
    - 角色：供 envelope/focus/runtime registry 统一打时间戳。
    """
    return datetime.now(timezone.utc).isoformat()


def _read_json(path: Path, default: Any) -> Any:
    """
    中文注解：
    - 功能：安全读取 JSON；读不到时返回默认值。
    - 角色：conversation context 的本地持久化辅助函数。
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
    - 功能：把 envelope/focus 写到固定路径。
    - 角色：conversation context 的真源落盘入口。
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return str(path)


def _normalize_text(text: str) -> str:
    """
    中文注解：
    - 功能：把消息压成便于规则判断的紧凑文本。
    - 角色：follow-up / status / contextual 指令识别辅助。
    """
    compact = re.sub(r"\s+", "", str(text or "").strip().lower())
    return re.sub(r"[^\w\u4e00-\u9fff]+", "", compact)


def conversation_context_key(provider: str, conversation_id: str) -> str:
    """
    中文注解：
    - 功能：把 transport 会话标识转成稳定的本地 key。
    - 角色：envelope/focus 文件命名真源。
    """
    safe_provider = str(provider or "").strip().replace("/", "-") or "unknown"
    safe_conversation = str(conversation_id or "").strip().replace("/", "-") or "unknown"
    return f"{safe_provider}__{safe_conversation}"


def instruction_envelope_path(provider: str, conversation_id: str) -> Path:
    """
    中文注解：
    - 功能：返回指定会话的 envelope 路径。
    - 角色：供 brain router / doctor / tests 复用。
    """
    return INSTRUCTION_ENVELOPES_ROOT / f"{conversation_context_key(provider, conversation_id)}.json"


def conversation_focus_path(provider: str, conversation_id: str) -> Path:
    """
    中文注解：
    - 功能：返回指定会话的 focus 路径。
    - 角色：供 route/runtime/doctor/control plane 读取当前会话上下文真源。
    """
    return CONVERSATION_FOCUS_ROOT / f"{conversation_context_key(provider, conversation_id)}.json"


def load_conversation_focus(provider: str, conversation_id: str) -> Dict[str, Any]:
    """
    中文注解：
    - 功能：读取当前会话 focus。
    - 角色：Telegram / 直连会话都可共用的上下文恢复入口。
    """
    return _read_json(conversation_focus_path(provider, conversation_id), {})


def write_instruction_envelope(provider: str, conversation_id: str, payload: Dict[str, Any]) -> str:
    """
    中文注解：
    - 功能：把标准化 instruction envelope 落盘。
    - 角色：让 doctor / replay / parity benchmark 能看到入口消息是如何被解释的。
    """
    return _write_json(instruction_envelope_path(provider, conversation_id), payload)


def _looks_contextual_followup(normalized_text: str, focus_goal: str) -> bool:
    """
    中文注解：
    - 功能：识别“还是三月”“切到美国站”这类依赖当前上下文才能理解的短跟进。
    - 角色：避免这类短句在 Telegram 中被当成无意义噪声。
    """
    if not normalized_text or not focus_goal:
        return False
    if normalized_text in CONTEXTUAL_TOKENS:
        return True
    if any(normalized_text.startswith(prefix) for prefix in CONTEXTUAL_PREFIXES):
        return True
    return len(normalized_text) <= 18 and any(token in normalized_text for token in CONTEXTUAL_TOKENS)


def _derive_requested_mode(raw_text: str, normalized_text: str, explicit_intent_type: str, prior_focus: Dict[str, Any]) -> Dict[str, str]:
    """
    中文注解：
    - 功能：为当前消息推导 transport-neutral 的运行模式倾向。
    - 输出角色：供 brain router / runtime 后续区分 interactive_session 与 mission_runtime。
    """
    prior_requested_mode = str(prior_focus.get("resolved_mode", "")).strip() or str(prior_focus.get("requested_mode", "")).strip()
    explicit_type = str(explicit_intent_type or "").strip()
    if explicit_type in {"status_followup", "continue_current_task", "contextual_followup"} and prior_requested_mode:
        return {"requested_mode": prior_requested_mode, "requested_mode_reason": "inherit_prior_focus_mode"}
    lowered = str(raw_text or "").strip().lower()
    normalized = str(normalized_text or "").strip()
    if any(token in lowered or token in normalized for token in MISSION_MODE_HINTS):
        return {"requested_mode": "mission_runtime", "requested_mode_reason": "mission_keywords"}
    if any(token in lowered or token in normalized for token in INTERACTIVE_MODE_HINTS):
        return {"requested_mode": "interactive_session", "requested_mode_reason": "interactive_keywords"}
    if explicit_type == "status_followup":
        return {"requested_mode": "interactive_session", "requested_mode_reason": "status_followup_default"}
    return {"requested_mode": "interactive_session", "requested_mode_reason": "default_interactive"}


def build_instruction_envelope(
    *,
    provider: str,
    conversation_id: str,
    conversation_type: str,
    source: str,
    raw_text: str,
    cleaned_text: str,
    goal_text: str,
    message_id: str = "",
    sender_id: str = "",
    sender_name: str = "",
    session_key: str = "",
    existing_link: Dict[str, Any] | None = None,
    prior_focus: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    """
    中文注解：
    - 功能：把 transport 消息转成 transport-neutral 的标准 envelope。
    - 输入角色：消费原始消息文本、会话信息、现有 link 与 prior focus。
    - 输出角色：供 brain router 做统一解释，而不是让 Telegram/直连各自猜一遍。
    """
    existing_link = dict(existing_link or {})
    prior_focus = dict(prior_focus or {})
    cleaned = str(cleaned_text or raw_text or "").strip()
    goal = str(goal_text or cleaned).strip()
    normalized = _normalize_text(goal or cleaned or raw_text)
    focus_task_id = str(prior_focus.get("current_task_id", "")).strip() or str(existing_link.get("task_id", "")).strip()
    focus_goal = (
        str(prior_focus.get("current_goal", "")).strip()
        or str(existing_link.get("last_goal", "")).strip()
        or str(existing_link.get("goal", "")).strip()
    )
    focus_stage = str(prior_focus.get("current_stage", "")).strip()
    focus_next_action = str(prior_focus.get("next_action", "")).strip()
    focus_status = str(prior_focus.get("status", "")).strip()
    focus_available = bool(focus_task_id or focus_goal)
    explicit_intent_type = "action_request"
    resolved_with_focus = False
    contextual_goal = goal or cleaned or str(raw_text or "").strip()
    if focus_available:
        if normalized in STATUS_FOLLOWUP_TOKENS:
            explicit_intent_type = "status_followup"
            resolved_with_focus = True
            contextual_goal = (
                f"基于当前任务上下文，汇报权威状态和下一步。"
                f" 当前任务目标：{focus_goal or focus_task_id}。"
                f" 当前阶段：{focus_stage or 'unknown'}。"
                f" 当前下一步：{focus_next_action or 'unknown'}。"
                f" 用户跟进：{goal or cleaned or raw_text}。"
            )
        elif normalized in CONTINUE_FOLLOWUP_TOKENS:
            explicit_intent_type = "continue_current_task"
            resolved_with_focus = True
            contextual_goal = (
                f"继续推进当前任务直到最终目标达成。"
                f" 当前任务目标：{focus_goal or focus_task_id}。"
                f" 当前阶段：{focus_stage or 'unknown'}。"
                f" 当前下一步：{focus_next_action or 'unknown'}。"
                f" 用户跟进：{goal or cleaned or raw_text}。"
            )
        elif _looks_contextual_followup(normalized, focus_goal):
            explicit_intent_type = "contextual_followup"
            resolved_with_focus = True
            contextual_goal = (
                f"基于当前任务上下文处理这条跟进指令。"
                f" 当前任务目标：{focus_goal or focus_task_id}。"
                f" 当前状态：{focus_status or 'unknown'} / {focus_stage or 'unknown'}。"
                f" 当前下一步：{focus_next_action or 'unknown'}。"
                f" 用户补充：{goal or cleaned or raw_text}。"
            )
    requested_mode_bundle = _derive_requested_mode(goal or cleaned or raw_text, normalized, explicit_intent_type, prior_focus)
    return {
        "generated_at": _utc_now_iso(),
        "provider": provider,
        "conversation_id": conversation_id,
        "conversation_type": conversation_type,
        "source": source,
        "message_id": str(message_id or "").strip(),
        "sender_id": str(sender_id or "").strip(),
        "sender_name": str(sender_name or "").strip(),
        "session_key": str(session_key or existing_link.get("session_key") or prior_focus.get("session_key") or "").strip(),
        "raw_text": str(raw_text or "").strip(),
        "cleaned_text": cleaned,
        "goal_text": goal,
        "normalized_text": normalized,
        "explicit_intent_type": explicit_intent_type,
        "focus_available": focus_available,
        "resolved_with_focus": resolved_with_focus,
        "focus_task_id": focus_task_id,
        "focus_goal": focus_goal,
        "focus_status": focus_status,
        "focus_stage": focus_stage,
        "focus_next_action": focus_next_action,
        "contextual_goal": contextual_goal,
        "requested_mode": str(requested_mode_bundle.get("requested_mode", "")).strip() or "interactive_session",
        "requested_mode_reason": str(requested_mode_bundle.get("requested_mode_reason", "")).strip() or "default_interactive",
    }


def _append_recent(items: List[str], candidate: str, *, limit: int = 5) -> List[str]:
    """
    中文注解：
    - 功能：维护 focus 中最近几条短历史，避免无限膨胀。
    - 角色：给“然后呢”这类跟进提供轻量上下文证据。
    """
    values = [str(item).strip() for item in (items or []) if str(item).strip()]
    text = str(candidate or "").strip()
    if text:
        values.append(text)
    return values[-limit:]


def record_conversation_context(
    route: Dict[str, Any],
    *,
    provider: str,
    conversation_id: str,
    conversation_type: str,
    session_key: str = "",
) -> Dict[str, Any]:
    """
    中文注解：
    - 功能：把最终 route 回写成当前会话的 focus 真源。
    - 输入角色：消费 route、会话元数据以及最新 authoritative snapshot。
    - 输出角色：供后续 Telegram/直连 follow-up、doctor 与 control plane 共享。
    """
    prior_focus = load_conversation_focus(provider, conversation_id)
    envelope = dict(route.get("instruction_envelope", {}) or {})
    snapshot = dict(route.get("authoritative_task_status", {}) or {})
    raw_goal = str(route.get("raw_goal", "")).strip()
    resolved_goal = str(route.get("goal", "")).strip() or raw_goal
    explicit_intent_type = str(envelope.get("explicit_intent_type", "")).strip() or "unknown"
    focus_resolved = bool(envelope.get("resolved_with_focus"))
    current_task_id = str(route.get("task_id", "")).strip() or str(prior_focus.get("current_task_id", "")).strip()
    canonical_task_id = str(snapshot.get("task_id", "")).strip() or current_task_id
    prior_goal = str(prior_focus.get("current_goal", "")).strip()
    if focus_resolved and explicit_intent_type in {"status_followup", "continue_current_task", "contextual_followup"} and prior_goal:
        current_goal = prior_goal
    else:
        current_goal = resolved_goal or prior_goal
    status = str(snapshot.get("status", "")).strip() or str(prior_focus.get("status", "")).strip()
    current_stage = str(snapshot.get("current_stage", "")).strip() or str(prior_focus.get("current_stage", "")).strip()
    next_action = str(snapshot.get("next_action", "")).strip() or str(prior_focus.get("next_action", "")).strip()
    focus = {
        "updated_at": _utc_now_iso(),
        "provider": provider,
        "conversation_id": conversation_id,
        "conversation_type": conversation_type,
        "session_key": str(session_key or envelope.get("session_key") or prior_focus.get("session_key") or "").strip(),
        "last_message_id": str(route.get("message_id", "")).strip(),
        "last_sender_id": str(route.get("sender_id", "")).strip(),
        "last_sender_name": str(route.get("sender_name", "")).strip(),
        "last_source": str(route.get("source", "")).strip(),
        "current_task_id": current_task_id,
        "canonical_task_id": canonical_task_id,
        "lineage_root_task_id": str(route.get("lineage_root_task_id", "")).strip()
        or str(snapshot.get("lineage_root_task_id", "")).strip()
        or str(prior_focus.get("lineage_root_task_id", "")).strip(),
        "current_goal": current_goal,
        "raw_goal": raw_goal,
        "status": status or "unknown",
        "current_stage": current_stage,
        "next_action": next_action,
        "route_mode": str(route.get("mode", "")).strip() or "unknown",
        "explicit_intent_type": explicit_intent_type,
        "requested_mode": str(envelope.get("requested_mode", "")).strip() or str(prior_focus.get("requested_mode", "")).strip() or "interactive_session",
        "requested_mode_reason": str(envelope.get("requested_mode_reason", "")).strip() or str(prior_focus.get("requested_mode_reason", "")).strip(),
        "resolved_mode": str(route.get("conversation_runtime_mode", "")).strip() or str(prior_focus.get("resolved_mode", "")).strip() or str(envelope.get("requested_mode", "")).strip() or "interactive_session",
        "resolved_mode_reason": str(route.get("conversation_runtime_mode_reason", "")).strip() or str(prior_focus.get("resolved_mode_reason", "")).strip() or "requested_mode_fallback",
        "focus_available_at_ingress": bool(envelope.get("focus_available")),
        "resolved_with_focus": bool(envelope.get("resolved_with_focus")),
        "recovered_link_from_focus": bool(route.get("focus_restored_link")),
        "recent_user_goals": _append_recent(prior_focus.get("recent_user_goals", []) or [], raw_goal or resolved_goal),
        "recent_route_modes": _append_recent(prior_focus.get("recent_route_modes", []) or [], str(route.get("mode", ""))),
        "context_ready": bool(current_task_id and current_goal),
        "context_summary": (
            f"{current_goal or 'unknown goal'} | {status or 'unknown'} / {current_stage or 'unknown'}"
            f" -> {next_action or 'unknown'}"
        ),
    }
    path = conversation_focus_path(provider, conversation_id)
    focus["path"] = _write_json(path, focus)
    return focus


def build_conversation_focus_registry() -> Dict[str, Any]:
    """
    中文注解：
    - 功能：把所有 focus 文件整理成 control-plane 可消费的 registry。
    - 输出角色：供 doctor/status 面板解释“哪些会话已经具备稳定上下文真源”。
    """
    rows: List[Dict[str, Any]] = []
    if CONVERSATION_FOCUS_ROOT.exists():
        for path in sorted(CONVERSATION_FOCUS_ROOT.glob("*.json")):
            payload = _read_json(path, {})
            if not payload:
                continue
            rows.append(
                {
                    "provider": str(payload.get("provider", "")).strip(),
                    "conversation_id": str(payload.get("conversation_id", "")).strip(),
                    "conversation_type": str(payload.get("conversation_type", "")).strip() or "direct",
                    "current_task_id": str(payload.get("current_task_id", "")).strip(),
                    "canonical_task_id": str(payload.get("canonical_task_id", "")).strip(),
                    "current_goal": str(payload.get("current_goal", "")).strip(),
                    "status": str(payload.get("status", "")).strip() or "unknown",
                    "current_stage": str(payload.get("current_stage", "")).strip(),
                    "next_action": str(payload.get("next_action", "")).strip(),
                    "explicit_intent_type": str(payload.get("explicit_intent_type", "")).strip() or "unknown",
                    "requested_mode": str(payload.get("requested_mode", "")).strip() or "interactive_session",
                    "resolved_mode": str(payload.get("resolved_mode", "")).strip() or str(payload.get("requested_mode", "")).strip() or "interactive_session",
                    "resolved_with_focus": bool(payload.get("resolved_with_focus")),
                    "context_ready": bool(payload.get("context_ready")),
                    "updated_at": str(payload.get("updated_at", "")).strip(),
                    "path": str(path),
                }
            )
    rows.sort(key=lambda item: (str(item.get("provider", "")), str(item.get("conversation_id", ""))))
    return {
        "generated_at": _utc_now_iso(),
        "items": rows,
        "summary": {
            "focus_total": len(rows),
            "context_ready_total": sum(1 for item in rows if item.get("context_ready")),
            "task_bound_total": sum(1 for item in rows if str(item.get("current_task_id", "")).strip()),
            "resolved_with_focus_total": sum(1 for item in rows if item.get("resolved_with_focus")),
            "status_followup_total": sum(1 for item in rows if item.get("explicit_intent_type") == "status_followup"),
            "contextual_followup_total": sum(1 for item in rows if item.get("explicit_intent_type") == "contextual_followup"),
            "interactive_mode_total": sum(1 for item in rows if item.get("resolved_mode") == "interactive_session"),
            "mission_mode_total": sum(1 for item in rows if item.get("resolved_mode") == "mission_runtime"),
        },
    }
