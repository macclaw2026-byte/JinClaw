#!/usr/bin/env python3

from __future__ import annotations

import argparse
import json
import sys
import uuid

from pathlib import Path

BRIDGE_DIR = Path("/Users/mac_claw/.openclaw/workspace/tools/openmoss/bridge")
if str(BRIDGE_DIR) not in sys.path:
    sys.path.insert(0, str(BRIDGE_DIR))
AUTONOMY_DIR = Path("/Users/mac_claw/.openclaw/workspace/tools/openmoss/autonomy")
if str(AUTONOMY_DIR) not in sys.path:
    sys.path.insert(0, str(AUTONOMY_DIR))

from common import BRIDGE_STATE_ROOT, conversation_session_key, load_bridge_config, utc_now_iso, write_json_atomic
from telegram_binding import bind_telegram_message


def main() -> int:
    parser = argparse.ArgumentParser(description="Queue Telegram-native OpenMOSS dispatches into bridge runtime")
    parser.add_argument("--chat-id", required=True)
    parser.add_argument("--chat-type", default="group")
    parser.add_argument("--sender-id", required=True)
    parser.add_argument("--sender-name", default="telegram-user")
    parser.add_argument("--text", required=True)
    args = parser.parse_args()

    cfg = load_bridge_config()
    inbox_dir = BRIDGE_STATE_ROOT / "inbox"
    inbox_dir.mkdir(parents=True, exist_ok=True)
    message = {
        "id": uuid.uuid4().hex,
        "provider": "telegram",
        "conversation_id": args.chat_id,
        "conversation_type": args.chat_type,
        "sender_id": args.sender_id,
        "sender_name": args.sender_name,
        "content": args.text,
        "attachments": [],
        "received_at": utc_now_iso(),
        "source": "telegram-openmoss-bridge",
        "session_key_preview": conversation_session_key(cfg, "telegram", args.chat_id, args.chat_type),
    }
    out_path = inbox_dir / f"telegram-{message['id']}.json"
    write_json_atomic(out_path, message)
    autonomy = bind_telegram_message(
        chat_id=args.chat_id,
        chat_type=args.chat_type,
        sender_id=args.sender_id,
        sender_name=args.sender_name,
        message_id=message["id"],
        text=args.text,
    )
    print(
        json.dumps(
            {
                "queued": str(out_path),
                "session_key": message["session_key_preview"],
                "autonomy": autonomy,
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
