#!/usr/bin/env python3

from __future__ import annotations

import json
import re
import time
from pathlib import Path
from typing import Dict, List, Tuple

from brain_router import route_instruction
from goal_sanitizer import sanitize_goal_text
from paths import BRAIN_ROUTES_ROOT
from route_guardrails import persist_route, reroot_route_if_needed
from task_receipt_engine import emit_route_receipt, session_has_assistant_reply_after

SESSIONS_ROOT = Path("/Users/mac_claw/.openclaw/agents/main/sessions")
MAIN_SESSION_KEY = "agent:main:main"
MAIN_SESSION_REGISTRY = SESSIONS_ROOT / "sessions.json"
ENFORCER_STATE_PATH = BRAIN_ROUTES_ROOT / "openclaw-main" / "brain_enforcer_state.json"
LINKS_ROOT = Path("/Users/mac_claw/.openclaw/workspace/tools/openmoss/runtime/autonomy/links")
TASKS_ROOT = Path("/Users/mac_claw/.openclaw/workspace/tools/openmoss/runtime/autonomy/tasks")


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


def _strip_untrusted_metadata_wrapper(text: str) -> str:
    return sanitize_goal_text(str(text or ""))


def _looks_like_transport_noise(original_text: str, cleaned_text: str) -> bool:
    raw = str(original_text or "")
    cleaned = str(cleaned_text or "").strip()
    normalized = re.sub(r"\s+", "", cleaned)
    if not cleaned:
        return True
    if "Read HEARTBEAT.md if it exists" in raw or "Current time:" in raw:
        return True
    if raw.count("System:") >= 1 and normalized in {"?", "？", "done"}:
        return True
    if raw.count("System:") >= 2 and len(normalized) <= 8:
        return True
    return False


def _load_task_contract_payload(task_id: str) -> Dict[str, object]:
    path = TASKS_ROOT / task_id / "contract.json"
    return _load_json(path) if path.exists() else {}


def _load_task_state_payload(task_id: str) -> Dict[str, object]:
    path = TASKS_ROOT / task_id / "state.json"
    return _load_json(path) if path.exists() else {}


def _goal_looks_like_transport_noise(goal: str) -> bool:
    normalized = re.sub(r"\s+", "", str(goal or ""))
    if not normalized:
        return True
    if "ReadHEARTBEAT.mdifitexists" in normalized or "Currenttime:" in normalized:
        return True
    if normalized in {"?", "？", "好", "好的"}:
        return False
    if normalized.count("System:") >= 1 and "Queued#1" in normalized:
        return True
    if normalized.count("System:") >= 2:
        return True
    return False


def _find_active_root_mission_task_id() -> str:
    candidates: list[str] = []
    if not TASKS_ROOT.exists():
        return ""
    for task_root in sorted(TASKS_ROOT.iterdir()):
        if not task_root.is_dir():
            continue
        contract = _load_task_contract_payload(task_root.name)
        metadata = contract.get("metadata", {}) or {}
        control_center = metadata.get("control_center", {}) or {}
        is_root = bool(metadata.get("root_mission")) or bool(control_center.get("mission_profile_id"))
        if not is_root:
            continue
        state = _load_task_state_payload(task_root.name)
        if str(state.get("status", "")).strip() in {"completed", "failed"}:
            continue
        candidates.append(task_root.name)
    return candidates[-1] if candidates else ""


def _repair_noisy_main_link() -> Dict[str, object] | None:
    link_path = LINKS_ROOT / "openclaw-main__main.json"
    payload = _load_json(link_path)
    if not payload:
        return None
    if not _goal_looks_like_transport_noise(str(payload.get("goal", ""))):
        return None
    target_task_id = _find_active_root_mission_task_id()
    if not target_task_id or target_task_id == str(payload.get("task_id", "")).strip():
        return None
    contract = _load_task_contract_payload(target_task_id)
    payload["task_id"] = target_task_id
    payload["goal"] = str(contract.get("user_goal", "")).strip() or str(payload.get("goal", "")).strip()
    payload["updated_at"] = str(int(time.time() * 1000))
    _write_json(link_path, payload)
    return {
        "repaired": True,
        "task_id": target_task_id,
        "link_path": str(link_path),
    }


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


