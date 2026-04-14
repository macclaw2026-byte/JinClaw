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
- 文件路径：`tools/openmoss/control_center/task_receipt_engine.py`
- 文件作用：负责任务型指令的即时回执生成与发送。
- 顶层函数：_utc_now_iso、_write_json、_load_sessions_registry、_session_file_for_key、_append_session_receipt、session_has_assistant_reply_after、build_receipt_text、emit_route_receipt。
- 顶层类：无顶层类。
- 阅读建议：先看模块说明，再按函数/类 docstring 顺着主流程理解调用关系。
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List

from paths import BRAIN_RECEIPTS_ROOT, OPENCLAW_SESSIONS_ROOT
from conversation_events import record_conversation_event
from response_policy_engine import build_route_receipt_text, build_route_reply_projection
from response_drift_detector import reconcile_route_with_authoritative_state


def _utc_now_iso() -> str:
    """
    中文注解：
    - 功能：实现 `_utc_now_iso` 对应的处理逻辑。
    - 角色：属于本模块中的内部辅助逻辑；私有函数通常服务同文件主流程，公共函数通常作为跨模块入口或能力接口。
    - 调用关系：建议结合本文件的模块说明、调用方以及同名相关辅助函数一起阅读。
    """
    return datetime.now(timezone.utc).isoformat()


