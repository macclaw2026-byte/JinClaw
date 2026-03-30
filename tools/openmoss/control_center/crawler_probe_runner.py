#!/usr/bin/env python3

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
from typing import Any, Dict, Iterable, List


WORKSPACE_ROOT = Path("/Users/mac_claw/.openclaw/workspace")
TASKS_ROOT = WORKSPACE_ROOT / "tools/openmoss/runtime/autonomy/tasks"
LEARNING_ROOT = WORKSPACE_ROOT / "tools/openmoss/runtime/autonomy/learning"
TOOLS_ROOT = WORKSPACE_ROOT / "tools"
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
    if not requested and ("7个工具" in goal or "7 tools" in goal_lower or "七个工具" in goal):
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


def _summarize_site(site_payload: Dict[str, Any]) -> Dict[str, Any]:
    tool_results = list(site_payload.get("tool_results", []) or [])
    usable = [item for item in tool_results if str(item.get("status", "")).strip() == "usable"]
    blocked = [item for item in tool_results if str(item.get("status", "")).strip() == "blocked"]
    best = tool_results[0] if tool_results else {}
    return {
        "best_tool": str(best.get("tool", "")),
        "best_score": int(best.get("score", 0) or 0),
        "usable_tools": [str(item.get("tool", "")) for item in usable],
        "blocked_tools": [str(item.get("tool", "")) for item in blocked],
    }


def _normalize_tool_labels(values: Iterable[str]) -> List[str]:
    return [str(item).strip() for item in values if str(item).strip()]


def run_crawler_probe(task_id: str, goal: str, crawler_plan: Dict[str, Any]) -> Dict[str, Any]:
    """
    中文注解：
    - 功能：执行一轮真实 crawler 工具矩阵测试，并产出结构化报告。
    - 说明：当前版本优先服务“多站点、多工具验证”型抓取任务。
    """
    requested_sites = _detect_requested_sites(goal, crawler_plan)
    requested_tools = _detect_requested_tools(goal, crawler_plan)
    query = _detect_query(goal)
    output_dir = _task_crawler_dir(task_id)
    output_dir.mkdir(parents=True, exist_ok=True)

    site_payloads: List[Dict[str, Any]] = []
    for site_id in requested_sites:
        url = _site_url(site_id, query)
        tool_results = []
        for tool_id in requested_tools:
            runner_meta = TOOL_RUNNERS.get(tool_id)
            if not runner_meta:
                continue
            result = runner_meta["runner"](site_id, url)
            tool_results.append(result.__dict__)
        tool_results.sort(key=lambda item: (-int(item.get("score", 0) or 0), str(item.get("tool", ""))))
        site_payloads.append(
            {
                "site": site_id,
                "url": url,
                "tool_results": tool_results,
                "summary": _summarize_site({"tool_results": tool_results}),
            }
        )

    report_payload = {
        "task_id": task_id,
        "generated_at": _utc_now_iso(),
        "goal": goal,
        "query": query,
        "required_sites": requested_sites,
        "required_tools": requested_tools,
        "selected_stack": (crawler_plan.get("selected_stack", {}) or {}).get("stack_id", ""),
        "fallback_stacks": list(crawler_plan.get("fallback_stacks", []) or []),
        "sites": site_payloads,
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
        md_lines.append("| Tool | Score | Status | Product signals | Block signals |")
        md_lines.append("|---|---:|---|---:|---:|")
        for row in site.get("tool_results", []):
            md_lines.append(
                f"| {row.get('tool', '')} | {row.get('score', 0)} | {row.get('status', '')} | "
                f"{row.get('product_signal_count', 0)} | {row.get('block_signal_count', 0)} |"
            )
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
        "all_sites_attempted": sorted({site["site"] for site in site_payloads}) == sorted(requested_sites),
    }
    return {
        "report_json_path": str(report_json_path),
        "report_md_path": str(report_md_path),
        "required_sites": requested_sites,
        "required_tools": requested_tools,
        "coverage": coverage,
        "site_summaries": {site["site"]: site.get("summary", {}) for site in site_payloads},
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
        best = tool_results[0] if tool_results else {}
        best_tool = str(best.get("tool", "")).strip()
        best_tool_by_site[site_id] = {
            "tool": best_tool,
            "score": int(best.get("score", 0) or 0),
            "status": str(best.get("status", "")).strip(),
        }
        blocked = [str(item.get("tool", "")) for item in tool_results if str(item.get("status", "")).strip() == "blocked"]
        if best_tool:
            lessons.append(f"{site_id} 当前最优抓取栈是 {best_tool}，得分 {best_tool_by_site[site_id]['score']}。")
        if blocked:
            lessons.append(f"{site_id} 被明显拦截的工具包括：{', '.join(blocked)}。")
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
            "last_score": info.get("score", 0),
            "last_status": info.get("status", ""),
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
    parser.add_argument("--mode", choices=["probe", "retro"], default="probe")
    parser.add_argument("--execution-json", default="")
    args = parser.parse_args()
    crawler = json.loads(args.crawler_json)
    if args.mode == "probe":
        payload = run_crawler_probe(args.task_id, args.goal, crawler)
    else:
        payload = run_crawler_retro(args.task_id, args.goal, crawler, json.loads(args.execution_json or "{}"))
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
