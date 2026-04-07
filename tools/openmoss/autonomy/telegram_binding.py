#!/usr/bin/env python3

"""
中文说明：
- 文件路径：`tools/openmoss/autonomy/telegram_binding.py`
- 文件作用：负责Telegram 消息接入与任务绑定入口。
- 顶层函数：bind_telegram_message、main。
- 顶层类：无顶层类。
- 阅读建议：先看模块说明，再按函数/类 docstring 顺着主流程理解调用关系。
"""
from __future__ import annotations

import argparse
import json

from manager import build_args, contract_path, create_task, log_ingress, read_link, utc_now_iso, write_link
from task_ingress import slugify

from brain_router import route_instruction
from route_guardrails import persist_route, reroot_route_if_needed
from task_receipt_engine import emit_route_receipt


def telegram_session_key(chat_id: str, chat_type: str) -> str:
    """
    中文注解：
    - 功能：根据 Telegram 会话信息直接生成 OpenClaw/JinClaw 使用的 session key。
    - 角色：这是 Telegram 接入的本地辅助函数，用来替代已经退役的 bridge `conversation_session_key` 依赖。
    - 调用关系：仅由 `bind_telegram_message` 调用，避免主接入链再依赖 `tools/openmoss/bridge/`。
    """
    convo_type = (chat_type or "group").strip().lower()
    chat_norm = str(chat_id).strip()
    if chat_norm.startswith("-") or convo_type == "group":
        return f"agent:main:telegram:group:{chat_norm}"
    return f"agent:main:telegram:direct:{chat_norm}"


def bind_telegram_message(
    chat_id: str,
    chat_type: str,
    sender_id: str,
    sender_name: str,
    message_id: str,
    text: str,
) -> dict:
    """
    中文注解：
    - 功能：实现 `bind_telegram_message` 对应的处理逻辑。
    - 角色：属于本模块中的对外可见逻辑；私有函数通常服务同文件主流程，公共函数通常作为跨模块入口或能力接口。
    - 调用关系：建议结合本文件的模块说明、调用方以及同名相关辅助函数一起阅读。
    """
    ingress = {
        "provider": "telegram",
        "conversation_id": chat_id,
        "conversation_type": chat_type,
        "sender_id": sender_id,
        "sender_name": sender_name,
        "message_id": message_id,
        "text": text,
    }
    log_ingress("telegram", ingress)

    existing = read_link("telegram", chat_id)
    result = {
        "accepted_at": utc_now_iso(),
        "conversation_id": chat_id,
        "message_id": message_id,
        "created_task": None,
        "active_task": existing.get("task_id"),
        "mode": "ignored",
    }

    brain_route = route_instruction(
        provider="telegram",
        conversation_id=chat_id,
        conversation_type=chat_type,
        text=text,
        source="telegram",
        sender_id=sender_id,
        sender_name=sender_name,
        message_id=message_id,
    )
    session_key = telegram_session_key(chat_id, chat_type)
    brain_route = reroot_route_if_needed(
        route=brain_route,
        provider="telegram",
        conversation_id=chat_id,
        conversation_type=chat_type,
        goal=str(brain_route.get("goal") or text),
        session_key=session_key,
    )
    persist_route("telegram", chat_id, brain_route)
    receipt = emit_route_receipt(
        brain_route,
        provider="telegram",
        conversation_id=chat_id,
        session_key=session_key,
    )
    linked = read_link("telegram", chat_id)
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
        result["link_path"] = write_link("telegram", chat_id, linked)
        result["created_task"] = brain_route.get("task_id") if brain_route.get("created_task") else None
        return result

    if existing:
        existing["updated_at"] = utc_now_iso()
        existing["last_message_id"] = message_id
        existing["last_sender_id"] = sender_id
        existing["last_sender_name"] = sender_name
        result["active_task"] = existing.get("task_id")
        result["mode"] = "append_to_existing_task"
        result["link_path"] = write_link("telegram", chat_id, existing)
    result["brain_route"] = brain_route
    result["receipt"] = receipt
    return result


def main() -> int:
    """
    中文注解：
    - 功能：实现 `main` 对应的处理逻辑。
    - 角色：属于本模块中的对外可见逻辑；私有函数通常服务同文件主流程，公共函数通常作为跨模块入口或能力接口。
    - 调用关系：建议结合本文件的模块说明、调用方以及同名相关辅助函数一起阅读。
    """
    parser = argparse.ArgumentParser(description="Bind Telegram ingress directly into the autonomy runtime")
    parser.add_argument("--chat-id", required=True)
    parser.add_argument("--chat-type", default="group")
    parser.add_argument("--sender-id", required=True)
    parser.add_argument("--sender-name", default="telegram-user")
    parser.add_argument("--message-id", required=True)
    parser.add_argument("--text", required=True)
    args = parser.parse_args()

    result = bind_telegram_message(
        chat_id=args.chat_id,
        chat_type=args.chat_type,
        sender_id=args.sender_id,
        sender_name=args.sender_name,
        message_id=args.message_id,
        text=args.text,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
