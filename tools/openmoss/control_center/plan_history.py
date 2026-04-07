#!/usr/bin/env python3

"""
中文说明：
- 文件路径：`tools/openmoss/control_center/plan_history.py`
- 文件作用：负责控制中心中与 `plan_history` 相关的编排、分析或决策逻辑。
- 顶层函数：_utc_now_iso、_bucket_key、_history_default、_iter_bucket_dimensions、load_plan_history、record_plan_outcome、load_history_profile、success_rate、main。
- 顶层类：无顶层类。
- 阅读建议：先看模块说明，再按函数/类 docstring 顺着主流程理解调用关系。
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Dict, Iterable, List, Tuple

from cache_store import cache_get, cache_put


def _utc_now_iso() -> str:
    """
    中文注解：
    - 功能：实现 `_utc_now_iso` 对应的处理逻辑。
    - 角色：属于本模块中的内部辅助逻辑；私有函数通常服务同文件主流程，公共函数通常作为跨模块入口或能力接口。
    - 调用关系：建议结合本文件的模块说明、调用方以及同名相关辅助函数一起阅读。
    """
    return datetime.now(timezone.utc).isoformat()


def _bucket_key(plan_id: str, task_types: List[str] | None = None, risk_level: str = "") -> str:
    """
    中文注解：
    - 功能：实现 `_bucket_key` 对应的处理逻辑。
    - 角色：属于本模块中的内部辅助逻辑；私有函数通常服务同文件主流程，公共函数通常作为跨模块入口或能力接口。
    - 调用关系：建议结合本文件的模块说明、调用方以及同名相关辅助函数一起阅读。
    """
    types = ",".join(sorted([str(item).strip() for item in (task_types or []) if str(item).strip()])) or "general"
    risk = risk_level or "unknown"
    return f"plan::{plan_id or 'unknown'}::types={types}::risk={risk}"


def _history_default(plan_id: str, task_types: List[str] | None = None, risk_level: str = "") -> Dict[str, object]:
    """
    中文注解：
    - 功能：实现 `_history_default` 对应的处理逻辑。
    - 角色：属于本模块中的内部辅助逻辑；私有函数通常服务同文件主流程，公共函数通常作为跨模块入口或能力接口。
    - 调用关系：建议结合本文件的模块说明、调用方以及同名相关辅助函数一起阅读。
    """
    return {
        "plan_id": plan_id,
        "task_types": task_types or [],
        "risk_level": risk_level or "unknown",
        "successes": 0,
        "failures": 0,
        "blocked": 0,
        "last_result": "",
        "last_updated_at": "",
    }


def _iter_bucket_dimensions(task_types: List[str] | None = None, risk_level: str = "") -> Iterable[Tuple[List[str], str, str]]:
    """
    中文注解：
    - 功能：实现 `_iter_bucket_dimensions` 对应的处理逻辑。
    - 角色：属于本模块中的内部辅助逻辑；私有函数通常服务同文件主流程，公共函数通常作为跨模块入口或能力接口。
    - 调用关系：建议结合本文件的模块说明、调用方以及同名相关辅助函数一起阅读。
    """
    normalized_types = [str(item).strip() for item in (task_types or []) if str(item).strip()]
    normalized_risk = risk_level or ""
    yield (normalized_types, normalized_risk, "exact")
    if normalized_types:
        yield (normalized_types, "", "task_type")
    if normalized_risk:
        yield ([], normalized_risk, "risk")
    yield ([], "", "global")


def load_plan_history(plan_id: str, task_types: List[str] | None = None, risk_level: str = "") -> Dict[str, object]:
    """
    中文注解：
    - 功能：实现 `load_plan_history` 对应的处理逻辑。
    - 角色：属于本模块中的对外可见逻辑；私有函数通常服务同文件主流程，公共函数通常作为跨模块入口或能力接口。
    - 调用关系：建议结合本文件的模块说明、调用方以及同名相关辅助函数一起阅读。
    """
    return cache_get(
        "plan_history",
        _bucket_key(plan_id, task_types=task_types, risk_level=risk_level),
        _history_default(plan_id, task_types=task_types, risk_level=risk_level),
    )


def record_plan_outcome(plan_id: str, outcome: str, *, task_types: List[str] | None = None, risk_level: str = "") -> Dict[str, object]:
    """
    中文注解：
    - 功能：实现 `record_plan_outcome` 对应的处理逻辑。
    - 角色：属于本模块中的对外可见逻辑；私有函数通常服务同文件主流程，公共函数通常作为跨模块入口或能力接口。
    - 调用关系：建议结合本文件的模块说明、调用方以及同名相关辅助函数一起阅读。
    """
    updated: Dict[str, object] = {}
    seen = set()
    for scoped_types, scoped_risk, bucket_name in _iter_bucket_dimensions(task_types=task_types, risk_level=risk_level):
        key = _bucket_key(plan_id, task_types=scoped_types, risk_level=scoped_risk)
        if key in seen:
            continue
        seen.add(key)
        history = load_plan_history(plan_id, task_types=scoped_types, risk_level=scoped_risk)
        if outcome == "success":
            history["successes"] = int(history.get("successes", 0)) + 1
        elif outcome == "failure":
            history["failures"] = int(history.get("failures", 0)) + 1
        elif outcome == "blocked":
            history["blocked"] = int(history.get("blocked", 0)) + 1
        history["last_result"] = outcome
        history["last_updated_at"] = _utc_now_iso()
        history["bucket"] = bucket_name
        cache_put("plan_history", key, history)
        if bucket_name == "exact":
            updated = history
    return updated or _history_default(plan_id, task_types=task_types, risk_level=risk_level)


def load_history_profile(plan_id: str, task_types: List[str] | None = None, risk_level: str = "") -> Dict[str, object]:
    """
    中文注解：
    - 功能：实现 `load_history_profile` 对应的处理逻辑。
    - 角色：属于本模块中的对外可见逻辑；私有函数通常服务同文件主流程，公共函数通常作为跨模块入口或能力接口。
    - 调用关系：建议结合本文件的模块说明、调用方以及同名相关辅助函数一起阅读。
    """
    exact = load_plan_history(plan_id, task_types=task_types, risk_level=risk_level)
    task_type = load_plan_history(plan_id, task_types=task_types, risk_level="")
    risk = load_plan_history(plan_id, task_types=[], risk_level=risk_level)
    global_history = load_plan_history(plan_id, task_types=[], risk_level="")
    weighted_sources = [
        ("exact", exact, 1.0),
        ("task_type", task_type, 0.7),
        ("risk", risk, 0.55),
        ("global", global_history, 0.35),
    ]
    weighted_successes = 0.0
    weighted_failures = 0.0
    weighted_blocked = 0.0
    active_weights = 0.0
    for _, history, weight in weighted_sources:
        source_total = int(history.get("successes", 0)) + int(history.get("failures", 0)) + int(history.get("blocked", 0))
        if source_total <= 0:
            continue
        weighted_successes += int(history.get("successes", 0)) * weight
        weighted_failures += int(history.get("failures", 0)) * weight
        weighted_blocked += int(history.get("blocked", 0)) * weight
        active_weights += weight
    known_total = weighted_successes + weighted_failures
    blended_success_rate = 0.5 if known_total <= 0 else round(weighted_successes / known_total, 4)
    return {
        "plan_id": plan_id,
        "task_types": task_types or [],
        "risk_level": risk_level or "unknown",
        "sources": {
            "exact": exact,
            "task_type": task_type,
            "risk": risk,
            "global": global_history,
        },
        "active_weight": round(active_weights, 2),
        "blended_history": {
            "successes": round(weighted_successes, 2),
            "failures": round(weighted_failures, 2),
            "blocked": round(weighted_blocked, 2),
        },
        "blended_success_rate": blended_success_rate,
    }


def success_rate(plan_id: str, task_types: List[str] | None = None, risk_level: str = "") -> float:
    """
    中文注解：
    - 功能：实现 `success_rate` 对应的处理逻辑。
    - 角色：属于本模块中的对外可见逻辑；私有函数通常服务同文件主流程，公共函数通常作为跨模块入口或能力接口。
    - 调用关系：建议结合本文件的模块说明、调用方以及同名相关辅助函数一起阅读。
    """
    history = load_plan_history(plan_id, task_types=task_types, risk_level=risk_level)
    successes = int(history.get("successes", 0))
    failures = int(history.get("failures", 0))
    total = successes + failures
    if total <= 0:
        return 0.5
    return successes / total


def main() -> int:
    """
    中文注解：
    - 功能：实现 `main` 对应的处理逻辑。
    - 角色：属于本模块中的对外可见逻辑；私有函数通常服务同文件主流程，公共函数通常作为跨模块入口或能力接口。
    - 调用关系：建议结合本文件的模块说明、调用方以及同名相关辅助函数一起阅读。
    """
    import argparse

    parser = argparse.ArgumentParser(description="Read or update plan execution history")
    parser.add_argument("--plan-id", required=True)
    parser.add_argument("--outcome", default="")
    parser.add_argument("--task-types", default="")
    parser.add_argument("--risk-level", default="")
    parser.add_argument("--profile", action="store_true")
    args = parser.parse_args()
    task_types = [item.strip() for item in args.task_types.split(",") if item.strip()]
    if args.outcome:
        print(
            json.dumps(
                record_plan_outcome(args.plan_id, args.outcome, task_types=task_types, risk_level=args.risk_level),
                ensure_ascii=False,
                indent=2,
            )
        )
        return 0
    if args.profile:
        print(json.dumps(load_history_profile(args.plan_id, task_types=task_types, risk_level=args.risk_level), ensure_ascii=False, indent=2))
        return 0
    print(json.dumps(load_plan_history(args.plan_id, task_types=task_types, risk_level=args.risk_level), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