def _write_json(path: Path, payload: Dict[str, object]) -> None:
    """
    中文注解：
    - 功能：实现 `_write_json` 对应的处理逻辑。
    - 角色：属于本模块中的内部辅助逻辑；私有函数通常服务同文件主流程，公共函数通常作为跨模块入口或能力接口。
    - 调用关系：建议结合本文件的模块说明、调用方以及同名相关辅助函数一起阅读。
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _resolve_openclaw_bin() -> str:
    """
    中文注解：
    - 功能：定位本机可执行的 `openclaw` CLI，供回执链直接调用原生消息发送能力。
    - 设计意图：避免附件发送还要依赖旧 bridge；只要 OpenClaw 主 CLI 正常，这里就能直接把文件投递到原生聊天通道。
    """
    env_value = (os.environ.get("OPENCLAW_BIN") or "").strip()
    candidates: List[str] = []
    if env_value:
        candidates.append(env_value)
        if "/" not in env_value:
            resolved = shutil.which(env_value)
            if resolved:
                candidates.append(resolved)
    discovered = shutil.which("openclaw")
    if discovered:
        candidates.append(discovered)
    candidates.extend(["/opt/homebrew/bin/openclaw", "/usr/local/bin/openclaw"])
    for candidate in candidates:
        if candidate and Path(candidate).exists():
            return candidate
    return env_value or "openclaw"


def _load_sessions_registry() -> Dict[str, object]:
    """
    中文注解：
    - 功能：实现 `_load_sessions_registry` 对应的处理逻辑。
    - 角色：属于本模块中的内部辅助逻辑；私有函数通常服务同文件主流程，公共函数通常作为跨模块入口或能力接口。
    - 调用关系：建议结合本文件的模块说明、调用方以及同名相关辅助函数一起阅读。
    """
    registry_path = OPENCLAW_SESSIONS_ROOT / "sessions.json"
    if not registry_path.exists():
        return {}
    try:
        return json.loads(registry_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def _session_file_for_key(session_key: str) -> Path | None:
    """
    中文注解：
    - 功能：实现 `_session_file_for_key` 对应的处理逻辑。
    - 角色：属于本模块中的内部辅助逻辑；私有函数通常服务同文件主流程，公共函数通常作为跨模块入口或能力接口。
    - 调用关系：建议结合本文件的模块说明、调用方以及同名相关辅助函数一起阅读。
    """
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


def _channel_delivery_context(provider: str, conversation_id: str) -> Dict[str, object]:
    channel = str(provider or "").strip()
    target = str(conversation_id or "").strip()
    if channel == "telegram":
        return {
            "channel": "telegram",
            "to": f"telegram:{target}",
            "accountId": "default",
        }
    return {
        "channel": channel or "webchat",
        "to": target,
    }


def _ensure_session_receipt_target(session_key: str, provider: str, conversation_id: str) -> Path | None:
    """
    中文注解：
    - 功能：当聊天入口已经有 session_key 但 sessions registry 尚未建好时，补建一个最小可写 transcript。
    - 设计意图：避免 Telegram/其它聊天入口在“路由已成功、回执找不到 session 文件”时表现成已读不回。
    """
    existing = _session_file_for_key(session_key)
    if existing:
        return existing
    if not session_key:
        return None
    registry = _load_sessions_registry()
    if not isinstance(registry, dict):
        registry = {}
    now_ms = int(datetime.now(timezone.utc).timestamp() * 1000)
    session_id = uuid.uuid4().hex
    session_file = OPENCLAW_SESSIONS_ROOT / f"{session_id}.jsonl"
    session_file.parent.mkdir(parents=True, exist_ok=True)
    initial_record = {
        "type": "session",
        "version": 3,
        "id": session_id,
        "timestamp": datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "cwd": str(Path.home()),
    }
    session_file.write_text(json.dumps(initial_record, ensure_ascii=False) + "\n", encoding="utf-8")
    delivery_context = _channel_delivery_context(provider, conversation_id)
    display_name = f"{provider}:{conversation_id}"
    registry[session_key] = {
        "sessionId": session_id,
        "updatedAt": now_ms,
        "systemSent": True,
        "abortedLastRun": False,
        "displayName": display_name,
        "channel": delivery_context.get("channel", provider or "webchat"),
        "deliveryContext": delivery_context,
        "lastChannel": delivery_context.get("channel", provider or "webchat"),
        "lastTo": delivery_context.get("to", conversation_id),
        "lastAccountId": delivery_context.get("accountId", "default"),
        "sessionFile": str(session_file),
    }
    (OPENCLAW_SESSIONS_ROOT / "sessions.json").write_text(
        json.dumps(registry, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return session_file


def _append_session_receipt(session_key: str, text: str) -> Dict[str, object]:
    """
    中文注解：
    - 功能：实现 `_append_session_receipt` 对应的处理逻辑。
    - 角色：属于本模块中的内部辅助逻辑；私有函数通常服务同文件主流程，公共函数通常作为跨模块入口或能力接口。
    - 调用关系：建议结合本文件的模块说明、调用方以及同名相关辅助函数一起阅读。
    """
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


def _attachment_candidates_from_route(route: Dict[str, object]) -> List[Dict[str, object]]:
    """
    中文注解：
    - 功能：从路由结果里提取可发送附件列表。
    - 设计意图：优先读权威状态快照中的 `output_attachments`，这样任何任务只要把产物路径写进标准状态结构，就能自动获得“文件直发”能力。
    """
    explicit = route.get("output_attachments", [])
    if isinstance(explicit, list) and explicit:
        return [item for item in explicit if isinstance(item, dict)]
    snapshot = route.get("authoritative_task_status", {}) or {}
    candidates = snapshot.get("output_attachments", []) or []
    if isinstance(candidates, list):
        return [item for item in candidates if isinstance(item, dict)]
    return []


def _provider_supports_channel_delivery(provider: str) -> bool:
    return str(provider or "").strip() in {
        "telegram",
        "whatsapp",
        "discord",
        "slack",
        "signal",
        "imessage",
        "line",
        "irc",
        "googlechat",
    }


def _send_attachments_via_openclaw(provider: str, conversation_id: str, text: str, attachments: List[Dict[str, object]]) -> Dict[str, object]:
    """
    中文注解：
    - 功能：通过 OpenClaw 原生 `message send --media` 把本地文件直接投递到聊天通道。
    - 行为：
      - 第一条带正文和第一个附件；
      - 后续附件单独投递；
      - 支持通过环境变量 `OPENMOSS_RECEIPT_CHANNEL_DRY_RUN=1` 做干跑验证。
    """
    channel = str(provider or "").strip()
    target = str(conversation_id or "").strip()
    if not _provider_supports_channel_delivery(channel):
        return {"delivered": False, "reason": "provider_not_supported_for_channel_delivery", "provider": channel}
    if not target:
        return {"delivered": False, "reason": "missing_conversation_target", "provider": channel}
    valid_attachments = []
    for item in attachments:
        path = str(item.get("path", "")).strip()
        if path and Path(path).exists():
            valid_attachments.append(item)
    if not valid_attachments:
        return {"delivered": False, "reason": "no_valid_attachments", "provider": channel}

    openclaw_bin = _resolve_openclaw_bin()
    dry_run = (os.environ.get("OPENMOSS_RECEIPT_CHANNEL_DRY_RUN") or "").strip() == "1"
    deliveries = []
    first_message = str(text or "").strip()
    for index, item in enumerate(valid_attachments):
        media_path = str(item.get("path", "")).strip()
        cmd = [
            openclaw_bin,
            "message",
            "send",
            "--channel",
            channel,
            "--target",
            target,
            "--media",
            media_path,
            "--json",
        ]
        message_text = first_message if index == 0 and first_message else ""
        if message_text:
            cmd.extend(["--message", message_text])
        if channel == "telegram":
            cmd.append("--force-document")
        if dry_run:
            cmd.append("--dry-run")
        proc = subprocess.run(cmd, capture_output=True, text=True, check=False)
        result = {
            "path": media_path,
            "returncode": proc.returncode,
            "stdout": proc.stdout.strip(),
            "stderr": proc.stderr.strip(),
            "dry_run": dry_run,
        }
        deliveries.append(result)
        if proc.returncode != 0:
            return {
                "delivered": False,
                "reason": "openclaw_message_send_failed",
                "provider": channel,
                "conversation_id": target,
                "deliveries": deliveries,
            }
    return {
        "delivered": True,
        "provider": channel,
        "conversation_id": target,
        "dry_run": dry_run,
        "deliveries": deliveries,
    }


def session_has_assistant_reply_after(session_key: str, user_message_id: str) -> bool:
    """
    中文注解：
    - 功能：实现 `session_has_assistant_reply_after` 对应的处理逻辑。
    - 角色：属于本模块中的对外可见逻辑；私有函数通常服务同文件主流程，公共函数通常作为跨模块入口或能力接口。
    - 调用关系：建议结合本文件的模块说明、调用方以及同名相关辅助函数一起阅读。
    """
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
    """
    中文注解：
    - 功能：实现 `build_receipt_text` 对应的处理逻辑。
    - 角色：属于本模块中的对外可见逻辑；私有函数通常服务同文件主流程，公共函数通常作为跨模块入口或能力接口。
    - 调用关系：建议结合本文件的模块说明、调用方以及同名相关辅助函数一起阅读。
    """
    return build_route_receipt_text(route)


def build_receipt_projection(route: Dict[str, object]) -> Dict[str, object]:
    """
    中文注解：
    - 功能：把路由结果解释成 transport-neutral 的 reply projection。
    - 设计意图：让 receipt engine 不再只携带一段已经渲染好的文本，而是把结构化回复合同一起持久化，供 Telegram / 直连 / 后续 UI 复用。
    """
    return build_route_reply_projection(route)


def emit_route_receipt(route: Dict[str, object], *, provider: str, conversation_id: str, session_key: str = "") -> Dict[str, object]:
    """
    中文注解：
    - 功能：实现 `emit_route_receipt` 对应的处理逻辑。
    - 角色：属于本模块中的对外可见逻辑；私有函数通常服务同文件主流程，公共函数通常作为跨模块入口或能力接口。
    - 调用关系：建议结合本文件的模块说明、调用方以及同名相关辅助函数一起阅读。
    - 发送策略：若当前路由已经识别出可直接投递到聊天窗口的任务产物附件，则优先走原生聊天附件投递；
      附件直发成功后，不再额外往 session transcript 追加一条重复文字回执，避免用户在聊天框里看到“双回执”。
    """
    route = reconcile_route_with_authoritative_state(route)
    reply_projection = build_receipt_projection(route)
    text = str(reply_projection.get("rendered_text", "")).strip() or build_receipt_text(route)
    receipt = {
        "receipt_id": uuid.uuid4().hex,
        "created_at": _utc_now_iso(),
        "provider": provider,
        "conversation_id": conversation_id,
        "task_id": route.get("task_id", ""),
        "mode": route.get("mode", ""),
        "text": text,
        "reply_projection": reply_projection,
        "session_key": session_key,
        "governance": (route.get("authoritative_task_status", {}) or {}).get("governance", {}),
    }
    delivery_contract = ((route.get("authoritative_task_status", {}) or {}).get("delivery_contract", {}) or {})
    receipt["delivery_contract"] = delivery_contract
    _write_json(BRAIN_RECEIPTS_ROOT / provider / f"{conversation_id}.json", receipt)

    attachments = _attachment_candidates_from_route(route)
    attachment_delivery = {"delivered": False, "reason": "no_output_attachments"}
    if attachments:
        attachment_delivery = _send_attachments_via_openclaw(provider, conversation_id, text, attachments)

    delivery = {"delivered": False, "reason": "suppressed_due_to_attachment_delivery"}
    if attachment_delivery.get("delivered") is not True:
        delivery = {"delivered": False, "reason": "no_session_key"}
        if session_key:
            _ensure_session_receipt_target(session_key, provider, conversation_id)
            delivery = _append_session_receipt(session_key, text)

    receipt["delivery"] = delivery
    receipt["attachment_delivery"] = attachment_delivery
    receipt["attachments"] = attachments
    if bool(delivery_contract.get("prefer_attachment_delivery")) and attachments:
        receipt["delivery_strategy"] = "delivery_contract_attachment_first"
    elif attachments:
        receipt["delivery_strategy"] = "native_chat_attachment_first"
    else:
        receipt["delivery_strategy"] = "session_receipt_only"
    record_conversation_event(
        provider=provider,
        conversation_id=conversation_id,
        event_type="reply_projection_emitted",
        payload={
            "task_id": str(receipt.get("task_id", "")).strip(),
            "mode": str(receipt.get("mode", "")).strip(),
            "receipt_id": str(receipt.get("receipt_id", "")).strip(),
            "delivery_strategy": str(receipt.get("delivery_strategy", "")).strip(),
            "delivery_delivered": bool((delivery or {}).get("delivered")),
            "attachment_delivered": bool((attachment_delivery or {}).get("delivered")),
            "delivery_contract": dict(delivery_contract or {}),
            "reply_projection": dict(reply_projection or {}),
        },
    )
    _write_json(BRAIN_RECEIPTS_ROOT / provider / f"{conversation_id}.json", receipt)
    return receipt
