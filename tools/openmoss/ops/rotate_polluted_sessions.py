#!/usr/bin/env python3
"""轮换被历史 bridge / 内部执行流污染的活跃会话。

这个脚本只处理当前主链仍会引用的会话键，做法是：
1. 识别会话文件里是否存在旧 bridge dispatch、System Exec completed、toolCall/toolResult 等污染特征。
2. 若命中，则把旧 jsonl 改名为带时间戳的 `.polluted.*.jsonl` 备份。
3. 为原 session key 生成一个新的干净 sessionId/sessionFile，并保留必要的路由上下文。

这样可以把“用户主线程/Telegram 活跃线程”从历史污染中切出来，而不破坏旧证据文件。
"""

from __future__ import annotations

import json
import uuid
from copy import deepcopy
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path


SESSIONS_ROOT = Path("/Users/mac_claw/.openclaw/agents/main/sessions")
SESSIONS_INDEX = SESSIONS_ROOT / "sessions.json"
WORKSPACE = "/Users/mac_claw/.openclaw/workspace"
TARGET_KEYS = (
    "agent:main:main",
    "agent:main:telegram:group:-5194754912",
)
POLLUTION_MARKERS = (
    "[OpenMOSS bridge dispatch]",
    "System: [",
    "\"type\":\"toolCall\"",
    "\"type\":\"toolResult\"",
    "NO_REPLY",
)


@dataclass
class RotationResult:
    session_key: str
    rotated: bool
    reason: str
    old_session_id: str | None = None
    new_session_id: str | None = None
    backup_file: str | None = None


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _utc_now_ms() -> int:
    return int(datetime.now(timezone.utc).timestamp() * 1000)


def _load_sessions() -> dict:
    return json.loads(SESSIONS_INDEX.read_text(encoding="utf-8"))


def _write_sessions(payload: dict) -> None:
    SESSIONS_INDEX.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _session_file_for_entry(entry: dict) -> Path | None:
    session_file = entry.get("sessionFile")
    if session_file:
        return Path(session_file)
    session_id = entry.get("sessionId")
    if session_id:
        return SESSIONS_ROOT / f"{session_id}.jsonl"
    return None


def _looks_polluted(path: Path) -> tuple[bool, str]:
    if not path.exists():
        return False, "missing_session_file"
    text = path.read_text(encoding="utf-8", errors="replace")
    for marker in POLLUTION_MARKERS:
        if marker in text:
            return True, f"marker:{marker}"
    return False, "clean"


def _fresh_entry(session_key: str, previous: dict) -> dict:
    session_id = str(uuid.uuid4())
    now_ms = _utc_now_ms()
    entry = deepcopy(previous)
    entry["sessionId"] = session_id
    entry["sessionFile"] = str(SESSIONS_ROOT / f"{session_id}.jsonl")
    entry["updatedAt"] = now_ms
    entry["systemSent"] = False
    entry["abortedLastRun"] = False
    entry["compactionCount"] = 0
    entry["inputTokens"] = 0
    entry["outputTokens"] = 0
    entry["cacheRead"] = 0
    entry["cacheWrite"] = 0
    entry["totalTokens"] = 0
    entry["totalTokensFresh"] = 0
    entry.pop("status", None)
    entry.pop("startedAt", None)
    entry.pop("endedAt", None)
    entry.pop("runtimeMs", None)
    entry.pop("estimatedCostUsd", None)
    entry.pop("lastHeartbeatText", None)
    entry.pop("lastHeartbeatSentAt", None)
    entry.pop("memoryFlushAt", None)
    entry.pop("memoryFlushCompactionCount", None)
    if session_key.startswith("agent:main:telegram:group:"):
        entry["chatType"] = "group"
        entry["lastChannel"] = "telegram"
        entry["deliveryContext"] = {"channel": "telegram"}
        entry["origin"] = {
            "provider": "telegram",
            "surface": "telegram",
            "chatType": "group",
        }
    elif session_key == "agent:main:main":
        entry["chatType"] = "direct"
        entry["lastChannel"] = "telegram"
        entry["origin"] = {
            "provider": "jinclaw",
            "surface": "internal",
            "chatType": "direct",
        }
    return entry


def _write_minimal_session_file(path: Path, session_id: str) -> None:
    bootstrap = {
        "type": "session",
        "version": 3,
        "id": session_id,
        "timestamp": _utc_now_iso(),
        "cwd": WORKSPACE,
    }
    path.write_text(json.dumps(bootstrap, ensure_ascii=False) + "\n", encoding="utf-8")


def rotate_polluted_sessions() -> list[RotationResult]:
    registry = _load_sessions()
    results: list[RotationResult] = []
    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H-%M-%SZ")
    mutated = False

    for session_key in TARGET_KEYS:
        entry = registry.get(session_key)
        if not entry:
            results.append(RotationResult(session_key=session_key, rotated=False, reason="missing_registry_entry"))
            continue
        session_file = _session_file_for_entry(entry)
        if not session_file:
            results.append(RotationResult(session_key=session_key, rotated=False, reason="missing_session_file_path"))
            continue
        polluted, reason = _looks_polluted(session_file)
        if not polluted:
            results.append(RotationResult(session_key=session_key, rotated=False, reason=reason, old_session_id=entry.get("sessionId")))
            continue

        backup_file = session_file.with_suffix(session_file.suffix + f".polluted.{timestamp}")
        session_file.rename(backup_file)
        fresh = _fresh_entry(session_key, entry)
        _write_minimal_session_file(Path(fresh["sessionFile"]), fresh["sessionId"])
        registry[session_key] = fresh
        results.append(
            RotationResult(
                session_key=session_key,
                rotated=True,
                reason=reason,
                old_session_id=entry.get("sessionId"),
                new_session_id=fresh.get("sessionId"),
                backup_file=str(backup_file),
            )
        )
        mutated = True

    if mutated:
        _write_sessions(registry)
    return results


def main() -> None:
    results = rotate_polluted_sessions()
    print(
        json.dumps(
            [
                {
                    "session_key": item.session_key,
                    "rotated": item.rotated,
                    "reason": item.reason,
                    "old_session_id": item.old_session_id,
                    "new_session_id": item.new_session_id,
                    "backup_file": item.backup_file,
                }
                for item in results
            ],
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
