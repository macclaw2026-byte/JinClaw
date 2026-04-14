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
- 文件路径：`tools/openmoss/autonomy/telegram_binding.py`
- 文件作用：负责Telegram 消息接入与任务绑定入口。
- 顶层函数：bind_telegram_message、main。
- 顶层类：无顶层类。
- 阅读建议：先看模块说明，再按函数/类 docstring 顺着主流程理解调用关系。
"""
from __future__ import annotations

import argparse
import json

from transport_binding import bind_transport_message


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
    return bind_transport_message(
        provider="telegram",
        conversation_id=chat_id,
        conversation_type=chat_type,
        sender_id=sender_id,
        sender_name=sender_name,
        message_id=message_id,
        text=text,
        source="telegram",
        session_key=telegram_session_key(chat_id, chat_type),
        emit_receipt=True,
    )


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
