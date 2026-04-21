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
- 文件路径：`tools/openmoss/control_center/service_disable_registry.py`
- 文件作用：集中读取“服务被用户/治理层停用”的运行时哨兵文件。
- 顶层函数：normalize_service_name、disabled_service_path、read_disabled_service、is_service_disabled、build_disabled_services_summary。
- 设计意图：让调度、启动脚本、doctor 使用同一个停用真源，避免只停 launchd 后仍有孤儿 daemon 继续运行。
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable

from paths import CONTROL_CENTER_RUNTIME_ROOT, OPENCLAW_ROOT


DISABLED_SERVICES_ROOT = CONTROL_CENTER_RUNTIME_ROOT / "governance" / "disabled_services"
PERSISTENT_DISABLED_SERVICES_ROOT = OPENCLAW_ROOT / "operator_state" / "disabled_services"

SERVICE_ALIASES = {
    "ai.jinclaw.cross-market-arbitrage": "cross_market_arbitrage",
    "cross-market-arbitrage": "cross_market_arbitrage",
    "cross_market_arbitrage": "cross_market_arbitrage",
}


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def normalize_service_name(service_name: str) -> str:
    """
    中文注解：
    - 输入角色：接收 launchd label、人类可读名称或内部服务名。
    - 输出角色：返回统一的内部服务名，供哨兵文件路径和 doctor 汇总复用。
    """
    raw = str(service_name or "").strip()
    if raw in SERVICE_ALIASES:
        return SERVICE_ALIASES[raw]
    return raw.replace("-", "_").replace(".", "_")


def disabled_service_path(service_name: str) -> Path:
    """
    中文注解：
    - 输入角色：接收服务名。
    - 输出角色：返回该服务的运行时停用哨兵路径；该路径在 git ignore 的 runtime 目录下。
    """
    return DISABLED_SERVICES_ROOT / f"{normalize_service_name(service_name)}.json"


def persistent_disabled_service_path(service_name: str) -> Path:
    """
    中文注解：
    - 输入角色：接收服务名。
    - 输出角色：返回持久化停用哨兵路径；即使 workspace runtime 被清理，用户显式停用意图仍可保留。
    """
    return PERSISTENT_DISABLED_SERVICES_ROOT / f"{normalize_service_name(service_name)}.json"


def read_disabled_service(service_name: str) -> Dict[str, Any]:
    """
    中文注解：
    - 输入角色：接收需要检查的服务名。
    - 输出角色：返回结构化、可序列化的停用状态；哨兵存在但不可读时按 fail-closed 处理为 disabled。
    """
    normalized = normalize_service_name(service_name)
    runtime_path = disabled_service_path(normalized)
    persistent_path = persistent_disabled_service_path(normalized)
    paths = [runtime_path, persistent_path]
    existing_path = next((path for path in paths if path.exists()), runtime_path)
    base: Dict[str, Any] = {
        "service": normalized,
        "path": str(existing_path),
        "paths": [str(path) for path in paths],
        "exists": any(path.exists() for path in paths),
        "disabled": False,
        "reason": "",
        "checked_at": _utc_now_iso(),
        "fail_closed": False,
    }
    if not base["exists"]:
        return base
    path = existing_path
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        base.update(
            {
                "disabled": True,
                "reason": "disabled_service_sentinel_unreadable",
                "error": str(exc),
                "fail_closed": True,
            }
        )
        return base
    if not isinstance(payload, dict):
        base.update(
            {
                "disabled": True,
                "reason": "disabled_service_sentinel_invalid",
                "payload_type": type(payload).__name__,
                "fail_closed": True,
            }
        )
        return base
    disabled = bool(payload.get("disabled", True))
    base.update(
        {
            "disabled": disabled,
            "reason": str(payload.get("reason") or ("disabled_service_sentinel_present" if disabled else "")).strip(),
            "disabled_at": str(payload.get("disabled_at") or payload.get("created_at") or "").strip(),
            "disabled_by": str(payload.get("disabled_by") or "").strip(),
            "operator_intent": str(payload.get("operator_intent") or "").strip(),
            "requires_manual_reenable": bool(payload.get("requires_manual_reenable", disabled)),
            "evidence": payload.get("evidence", {}) if isinstance(payload.get("evidence", {}), dict) else {},
        }
    )
    return base


def is_service_disabled(service_name: str) -> bool:
    """
    中文注解：
    - 输入角色：接收服务名。
    - 输出角色：返回是否停用的布尔值，供只需要快速门禁的入口使用。
    """
    return bool(read_disabled_service(service_name).get("disabled"))


def build_disabled_services_summary(service_names: Iterable[str]) -> Dict[str, Any]:
    """
    中文注解：
    - 输入角色：接收服务名列表。
    - 输出角色：返回 doctor/control-plane 可消费的多服务停用摘要。
    """
    items = [read_disabled_service(name) for name in service_names]
    return {
        "generated_at": _utc_now_iso(),
        "disabled_total": sum(1 for item in items if item.get("disabled")),
        "items": items,
    }
