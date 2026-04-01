#!/usr/bin/env python3

"""
中文说明：
- 文件路径：`tools/openmoss/control_center/crawler_remediation_planner.py`
- 文件作用：把 crawler remediation queue 转换成项目级可执行加固计划，供 control plane / doctor / supervisor 共享。
- 顶层函数：build_crawler_remediation_plan、main。
- 顶层类：无顶层类。
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

from paths import (
    CRAWLER_CAPABILITY_PROFILE_PATH,
    CRAWLER_REMEDIATION_PLAN_PATH,
    CRAWLER_REMEDIATION_QUEUE_PATH,
)


REPORTS_ROOT = Path("/Users/mac_claw/.openclaw/workspace/crawler/reports")
SITE_PROFILES_ROOT = Path("/Users/mac_claw/.openclaw/workspace/crawler/site-profiles")


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _read_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return default


def _write_json(path: Path, payload: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _plan_for_action(item: Dict[str, Any], site_map: Dict[str, Dict[str, Any]]) -> Dict[str, Any]:
    site = str(item.get("site", "")).strip().lower()
    action = str(item.get("action", "")).strip()
    site_profile = site_map.get(site, {})
    preferred_tools = site_profile.get("preferred_tool_order", []) or []
    task_output_fields = list((site_profile.get("task_output_fields", {}) or {}).keys())
    if action == "stabilize_site_profile":
        return {
            "id": item.get("id", ""),
            "priority": item.get("priority", "medium"),
            "execution_type": "site_revalidation",
            "site": site,
            "goal": f"重新验证 {site} 的抓取矩阵，优先补齐可用主栈与关键结构字段。",
            "suggested_route": "authorized_session" if site_profile.get("authenticated_supported") else "browser_render",
            "suggested_tools": preferred_tools[:4],
            "verification_targets": [
                "best_status becomes usable",
                "at least one usable tool is confirmed",
                "critical task_output_fields are populated",
            ],
            "evidence_inputs": [
                str(REPORTS_ROOT / f"{site}-latest-run.json"),
                str(SITE_PROFILES_ROOT / f"{site}.json"),
            ],
        }
    if action == "improve_structured_field_coverage":
        return {
            "id": item.get("id", ""),
            "priority": item.get("priority", "medium"),
            "execution_type": "field_coverage_upgrade",
            "site": site,
            "goal": "补齐项目级 crawler 关键结构字段覆盖率，优先修复当前为空或缺失的字段。",
            "suggested_route": "structured_public_endpoint",
            "suggested_tools": ["httpx", "selectolax", "crawl4ai", "playwright"],
            "verification_targets": [
                "project depth score improves",
                "missing structured fields are reduced",
                "site profiles expose usable task_output_fields",
            ],
            "evidence_inputs": [
                str(CRAWLER_CAPABILITY_PROFILE_PATH),
            ],
            "focus_fields": task_output_fields[:8],
        }
    return {
        "id": item.get("id", ""),
        "priority": item.get("priority", "medium"),
        "execution_type": "manual_triage",
        "site": site,
        "goal": str(item.get("reason", "")).strip() or "人工检查 remediation action",
        "suggested_route": "human_checkpoint",
        "suggested_tools": [],
        "verification_targets": ["root cause is clarified"],
        "evidence_inputs": [],
    }


def build_crawler_remediation_plan() -> Dict[str, Any]:
    queue = _read_json(CRAWLER_REMEDIATION_QUEUE_PATH, {"items": []}) or {"items": []}
    profile = _read_json(CRAWLER_CAPABILITY_PROFILE_PATH, {}) or {}
    sites = profile.get("sites", []) or []
    site_map = {
        str(site.get("site", "")).strip().lower(): site
        for site in sites
        if str(site.get("site", "")).strip()
    }
    plans = [_plan_for_action(item, site_map) for item in (queue.get("items", []) or [])]
    payload = {
        "generated_at": _utc_now_iso(),
        "summary": {
            "items_total": len(plans),
            "high_priority_total": sum(1 for item in plans if item.get("priority") == "high"),
            "sites_covered": sorted({item.get("site", "") for item in plans if item.get("site", "")}),
        },
        "items": plans,
    }
    _write_json(CRAWLER_REMEDIATION_PLAN_PATH, payload)
    return payload


def main() -> int:
    print(json.dumps(build_crawler_remediation_plan(), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
