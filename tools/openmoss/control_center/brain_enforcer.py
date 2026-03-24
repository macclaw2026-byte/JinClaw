#!/usr/bin/env python3

from __future__ import annotations

import json
from pathlib import Path
from typing import Dict, List

from brain_router import route_instruction
from paths import BRAIN_ROUTES_ROOT

SESSIONS_ROOT = Path("/Users/mac_claw/.openclaw/agents/main/sessions")
MAIN_SESSION_KEY = "agent:main:main"
MAIN_SESSION_REGISTRY = SESSIONS_ROOT / "sessions.json"


def _load_json(path: Path):
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def _load_main_session_messages(limit: int = 20) -> List[Dict[str, object]]:
    registry = _load_json(MAIN_SESSION_REGISTRY)
    session_info = registry.get(MAIN_SESSION_KEY, {})
    session_file = str(session_info.get("sessionFile") or "")
    session_id = str(session_info.get("sessionId") or "")
    if session_file:
        transcript = Path(session_file)
    elif session_id:
        transcript = SESSIONS_ROOT / f"{session_id}.jsonl"
    else:
        return []
    if not transcript.exists():
        return []
    lines = transcript.read_text(encoding="utf-8").splitlines()[-limit:]
    records = []
    for line in lines:
        try:
            records.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return records


def enforce_brain_first(limit: int = 20) -> Dict[str, object]:
    messages = _load_main_session_messages(limit=limit)
    latest_user = None
    for record in reversed(messages):
        message = record.get("message", {})
        if message.get("role") != "user":
            continue
        content = message.get("content", [])
        text_parts = [part.get("text", "") for part in content if part.get("type") == "text"]
        text = "\n".join(part for part in text_parts if part).strip()
        if text:
            latest_user = {
                "message_id": record.get("id", ""),
                "text": text,
                "timestamp": record.get("timestamp", ""),
            }
            break
    if not latest_user:
        return {"status": "no_user_message"}

    route = route_instruction(
        provider="openclaw-main",
        conversation_id="main",
        conversation_type="direct",
        text=latest_user["text"],
        source="brain_enforcer",
        sender_id="user",
        sender_name="openclaw-user",
        message_id=str(latest_user["message_id"]),
        session_key="agent:main:main",
    )
    return {
        "status": "routed",
        "latest_user_message": latest_user,
        "route": route,
        "route_store": str(BRAIN_ROUTES_ROOT / "openclaw-main" / "main.json"),
    }


def main() -> int:
    import argparse

    parser = argparse.ArgumentParser(description="Ensure ordinary main-session instructions are routed through the control-center brain")
    parser.add_argument("--limit", type=int, default=20)
    args = parser.parse_args()
    print(json.dumps(enforce_brain_first(limit=args.limit), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
