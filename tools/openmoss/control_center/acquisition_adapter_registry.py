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
- 文件路径：`tools/openmoss/control_center/acquisition_adapter_registry.py`
- 文件作用：把现有 crawler/data-fetch 工具目录提升为统一的 acquisition adapter market。
- 顶层函数：build_acquisition_adapter_registry、main。
- 顶层类：无顶层类。
"""
from __future__ import annotations

import json
from typing import Any, Dict, List

from control_center_schemas import build_acquisition_adapter_schema
from crawler_stack_registry import build_crawler_stack_registry


CONCRETE_ADAPTER_SPECS: List[Dict[str, Any]] = [
    {
        "adapter_id": "official_api_search",
        "label": "Official API / Search",
        "stack_id": "official_api",
        "route_type": "official_api",
        "tool_requirements": ["web", "search"],
        "tool_labels": ["web", "search"],
        "always_available": True,
        "execution_profile": "connector_search",
        "validation_family": "official_source",
        "source_trust_tier": "official_source",
        "best_for": ["official_api", "stable_schema", "fresh_known_sources"],
        "strengths": ["稳定", "结构化", "最适合作为第一选择"],
        "limits": ["依赖目标存在官方或半官方可用入口"],
        "risk_level": "low",
        "anti_bot_readiness": "highest_when_available",
        "cost_profile": "low",
        "structured_output_level": "high",
        "supports_parallel_validation": True,
        "execution_tool_id": "web_search",
        "execution_runtime": "connector",
        "notes": ["优先用于官方接口、公开结构化端点和搜索型获取。"],
    },
    {
        "adapter_id": "structured_public_web",
        "label": "Structured Public Endpoint",
        "stack_id": "official_api",
        "route_type": "structured_public_endpoint",
        "tool_requirements": ["web", "search"],
        "tool_labels": ["web", "search"],
        "always_available": True,
        "execution_profile": "connector_structured_public",
        "validation_family": "structured_public",
        "source_trust_tier": "structured_public",
        "best_for": ["public_endpoint", "search_result_page", "semi_structured_public_data"],
        "strengths": ["覆盖公开资料", "低风险", "解释性强"],
        "limits": ["不一定能拿到深层字段"],
        "risk_level": "low",
        "anti_bot_readiness": "high",
        "cost_profile": "low",
        "structured_output_level": "high",
        "supports_parallel_validation": True,
        "execution_tool_id": "web_search",
        "execution_runtime": "connector",
        "notes": ["适合作为官方 API 不存在时的保守替代路线。"],
    },
    {
        "adapter_id": "curl_cffi_http",
        "label": "curl_cffi HTTP",
        "stack_id": "http_static",
        "route_type": "static_fetch",
        "tool_requirements": ["curl_cffi"],
        "tool_labels": ["curl-cffi"],
        "execution_profile": "http_impersonated_html",
        "validation_family": "http_fetch",
        "source_trust_tier": "public_fetch",
        "best_for": ["static_fetch", "list_pages", "detail_pages", "anti_bot_light"],
        "strengths": ["轻量", "拟真 HTTP", "适合做低成本主路线或验证路线"],
        "limits": ["对强交互流程无能为力"],
        "risk_level": "low",
        "anti_bot_readiness": "medium_high",
        "cost_profile": "low",
        "structured_output_level": "medium",
        "supports_parallel_validation": True,
        "execution_tool_id": "curl_cffi",
        "execution_runtime": "matrix_venv",
    },
    {
        "adapter_id": "direct_http_html",
        "label": "Direct HTTP HTML",
        "stack_id": "http_static",
        "route_type": "static_fetch",
        "tool_requirements": ["python"],
        "tool_labels": ["direct-http-html"],
        "execution_profile": "direct_http_html",
        "validation_family": "http_fetch",
        "source_trust_tier": "public_fetch",
        "best_for": ["simple_static_page", "fast_truth_check", "cheap_validation"],
        "strengths": ["最轻量", "最低成本", "适合快速排查"],
        "limits": ["容易被壳页和轻风控误导"],
        "risk_level": "low",
        "anti_bot_readiness": "low_medium",
        "cost_profile": "low",
        "structured_output_level": "medium",
        "supports_parallel_validation": True,
        "execution_tool_id": "direct_http",
        "execution_runtime": "python_runtime",
    },
    {
        "adapter_id": "scrapy_cffi_extract",
        "label": "Scrapy + curl_cffi",
        "stack_id": "scrapy_cffi",
        "route_type": "static_fetch",
        "tool_requirements": ["python", "curl_cffi"],
        "tool_labels": ["scrapy-cffi"],
        "execution_profile": "scrapy_text_extract",
        "validation_family": "http_fetch",
        "source_trust_tier": "public_fetch",
        "best_for": ["deep_crawl", "pagination", "batch_validation"],
        "strengths": ["批量稳定", "可扩展", "适合作为验证或扩展路线"],
        "limits": ["交互型站点仍然受限"],
        "risk_level": "medium",
        "anti_bot_readiness": "medium",
        "cost_profile": "medium",
        "structured_output_level": "medium",
        "supports_parallel_validation": True,
        "execution_tool_id": "scrapy_cffi",
        "execution_runtime": "matrix_venv",
    },
    {
        "adapter_id": "crawl4ai_cli",
        "label": "Crawl4AI CLI",
        "stack_id": "crawl4ai_extract",
        "route_type": "crawl4ai",
        "tool_requirements": ["crawl4ai"],
        "tool_labels": ["crawl4ai-cli"],
        "execution_profile": "content_extraction_cli",
        "validation_family": "content_extraction",
        "source_trust_tier": "content_extraction",
        "best_for": ["content_extraction", "research", "semi_dynamic_pages"],
        "strengths": ["内容提取好", "研究型页面友好"],
        "limits": ["不是高频批量路线"],
        "risk_level": "medium",
        "anti_bot_readiness": "medium",
        "cost_profile": "medium",
        "structured_output_level": "high",
        "supports_parallel_validation": True,
        "execution_tool_id": "crawl4ai",
        "execution_runtime": "local_cli",
    },
    {
        "adapter_id": "playwright_stealth_scroll_browser",
        "label": "Playwright Stealth Scroll",
        "stack_id": "playwright_stealth",
        "route_type": "browser_render",
        "tool_requirements": ["playwright", "playwright_stealth"],
        "tool_labels": ["playwright-stealth-scroll"],
        "execution_profile": "stealth_scroll_capture",
        "validation_family": "browser_render",
        "source_trust_tier": "browser_observation",
        "best_for": ["dynamic_content", "lazy_loaded_list", "browser_truth_check", "challenge_followup"],
        "strengths": ["适合懒加载页面", "可作为更强的浏览器验证路线", "仍沿用现有 Playwright 栈"],
        "limits": ["成本高", "速度慢", "仍需遵守审批与人工检查边界"],
        "risk_level": "high",
        "anti_bot_readiness": "high",
        "cost_profile": "high",
        "structured_output_level": "medium",
        "supports_parallel_validation": False,
        "execution_tool_id": "playwright_stealth_scroll",
        "execution_runtime": "matrix_venv",
    },
    {
        "adapter_id": "playwright_stealth_browser",
        "label": "Playwright Stealth",
        "stack_id": "playwright_stealth",
        "route_type": "browser_render",
        "tool_requirements": ["playwright", "playwright_stealth"],
        "tool_labels": ["playwright-stealth"],
        "execution_profile": "stealth_dom_capture",
        "validation_family": "browser_render",
        "source_trust_tier": "browser_observation",
        "best_for": ["browser_render", "dynamic_content", "interactive_flow"],
        "strengths": ["动态渲染能力强", "当前已接入运行链"],
        "limits": ["成本高", "速度慢"],
        "risk_level": "high",
        "anti_bot_readiness": "high",
        "cost_profile": "high",
        "structured_output_level": "medium",
        "supports_parallel_validation": False,
        "execution_tool_id": "playwright_stealth",
        "execution_runtime": "matrix_venv",
    },
    {
        "adapter_id": "playwright_scroll_browser",
        "label": "Playwright Scroll Browser",
        "stack_id": "playwright_stealth",
        "route_type": "browser_render",
        "tool_requirements": ["playwright"],
        "tool_labels": ["playwright-scroll"],
        "execution_profile": "scroll_capture",
        "validation_family": "browser_render",
        "source_trust_tier": "browser_observation",
        "best_for": ["dynamic_page", "lazy_loaded_list", "browser_truth_check"],
        "strengths": ["比纯 DOM render 更适合长列表", "可作为非 stealth 浏览器对照路线"],
        "limits": ["容易遇到风控", "成本高"],
        "risk_level": "high",
        "anti_bot_readiness": "medium",
        "cost_profile": "high",
        "structured_output_level": "medium",
        "supports_parallel_validation": False,
        "execution_tool_id": "playwright_scroll",
        "execution_runtime": "matrix_venv",
    },
    {
        "adapter_id": "playwright_browser",
        "label": "Playwright Browser",
        "stack_id": "playwright_stealth",
        "route_type": "browser_render",
        "tool_requirements": ["playwright"],
        "tool_labels": ["playwright"],
        "execution_profile": "dom_capture",
        "validation_family": "browser_render",
        "source_trust_tier": "browser_observation",
        "best_for": ["dynamic_page", "browser_truth_check"],
        "strengths": ["浏览器能力通用", "适合作为非 stealth 对照路线"],
        "limits": ["容易遇到风控", "成本高"],
        "risk_level": "high",
        "anti_bot_readiness": "medium",
        "cost_profile": "high",
        "structured_output_level": "medium",
        "supports_parallel_validation": False,
        "execution_tool_id": "playwright",
        "execution_runtime": "matrix_venv",
    },
    {
        "adapter_id": "agent_browser_local",
        "label": "Local Agent Browser",
        "stack_id": "playwright_stealth",
        "route_type": "browser_render",
        "tool_requirements": ["agent-browser-local"],
        "tool_labels": ["local-agent-browser-cli"],
        "execution_profile": "local_live_snapshot",
        "validation_family": "browser_render",
        "source_trust_tier": "browser_observation",
        "best_for": ["interactive_snapshot", "browser_truth_check", "session-aware-observation"],
        "strengths": ["适合本地真实浏览器观察", "可作为浏览器补充证据"],
        "limits": ["成本高", "并发差"],
        "risk_level": "high",
        "anti_bot_readiness": "medium_high",
        "cost_profile": "high",
        "structured_output_level": "medium",
        "supports_parallel_validation": False,
        "execution_tool_id": "agent_browser",
        "execution_runtime": "local_browser_cli",
    },
    {
        "adapter_id": "authorized_browser_session",
        "label": "Authorized Browser Session",
        "stack_id": "authorized_session",
        "route_type": "authorized_session",
        "tool_requirements": ["agent-browser-local"],
        "tool_labels": ["local-agent-browser-cli"],
        "execution_profile": "approved_isolated_session",
        "validation_family": "authorized_session",
        "source_trust_tier": "reviewed_session",
        "best_for": ["requires_login", "approved_session", "private_data"],
        "strengths": ["登录后数据可达", "适合审批后的授权态路线"],
        "limits": ["必须审批", "高风险", "不可默认放行"],
        "risk_level": "high",
        "anti_bot_readiness": "approved-session-only",
        "auth_requirement": "explicit_review_and_user_approval",
        "cost_profile": "high",
        "structured_output_level": "medium",
        "supports_parallel_validation": False,
        "execution_tool_id": "agent_browser",
        "execution_runtime": "approved_browser_cli",
    },
    {
        "adapter_id": "patchright_browser",
        "label": "Patchright Browser",
        "stack_id": "playwright_stealth",
        "route_type": "browser_render",
        "tool_requirements": ["patchright"],
        "tool_labels": ["patchright"],
        "execution_profile": "patchright_dom_capture",
        "validation_family": "browser_render",
        "best_for": ["chromium_drop_in", "browser_detect_reduction"],
        "strengths": ["生态友好", "适合作为未来浏览器接入点"],
        "limits": ["当前尚未接入执行器"],
        "risk_level": "high",
        "anti_bot_readiness": "high",
        "cost_profile": "high",
        "structured_output_level": "medium",
        "supports_parallel_validation": False,
        "observed_only": True,
        "notes": ["检测到包时会出现在 market 中，但不会自动进入执行路线。"],
    },
    {
        "adapter_id": "nodriver_cdp",
        "label": "Nodriver CDP",
        "stack_id": "playwright_stealth",
        "route_type": "browser_render",
        "tool_requirements": ["nodriver"],
        "tool_labels": ["nodriver"],
        "execution_profile": "webdriverless_cdp_capture",
        "validation_family": "browser_render",
        "best_for": ["webdriverless_browser", "cdp_control"],
        "strengths": ["可作为未来浏览器控制路线"],
        "limits": ["当前尚未接入执行器"],
        "risk_level": "high",
        "anti_bot_readiness": "high",
        "cost_profile": "high",
        "structured_output_level": "medium",
        "supports_parallel_validation": False,
        "observed_only": True,
    },
    {
        "adapter_id": "camoufox_browser",
        "label": "Camoufox Browser",
        "stack_id": "playwright_stealth",
        "route_type": "browser_render",
        "tool_requirements": ["camoufox"],
        "tool_labels": ["camoufox"],
        "execution_profile": "fingerprint_sensitive_capture",
        "validation_family": "browser_render",
        "best_for": ["fingerprint_sensitive_browser_routes"],
        "strengths": ["适合作为未来强指纹浏览器栈"],
        "limits": ["当前尚未接入执行器"],
        "risk_level": "high",
        "anti_bot_readiness": "high",
        "cost_profile": "high",
        "structured_output_level": "medium",
        "supports_parallel_validation": False,
        "observed_only": True,
    },
    {
        "adapter_id": "undetected_chromedriver_browser",
        "label": "Undetected ChromeDriver",
        "stack_id": "playwright_stealth",
        "route_type": "browser_render",
        "tool_requirements": ["undetected_chromedriver"],
        "tool_labels": ["undetected-chromedriver"],
        "execution_profile": "selenium_compat_capture",
        "validation_family": "browser_render",
        "best_for": ["selenium_compat_browser_routes"],
        "strengths": ["适合作为存量 Selenium 路线观察对象"],
        "limits": ["当前尚未接入执行器"],
        "risk_level": "high",
        "anti_bot_readiness": "medium_high",
        "cost_profile": "high",
        "structured_output_level": "medium",
        "supports_parallel_validation": False,
        "observed_only": True,
    },
    {
        "adapter_id": "seleniumbase_uc",
        "label": "SeleniumBase UC",
        "stack_id": "playwright_stealth",
        "route_type": "browser_render",
        "tool_requirements": ["seleniumbase"],
        "tool_labels": ["seleniumbase-uc"],
        "execution_profile": "seleniumbase_uc_capture",
        "validation_family": "browser_render",
        "best_for": ["selenium_uc_mode", "legacy_browser_stack_upgrade"],
        "strengths": ["适合作为未来 Selenium 存量改造路线"],
        "limits": ["当前尚未接入执行器"],
        "risk_level": "high",
        "anti_bot_readiness": "medium_high",
        "cost_profile": "high",
        "structured_output_level": "medium",
        "supports_parallel_validation": False,
        "observed_only": True,
    },
]

ROUTE_ORDER: Dict[str, List[str]] = {
    "official_api": ["official_api_search"],
    "structured_public_endpoint": ["structured_public_web"],
    "static_fetch": ["curl_cffi_http", "direct_http_html", "scrapy_cffi_extract"],
    "crawl4ai": ["crawl4ai_cli"],
    "browser_render": [
        "playwright_stealth_scroll_browser",
        "playwright_stealth_browser",
        "playwright_scroll_browser",
        "playwright_browser",
        "agent_browser_local",
        "patchright_browser",
        "nodriver_cdp",
        "camoufox_browser",
        "undetected_chromedriver_browser",
        "seleniumbase_uc",
    ],
    "authorized_session": ["authorized_browser_session"],
    "human_checkpoint": [],
}

TOOL_CAPABILITY_ALIASES = {
    "web": ["web"],
    "search": ["search"],
    "python": ["python"],
    "curl_cffi": ["curl_cffi"],
    "crawl4ai": ["crawl4ai"],
    "playwright": ["playwright"],
    "playwright_stealth": ["playwright_stealth"],
    "agent-browser-local": ["agent-browser-local", "browser", "agent-browser"],
    "patchright": ["patchright"],
    "nodriver": ["nodriver"],
    "camoufox": ["camoufox"],
    "undetected_chromedriver": ["undetected_chromedriver"],
    "seleniumbase": ["seleniumbase"],
}


def _tool_existence_map(capabilities: Dict[str, Any]) -> Dict[str, bool]:
    """
    中文注解：
    - 功能：把 capability registry 的工具快照压成是否可用的查表。
    - 输出角色：供 adapter market 判断哪些 adapter 已检测到、哪些已真正 ready。
    """
    exists: Dict[str, bool] = {}
    for item in capabilities.get("tools", []) or []:
        name = str(item.get("name", "")).strip()
        if not name:
            continue
        value = bool(item.get("exists"))
        exists[name] = bool(exists.get(name)) or value
        for alias in item.get("provides", []) or []:
            alias_name = str(alias).strip()
            if alias_name:
                exists[alias_name] = bool(exists.get(alias_name)) or value
    return exists


def _requirements_available(requirements: List[str], tool_exists: Dict[str, bool], *, always_available: bool = False) -> bool:
    """
    中文注解：
    - 功能：判断某个 adapter 的最小依赖是否满足。
    - 设计意图：让 market 同时知道“这条路在理念上存在”和“当前机器上是否真的可用”。
    """
    if always_available:
        return True
    normalized = [str(item).strip() for item in requirements if str(item).strip()]
    if not normalized:
        return False
    return all(any(bool(tool_exists.get(alias)) for alias in TOOL_CAPABILITY_ALIASES.get(req, [req])) for req in normalized)


def _adapter_matches_site(adapter: Dict[str, Any], site: Dict[str, Any]) -> bool:
    """
    中文注解：
    - 功能：判断某个站点画像是否对某个 concrete adapter 有“已验证偏好”。
    - 设计意图：让 adapter market 带上项目内真实成功经验，而不是只靠静态描述。
    """
    selected_tool = str(site.get("selected_tool", "")).strip().lower()
    tool_labels = {str(item).strip().lower() for item in adapter.get("tool_labels", []) if str(item).strip()}
    if not selected_tool or not tool_labels:
        return False
    return selected_tool in tool_labels


def _selection_state(enabled: bool, detected: bool, runtime_ready: bool, auth_requirement: str) -> str:
    if enabled and auth_requirement not in {"", "none"}:
        return "ready_with_review"
    if enabled:
        return "ready"
    if detected and not runtime_ready:
        return "observed_only"
    if detected:
        return "detected_but_blocked"
    return "missing_dependency"


def build_acquisition_adapter_registry(capabilities: Dict[str, Any]) -> Dict[str, Any]:
    """
    中文注解：
    - 功能：构建 acquisition adapter market。
    - 输入角色：读取 capability registry 和 crawler capability profile。
    - 输出角色：给 orchestrator / runtime / doctor 提供统一的 adapter 目录、路由映射和观测到的未来接入点。
    """
    tool_exists = _tool_existence_map(capabilities)
    crawler_profile = capabilities.get("crawler_capability_profile", {}) or {}
    stack_registry = build_crawler_stack_registry()
    adapters: List[Dict[str, Any]] = []

    for spec in CONCRETE_ADAPTER_SPECS:
        detected = _requirements_available(
            [str(item) for item in spec.get("tool_requirements", []) if str(item).strip()],
            tool_exists,
            always_available=bool(spec.get("always_available")),
        )
        runtime_ready = detected and not bool(spec.get("observed_only"))
        auth_requirement = str(spec.get("auth_requirement", "none")).strip() or "none"
        enabled = runtime_ready
        preferred_sites = [
            str(site.get("site", "")).strip()
            for site in crawler_profile.get("sites", []) or []
            if site.get("readiness") in {"production_ready", "governed_ready"} and _adapter_matches_site(spec, site)
        ]
        notes = [str(item) for item in spec.get("notes", []) if str(item).strip()]
        if detected and not runtime_ready:
            notes.append("检测到依赖，但当前执行链尚未接入该 adapter。")
        adapters.append(
            build_acquisition_adapter_schema(
                str(spec.get("adapter_id", "")).strip(),
                label=str(spec.get("label", "")).strip(),
                stack_id=str(spec.get("stack_id", "")).strip(),
                route_type=str(spec.get("route_type", "")).strip(),
                enabled=enabled,
                detected=detected,
                runtime_ready=runtime_ready,
                selection_state=_selection_state(enabled, detected, runtime_ready, auth_requirement),
                tools=[str(item) for item in spec.get("tool_requirements", []) if str(item).strip()],
                tool_labels=[str(item) for item in spec.get("tool_labels", []) if str(item).strip()],
                execution_tool_id=str(spec.get("execution_tool_id", "")).strip(),
                execution_runtime=str(spec.get("execution_runtime", "")).strip(),
                execution_profile=str(spec.get("execution_profile", "")).strip(),
                validation_family=str(spec.get("validation_family", "")).strip(),
                source_trust_tier=str(spec.get("source_trust_tier", "")).strip(),
                best_for=[str(item) for item in spec.get("best_for", []) if str(item).strip()],
                strengths=[str(item) for item in spec.get("strengths", []) if str(item).strip()],
                limits=[str(item) for item in spec.get("limits", []) if str(item).strip()],
                risk_level=str(spec.get("risk_level", "medium")).strip() or "medium",
                anti_bot_readiness=str(spec.get("anti_bot_readiness", "medium")).strip() or "medium",
                auth_requirement=auth_requirement,
                cost_profile=str(spec.get("cost_profile", "medium")).strip() or "medium",
                structured_output_level=str(spec.get("structured_output_level", "medium")).strip() or "medium",
                supports_parallel_validation=bool(spec.get("supports_parallel_validation")),
                preferred_sites=preferred_sites,
                notes=notes,
            )
        )

    adapters_by_id = {str(item.get("adapter_id", "")).strip(): item for item in adapters if str(item.get("adapter_id", "")).strip()}
    route_to_adapter_ids: Dict[str, List[str]] = {
        route_name: [adapter_id for adapter_id in adapter_ids if adapter_id in adapters_by_id]
        for route_name, adapter_ids in ROUTE_ORDER.items()
    }
    route_to_enabled_adapter_ids: Dict[str, List[str]] = {
        route_name: [adapter_id for adapter_id in adapter_ids if bool((adapters_by_id.get(adapter_id, {}) or {}).get("enabled"))]
        for route_name, adapter_ids in route_to_adapter_ids.items()
    }

    stack_to_adapter_ids: Dict[str, List[str]] = {}
    stack_to_enabled_adapter_ids: Dict[str, List[str]] = {}
    for adapter in adapters:
        stack_id = str(adapter.get("stack_id", "")).strip()
        adapter_id = str(adapter.get("adapter_id", "")).strip()
        if not stack_id or not adapter_id:
            continue
        stack_to_adapter_ids.setdefault(stack_id, []).append(adapter_id)
        if adapter.get("enabled"):
            stack_to_enabled_adapter_ids.setdefault(stack_id, []).append(adapter_id)

    enabled_ids = [adapter["adapter_id"] for adapter in adapters if adapter.get("enabled")]
    detected_ids = [adapter["adapter_id"] for adapter in adapters if adapter.get("detected")]
    runtime_ready_ids = [adapter["adapter_id"] for adapter in adapters if adapter.get("runtime_ready")]
    observed_only_ids = [
        adapter["adapter_id"]
        for adapter in adapters
        if adapter.get("detected") and not adapter.get("runtime_ready")
    ]

    return {
        "version": "acquisition-adapter-registry-v2",
        "adapters": adapters,
        "total_adapters": len(adapters),
        "available_adapter_ids": enabled_ids,
        "available_adapter_total": len(enabled_ids),
        "detected_adapter_ids": detected_ids,
        "runtime_ready_adapter_ids": runtime_ready_ids,
        "observed_only_adapter_ids": observed_only_ids,
        "route_to_adapter_ids": route_to_adapter_ids,
        "route_to_enabled_adapter_ids": route_to_enabled_adapter_ids,
        "stack_to_adapter_ids": stack_to_adapter_ids,
        "stack_to_enabled_adapter_ids": stack_to_enabled_adapter_ids,
        "default_escalation_order": stack_registry.get("default_escalation_order", []),
    }


def main() -> int:
    """
    中文注解：
    - 功能：输出当前 acquisition adapter market。
    - 设计意图：作为调试入口，便于单独检查本机当前 adapter 可用性与“已检测但未接线”的能力。
    """
    from capability_registry import build_capability_registry

    print(json.dumps(build_acquisition_adapter_registry(build_capability_registry()), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
