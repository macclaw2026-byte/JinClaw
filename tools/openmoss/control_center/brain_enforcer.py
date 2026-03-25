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
ENFORCER_STATE_PATH = BRAIN_ROUTES_ROOT / "openclaw-main" / "brain_enforcer_state.json"


def _load_json(path: Path):
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, payload: Dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _is_internal_runtime_request(text: str) -> bool:
    normalized = text.strip()
    return (
        "[Autonomy runtime execution request]" in normalized
        and "task_id:" in normalized
        and "stage:" in normalized
        and "user_goal:" in normalized
    )


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
    state = _load_json(ENFORCER_STATE_PATH)
    last_external_message_id = str(state.get("last_external_message_id", ""))
    latest_user = None
    for record in reversed(messages):
        message = record.get("message", {})
        if message.get("role") != "user":
            continue
        content = message.get("content", [])
        text_parts = [part.get("text", "") for part in content if part.get("type") == "text"]
        text = "\n".join(part for part in text_parts if part).strip()
        if text and not _is_internal_runtime_request(text):
            latest_user = {
                "message_id": record.get("id", ""),
                "text": text,
                "timestamp": record.get("timestamp", ""),
            }
            break
    if not latest_user:
        return {"status": "no_external_user_message"}
    if str(latest_user["message_id"]) == last_external_message_id:
        return {
            "status": "no_new_external_user_message",
            "latest_user_message": latest_user,
            "route_store": str(BRAIN_ROUTES_ROOT / "openclaw-main" / "main.json"),
        }

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
    _write_json(
        ENFORCER_STATE_PATH,
        {
            "last_external_message_id": str(latest_user["message_id"]),
            "last_external_timestamp": str(latest_user["timestamp"]),
            "last_routed_at": route.get("routed_at", ""),
        },
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
