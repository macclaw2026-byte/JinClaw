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
- 文件路径：`tools/openmoss/control_center/crawler_probe_runner.py`
- 文件作用：为 crawler layer 提供可复用的本地多工具抓取测试执行器，并负责生成报告、复盘和学习沉淀。
- 顶层函数：run_crawler_probe、run_crawler_retro、main。
- 顶层类：无顶层类。
"""
from __future__ import annotations

import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Tuple


WORKSPACE_ROOT = Path("/Users/mac_claw/.openclaw/workspace")
TASKS_ROOT = WORKSPACE_ROOT / "tools/openmoss/runtime/autonomy/tasks"
LEARNING_ROOT = WORKSPACE_ROOT / "tools/openmoss/runtime/autonomy/learning"
TOOLS_ROOT = WORKSPACE_ROOT / "tools"
SITE_PROFILE_ROOT = WORKSPACE_ROOT / "crawler/site-profiles"
if str(TOOLS_ROOT) not in sys.path:
    sys.path.insert(0, str(TOOLS_ROOT))

from site_tool_matrix_v2 import (  # type: ignore
    QUERY as DEFAULT_QUERY,
    SITES as DEFAULT_SITES,
    agent_browser_tool,
    crawl4ai_tool,
    curl_cffi_tool,
    direct_http_tool,
    playwright_stealth_tool,
    playwright_tool,
    scrapy_cffi_tool,
)
from acquisition_result_normalizer import build_acquisition_execution_summary, render_acquisition_execution_summary_markdown


SUPPORTED_SITES = {
    "amazon": {"aliases": ["amazon", "亚马逊"]},
    "walmart": {"aliases": ["walmart", "沃尔玛"]},
    "temu": {"aliases": ["temu", "拼多多海外", "特木"]},
    "1688": {"aliases": ["1688", "阿里巴巴", "阿里 1688"]},
}

TOOL_RUNNERS = {
    "crawl4ai": {"label": "crawl4ai-cli", "runner": crawl4ai_tool},
    "direct_http": {"label": "direct-http-html", "runner": direct_http_tool},
    "curl_cffi": {"label": "curl-cffi", "runner": curl_cffi_tool},
    "playwright": {"label": "playwright", "runner": playwright_tool},
    "playwright_stealth": {"label": "playwright-stealth", "runner": playwright_stealth_tool},
    "scrapy_cffi": {"label": "scrapy-cffi", "runner": scrapy_cffi_tool},
    "agent_browser": {"label": "local-agent-browser-cli", "runner": agent_browser_tool},
}

TOOL_ALIASES = {
    "crawl4ai": ["crawl4ai", "crawl4ai-cli"],
    "direct_http": ["direct-http", "direct_http", "http static", "http_static", "direct-http-html"],
    "curl_cffi": ["curl_cffi", "curl-cffi"],
    "playwright": ["playwright"],
    "playwright_stealth": ["playwright_stealth", "playwright-stealth", "playwright stealth", "stealth"],
    "scrapy_cffi": ["scrapy_cffi", "scrapy-cffi", "scrapy + curl_cffi", "scrapy+curl_cffi", "scrapy"],
    "agent_browser": ["agent-browser", "agent browser", "agent_browser", "local-agent-browser-cli", "local agent browser"],
}

DEFAULT_TOOL_ORDER = [
    "crawl4ai",
    "direct_http",
    "curl_cffi",
    "playwright",
    "playwright_stealth",
    "scrapy_cffi",
    "agent_browser",
]

FULL_MATRIX_REQUEST_TOKENS = [
    "7个工具",
    "7 tools",
    "七个工具",
    "all known tools",
    "all tools",
    "所有已知工具",
    "全部工具",
    "首次",
    "第一次",
]

SITE_TASK_FIELDS = {
    "amazon": ["title", "price", "rating", "reviews", "link"],
    "walmart": ["title", "price", "rating", "link"],
    "temu": ["title", "price", "link", "promo"],
    "1688": ["title", "price", "moq", "supplier", "link"],
}

FALSE_POSITIVE_PATTERNS = {
    "all": [
        r"access denied",
        r"forbidden",
        r"service unavailable",
        r"temporarily unavailable",
        r"please enable javascript",
    ],
    "amazon": [
        r"automated access",
        r"enter the characters you see below",
        r"sorry, we just need to make sure",
        r"captcha",
    ],
    "walmart": [
        r"robot or human",
        r"confirm that you.?re human",
        r"activate and hold the button",
    ],
    "temu": [
        r"verify",
        r"captcha",
        r"sign in",
        r"login",
        r"puzzle",
    ],
    "1688": [
        r"登录",
        r"密码登录",
        r"短信登录",
        r"请按住滑块",
        r"captcha",
        r"punish",
        r"x5secdata",
        r"nocaptcha",
    ],
}

SITE_NORMALIZATION_RULES = {
    "amazon": {
        "title": [r"aria-label=\"([^\"]+)\"", r"alt=\"([^\"]+)\""],
        "price": [r"\$(\d+(?:\.\d{2})?)"],
        "rating": [r"(\d\.\d) out of 5"],
        "reviews": [r"(\d[\d,]*) ratings"],
        "link": [r"(/dp/[A-Z0-9]{10})"],
    },
    "walmart": {
        "title": [r"aria-label=\"([^\"]+)\"", r"<title>([^<]+)</title>"],
        "price": [r"\$(\d+(?:\.\d{2})?)"],
        "rating": [r"(\d\.\d) out of 5 Stars"],
        "link": [r"(/ip/[^\"'\s<>]+)"],
    },
    "temu": {
        "title": [r"aria-label=\"([^\"]+)\"", r"<title>([^<]+)</title>"],
        "price": [r"\$(\d+(?:\.\d{2})?)"],
        "promo": [r"(free shipping|flash sale|limited time|discount)"],
        "link": [r"(/goods\.html[^\"'\s<>]*)"],
    },
    "1688": {
        "title": [r"title\s*[:=]\s*['\"]([^'\"]+)['\"]", r"<title>([^<]+)</title>"],
        "price": [r"¥\s*(\d+(?:\.\d+)?)"],
        "moq": [r"(\d+)\s*(?:件起批|pcs|min\. order)"],
        "supplier": [r"(?:supplier|供应商|公司名称)[:：\s]*([^\n<]{2,80})"],
        "link": [r"(https?://[^\s\"']+|/offer/[^\"'\s<>]+)"],
    },
}

AUTHENTICATED_MODE_NOTES = {
    "1688": {
        "supported": True,
        "mode": "browser_authorized_session",
        "policy": [
            "需要用户明确授权后才可进入登录态自动化。",
            "优先使用浏览器型工具完成一次正常登录，而不是把凭证分发给所有抓取栈。",
            "登录态 profile 与匿名 profile 必须分开记录。",
            "若遇到 slider/captcha/device-risk，需要人工介入，不做绕过。",
        ],
    }
}


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _normalized(text: str) -> str:
    return re.sub(r"\s+", " ", str(text or "")).strip().lower()


def _detect_requested_sites(goal: str, crawler_plan: Dict[str, Any]) -> List[str]:
    goal_lower = _normalized(goal)
    detected: List[str] = []
    for site_id, meta in SUPPORTED_SITES.items():
        aliases = [site_id, *meta.get("aliases", [])]
        if any(_normalized(alias) in goal_lower for alias in aliases):
            detected.append(site_id)
    likely = [str(item).strip().lower() for item in (crawler_plan.get("requirements", {}) or {}).get("likely_platforms", []) if str(item).strip()]
    for item in likely:
        if item in SUPPORTED_SITES and item not in detected:
            detected.append(item)
    if not detected and ("测试" in goal or "matrix" in goal_lower or "tool" in goal_lower):
        detected = list(SUPPORTED_SITES.keys())
    return detected or ["amazon"]


def _detect_requested_tools(goal: str, crawler_plan: Dict[str, Any]) -> List[str]:
    goal_lower = _normalized(goal)
    requested: List[str] = []
    for canonical, aliases in TOOL_ALIASES.items():
        if any(_normalized(alias) in goal_lower for alias in aliases):
            requested.append(canonical)
    if not requested and _goal_requests_full_matrix(goal):
        requested = list(DEFAULT_TOOL_ORDER)
    selected_stack = (crawler_plan.get("selected_stack", {}) or {}).get("tools", []) or []
    fallback_ids = {str(item) for item in crawler_plan.get("fallback_stacks", []) if str(item).strip()}
    fallback_tools: List[str] = []
    for row in crawler_plan.get("scores", []) or []:
        if str(row.get("stack_id", "")).strip() in fallback_ids:
            fallback_tools.extend([str(item) for item in row.get("tools", []) if str(item).strip()])
    derived_tools = [*selected_stack, *fallback_tools]
    for tool in derived_tools:
        lowered = _normalized(tool)
        for canonical, aliases in TOOL_ALIASES.items():
            if canonical in requested:
                continue
            if lowered == canonical or lowered in [_normalized(alias) for alias in aliases]:
                requested.append(canonical)
    ordered = [tool for tool in DEFAULT_TOOL_ORDER if tool in requested]
    return ordered or list(DEFAULT_TOOL_ORDER)


def _goal_requests_full_matrix(goal: str) -> bool:
    """
    中文注解：
    - 功能：判断用户是否显式要求“全工具矩阵”级别的探测。
    - 设计意图：只有在用户明确要全量矩阵时，probe 才应无条件铺满所有本地工具。
    """
    normalized = _normalized(goal)
    return any(token in normalized for token in FULL_MATRIX_REQUEST_TOKENS)


def _dedupe_ordered(values: Iterable[str]) -> List[str]:
    """
    中文注解：
    - 功能：对字符串序列去重并保持顺序。
    - 设计意图：执行计划、route ids 与 tool ids 都需要稳定顺序，便于 doctor 和 verifier 对账。
    """
    seen: set[str] = set()
    ordered: List[str] = []
    for value in values:
        text = str(value).strip()
        if not text or text in seen:
            continue
        seen.add(text)
        ordered.append(text)
    return ordered


def _candidate_execution_binding(candidate: Dict[str, Any], adapters_by_id: Dict[str, Dict[str, Any]]) -> Dict[str, Any]:
    """
    中文注解：
    - 功能：把 acquisition route candidate 映射成 crawler probe 可直接执行的本地 runner 绑定。
    - 设计意图：计划层按 adapter 思考，执行层按本地 runner 思考，这里负责把两层接起来。
    """
    adapter_id = str(candidate.get("adapter_id", "")).strip()
    adapter = adapters_by_id.get(adapter_id, {})
    tool_id = str(adapter.get("execution_tool_id", "")).strip()
    if not tool_id or tool_id not in TOOL_RUNNERS:
        return {}
    runner_meta = TOOL_RUNNERS.get(tool_id, {}) or {}
    return {
        "route_id": str(candidate.get("route_id", "")).strip(),
        "adapter_id": adapter_id,
        "route_type": str(candidate.get("route_type", "")).strip(),
        "parallel_role": str(candidate.get("parallel_role", "")).strip(),
        "tool_id": tool_id,
        "tool_label": str(runner_meta.get("label", "")).strip(),
        "execution_runtime": str(adapter.get("execution_runtime", "")).strip(),
    }


def _derive_probe_execution_plan(
    goal: str,
    crawler_plan: Dict[str, Any],
    acquisition_hand: Dict[str, Any] | None,
) -> Dict[str, Any]:
    """
    中文注解：
    - 功能：为本地 crawler probe 推导一份局部执行计划。
    - 输入角色：消费 acquisition hand 的路由策略，以及 legacy crawler plan 的回退信息。
    - 输出角色：告诉 probe 本轮该跑哪些本地 runner、哪些全局路线因本地不可执行而跳过。
    """
    legacy_tools = _detect_requested_tools(goal, crawler_plan)
    if not acquisition_hand or not bool(acquisition_hand.get("enabled")):
        return {
            "source": "legacy_requested_tools",
            "global_planned_route_ids": [],
            "active_route_ids": [],
            "skipped_route_ids": [],
            "tool_ids": legacy_tools,
            "route_plan": [],
            "fallback_reason": "acquisition_hand_disabled",
        }

    adapter_registry = acquisition_hand.get("adapter_registry", {}) or {}
    route_candidates = [item for item in (acquisition_hand.get("route_candidates", []) or []) if isinstance(item, dict)]
    adapters_by_id = {
        str(item.get("adapter_id", "")).strip(): item
        for item in adapter_registry.get("adapters", []) or []
        if str(item.get("adapter_id", "")).strip()
    }
    candidates_by_id = {
        str(item.get("route_id", "")).strip(): item
        for item in route_candidates
        if str(item.get("route_id", "")).strip()
    }
    strategy = acquisition_hand.get("execution_strategy", {}) or {}
    global_planned_route_ids = _dedupe_ordered(
        [
            str(strategy.get("primary_route_id", "")).strip(),
            *[str(item).strip() for item in strategy.get("validation_route_ids", []) or []],
            *[str(item).strip() for item in strategy.get("escalation_route_ids", []) or []],
        ]
    )
    route_plan: List[Dict[str, Any]] = []
    active_route_ids: List[str] = []
    active_tool_ids: List[str] = []
    skipped_route_ids: List[str] = []
    full_matrix_requested = _goal_requests_full_matrix(goal)

    def _append_candidate(candidate: Dict[str, Any], reason: str) -> bool:
        binding = _candidate_execution_binding(candidate, adapters_by_id)
        route_id = str(candidate.get("route_id", "")).strip()
        if not binding:
            if route_id:
                skipped_route_ids.append(route_id)
            return False
        tool_id = str(binding.get("tool_id", "")).strip()
        if tool_id in active_tool_ids or route_id in active_route_ids:
            return False
        route_plan.append({**binding, "reason": reason})
        active_route_ids.append(route_id)
        active_tool_ids.append(tool_id)
        return True

    if full_matrix_requested:
        for candidate in route_candidates:
            _append_candidate(candidate, "user_requested_full_matrix")
    else:
        for route_id in global_planned_route_ids:
            candidate = candidates_by_id.get(route_id, {})
            if candidate:
                _append_candidate(candidate, "acquisition_execution_strategy")
        desired_local_total = 2 if bool(strategy.get("allow_parallel_validation")) else 1
        if len(active_tool_ids) < desired_local_total:
            for candidate in route_candidates:
                if len(active_tool_ids) >= desired_local_total:
                    break
                if str(candidate.get("route_id", "")).strip() in active_route_ids:
                    continue
                _append_candidate(candidate, "local_probe_strategy_fill")

    active_tool_ids = _dedupe_ordered(active_tool_ids)
    active_route_ids = _dedupe_ordered(active_route_ids)
    skipped_route_ids = _dedupe_ordered(skipped_route_ids)
    if active_tool_ids:
        return {
            "source": "acquisition_full_matrix" if full_matrix_requested else "acquisition_execution_strategy",
            "global_planned_route_ids": global_planned_route_ids,
            "active_route_ids": active_route_ids,
            "skipped_route_ids": skipped_route_ids,
            "tool_ids": active_tool_ids,
            "route_plan": route_plan,
            "fallback_reason": "",
        }
    return {
        "source": "legacy_requested_tools",
        "global_planned_route_ids": global_planned_route_ids,
        "active_route_ids": [],
        "skipped_route_ids": skipped_route_ids,
        "tool_ids": legacy_tools,
        "route_plan": [],
        "fallback_reason": "no_local_runner_for_current_acquisition_routes",
    }


def _detect_query(goal: str) -> str:
    for pattern in [r"关键词[:：]\s*([^\n。；;]+)", r"query[:：]\s*([^\n。；;]+)", r"搜索词[:：]\s*([^\n。；;]+)"]:
        match = re.search(pattern, goal, flags=re.IGNORECASE)
        if match:
            query = match.group(1).strip().strip("`'\"")
            if query:
                return query
    return DEFAULT_QUERY


def _site_url(site_id: str, query: str) -> str:
    if query == DEFAULT_QUERY and site_id in DEFAULT_SITES:
        return DEFAULT_SITES[site_id]
    from urllib.parse import quote_plus

    if site_id == "amazon":
        return f"https://www.amazon.com/s?k={quote_plus(query)}"
    if site_id == "walmart":
        return f"https://www.walmart.com/search?q={quote_plus(query)}"
    if site_id == "temu":
        return f"https://www.temu.com/search_result.html?search_key={quote_plus(query)}"
    if site_id == "1688":
        return f"https://s.1688.com/selloffer/offer_search.htm?keywords={quote_plus(query)}"
    raise ValueError(f"unsupported site: {site_id}")


def _task_crawler_dir(task_id: str) -> Path:
    return TASKS_ROOT / task_id / "crawler_artifacts"


def _normalize_tool_labels(values: Iterable[str]) -> List[str]:
    return [str(item).strip() for item in values if str(item).strip()]


def _tool_output_text(row: Dict[str, Any]) -> str:
    return "\n".join([str(row.get("stdout_head", "") or ""), str(row.get("stderr_head", "") or "")]).strip()


def _match_count(patterns: List[str], text: str) -> int:
    total = 0
    for pattern in patterns:
        total += len(re.findall(pattern, text, flags=re.IGNORECASE))
    return total


def _detect_false_positive(site_id: str, row: Dict[str, Any]) -> Dict[str, Any]:
    text = _tool_output_text(row)
    low = _normalized(text)
    site_patterns = FALSE_POSITIVE_PATTERNS.get(site_id, [])
    general_patterns = FALSE_POSITIVE_PATTERNS.get("all", [])
    hits: List[str] = []
    for pattern in [*general_patterns, *site_patterns]:
        if re.search(pattern, low, flags=re.IGNORECASE):
            hits.append(pattern)
    tiny_output = len(str(row.get("stdout_head", "") or "").strip()) < 20 and int(row.get("stdout_chars", 0) or 0) < 200
    shell_like = site_id in {"temu", "1688"} and int(row.get("stdout_chars", 0) or 0) > 5000 and int(row.get("product_signal_count", 0) or 0) == 0
    return {
        "is_false_positive": bool(hits or tiny_output or shell_like),
        "reasons": hits + (["tiny_output"] if tiny_output else []) + (["shell_without_task_fields"] if shell_like else []),
    }


def _extract_first(patterns: List[str], text: str) -> str:
    for pattern in patterns:
        match = re.search(pattern, text, flags=re.IGNORECASE)
        if match:
            value = next((g for g in match.groups() if g is not None), match.group(0))
            value = re.sub(r"\s+", " ", str(value)).strip()
            if value:
                return value
    return ""


def _normalize_task_fields(site_id: str, row: Dict[str, Any]) -> Dict[str, Any]:
    text = _tool_output_text(row)
    rules = SITE_NORMALIZATION_RULES.get(site_id, {})
    fields: Dict[str, str] = {}
    for field, patterns in rules.items():
        fields[field] = _extract_first(patterns, text)
    populated = {k: v for k, v in fields.items() if v}
    expected = SITE_TASK_FIELDS.get(site_id, [])
    completeness = round(len(populated) / max(1, len(expected)), 3)
    return {
        "fields": fields,
        "populated_fields": sorted(populated.keys()),
        "field_completeness": completeness,
        "expected_fields": expected,
    }


def _normalized_status(row: Dict[str, Any], false_positive: Dict[str, Any], field_payload: Dict[str, Any]) -> str:
    base_status = str(row.get("status", "")).strip() or "failed"
    if false_positive.get("is_false_positive"):
        if any("tiny_output" == reason for reason in false_positive.get("reasons", [])):
            return "failed"
        return "blocked"
    if field_payload.get("field_completeness", 0.0) >= 0.5 and base_status in {"usable", "partial"}:
        return "usable"
    if field_payload.get("field_completeness", 0.0) > 0.0 and base_status in {"usable", "partial", "failed"}:
        return "partial"
    return base_status


def _rank_tool_result(row: Dict[str, Any], normalized_status: str, field_payload: Dict[str, Any], false_positive: Dict[str, Any]) -> int:
    score = int(row.get("score", 0) or 0)
    score += int(round(float(field_payload.get("field_completeness", 0.0)) * 40))
    if normalized_status == "usable":
        score += 15
    elif normalized_status == "partial":
        score += 5
    elif normalized_status == "blocked":
        score -= 25
    elif normalized_status == "failed":
        score -= 15
    if false_positive.get("is_false_positive"):
        score -= 20
    return max(0, min(100, score))


def _enrich_tool_result(site_id: str, row: Dict[str, Any]) -> Dict[str, Any]:
    false_positive = _detect_false_positive(site_id, row)
    field_payload = _normalize_task_fields(site_id, row)
    normalized_status = _normalized_status(row, false_positive, field_payload)
    arbitration_score = _rank_tool_result(row, normalized_status, field_payload, false_positive)
    enriched = dict(row)
    enriched.update(
        {
            "initial_status": str(row.get("status", "")).strip(),
            "status": normalized_status,
            "false_positive": false_positive,
            "normalized_task_output": field_payload,
            "arbitration_score": arbitration_score,
            "usable_for_task": normalized_status == "usable",
        }
    )
    return enriched


def _site_mode(site_id: str) -> str:
    if site_id == "1688":
        return "anonymous_truth_check_only"
    if site_id in {"amazon", "walmart", "temu"}:
        return "anonymous_public_crawl"
    return "unknown"


def _preferred_tool_order(tool_results: List[Dict[str, Any]]) -> List[str]:
    ordered = sorted(
        tool_results,
        key=lambda item: (
            0 if item.get("status") == "usable" else 1 if item.get("status") == "partial" else 2 if item.get("status") == "blocked" else 3,
            -int(item.get("arbitration_score", 0) or 0),
            -float((item.get("normalized_task_output", {}) or {}).get("field_completeness", 0.0) or 0.0),
            str(item.get("tool", "")),
        ),
    )
    return [str(item.get("tool", "")).strip() for item in ordered if str(item.get("tool", "")).strip()]


def _task_output_choice(site_id: str, tool_results: List[Dict[str, Any]]) -> Dict[str, Any]:
    surviving = [item for item in tool_results if item.get("status") in {"usable", "partial"}]
    surviving.sort(
        key=lambda item: (
            0 if item.get("status") == "usable" else 1,
            -int(item.get("arbitration_score", 0) or 0),
            -float((item.get("normalized_task_output", {}) or {}).get("field_completeness", 0.0) or 0.0),
        )
    )
    if not surviving:
        return {
            "decision": "blocked_or_insufficient_evidence",
            "selected_tool": "",
            "task_output": {},
            "confidence": "low",
        }
    best = surviving[0]
    return {
        "decision": "best_single_tool_output",
        "selected_tool": str(best.get("tool", "")).strip(),
        "task_output": (best.get("normalized_task_output", {}) or {}).get("fields", {}),
        "confidence": "high" if best.get("status") == "usable" else "medium",
    }


def _summarize_site(site_payload: Dict[str, Any]) -> Dict[str, Any]:
    tool_results = list(site_payload.get("tool_results", []) or [])
    usable = [item for item in tool_results if str(item.get("status", "")).strip() == "usable"]
    blocked = [item for item in tool_results if str(item.get("status", "")).strip() == "blocked"]
    best = tool_results[0] if tool_results else {}
    return {
        "best_tool": str(best.get("tool", "")),
        "best_score": int(best.get("arbitration_score", best.get("score", 0)) or 0),
        "usable_tools": [str(item.get("tool", "")) for item in usable],
        "blocked_tools": [str(item.get("tool", "")) for item in blocked],
        "preferred_tool_order": _preferred_tool_order(tool_results),
        "task_output_choice": _task_output_choice(str(site_payload.get("site", "")), tool_results),
    }


def _build_site_profile(site_id: str, site_payload: Dict[str, Any]) -> Tuple[Dict[str, Any], str]:
    tool_results = list(site_payload.get("tool_results", []) or [])
    preferred_tool_order = _preferred_tool_order(tool_results)
    blocked_tools = [str(item.get("tool", "")) for item in tool_results if item.get("status") == "blocked"]
    usable_tools = [str(item.get("tool", "")) for item in tool_results if item.get("status") == "usable"]
    best_choice = _task_output_choice(site_id, tool_results)
    confidence = "high" if usable_tools else "medium" if best_choice.get("decision") != "blocked_or_insufficient_evidence" else "low"
    authenticated = AUTHENTICATED_MODE_NOTES.get(site_id)
    payload = {
        "site": site_id,
        "last_evaluated": datetime.now().date().isoformat(),
        "mode": _site_mode(site_id),
        "confidence": confidence,
        "tested_tools": [str(item.get("tool", "")) for item in tool_results],
        "preferred_tool_order": preferred_tool_order,
        "blocked_tools": blocked_tools,
        "usable_tools": usable_tools,
        "first_choice_extraction_mode": best_choice.get("decision", ""),
        "selected_tool": best_choice.get("selected_tool", ""),
        "task_output_fields": (best_choice.get("task_output", {}) or {}),
        "fallback_policy": "Start with the first preferred tool; if blocked/weak, step through the remaining preferred tools in order. Trigger full all-tools re-evaluation when the top path degrades materially.",
        "known_failure_modes": [
            {
                "tool": str(item.get("tool", "")),
                "status": str(item.get("status", "")),
                "reasons": list(((item.get("false_positive", {}) or {}).get("reasons", [])) or []),
            }
            for item in tool_results
            if item.get("status") in {"blocked", "failed"}
        ],
        "authenticated_mode": authenticated or {"supported": False},
    }

    lines = [
        f"# {site_id.capitalize() if site_id != '1688' else '1688'} Site Profile",
        "",
        f"- Last evaluated: {payload['last_evaluated']}",
        f"- Confidence: {payload['confidence']}",
        f"- Recommended mode: {payload['mode']}",
        "",
        "## Preferred tool order",
    ]
    for idx, tool in enumerate(preferred_tool_order, start=1):
        lines.append(f"{idx}. {tool}")
    lines.extend(
        [
            "",
            "## Recommended default",
            f"- Primary: {best_choice.get('selected_tool', '') or 'none'}",
            f"- Extraction decision: {best_choice.get('decision', '')}",
            "",
            "## Task-ready fields from current best result",
        ]
    )
    fields = best_choice.get("task_output", {}) or {}
    if fields:
        for key, value in fields.items():
            lines.append(f"- {key}: {value or '(empty)'}")
    else:
        lines.append("- No task-ready fields survived arbitration in the current anonymous run")
    lines.extend(["", "## Known behavior"])
    for item in tool_results:
        reasons = list(((item.get("false_positive", {}) or {}).get("reasons", [])) or [])
        completeness = float(((item.get("normalized_task_output", {}) or {}).get("field_completeness", 0.0) or 0.0))
        lines.append(
            f"- {item.get('tool', '')}: status={item.get('status', '')}, arbitration_score={item.get('arbitration_score', 0)}, field_completeness={completeness}, false_positive_reasons={reasons or ['none']}"
        )
    lines.extend(["", "## Repeat-run policy"])
    lines.append("- Start with the first preferred tool")
    lines.append("- If blocked or weak, try the next fallback in order")
    lines.append("- If the top path degrades materially, trigger a fresh all-tools first-run evaluation")
    if authenticated:
        lines.extend(["", "## Auth note"])
        for note in authenticated.get("policy", []):
            lines.append(f"- {note}")
    return payload, "\n".join(lines)


def run_crawler_probe(
    task_id: str,
    goal: str,
    crawler_plan: Dict[str, Any],
    acquisition_hand: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    """
    中文注解：
    - 功能：执行一轮真实 crawler 工具矩阵测试，并产出结构化报告。
    - 说明：当前版本优先服务“多站点、多工具验证”型抓取任务。
    """
    requested_sites = _detect_requested_sites(goal, crawler_plan)
    execution_plan = _derive_probe_execution_plan(goal, crawler_plan, acquisition_hand)
    requested_tools = [str(item) for item in execution_plan.get("tool_ids", []) if str(item).strip()]
    query = _detect_query(goal)
    output_dir = _task_crawler_dir(task_id)
    output_dir.mkdir(parents=True, exist_ok=True)

    site_payloads: List[Dict[str, Any]] = []
    site_profile_updates: Dict[str, Any] = {}
    for site_id in requested_sites:
        url = _site_url(site_id, query)
        tool_results = []
        for tool_id in requested_tools:
            runner_meta = TOOL_RUNNERS.get(tool_id)
            if not runner_meta:
                continue
            result = runner_meta["runner"](site_id, url)
            enriched = _enrich_tool_result(site_id, result.__dict__)
            if site_id == "walmart" and str(enriched.get("tool", "")).strip() == "direct-http-html":
                task_fields = ((enriched.get("normalized_task_output", {}) or {}).get("fields", {}) or {})
                title = str(task_fields.get("title", "") or "").strip().lower()
                if title.endswith("- walmart.com"):
                    task_fields["title"] = ""
                    normalized = dict(enriched.get("normalized_task_output", {}) or {})
                    normalized["fields"] = task_fields
                    populated = sorted([k for k, v in task_fields.items() if str(v).strip()])
                    normalized["populated_fields"] = populated
                    expected = normalized.get("expected_fields", []) or []
                    normalized["field_completeness"] = round(len(populated) / max(1, len(expected)), 3)
                    enriched["normalized_task_output"] = normalized
                    enriched["status"] = "blocked"
                    enriched["usable_for_task"] = False
                    fp = dict(enriched.get("false_positive", {}) or {})
                    reasons = list(fp.get("reasons", []) or [])
                    if "title_only_shell_page" not in reasons:
                        reasons.append("title_only_shell_page")
                    fp["is_false_positive"] = True
                    fp["reasons"] = reasons
                    enriched["false_positive"] = fp
                    enriched["arbitration_score"] = 0
            tool_results.append(enriched)
        tool_results.sort(
            key=lambda item: (
                0 if item.get("status") == "usable" else 1 if item.get("status") == "partial" else 2 if item.get("status") == "blocked" else 3,
                -int(item.get("arbitration_score", 0) or 0),
                str(item.get("tool", "")),
            )
        )
        site_payload = {
            "site": site_id,
            "url": url,
            "tool_results": tool_results,
        }
        site_payload["summary"] = _summarize_site(site_payload)
        profile_payload, profile_markdown = _build_site_profile(site_id, site_payload)
        site_profile_path = SITE_PROFILE_ROOT / f"{site_id}.md"
        site_profile_json_path = SITE_PROFILE_ROOT / f"{site_id}.json"
        _write_text(site_profile_path, profile_markdown)
        _write_json(site_profile_json_path, profile_payload)
        site_profile_updates[site_id] = {
            "markdown_path": str(site_profile_path),
            "json_path": str(site_profile_json_path),
            "selected_tool": profile_payload.get("selected_tool", ""),
            "preferred_tool_order": profile_payload.get("preferred_tool_order", []),
        }
        site_payloads.append(site_payload)

    report_payload = {
        "task_id": task_id,
        "generated_at": _utc_now_iso(),
        "goal": goal,
        "query": query,
        "required_sites": requested_sites,
        "required_tools": requested_tools,
        "planned_execution": execution_plan,
        "selected_stack": (crawler_plan.get("selected_stack", {}) or {}).get("stack_id", ""),
        "fallback_stacks": list(crawler_plan.get("fallback_stacks", []) or []),
        "sites": site_payloads,
        "site_profile_updates": site_profile_updates,
        "authenticated_mode_policy": AUTHENTICATED_MODE_NOTES,
    }
    report_json_path = output_dir / "crawler-tool-matrix.json"
    _write_json(report_json_path, report_payload)

    md_lines = [
        "# Crawler tool matrix report",
        "",
        f"- Task: `{task_id}`",
        f"- Query: `{query}`",
        f"- Required sites: `{', '.join(requested_sites)}`",
        f"- Required tools: `{', '.join(requested_tools)}`",
        f"- Generated at: `{report_payload['generated_at']}`",
        "",
    ]
    for site in site_payloads:
        md_lines.append(f"## {site['site']}")
        md_lines.append("")
        md_lines.append("| Tool | Status | Arbitration score | Field completeness | False positive |")
        md_lines.append("|---|---|---:|---:|---|")
        for row in site.get("tool_results", []):
            md_lines.append(
                f"| {row.get('tool', '')} | {row.get('status', '')} | {row.get('arbitration_score', 0)} | "
                f"{(row.get('normalized_task_output', {}) or {}).get('field_completeness', 0.0)} | "
                f"{','.join(((row.get('false_positive', {}) or {}).get('reasons', []) or ['none']))} |"
            )
        md_lines.append("")
        choice = (site.get("summary", {}) or {}).get("task_output_choice", {}) or {}
        md_lines.append(f"- Selected task-output tool: `{choice.get('selected_tool', '') or 'none'}`")
        md_lines.append(f"- Output decision: `{choice.get('decision', '')}`")
        md_lines.append(f"- Confidence: `{choice.get('confidence', '')}`")
        md_lines.append("")
    report_md_path = output_dir / "crawler-tool-matrix-report.md"
    _write_text(report_md_path, "\n".join(md_lines))

    attempted_tool_labels = {
        site["site"]: _normalize_tool_labels(row.get("tool", "") for row in site.get("tool_results", []))
        for site in site_payloads
    }
    coverage = {
        "required_sites_covered": sorted({site["site"] for site in site_payloads}),
        "required_tools_requested": requested_tools,
        "attempted_tool_labels": attempted_tool_labels,
        "planned_execution": {
            "source": str(execution_plan.get("source", "")).strip(),
            "global_planned_route_ids": [str(item) for item in execution_plan.get("global_planned_route_ids", []) if str(item).strip()],
            "active_route_ids": [str(item) for item in execution_plan.get("active_route_ids", []) if str(item).strip()],
            "skipped_route_ids": [str(item) for item in execution_plan.get("skipped_route_ids", []) if str(item).strip()],
            "active_tool_ids": requested_tools,
            "fallback_reason": str(execution_plan.get("fallback_reason", "")).strip(),
        },
        "all_sites_attempted": sorted({site["site"] for site in site_payloads}) == sorted(requested_sites),
    }
    acquisition_summary: Dict[str, Any] = {}
    acquisition_summary_json_path = ""
    acquisition_summary_md_path = ""
    if acquisition_hand:
        acquisition_summary = build_acquisition_execution_summary(
            task_id,
            goal,
            report_payload,
            acquisition_hand,
            report_path=str(report_json_path),
        )
        acquisition_summary_json_path = str(output_dir / "crawler-acquisition-summary.json")
        acquisition_summary_md_path = str(output_dir / "crawler-acquisition-summary.md")
        _write_json(Path(acquisition_summary_json_path), acquisition_summary)
        _write_text(
            Path(acquisition_summary_md_path),
            render_acquisition_execution_summary_markdown(acquisition_summary),
        )
    return {
        "report_json_path": str(report_json_path),
        "report_md_path": str(report_md_path),
        "acquisition_summary_json_path": acquisition_summary_json_path,
        "acquisition_summary_md_path": acquisition_summary_md_path,
        "acquisition_summary": acquisition_summary,
        "required_sites": requested_sites,
        "required_tools": requested_tools,
        "planned_execution": execution_plan,
        "coverage": coverage,
        "site_summaries": {site["site"]: site.get("summary", {}) for site in site_payloads},
        "site_profile_updates": site_profile_updates,
    }


def run_crawler_retro(task_id: str, goal: str, crawler_plan: Dict[str, Any], execution_artifacts: Dict[str, Any]) -> Dict[str, Any]:
    """
    中文注解：
    - 功能：根据 execute 结果生成 crawler 复盘与学习产物，并把站点偏好写入长期学习存储。
    """
    report_json_path = Path(str(execution_artifacts.get("report_json_path", "")))
    if not report_json_path.exists():
        raise FileNotFoundError(f"crawler report missing: {report_json_path}")
    payload = json.loads(report_json_path.read_text(encoding="utf-8"))
    sites = payload.get("sites", []) or []
    best_tool_by_site = {}
    lessons: List[str] = []
    for site in sites:
        site_id = str(site.get("site", "")).strip()
        tool_results = list(site.get("tool_results", []) or [])
        best_choice = _task_output_choice(site_id, tool_results)
        best_tool = str(best_choice.get("selected_tool", "")).strip()
        ranked_first = tool_results[0] if tool_results else {}
        best_tool_by_site[site_id] = {
            "tool": best_tool,
            "score": int(ranked_first.get("arbitration_score", ranked_first.get("score", 0)) or 0),
            "status": str(ranked_first.get("status", "")).strip(),
            "preferred_tool_order": _preferred_tool_order(tool_results),
            "decision": best_choice.get("decision", ""),
        }
        blocked = [str(item.get("tool", "")) for item in tool_results if str(item.get("status", "")).strip() == "blocked"]
        if best_tool:
            lessons.append(f"{site_id} 当前任务输出首选是 {best_tool}，优先顺序为 {', '.join(best_tool_by_site[site_id]['preferred_tool_order'])}。")
        else:
            lessons.append(f"{site_id} 当前没有足够稳定的任务输出工具，结论应保持 blocked/insufficient。")
        if blocked:
            lessons.append(f"{site_id} 被明显拦截的工具包括：{', '.join(blocked)}。")
        if site_id == "1688":
            lessons.append("1688 可设计授权登录态模式，但必须与匿名 profile 分离，且不能承诺无人工干预通过 slider/captcha/device-risk。")
    output_dir = _task_crawler_dir(task_id)
    retro_payload = {
        "task_id": task_id,
        "generated_at": _utc_now_iso(),
        "goal": goal,
        "best_tool_by_site": best_tool_by_site,
        "lessons": lessons,
        "selected_stack": (crawler_plan.get("selected_stack", {}) or {}).get("stack_id", ""),
        "fallback_stacks": list(crawler_plan.get("fallback_stacks", []) or []),
        "coverage": execution_artifacts.get("coverage", {}),
        "site_profile_updates": execution_artifacts.get("site_profile_updates", {}),
    }
    retro_json_path = output_dir / "crawler-retro.json"
    _write_json(retro_json_path, retro_payload)
    retro_md_path = output_dir / "crawler-retro.md"
    _write_text(
        retro_md_path,
        "\n".join(
            [
                "# Crawler retro",
                "",
                f"- Task: `{task_id}`",
                "",
                *[f"- {lesson}" for lesson in lessons],
            ]
        ),
    )

    learning_path = LEARNING_ROOT / "crawler_site_preferences.json"
    current = json.loads(learning_path.read_text(encoding="utf-8")) if learning_path.exists() else {"sites": {}}
    for site_id, info in best_tool_by_site.items():
        current.setdefault("sites", {})[site_id] = {
            "preferred_tool": info.get("tool", ""),
            "preferred_tool_order": info.get("preferred_tool_order", []),
            "last_score": info.get("score", 0),
            "last_status": info.get("status", ""),
            "last_decision": info.get("decision", ""),
            "last_task_id": task_id,
            "updated_at": _utc_now_iso(),
        }
    _write_json(learning_path, current)

    evolution_payload = {
        "task_id": task_id,
        "generated_at": _utc_now_iso(),
        "reason": "crawler_task_completed_with_real_probe_results",
        "recommended_rank_adjustments": best_tool_by_site,
        "learning_store_path": str(learning_path),
    }
    evolution_json_path = output_dir / "crawler-evolution.json"
    _write_json(evolution_json_path, evolution_payload)

    return {
        "retro_json_path": str(retro_json_path),
        "retro_md_path": str(retro_md_path),
        "learning_store_path": str(learning_path),
        "evolution_json_path": str(evolution_json_path),
        "best_tool_by_site": best_tool_by_site,
        "lessons": lessons,
    }


def main() -> int:
    import argparse

    parser = argparse.ArgumentParser(description="Run crawler probe / retro for a task")
    parser.add_argument("--task-id", required=True)
    parser.add_argument("--goal", required=True)
    parser.add_argument("--crawler-json", required=True)
    parser.add_argument("--acquisition-hand-json", default="")
    parser.add_argument("--mode", choices=["probe", "retro"], default="probe")
    parser.add_argument("--execution-json", default="")
    args = parser.parse_args()
    crawler = json.loads(args.crawler_json)
    if args.mode == "probe":
        payload = run_crawler_probe(
            args.task_id,
            args.goal,
            crawler,
            json.loads(args.acquisition_hand_json or "{}"),
        )
    else:
        payload = run_crawler_retro(args.task_id, args.goal, crawler, json.loads(args.execution_json or "{}"))
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
