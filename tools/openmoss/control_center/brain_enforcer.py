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
- 文件路径：`tools/openmoss/control_center/brain_enforcer.py`
- 文件作用：负责主会话回执补偿与脑路由兜底执行。
- 顶层函数：_load_json、_write_json、_is_internal_runtime_request、_strip_untrusted_metadata_wrapper、_load_main_session_messages、_latest_external_user_message、_latest_prompt_error_after、_assistant_reply_assessment_after、_resolve_route_for_message、enforce_brain_first、main。
- 顶层类：无顶层类。
- 阅读建议：先看模块说明，再按函数/类 docstring 顺着主流程理解调用关系。
"""
from __future__ import annotations

import json
import re
import time
from pathlib import Path
from typing import Dict, List, Tuple

from brain_router import route_instruction
from paths import BRAIN_ROUTES_ROOT
from route_guardrails import persist_route, reroot_route_if_needed
from task_receipt_engine import emit_route_receipt, session_has_assistant_reply_after
from task_status_snapshot import build_task_status_snapshot

SESSIONS_ROOT = Path("/Users/mac_claw/.openclaw/agents/main/sessions")
MAIN_SESSION_KEY = "agent:main:main"
MAIN_SESSION_REGISTRY = SESSIONS_ROOT / "sessions.json"
ENFORCER_STATE_PATH = BRAIN_ROUTES_ROOT / "openclaw-main" / "brain_enforcer_state.json"


def _load_json(path: Path):
    """
    中文注解：
    - 功能：实现 `_load_json` 对应的处理逻辑。
    - 角色：属于本模块中的内部辅助逻辑；私有函数通常服务同文件主流程，公共函数通常作为跨模块入口或能力接口。
    - 调用关系：建议结合本文件的模块说明、调用方以及同名相关辅助函数一起阅读。
    """
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, payload: Dict[str, object]) -> None:
    """
    中文注解：
    - 功能：实现 `_write_json` 对应的处理逻辑。
    - 角色：属于本模块中的内部辅助逻辑；私有函数通常服务同文件主流程，公共函数通常作为跨模块入口或能力接口。
    - 调用关系：建议结合本文件的模块说明、调用方以及同名相关辅助函数一起阅读。
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _is_internal_runtime_request(text: str) -> bool:
    """
    中文注解：
    - 功能：实现 `_is_internal_runtime_request` 对应的处理逻辑。
    - 角色：属于本模块中的内部辅助逻辑；私有函数通常服务同文件主流程，公共函数通常作为跨模块入口或能力接口。
    - 调用关系：建议结合本文件的模块说明、调用方以及同名相关辅助函数一起阅读。
    """
    normalized = text.strip()
    return (
        "[Autonomy runtime execution request]" in normalized
        and "task_id:" in normalized
        and "stage:" in normalized
        and "user_goal:" in normalized
    )


def _strip_untrusted_metadata_wrapper(text: str) -> str:
    """
    中文注解：
    - 功能：实现 `_strip_untrusted_metadata_wrapper` 对应的处理逻辑。
    - 角色：属于本模块中的内部辅助逻辑；私有函数通常服务同文件主流程，公共函数通常作为跨模块入口或能力接口。
    - 调用关系：建议结合本文件的模块说明、调用方以及同名相关辅助函数一起阅读。
    """
    cleaned = str(text or "")
    patterns = [
        r"Conversation info \(untrusted metadata\):\s*```json.*?```\s*",
        r"Sender \(untrusted metadata\):\s*```json.*?```\s*",
    ]
    for pattern in patterns:
        cleaned = re.sub(pattern, "", cleaned, flags=re.DOTALL)
    return cleaned.strip()


def _load_main_session_messages(limit: int = 20) -> List[Dict[str, object]]:
    """
    中文注解：
    - 功能：实现 `_load_main_session_messages` 对应的处理逻辑。
    - 角色：属于本模块中的内部辅助逻辑；私有函数通常服务同文件主流程，公共函数通常作为跨模块入口或能力接口。
    - 调用关系：建议结合本文件的模块说明、调用方以及同名相关辅助函数一起阅读。
    """
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
    """
    中文注解：
    - 功能：实现 `_latest_external_user_message` 对应的处理逻辑。
    - 角色：属于本模块中的内部辅助逻辑；私有函数通常服务同文件主流程，公共函数通常作为跨模块入口或能力接口。
    - 调用关系：建议结合本文件的模块说明、调用方以及同名相关辅助函数一起阅读。
    """
    for record in reversed(records):
        message = record.get("message", {})
        if message.get("role") != "user":
            continue
        content = message.get("content", [])
        text_parts = [part.get("text", "") for part in content if part.get("type") == "text"]
        text = "\n".join(part for part in text_parts if part).strip()
        if text and not _is_internal_runtime_request(text):
            return {
                "message_id": record.get("id", ""),
                "text": _strip_untrusted_metadata_wrapper(text),
                "timestamp": record.get("timestamp", ""),
            }
    return None


def _latest_prompt_error_after(records: List[Dict[str, object]], message_id: str) -> Dict[str, object] | None:
    """
    中文注解：
    - 功能：实现 `_latest_prompt_error_after` 对应的处理逻辑。
    - 角色：属于本模块中的内部辅助逻辑；私有函数通常服务同文件主流程，公共函数通常作为跨模块入口或能力接口。
    - 调用关系：建议结合本文件的模块说明、调用方以及同名相关辅助函数一起阅读。
    """
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


