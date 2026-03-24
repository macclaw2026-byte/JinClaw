#!/usr/bin/env python3

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict

from cache_store import cache_get, cache_put
from paths import RESEARCH_ROOT


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _write_json(path: Path, payload) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _signature(scout: Dict[str, object], intent: Dict[str, object]) -> str:
    payload = {
        "goal": intent.get("goal", ""),
        "queries": scout.get("queries", []),
        "rules": scout.get("rules", []),
        "trusted_source_types": scout.get("trusted_source_types", []),
    }
    return json.dumps(payload, ensure_ascii=False, sort_keys=True)


def prepare_research_package(task_id: str, scout: Dict[str, object], intent: Dict[str, object]) -> Dict[str, object]:
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
