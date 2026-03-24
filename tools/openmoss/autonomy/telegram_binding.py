#!/usr/bin/env python3

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from manager import build_args, contract_path, create_task, log_ingress, read_link, utc_now_iso, write_link
from task_ingress import slugify

BRIDGE_DIR = Path("/Users/mac_claw/.openclaw/workspace/tools/openmoss/bridge")
if str(BRIDGE_DIR) not in sys.path:
    sys.path.insert(0, str(BRIDGE_DIR))
from common import conversation_session_key, load_bridge_config

CONTROL_CENTER_DIR = Path("/Users/mac_claw/.openclaw/workspace/tools/openmoss/control_center")
if str(CONTROL_CENTER_DIR) not in sys.path:
    sys.path.insert(0, str(CONTROL_CENTER_DIR))

from brain_router import route_instruction


def bind_telegram_message(
    chat_id: str,
    chat_type: str,
    sender_id: str,
    sender_name: str,
    message_id: str,
    text: str,
) -> dict:
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
    cfg = load_bridge_config()
    linked = read_link("telegram", chat_id)
    if linked:
        linked["session_key"] = conversation_session_key(cfg, "telegram", chat_id, chat_type)
        linked["updated_at"] = utc_now_iso()
        linked["last_message_id"] = message_id
        linked["last_sender_id"] = sender_id
        linked["last_sender_name"] = sender_name
        result["active_task"] = linked.get("task_id")
        result["mode"] = brain_route.get("mode", "append_to_existing_task")
        result["brain_route"] = brain_route
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
    return result


def main() -> int:
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