def _latest_external_user_message(records: List[Dict[str, object]]) -> Dict[str, object] | None:
    for record in reversed(records):
        message = record.get("message", {})
        if message.get("role") != "user":
            continue
        content = message.get("content", [])
        text_parts = [part.get("text", "") for part in content if part.get("type") == "text"]
        original_text = "\n".join(part for part in text_parts if part).strip()
        if original_text and not _is_internal_runtime_request(original_text):
            text = _strip_untrusted_metadata_wrapper(original_text)
            if _looks_like_transport_noise(original_text, text):
                continue
            return {
                "message_id": record.get("id", ""),
                "text": text,
                "timestamp": record.get("timestamp", ""),
            }
    return None


def _latest_prompt_error_after(records: List[Dict[str, object]], message_id: str) -> Dict[str, object] | None:
    if not message_id:
        return None
    seen_user = False
    latest_error: Dict[str, object] | None = None
    for record in records:
        if str(record.get("id", "")).strip() == str(message_id).strip():
            seen_user = True
            continue
        if not seen_user:
            continue
        if str(record.get("customType", "")).strip() == "openclaw:prompt-error":
            latest_error = {
                "record_id": str(record.get("id", "")).strip(),
                "timestamp": str(record.get("timestamp", "")).strip(),
                "error": str((record.get("data", {}) or {}).get("error", "")).strip(),
                "run_id": str((record.get("data", {}) or {}).get("runId", "")).strip(),
            }
    return latest_error


def _resolve_route_for_message(latest_user: Dict[str, object]) -> Tuple[Dict[str, object], Path]:
    route_path = BRAIN_ROUTES_ROOT / "openclaw-main" / "main.json"
    route = _load_json(route_path)
    if str(route.get("message_id", "")) != str(latest_user["message_id"]):
        route = route_instruction(
            provider="openclaw-main",
            conversation_id="main",
            conversation_type="direct",
            text=str(latest_user["text"]),
            source="brain_enforcer",
            sender_id="user",
            sender_name="openclaw-user",
            message_id=str(latest_user["message_id"]),
            session_key="agent:main:main",
        )
    route = reroot_route_if_needed(
        route=route,
        provider="openclaw-main",
        conversation_id="main",
        conversation_type="direct",
        goal=str(route.get("goal") or latest_user["text"]),
        session_key="agent:main:main",
    )
    persist_route("openclaw-main", "main", route)
    return route, route_path


