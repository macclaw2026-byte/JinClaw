#!/usr/bin/env python3

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict

from paths import BRAIN_RECEIPTS_ROOT, OPENCLAW_SESSIONS_ROOT


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
    mode = str(route.get("mode", "instant_reply_only"))
    task_id = str(route.get("task_id", "")).strip()
    goal = str(route.get("goal", "")).strip()
    if mode == "authoritative_task_status":
        snapshot = route.get("authoritative_task_status", {}) or {}
        return str(snapshot.get("authoritative_summary", "")).strip() or f"当前任务状态已刷新，任务 ID: {task_id or 'unknown'}。"
    if mode in {"create_new_root_task", "create_or_attach"}:
        return f"已识别为新任务，任务 ID: {task_id}。我会先进入 understand 阶段，梳理目标、约束和所需条件，然后继续推进。"
    if mode in {"create_successor_task", "branch_from_active_task", "append_to_active_successor_task"}:
        return f"已识别为后续任务，任务 ID: {task_id}。我会在当前链路上继续推进，并在遇到明确阻塞时如实反馈。"
    if mode == "append_to_existing_task":
        return f"已把这条新指令挂到当前任务 {task_id}，会继续按现有任务链推进。"
    return f"已收到任务型指令。当前路由模式: {mode}。任务 ID: {task_id or '未创建'}。"


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
