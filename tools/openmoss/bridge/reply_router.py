#!/usr/bin/env python3

from __future__ import annotations

import argparse
import json
import uuid
from datetime import datetime

from common import ensure_bridge_layout, load_bridge_config, read_json, utc_now_iso, write_bridge_status, write_json_atomic


def _outbox_name() -> str:
    return f"reply-{datetime.utcnow().strftime('%Y%m%dT%H%M%S')}-{uuid.uuid4().hex[:8]}.json"


def main() -> int:
    parser = argparse.ArgumentParser(description="Queue outbound replies for the OpenMOSS bridge")
    parser.add_argument("--conversation-id", required=True)
    parser.add_argument("--text", required=True)
    parser.add_argument("--provider", default="")
    parser.add_argument("--session-key", default="")
    parser.add_argument("--sender-role", default="assistant")
    args = parser.parse_args()

    cfg = load_bridge_config()
    ensure_bridge_layout(cfg)

    provider = args.provider or cfg.provider
    session_key = args.session_key
    if not session_key:
        session_file = cfg.sessions_dir / f"{args.conversation_id}.json"
        session_state = read_json(session_file, {})
        session_key = session_state.get("session_key", "")

    payload = {
        "reply_id": uuid.uuid4().hex,
        "created_at": utc_now_iso(),
        "provider": provider,
        "conversation_id": args.conversation_id,
        "session_key": session_key,
        "sender_role": args.sender_role,
        "text": args.text,
        "attachments": [],
        "delivery_mode": "queued",
        "dry_run": cfg.dry_run,
    }
    out_path = cfg.outbox_dir / _outbox_name()
    write_json_atomic(out_path, payload)
    write_bridge_status(
        cfg,
        status="reply_queued",
        last_outbound_file=str(out_path),
        last_conversation_id=args.conversation_id,
    )
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
