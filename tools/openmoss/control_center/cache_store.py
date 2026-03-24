#!/usr/bin/env python3

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from paths import CACHE_ROOT


def _safe_key(key: str) -> str:
    return re.sub(r"[^a-zA-Z0-9._-]+", "-", key).strip("-")[:120] or "cache-entry"


def _cache_path(namespace: str, key: str) -> Path:
    return CACHE_ROOT / namespace / f"{_safe_key(key)}.json"


def cache_get(namespace: str, key: str, default: Any = None) -> Any:
    path = _cache_path(namespace, key)
    if not path.exists():
        return default
    return json.loads(path.read_text(encoding="utf-8"))


def cache_put(namespace: str, key: str, payload: Any) -> str:
    path = _cache_path(namespace, key)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return str(path)


def main() -> int:
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
