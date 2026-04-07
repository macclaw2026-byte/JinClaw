#!/usr/bin/env python3

"""
中文说明：
- 文件路径：`tools/openmoss/control_center/research_loop.py`
- 文件作用：负责控制中心中与 `research_loop` 相关的编排、分析或决策逻辑。
- 顶层函数：_utc_now_iso、_write_json、_signature、prepare_research_package、main。
- 顶层类：无顶层类。
- 阅读建议：先看模块说明，再按函数/类 docstring 顺着主流程理解调用关系。
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict

from cache_store import cache_get, cache_put
from paths import RESEARCH_ROOT


def _utc_now_iso() -> str:
    """
    中文注解：
    - 功能：实现 `_utc_now_iso` 对应的处理逻辑。
    - 角色：属于本模块中的内部辅助逻辑；私有函数通常服务同文件主流程，公共函数通常作为跨模块入口或能力接口。
    - 调用关系：建议结合本文件的模块说明、调用方以及同名相关辅助函数一起阅读。
    """
    return datetime.now(timezone.utc).isoformat()


def _write_json(path: Path, payload) -> None:
    """
    中文注解：
    - 功能：实现 `_write_json` 对应的处理逻辑。
    - 角色：属于本模块中的内部辅助逻辑；私有函数通常服务同文件主流程，公共函数通常作为跨模块入口或能力接口。
    - 调用关系：建议结合本文件的模块说明、调用方以及同名相关辅助函数一起阅读。
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _signature(scout: Dict[str, object], intent: Dict[str, object]) -> str:
    """
    中文注解：
    - 功能：实现 `_signature` 对应的处理逻辑。
    - 角色：属于本模块中的内部辅助逻辑；私有函数通常服务同文件主流程，公共函数通常作为跨模块入口或能力接口。
    - 调用关系：建议结合本文件的模块说明、调用方以及同名相关辅助函数一起阅读。
    """
    payload = {
        "goal": intent.get("goal", ""),
        "queries": scout.get("queries", []),
        "rules": scout.get("rules", []),
        "trusted_source_types": scout.get("trusted_source_types", []),
    }
    return json.dumps(payload, ensure_ascii=False, sort_keys=True)


def prepare_research_package(task_id: str, scout: Dict[str, object], intent: Dict[str, object]) -> Dict[str, object]:
    """
    中文注解：
    - 功能：实现 `prepare_research_package` 对应的处理逻辑。
    - 角色：属于本模块中的对外可见逻辑；私有函数通常服务同文件主流程，公共函数通常作为跨模块入口或能力接口。
    - 调用关系：建议结合本文件的模块说明、调用方以及同名相关辅助函数一起阅读。
    """
    cached = cache_get("research", task_id, {})
    signature = _signature(scout, intent)
    if cached and cached.get("signature") == signature:
        cached["cache_hit"] = True
        return cached
    package = {
        "task_id": task_id,
        "prepared_at": _utc_now_iso(),
        "goal": intent.get("goal", ""),
        "enabled": scout.get("enabled", False),
        "queries": scout.get("queries", []),
        "trusted_source_types": scout.get("trusted_source_types", []),
        "rules": scout.get("rules", []),
        "mode": "public_read_only_until_approval",
        "signature": signature,
        "cache_hit": False,
    }
    cache_put("research", task_id, package)
    _write_json(RESEARCH_ROOT / f"{task_id}.json", package)
    return package


def main() -> int:
    """
    中文注解：
    - 功能：实现 `main` 对应的处理逻辑。
    - 角色：属于本模块中的对外可见逻辑；私有函数通常服务同文件主流程，公共函数通常作为跨模块入口或能力接口。
    - 调用关系：建议结合本文件的模块说明、调用方以及同名相关辅助函数一起阅读。
    """
    import argparse

    parser = argparse.ArgumentParser(description="Prepare a structured research package for a task")
    parser.add_argument("--task-id", required=True)
    parser.add_argument("--scout-json", required=True)
    parser.add_argument("--intent-json", required=True)
    args = parser.parse_args()
    print(json.dumps(prepare_research_package(args.task_id, json.loads(args.scout_json), json.loads(args.intent_json)), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
