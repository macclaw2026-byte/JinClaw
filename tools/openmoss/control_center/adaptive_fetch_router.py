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
- 文件路径：`tools/openmoss/control_center/adaptive_fetch_router.py`
- 文件作用：负责控制中心中与 `adaptive_fetch_router` 相关的编排、分析或决策逻辑。
- 顶层函数：_write_json、_route_ladder、build_fetch_route、main。
- 顶层类：无顶层类。
- 阅读建议：先看模块说明，再按函数/类 docstring 顺着主流程理解调用关系。
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Dict, List

from crawler_capability_profile import build_crawler_capability_profile
from paths import FETCH_ROUTES_ROOT


SITE_ALIASES = {
    "amazon": ["amazon", "亚马逊"],
    "walmart": ["walmart", "沃尔玛"],
    "temu": ["temu", "特木"],
    "1688": ["1688", "阿里巴巴", "阿里 1688"],
    "yiwugo": ["yiwugo", "义乌购"],
    "made-in-china": ["made-in-china", "made in china", "中国制造网"],
}


def _write_json(path: Path, payload: object) -> None:
    """
    中文注解：
    - 功能：实现 `_write_json` 对应的处理逻辑。
    - 角色：属于本模块中的内部辅助逻辑；私有函数通常服务同文件主流程，公共函数通常作为跨模块入口或能力接口。
    - 调用关系：建议结合本文件的模块说明、调用方以及同名相关辅助函数一起阅读。
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _requested_sites(intent: Dict[str, object]) -> List[str]:
    goal = str(intent.get("goal", "") or "").lower()
    likely = {str(item).strip().lower() for item in intent.get("likely_platforms", []) if str(item).strip()}
    domains = {str(item).strip().lower() for item in intent.get("domains", []) if str(item).strip()}
    sites: List[str] = []
    for site_id, aliases in SITE_ALIASES.items():
        if site_id in likely or site_id in domains or any(alias.lower() in goal for alias in aliases):
            sites.append(site_id)
    return sites


def _tool_to_route(tool_name: str) -> str:
    lowered = str(tool_name or "").strip().lower()
    if lowered in {"web", "search"}:
        return "official_api"
    if lowered in {"httpx", "curl_cffi", "selectolax", "scrapy"}:
        return "static_fetch"
    if lowered in {"crawl4ai"}:
        return "crawl4ai"
    if lowered in {"playwright", "playwright_stealth", "browser", "agent-browser", "local-agent-browser-cli"}:
        return "browser_render"
    return ""


def _apply_crawler_profile_guidance(ladder: List[str], intent: Dict[str, object]) -> Dict[str, object]:
    profile = build_crawler_capability_profile()
    sites = profile.get("sites", []) or []
    feedback = profile.get("feedback", {}) or {}
    requested_sites = _requested_sites(intent)
    relevant = [
        site for site in sites if str(site.get("site", "")).strip().lower() in set(requested_sites)
    ]
    guidance = {
        "requested_sites": requested_sites,
        "relevant_sites": [],
        "project_summary": profile.get("summary", {}) or {},
        "project_feedback": feedback,
        "route_overrides": [],
    }
    adjusted = list(ladder)
    coverage_status = str(feedback.get("coverage_status", "")).strip().lower()
    if coverage_status == "thin":
        adjusted = [item for item in ["official_api", "structured_public_endpoint", *adjusted, "human_checkpoint"] if item]
        guidance["route_overrides"].append("project:feedback_thin:prefer_low_risk_routes")
    elif coverage_status == "partial" and "structured_public_endpoint" in adjusted:
        adjusted = ["structured_public_endpoint"] + [item for item in adjusted if item != "structured_public_endpoint"]
        guidance["route_overrides"].append("project:feedback_partial:prefer_structured_endpoint")
    for site in relevant:
        site_name = str(site.get("site", "")).strip().lower()
        selected_tool = str(site.get("selected_tool", "")).strip()
        best_status = str(site.get("best_status", "")).strip().lower()
        authenticated_supported = bool(site.get("authenticated_supported"))
        readiness = str(site.get("readiness", "")).strip()
        route = _tool_to_route(selected_tool)
        guidance["relevant_sites"].append(
            {
                "site": site_name,
                "readiness": readiness,
                "best_status": best_status,
                "selected_tool": selected_tool,
                "primary_limitations": site.get("primary_limitations", []),
            }
        )
        if readiness == "production_ready" and route and route in adjusted:
            adjusted = [route] + [item for item in adjusted if item != route]
            guidance["route_overrides"].append(f"{site_name}:prefer:{route}")
        elif readiness == "attention_required" and authenticated_supported and "authorized_session" in adjusted:
            adjusted = ["authorized_session"] + [item for item in adjusted if item != "authorized_session"]
            guidance["route_overrides"].append(f"{site_name}:escalate:authorized_session")
        elif readiness == "attention_required" and best_status == "blocked" and "human_checkpoint" in adjusted:
            without_human = [item for item in adjusted if item != "human_checkpoint"]
            adjusted = without_human + ["human_checkpoint"]
            guidance["route_overrides"].append(f"{site_name}:retain_human_checkpoint")
    seen: set[str] = set()
    normalized = []
    for item in adjusted:
        if item in seen:
            continue
        seen.add(item)
        normalized.append(item)
    guidance["adjusted_ladder"] = normalized
    return guidance


def _route_ladder(intent: Dict[str, object], selected_plan: Dict[str, object], domain_profile: Dict[str, object], challenge: Dict[str, object]) -> List[str]:
    """
    中文注解：
    - 功能：实现 `_route_ladder` 对应的处理逻辑。
    - 角色：属于本模块中的内部辅助逻辑；私有函数通常服务同文件主流程，公共函数通常作为跨模块入口或能力接口。
    - 调用关系：建议结合本文件的模块说明、调用方以及同名相关辅助函数一起阅读。
    """
    ladder = list(domain_profile.get("default_fetch_ladder", [])) or [
        "official_api",
        "structured_public_endpoint",
        "static_fetch",
        "crawl4ai",
        "browser_render",
        "authorized_session",
        "human_checkpoint",
    ]
    safe_next_routes = [str(item) for item in challenge.get("safe_next_routes", []) if str(item).strip()]
    if safe_next_routes:
        return safe_next_routes
    if challenge.get("recommended_route") == "browser_render":
        return ["browser_render", "authorized_session", "human_checkpoint"]
    if challenge.get("recommended_route") == "official_source_or_authorized_session":
        return ["official_api", "structured_public_endpoint", "authorized_session", "human_checkpoint"]
    if challenge.get("recommended_route") == "slow_down_and_switch_to_structured_source":
        return ["official_api", "structured_public_endpoint", "static_fetch", "browser_render"]
    if challenge.get("recommended_route") == "authorized_session":
        return ["authorized_session", "human_checkpoint"]
    if challenge.get("recommended_route") == "human_checkpoint":
        return ["human_checkpoint"]
    if selected_plan.get("plan_id") == "audited_external_extension":
        return ["official_api", "structured_public_endpoint", "static_fetch", "crawl4ai", "browser_render", "authorized_session", "human_checkpoint"]
    return ladder


def build_fetch_route(task_id: str, intent: Dict[str, object], selected_plan: Dict[str, object], domain_profile: Dict[str, object], challenge: Dict[str, object]) -> Dict[str, object]:
    """
    中文注解：
    - 功能：实现 `build_fetch_route` 对应的处理逻辑。
    - 角色：属于本模块中的对外可见逻辑；私有函数通常服务同文件主流程，公共函数通常作为跨模块入口或能力接口。
    - 调用关系：建议结合本文件的模块说明、调用方以及同名相关辅助函数一起阅读。
    """
    ladder = _route_ladder(intent, selected_plan, domain_profile, challenge)
    crawler_guidance = _apply_crawler_profile_guidance(ladder, intent)
    ladder = list(crawler_guidance.get("adjusted_ladder", ladder))
    current = ladder[0] if ladder else "monitor"
    payload = {
        "task_id": task_id,
        "current_route": current,
        "route_ladder": ladder,
        "crawler_project_guidance": crawler_guidance,
        "official_first": True,
        "browser_last_before_authorized": True,
        "challenge_awareness": challenge,
        "strategy": {
            "api_first": True,
            "static_fetch_before_browser": True,
            "browser_only_when_needed": True,
            "authorized_session_requires_review": True,
            "never_bypass_verification": True,
        },
    }
    _write_json(FETCH_ROUTES_ROOT / f"{task_id}.json", payload)
    return payload


def main() -> int:
    """
    中文注解：
    - 功能：实现 `main` 对应的处理逻辑。
    - 角色：属于本模块中的对外可见逻辑；私有函数通常服务同文件主流程，公共函数通常作为跨模块入口或能力接口。
    - 调用关系：建议结合本文件的模块说明、调用方以及同名相关辅助函数一起阅读。
    """
    import argparse

    parser = argparse.ArgumentParser(description="Build an adaptive fetch route for a task")
    parser.add_argument("--task-id", required=True)
    parser.add_argument("--intent-json", required=True)
    parser.add_argument("--plan-json", required=True)
    parser.add_argument("--domain-profile-json", required=True)
    parser.add_argument("--challenge-json", required=True)
    args = parser.parse_args()
    print(
        json.dumps(
            build_fetch_route(
                args.task_id,
                json.loads(args.intent_json),
                json.loads(args.plan_json),
                json.loads(args.domain_profile_json),
                json.loads(args.challenge_json),
            ),
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
