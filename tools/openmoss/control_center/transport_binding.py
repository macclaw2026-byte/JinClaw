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
- 文件路径：`tools/openmoss/control_center/transport_binding.py`
- 文件作用：为 Telegram / OpenClaw 主会话等不同 transport 提供统一的 ingress 绑定内核。
- 顶层函数：`bind_transport_message`。
- 顶层类：无。
- 阅读建议：先看 `bind_transport_message`，再结合 `telegram_binding.py` 与 `brain_enforcer.py` 的调用关系理解 transport parity。
"""
from __future__ import annotations

from typing import Any, Dict

from manager import log_ingress, read_link, utc_now_iso, write_link

from brain_router import route_instruction
from conversation_events import record_conversation_event
from route_guardrails import persist_route, reroot_route_if_needed
from task_receipt_engine import emit_route_receipt


def bind_transport_message(
    *,
    provider: str,
    conversation_id: str,
    conversation_type: str,
    sender_id: str,
    sender_name: str,
    message_id: str,
    text: str,
    source: str,
    session_key: str,
    emit_receipt: bool = True,
) -> Dict[str, Any]:
    """
    中文注解：
    - 功能：把 transport 的 ingress、brain route、route persistence、receipt emission 收敛为统一绑定内核。
    - 输入角色：消费 Telegram / openclaw-main 等 transport 的消息元数据与 session key。
    - 输出角色：向调用方返回结构化 route / receipt / link 结果，避免每个 transport 再复制一条近似逻辑链。
    """
    ingress = {
        "provider": provider,
        "conversation_id": conversation_id,
        "conversation_type": conversation_type,
        "sender_id": sender_id,
        "sender_name": sender_name,
        "message_id": message_id,
        "text": text,
        "source": source,
        "session_key": session_key,
    }
    log_ingress(provider, ingress)

    existing = read_link(provider, conversation_id)
    result: Dict[str, Any] = {
        "accepted_at": utc_now_iso(),
        "provider": provider,
        "conversation_id": conversation_id,
        "conversation_type": conversation_type,
        "message_id": message_id,
        "created_task": None,
        "active_task": existing.get("task_id"),
        "mode": "ignored",
        "session_key": session_key,
        "source": source,
    }
    record_conversation_event(
        provider=provider,
        conversation_id=conversation_id,
        event_type="ingress_received",
        payload={
            "message_id": message_id,
            "sender_id": sender_id,
            "sender_name": sender_name,
            "text": text,
            "conversation_type": conversation_type,
            "session_key": session_key,
            "source": source,
        },
    )

    brain_route = route_instruction(
        provider=provider,
        conversation_id=conversation_id,
        conversation_type=conversation_type,
        text=text,
        source=source,
        sender_id=sender_id,
        sender_name=sender_name,
        message_id=message_id,
        session_key=session_key,
    )
    brain_route = reroot_route_if_needed(
        route=brain_route,
        provider=provider,
        conversation_id=conversation_id,
        conversation_type=conversation_type,
        goal=str(brain_route.get("goal") or text),
        session_key=session_key,
    )
    route_store = persist_route(provider, conversation_id, brain_route)
    receipt = (
        emit_route_receipt(
            brain_route,
            provider=provider,
            conversation_id=conversation_id,
            session_key=session_key,
        )
        if emit_receipt
        else {}
    )

    linked = read_link(provider, conversation_id)
    if linked:
        linked["session_key"] = session_key
        linked["updated_at"] = utc_now_iso()
        linked["last_message_id"] = message_id
        linked["last_sender_id"] = sender_id
        linked["last_sender_name"] = sender_name
        result["active_task"] = linked.get("task_id")
        result["mode"] = brain_route.get("mode", "append_to_existing_task")
        result["brain_route"] = brain_route
        result["receipt"] = receipt
        result["route_store"] = route_store
        result["link_path"] = write_link(provider, conversation_id, linked)
        result["created_task"] = brain_route.get("task_id") if brain_route.get("created_task") else None
        return result

    if existing:
        existing["updated_at"] = utc_now_iso()
        existing["last_message_id"] = message_id
        existing["last_sender_id"] = sender_id
        existing["last_sender_name"] = sender_name
        existing["session_key"] = session_key
        result["active_task"] = existing.get("task_id")
        result["mode"] = "append_to_existing_task"
        result["link_path"] = write_link(provider, conversation_id, existing)
    result["brain_route"] = brain_route
    result["receipt"] = receipt
    result["route_store"] = route_store
    return result
