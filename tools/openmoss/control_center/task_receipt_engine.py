#!/usr/bin/env python3

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict

from paths import BRAIN_RECEIPTS_ROOT, OPENCLAW_SESSIONS_ROOT
from response_policy_engine import build_route_receipt_text


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _write_json(path: Path, payload: Dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _load_sessions_registry() -> Dict[str, object]:
    registry_path = OPENCLAW_SESSIONS_ROOT / "sessions.json"
    if not registry_path.exists():
        return {}
    try:
        return json.loads(registry_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def _session_file_for_key(session_key: str) -> Path | None:
    registry = _load_sessions_registry()
    session_info = registry.get(session_key, {}) if isinstance(registry, dict) else {}
    session_file = str(session_info.get("sessionFile") or "").strip()
    if session_file:
        path = Path(session_file)
        if path.exists():
            return path
    session_id = str(session_info.get("sessionId") or "").strip()
    if session_id:
        path = OPENCLAW_SESSIONS_ROOT / f"{session_id}.jsonl"
        if path.exists():
            return path
    return None


def _append_session_receipt(session_key: str, text: str) -> Dict[str, object]:
    session_file = _session_file_for_key(session_key)
    if not session_file:
        return {"delivered": False, "reason": "session_file_not_found", "session_key": session_key}
    last_id = ""
    try:
        lines = session_file.read_text(encoding="utf-8", errors="ignore").splitlines()
    except OSError as exc:
        return {"delivered": False, "reason": f"session_read_failed:{exc}", "session_key": session_key}
    for line in reversed(lines):
        try:
            payload = json.loads(line)
        except json.JSONDecodeError:
            continue
        last_id = str(payload.get("id", "")).strip()
        if last_id:
            break
    message_id = uuid.uuid4().hex[:8]
    timestamp = datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    record = {
        "type": "message",
        "id": message_id,
        "parentId": last_id,
        "timestamp": timestamp,
        "message": {
            "role": "assistant",
            "content": [
                {
                    "type": "text",
                    "text": f"[[reply_to_current]] {text}",
                }
            ],
            "timestamp": int(datetime.now(timezone.utc).timestamp() * 1000),
        },
    }
    with session_file.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(record, ensure_ascii=False) + "\n")
    registry = _load_sessions_registry()
    if isinstance(registry, dict) and session_key in registry:
        registry[session_key]["updatedAt"] = int(datetime.now(timezone.utc).timestamp() * 1000)
        (OPENCLAW_SESSIONS_ROOT / "sessions.json").write_text(json.dumps(registry, ensure_ascii=False, indent=2), encoding="utf-8")
    return {
        "delivered": True,
        "session_key": session_key,
        "session_file": str(session_file),
        "message_id": message_id,
    }


def session_has_assistant_reply_after(session_key: str, user_message_id: str) -> bool:
    session_file = _session_file_for_key(session_key)
    if not session_file or not user_message_id:
        return False
    try:
        lines = session_file.read_text(encoding="utf-8", errors="ignore").splitlines()
    except OSError:
        return False
    seen_user = False
    for line in lines:
        try:
            payload = json.loads(line)
        except json.JSONDecodeError:
            continue
        if str(payload.get("id", "")).strip() == str(user_message_id).strip():
            seen_user = True
            continue
        if not seen_user:
            continue
        message = payload.get("message", {}) or {}
        if message.get("role") == "assistant":
            return True
    return False


def build_receipt_text(route: Dict[str, object]) -> str:
    return build_route_receipt_text(route)


def emit_route_receipt(route: Dict[str, object], *, provider: str, conversation_id: str, session_key: str = "") -> Dict[str, object]:
    text = build_receipt_text(route)
    receipt = {
        "receipt_id": uuid.uuid4().hex,
        "created_at": _utc_now_iso(),
        "provider": provider,
        "conversation_id": conversation_id,
        "task_id": route.get("task_id", ""),
        "mode": route.get("mode", ""),
        "text": text,
        "session_key": session_key,
    }
    _write_json(BRAIN_RECEIPTS_ROOT / provider / f"{conversation_id}.json", receipt)
    delivery = {"delivered": False, "reason": "no_session_key"}
    if session_key:
        delivery = _append_session_receipt(session_key, text)
    receipt["delivery"] = delivery
    _write_json(BRAIN_RECEIPTS_ROOT / provider / f"{conversation_id}.json", receipt)
    return receipt
