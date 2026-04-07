#!/usr/bin/env python3

"""
中文说明：
- 文件路径：`tools/openmoss/control_center/cache_store.py`
- 文件作用：负责控制中心中与 `cache_store` 相关的编排、分析或决策逻辑。
- 顶层函数：_safe_key、_cache_path、cache_get、cache_put、main。
- 顶层类：无顶层类。
- 阅读建议：先看模块说明，再按函数/类 docstring 顺着主流程理解调用关系。
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from paths import CACHE_ROOT


def _safe_key(key: str) -> str:
    """
    中文注解：
    - 功能：实现 `_safe_key` 对应的处理逻辑。
    - 角色：属于本模块中的内部辅助逻辑；私有函数通常服务同文件主流程，公共函数通常作为跨模块入口或能力接口。
    - 调用关系：建议结合本文件的模块说明、调用方以及同名相关辅助函数一起阅读。
    """
    return re.sub(r"[^a-zA-Z0-9._-]+", "-", key).strip("-")[:120] or "cache-entry"


def _cache_path(namespace: str, key: str) -> Path:
    """
    中文注解：
    - 功能：实现 `_cache_path` 对应的处理逻辑。
    - 角色：属于本模块中的内部辅助逻辑；私有函数通常服务同文件主流程，公共函数通常作为跨模块入口或能力接口。
    - 调用关系：建议结合本文件的模块说明、调用方以及同名相关辅助函数一起阅读。
    """
    return CACHE_ROOT / namespace / f"{_safe_key(key)}.json"


def cache_get(namespace: str, key: str, default: Any = None) -> Any:
    """
    中文注解：
    - 功能：实现 `cache_get` 对应的处理逻辑。
    - 角色：属于本模块中的对外可见逻辑；私有函数通常服务同文件主流程，公共函数通常作为跨模块入口或能力接口。
    - 调用关系：建议结合本文件的模块说明、调用方以及同名相关辅助函数一起阅读。
    """
    path = _cache_path(namespace, key)
    if not path.exists():
        return default
    return json.loads(path.read_text(encoding="utf-8"))


def cache_put(namespace: str, key: str, payload: Any) -> str:
    """
    中文注解：
    - 功能：实现 `cache_put` 对应的处理逻辑。
    - 角色：属于本模块中的对外可见逻辑；私有函数通常服务同文件主流程，公共函数通常作为跨模块入口或能力接口。
    - 调用关系：建议结合本文件的模块说明、调用方以及同名相关辅助函数一起阅读。
    """
    path = _cache_path(namespace, key)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return str(path)


def main() -> int:
    """
    中文注解：
    - 功能：实现 `main` 对应的处理逻辑。
    - 角色：属于本模块中的对外可见逻辑；私有函数通常服务同文件主流程，公共函数通常作为跨模块入口或能力接口。
    - 调用关系：建议结合本文件的模块说明、调用方以及同名相关辅助函数一起阅读。
    """
    import argparse

    parser = argparse.ArgumentParser(description="Minimal JSON cache for control-center artifacts")
    parser.add_argument("--namespace", required=True)
    parser.add_argument("--key", required=True)
    parser.add_argument("--value-json", default="")
    args = parser.parse_args()
    if args.value_json:
        print(cache_put(args.namespace, args.key, json.loads(args.value_json)))
        return 0
    print(json.dumps(cache_get(args.namespace, args.key, {}), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
