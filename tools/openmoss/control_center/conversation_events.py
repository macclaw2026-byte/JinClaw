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
- 文件路径：`tools/openmoss/control_center/conversation_events.py`
- 文件作用：为不同 transport 记录统一的会话事件流真源。
- 顶层函数：conversation_event_key、conversation_event_path、record_conversation_event、load_conversation_events、build_conversation_event_registry。
- 顶层类：无顶层类。
- 阅读建议：先看事件落盘，再看 registry 聚合。
"""
from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

from paths import CONVERSATION_EVENT_REGISTRY_PATH, CONVERSATION_EVENTS_ROOT


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def conversation_event_key(provider: str, conversation_id: str) -> str:
    safe_provider = str(provider or "").strip().replace("/", "-") or "unknown"
    safe_conversation = str(conversation_id or "").strip().replace("/", "-") or "unknown"
    return f"{safe_provider}__{safe_conversation}"


def conversation_event_path(provider: str, conversation_id: str) -> Path:
    return CONVERSATION_EVENTS_ROOT / f"{conversation_event_key(provider, conversation_id)}.jsonl"


def record_conversation_event(
    *,
    provider: str,
    conversation_id: str,
    event_type: str,
    payload: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    """
    中文注解：
    - 功能：把一条 transport-neutral conversation event 追加写入事件流。
    - 输入角色：消费 ingress / route / receipt / doctor notice 等结构化事件。
    - 输出角色：供 doctor、control plane、未来 transport projector 读取真源。
    """
    event = {
        "event_id": uuid.uuid4().hex,
        "recorded_at": _utc_now_iso(),
        "provider": str(provider or "").strip(),
        "conversation_id": str(conversation_id or "").strip(),
        "event_type": str(event_type or "").strip() or "unknown",
        "payload": dict(payload or {}),
    }
    path = conversation_event_path(provider, conversation_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(event, ensure_ascii=False) + "\n")
    event["path"] = str(path)
    return event


def load_conversation_events(provider: str, conversation_id: str, *, limit: int = 50) -> List[Dict[str, Any]]:
    """
    中文注解：
    - 功能：读取指定会话最近几条 conversation events。
    - 输出角色：供 tests / doctor / projector 对账。
    """
    path = conversation_event_path(provider, conversation_id)
    if not path.exists():
        return []
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return []
    rows: List[Dict[str, Any]] = []
    for line in lines[-limit:]:
        try:
            rows.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return rows


def build_conversation_event_registry() -> Dict[str, Any]:
    """
    中文注解：
    - 功能：把 conversation event 流整理成 control-plane 可消费的 registry。
    - 输出角色：供 doctor/status 判断 transport parity 的事件链是否完整。
    """
    rows: List[Dict[str, Any]] = []
    if CONVERSATION_EVENTS_ROOT.exists():
        for path in sorted(CONVERSATION_EVENTS_ROOT.glob("*.jsonl")):
            try:
                lines = path.read_text(encoding="utf-8").splitlines()
            except OSError:
                continue
            events: List[Dict[str, Any]] = []
            for line in lines[-100:]:
                try:
                    events.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
            if not events:
                continue
            latest = events[-1]
            event_types = [str(item.get("event_type", "")).strip() for item in events if str(item.get("event_type", "")).strip()]
            latest_payload = latest.get("payload", {}) or {}
            rows.append(
                {
                    "provider": str(latest.get("provider", "")).strip(),
                    "conversation_id": str(latest.get("conversation_id", "")).strip(),
                    "event_total": len(events),
                    "latest_event_type": str(latest.get("event_type", "")).strip(),
                    "latest_task_id": str(latest_payload.get("task_id", "")).strip(),
                    "latest_mode": str(latest_payload.get("mode", "")).strip(),
                    "latest_message_kind": str((latest_payload.get("reply_projection", {}) or {}).get("message_kind", "")).strip(),
                    "latest_recorded_at": str(latest.get("recorded_at", "")).strip(),
                    "path": str(path),
                    "has_ingress_event": "ingress_received" in event_types,
                    "has_route_event": "route_resolved" in event_types,
                    "has_reply_event": "reply_projection_emitted" in event_types,
                }
            )
    rows.sort(key=lambda item: (str(item.get("provider", "")), str(item.get("conversation_id", ""))))
    registry = {
        "generated_at": _utc_now_iso(),
        "items": rows,
        "summary": {
            "conversation_total": len(rows),
            "event_total": sum(int(item.get("event_total", 0) or 0) for item in rows),
            "with_ingress_total": sum(1 for item in rows if item.get("has_ingress_event")),
            "with_route_total": sum(1 for item in rows if item.get("has_route_event")),
            "with_reply_total": sum(1 for item in rows if item.get("has_reply_event")),
        },
    }
    CONVERSATION_EVENT_REGISTRY_PATH.parent.mkdir(parents=True, exist_ok=True)
    CONVERSATION_EVENT_REGISTRY_PATH.write_text(json.dumps(registry, ensure_ascii=False, indent=2), encoding="utf-8")
    registry["path"] = str(CONVERSATION_EVENT_REGISTRY_PATH)
    return registry
