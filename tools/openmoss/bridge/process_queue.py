#!/usr/bin/env python3

from __future__ import annotations

import argparse
import json
import uuid
from datetime import datetime
from pathlib import Path

from common import (
    append_jsonl,
    conversation_session_key,
    ensure_bridge_layout,
    load_bridge_config,
    queue_counts,
    read_json,
    utc_now_iso,
    write_bridge_status,
    write_json_atomic,
)


def _processed_jsonl_path(processed_dir: Path, conversation_id: str) -> Path:
    now = datetime.utcnow()
    return (
        processed_dir
        / now.strftime("%Y")
        / now.strftime("%m")
        / now.strftime("%d")
        / f"{conversation_id}.jsonl"
    )


def _dispatch_file_name() -> str:
    return f"dispatch-{datetime.utcnow().strftime('%Y%m%dT%H%M%S')}-{uuid.uuid4().hex[:8]}.json"


def process_one(message_file: Path) -> dict:
    cfg = load_bridge_config()
    message = read_json(message_file, {})
    provider = str(message.get("provider") or cfg.provider)
    conversation_id = str(message.get("conversation_id") or "unknown")
    conversation_type = str(message.get("conversation_type") or "group")
    session_key = conversation_session_key(cfg, provider, conversation_id, conversation_type)

    session_state_file = cfg.sessions_dir / f"{conversation_id}.json"
    session_state = read_json(session_state_file, {})
    session_state.update(
        {
            "conversation_id": conversation_id,
            "provider": provider,
            "session_key": session_key,
            "conversation_type": conversation_type,
            "last_sender_id": message.get("sender_id"),
            "last_sender_name": message.get("sender_name"),
            "last_message_id": message.get("id"),
            "last_message_preview": str(message.get("content", ""))[:200],
            "updated_at": utc_now_iso(),
        }
    )
    write_json_atomic(session_state_file, session_state)

    dispatch_payload = {
        "dispatch_id": uuid.uuid4().hex,
        "created_at": utc_now_iso(),
        "provider": provider,
        "conversation_id": conversation_id,
        "conversation_type": conversation_type,
        "session_key": session_key,
        "message": message,
        "dispatch_mode": cfg.wake_mode,
        "dry_run": cfg.dry_run,
    }
    dispatch_path = cfg.dispatch_dir / _dispatch_file_name()
    write_json_atomic(dispatch_path, dispatch_payload)

    archive_path = _processed_jsonl_path(cfg.processed_dir, conversation_id)
    archived = dict(message)
    archived["_processed_at"] = utc_now_iso()
    archived["_dispatch_file"] = str(dispatch_path)
    append_jsonl(archive_path, archived)

    message_file.unlink()
    return {
        "message_id": message.get("id"),
        "conversation_id": conversation_id,
        "session_key": session_key,
        "dispatch_file": str(dispatch_path),
        "archive_file": str(archive_path),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Process local OpenMOSS bridge inbox")
    parser.add_argument("--limit", type=int, default=20)
    args = parser.parse_args()

    cfg = load_bridge_config()
    ensure_bridge_layout(cfg)
    inbox_files = sorted(cfg.inbox_dir.glob("*.json"))[: args.limit]
    results = [process_one(path) for path in inbox_files]
    write_bridge_status(
        cfg,
        status="queue_processed",
        processed_count=len(results),
        queue_counts=queue_counts(cfg),
        last_dispatch=results[-1] if results else None,
    )
    print(json.dumps({"processed": results, "count": len(results)}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