def _assistant_reply_assessment_after(records: List[Dict[str, object]], message_id: str) -> Dict[str, object]:
    """
    中文注解：
    - 功能：检查用户消息之后出现的 assistant 回复是否“真正对外可用”。
    - 设计意图：
      - 不是所有 assistant 回复都应当视为“已经回复用户”；
      - 纯 authoritative status 回执、内部状态解释、无 reply 标记的内部评论，都会让用户感觉像没回。
    - 调用关系：由 `enforce_brain_first(...)` 在决定是否补发更好回执前调用。
    """
    seen_user = False
    latest_text = ""
    has_reply = False
    has_substantive_reply = False
    low_quality_reason = ""
    for record in records:
        if str(record.get("id", "")).strip() == str(message_id).strip():
            seen_user = True
            continue
        if not seen_user:
            continue
        message = record.get("message", {}) or {}
        if message.get("role") != "assistant":
            continue
        text = "\n".join(
            part.get("text", "")
            for part in message.get("content", []) or []
            if part.get("type") == "text"
        ).strip()
        if not text:
            continue
        has_reply = True
        latest_text = text
        normalized = text.strip()
        if normalized.startswith("[[reply_to_current]] Authoritative task state says"):
            low_quality_reason = "status_only_receipt"
            continue
        if "内部状态，不该发出来" in normalized or "内部状态" in normalized:
            low_quality_reason = "internal_state_leak"
            continue
        if "[[reply_to_current]]" not in normalized and "Authoritative task state says" in normalized:
            low_quality_reason = "untagged_status_leak"
            continue
        has_substantive_reply = True
        low_quality_reason = ""
    return {
        "has_reply": has_reply,
        "has_substantive_reply": has_substantive_reply,
        "latest_text": latest_text,
        "low_quality_reason": low_quality_reason,
    }


def _route_governance_summary(route: Dict[str, object]) -> Dict[str, object]:
    """
    中文注解：
    - 功能：提炼 route 当前绑定任务的治理摘要，供 enforcer 记录和后续补偿决策参考。
    """
    task_id = str(route.get("task_id", "")).strip()
    if not task_id:
        return {}
    snapshot = route.get("authoritative_task_status", {}) or build_task_status_snapshot(task_id)
    governance = snapshot.get("governance", {}) or {}
    policy = governance.get("policy", {}) or {}
    memory = governance.get("memory", {}) or snapshot.get("memory", {}) or {}
    return {
        "risk": policy.get("risk", ""),
        "pending_approvals": len(policy.get("pending_approvals", []) or []),
        "matched_promoted_rules": len(memory.get("matched_promoted_rules", []) or []),
        "matched_error_recurrence": len(memory.get("matched_error_recurrence", []) or []),
    }


def _resolve_route_for_message(latest_user: Dict[str, object]) -> Tuple[Dict[str, object], Path]:
    """
    中文注解：
    - 功能：实现 `_resolve_route_for_message` 对应的处理逻辑。
    - 角色：属于本模块中的内部辅助逻辑；私有函数通常服务同文件主流程，公共函数通常作为跨模块入口或能力接口。
    - 调用关系：建议结合本文件的模块说明、调用方以及同名相关辅助函数一起阅读。
    """
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
    """
    中文注解：
    - 功能：实现 `enforce_brain_first` 对应的处理逻辑。
    - 角色：属于本模块中的对外可见逻辑；私有函数通常服务同文件主流程，公共函数通常作为跨模块入口或能力接口。
    - 调用关系：建议结合本文件的模块说明、调用方以及同名相关辅助函数一起阅读。
    """
    messages = _load_main_session_messages(limit=limit)
    state = _load_json(ENFORCER_STATE_PATH)
    last_external_message_id = str(state.get("last_external_message_id", ""))
    last_prompt_error_id = str(state.get("last_prompt_error_id", ""))
    latest_user = _latest_external_user_message(messages)
    if not latest_user:
        return {"status": "no_external_user_message"}
    reply_assessment = _assistant_reply_assessment_after(messages, str(latest_user["message_id"]))
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
                "last_governance_summary": _route_governance_summary(route),
            },
        )
        return {
            "status": "prompt_error_backfilled",
            "latest_user_message": latest_user,
            "reply_assessment": reply_assessment,
            "prompt_error": latest_prompt_error,
            "route": route,
            "receipt": receipt,
            "route_store": str(route_path),
        }
    if str(latest_user["message_id"]) == last_external_message_id:
        route_path = BRAIN_ROUTES_ROOT / "openclaw-main" / "main.json"
        route = _load_json(route_path)
        needs_receipt = bool(route) and str(route.get("message_id", "")) == str(latest_user["message_id"]) and (
            not reply_assessment.get("has_reply")
            or not reply_assessment.get("has_substantive_reply")
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
                    "last_governance_summary": _route_governance_summary(route),
                },
            )
            return {
                "status": "receipt_backfilled",
                "latest_user_message": latest_user,
                "reply_assessment": reply_assessment,
                "route": route,
                "receipt": receipt,
                "route_store": str(route_path),
            }
        return {
            "status": "no_new_external_user_message",
            "latest_user_message": latest_user,
            "reply_assessment": reply_assessment,
            "route_store": str(route_path),
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
        "reply_assessment": reply_assessment,
        "route": route,
        "receipt": receipt,
        "route_store": str(route_path),
    }


def main() -> int:
    """
    中文注解：
    - 功能：实现 `main` 对应的处理逻辑。
    - 角色：属于本模块中的对外可见逻辑；私有函数通常服务同文件主流程，公共函数通常作为跨模块入口或能力接口。
    - 调用关系：建议结合本文件的模块说明、调用方以及同名相关辅助函数一起阅读。
    """
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
