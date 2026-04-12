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
- 文件路径：`tools/openmoss/control_center/crawler_stack_registry.py`
- 文件作用：定义 crawler layer 可调度的抓取栈目录，以及每种抓取栈的能力画像、适用场景和风险特征。
- 顶层函数：build_crawler_stack_registry、main。
- 顶层类：无顶层类。
"""
from __future__ import annotations

import json
from typing import Dict, List


def build_crawler_stack_registry() -> Dict[str, object]:
    """
    中文注解：
    - 功能：返回 crawler layer 的标准抓取栈清单。
    - 设计意图：把“有哪些抓取方案可选”与“怎么评分选择”解耦，方便后续扩展/降级。
    """
    stacks: List[Dict[str, object]] = [
        {
            "stack_id": "official_api",
            "label": "Official API",
            "class": "api",
            "tools": ["web", "search"],
            "best_for": ["official_api", "structured_public_endpoint", "stable_schema"],
            "strengths": ["最高稳定性", "结构化程度高", "成本低"],
            "limits": ["需要目标站存在可用官方接口"],
            "risk_level": "low",
        },
        {
            "stack_id": "http_static",
            "label": "HTTP Static Fetch",
            "class": "lightweight_http",
            "tools": ["httpx", "curl_cffi", "selectolax"],
            "best_for": ["static_fetch", "list_pages", "detail_pages", "high_volume"],
            "strengths": ["快", "便宜", "适合批量", "容易重试"],
            "limits": ["对强 JS 页面效果差"],
            "risk_level": "low",
        },
        {
            "stack_id": "scrapy_cffi",
            "label": "Scrapy + curl_cffi",
            "class": "crawler_batch",
            "tools": ["scrapy", "curl_cffi", "selectolax"],
            "best_for": ["deep_crawl", "multi_page", "queue", "pagination", "high_volume"],
            "strengths": ["批量能力强", "调度成熟", "并发稳定"],
            "limits": ["对复杂交互页面无能为力"],
            "risk_level": "medium",
        },
        {
            "stack_id": "crawlee_flow",
            "label": "Crawlee Flow",
            "class": "crawler_orchestrated",
            "tools": ["crawlee", "playwright"],
            "best_for": ["workflow_crawl", "site_map_expansion", "adaptive_queue", "hybrid_pages"],
            "strengths": ["流程化", "站点遍历强", "适合复杂抓取流程"],
            "limits": ["部署和运行开销更高"],
            "risk_level": "medium",
        },
        {
            "stack_id": "crawl4ai_extract",
            "label": "Crawl4AI Extract",
            "class": "semantic_extract",
            "tools": ["crawl4ai"],
            "best_for": ["content_extraction", "research", "semi_dynamic_pages"],
            "strengths": ["内容提取友好", "适合 research 场景"],
            "limits": ["大规模批量抓取不是最优"],
            "risk_level": "medium",
        },
        {
            "stack_id": "playwright_stealth",
            "label": "Playwright + Stealth",
            "class": "browser_render",
            "tools": ["playwright", "playwright_stealth"],
            "best_for": ["browser_render", "strong_js", "interactive_pages", "anti_bot"],
            "strengths": ["对动态站最强", "适合复杂交互"],
            "limits": ["成本高", "速度慢", "更容易卡在站点风控"],
            "risk_level": "high",
        },
        {
            "stack_id": "authorized_session",
            "label": "Authorized Session",
            "class": "authorized_session",
            "tools": ["browser", "agent-browser"],
            "best_for": ["requires_login", "private_data", "approved_session"],
            "strengths": ["可访问登录后数据"],
            "limits": ["必须审批", "高风险"],
            "risk_level": "high",
        },
    ]
    return {
        "version": "crawler-layer-v1",
        "stacks": stacks,
        "default_escalation_order": [
            "official_api",
            "http_static",
            "scrapy_cffi",
            "crawlee_flow",
            "crawl4ai_extract",
            "playwright_stealth",
            "authorized_session",
            "human_checkpoint",
        ],
    }


def main() -> int:
    print(json.dumps(build_crawler_stack_registry(), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