def enforce_brain_first(limit: int = 20) -> Dict[str, object]:
    link_repair = _repair_noisy_main_link()
    messages = _load_main_session_messages(limit=limit)
    state = _load_json(ENFORCER_STATE_PATH)
    last_external_message_id = str(state.get("last_external_message_id", ""))
    last_prompt_error_id = str(state.get("last_prompt_error_id", ""))
    latest_user = _latest_external_user_message(messages)
    if not latest_user:
        return {"status": "no_external_user_message", "link_repair": link_repair}
    latest_prompt_error = _latest_prompt_error_after(messages, str(latest_user["message_id"]))
    if latest_prompt_error and not session_has_assistant_reply_after(
        "agent:main:main",
        str(latest_prompt_error.get("record_id", "")),
    ) and str(latest_prompt_error.get("record_id", "")) != last_prompt_error_id:
        route, route_path = _resolve_route_for_message(latest_user)
        route = dict(route)
        route["mode"] = "authoritative_task_status"
        route["prompt_error"] = latest_prompt_error
        receipt = emit_route_receipt(
            route,
            provider="openclaw-main",
            conversation_id="main",
            session_key="agent:main:main",
        )
        _write_json(
            ENFORCER_STATE_PATH,
            {
                "last_external_message_id": str(latest_user["message_id"]),
                "last_external_timestamp": str(latest_user["timestamp"]),
                "last_routed_at": route.get("routed_at", ""),
                "last_receipt_at": receipt.get("created_at", ""),
                "last_prompt_error_id": str(latest_prompt_error.get("record_id", "")),
            },
        )
        return {
            "status": "prompt_error_backfilled",
            "latest_user_message": latest_user,
            "prompt_error": latest_prompt_error,
            "route": route,
            "receipt": receipt,
            "route_store": str(route_path),
            "link_repair": link_repair,
        }
    if str(latest_user["message_id"]) == last_external_message_id:
        route_path = BRAIN_ROUTES_ROOT / "openclaw-main" / "main.json"
        route = _load_json(route_path)
        needs_receipt = bool(route) and str(route.get("message_id", "")) == str(latest_user["message_id"]) and not session_has_assistant_reply_after(
            "agent:main:main",
            str(latest_user["message_id"]),
        )
        if needs_receipt:
            route = reroot_route_if_needed(
                route=route,
                provider="openclaw-main",
                conversation_id="main",
                conversation_type="direct",
                goal=str(route.get("goal") or latest_user["text"]),
                session_key="agent:main:main",
            )
            persist_route("openclaw-main", "main", route)
            receipt = emit_route_receipt(
                route,
                provider="openclaw-main",
                conversation_id="main",
                session_key="agent:main:main",
            )
            _write_json(
                ENFORCER_STATE_PATH,
                {
                    "last_external_message_id": str(latest_user["message_id"]),
                    "last_external_timestamp": str(latest_user["timestamp"]),
                    "last_routed_at": route.get("routed_at", ""),
                    "last_receipt_at": receipt.get("created_at", ""),
                    "last_prompt_error_id": last_prompt_error_id,
                },
            )
            return {
                "status": "receipt_backfilled",
                "latest_user_message": latest_user,
                "route": route,
                "receipt": receipt,
                "route_store": str(route_path),
                "link_repair": link_repair,
            }
        return {
            "status": "no_new_external_user_message",
            "latest_user_message": latest_user,
            "route_store": str(route_path),
            "link_repair": link_repair,
        }

    route, route_path = _resolve_route_for_message(latest_user)
    receipt = emit_route_receipt(
        route,
        provider="openclaw-main",
        conversation_id="main",
        session_key="agent:main:main",
    )
    _write_json(
        ENFORCER_STATE_PATH,
        {
            "last_external_message_id": str(latest_user["message_id"]),
            "last_external_timestamp": str(latest_user["timestamp"]),
            "last_routed_at": route.get("routed_at", ""),
            "last_receipt_at": receipt.get("created_at", ""),
            "last_prompt_error_id": last_prompt_error_id,
        },
    )
    return {
        "status": "routed",
        "latest_user_message": latest_user,
        "route": route,
        "receipt": receipt,
        "route_store": str(route_path),
        "link_repair": link_repair,
    }


def main() -> int:
    import argparse

    parser = argparse.ArgumentParser(description="Ensure ordinary main-session instructions are routed through the control-center brain")
    parser.add_argument("--limit", type=int, default=20)
    parser.add_argument("--forever", action="store_true")
    parser.add_argument("--interval-seconds", type=float, default=5.0)
    args = parser.parse_args()
    if not args.forever:
        print(json.dumps(enforce_brain_first(limit=args.limit), ensure_ascii=False, indent=2))
        return 0
    while True:
        try:
            result = enforce_brain_first(limit=args.limit)
        except Exception as exc:
            result = {"status": "brain_enforcer_exception", "error": str(exc)}
        print(json.dumps(result, ensure_ascii=False, indent=2), flush=True)
        time.sleep(max(1.0, float(args.interval_seconds)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
