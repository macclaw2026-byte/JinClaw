#!/usr/bin/env python3

from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict

from intent_analyzer import analyze_intent
from orchestrator import build_control_center_package
from paths import BRAIN_ROUTES_ROOT

AUTONOMY_DIR = Path("/Users/mac_claw/.openclaw/workspace/tools/openmoss/autonomy")
import sys

if str(AUTONOMY_DIR) not in sys.path:
    sys.path.insert(0, str(AUTONOMY_DIR))

from manager import build_args, contract_path, create_task, read_link, utc_now_iso, write_link
from task_ingress import slugify


ACTION_PATTERNS = (
    "请",
    "帮我",
    "需要",
    "生成",
    "制作",
    "上传",
    "分析",
    "抓取",
    "研究",
    "登录",
    "打开",
    "继续",
    "自动",
    "修复",
    "搭建",
    "install",
    "build",
    "generate",
    "upload",
    "analyze",
    "scrape",
    "research",
    "continue",
    "fix",
)


def _write_json(path: Path, payload: object) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return str(path)


def _strip_transport_wrapper(text: str) -> str:
    cleaned = text
    cleaned = re.sub(r"Conversation info \(untrusted metadata\):\s*```[\s\S]*?```", "", cleaned, flags=re.MULTILINE)
    cleaned = re.sub(r"Sender \(untrusted metadata\):\s*```[\s\S]*?```", "", cleaned, flags=re.MULTILINE)
    cleaned = re.sub(r"Replied message \(untrusted, for context\):\s*```[\s\S]*?```", "", cleaned, flags=re.MULTILINE)
    cleaned = re.sub(r"^\[[^\]]+\]\s*", "", cleaned).strip()
    lines = [line.strip() for line in cleaned.splitlines() if line.strip()]
    if lines:
        return "\n".join(lines)
    return text.strip()


def _looks_actionable(text: str, intent: Dict[str, object]) -> bool:
    normalized = text.strip()
    lowered = normalized.lower()
    if not normalized:
        return False
    if len(normalized) >= 24:
        return True
    if any(token in lowered for token in ACTION_PATTERNS):
        return True
    if any(intent.get(key) for key in ("requires_external_information", "needs_browser", "may_download_artifacts", "may_execute_external_code")):
        return True
    if intent.get("task_types", ["general"]) != ["general"]:
        return True
    return False


def _build_task(task_id: str, goal: str, source: str) -> Dict[str, object]:
    package = build_control_center_package(task_id, goal, source=source)
    create_task(
        build_args(
            task_id=task_id,
            goal=goal,
            done_definition=package["done_definition"],
            stage=[],
            stage_json=json.dumps(package["stages"], ensure_ascii=False),
            hard_constraint=package["hard_constraints"],
            soft_preference=[],
            allowed_tool=package["allowed_tools"],
            forbidden_action=[],
            metadata_json=json.dumps(package["metadata"], ensure_ascii=False),
        )
    )
    return package


def route_instruction(
    *,
    provider: str,
    conversation_id: str,
    conversation_type: str,
    text: str,
    source: str,
    sender_id: str = "",
    sender_name: str = "",
    message_id: str = "",
    session_key: str = "",
) -> Dict[str, object]:
    goal = _strip_transport_wrapper(text)
    intent = analyze_intent(goal, source=source)
    existing = read_link(provider, conversation_id)
    route: Dict[str, object] = {
        "routed_at": utc_now_iso(),
        "provider": provider,
        "conversation_id": conversation_id,
        "conversation_type": conversation_type,
        "sender_id": sender_id,
        "sender_name": sender_name,
        "message_id": message_id,
        "source": source,
        "goal": goal,
        "intent": intent,
        "mode": "instant_reply_only",
        "task_id": existing.get("task_id"),
        "created_task": False,
        "attached_existing": bool(existing),
        "brain_required": True,
    }

    if existing:
        existing["updated_at"] = utc_now_iso()
        existing["last_message_id"] = message_id
        existing["last_sender_id"] = sender_id
        existing["last_sender_name"] = sender_name
        existing["last_goal"] = goal
        route["mode"] = "append_to_existing_task"
        route["task_id"] = existing.get("task_id")
        route["link_path"] = write_link(provider, conversation_id, existing)
    elif _looks_actionable(goal, intent):
        task_id = slugify(goal)
        if not contract_path(task_id).exists():
            _build_task(task_id, goal, source=source)
            route["created_task"] = True
        payload = {
            "provider": provider,
            "conversation_id": conversation_id,
            "conversation_type": conversation_type,
            "task_id": task_id,
            "goal": goal,
            "updated_at": utc_now_iso(),
            "last_message_id": message_id,
            "last_sender_id": sender_id,
            "last_sender_name": sender_name,
            "brain_source": source,
        }
        if session_key:
            payload["session_key"] = session_key
        route["mode"] = "create_or_attach"
        route["task_id"] = task_id
        route["link_path"] = write_link(provider, conversation_id, payload)

    route["route_path"] = _write_json(BRAIN_ROUTES_ROOT / provider / f"{conversation_id}.json", route)
    return route


def main() -> int:
    import argparse

    parser = argparse.ArgumentParser(description="Route an incoming instruction through the control-center brain first")
    parser.add_argument("--provider", required=True)
    parser.add_argument("--conversation-id", required=True)
    parser.add_argument("--conversation-type", default="direct")
    parser.add_argument("--text", required=True)
    parser.add_argument("--source", default="manual")
    parser.add_argument("--sender-id", default="")
    parser.add_argument("--sender-name", default="")
    parser.add_argument("--message-id", default="")
    args = parser.parse_args()
    print(
        json.dumps(
            route_instruction(
                provider=args.provider,
                conversation_id=args.conversation_id,
                conversation_type=args.conversation_type,
                text=args.text,
                source=args.source,
                sender_id=args.sender_id,
                sender_name=args.sender_name,
                message_id=args.message_id,
                session_key="",
            ),
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
