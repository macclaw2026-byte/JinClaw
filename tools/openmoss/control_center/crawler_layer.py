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
- 文件路径：`tools/openmoss/control_center/crawler_layer.py`
- 文件作用：构建 crawler layer 的核心决策包，负责把抓取型任务翻译成“目标 + 方案评分 + 工具选择 + 迭代闭环”。
- 顶层函数：_goal_requirements、_score_stack、build_crawler_plan、main。
- 顶层类：无顶层类。
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Dict, List

from crawler_capability_profile import build_crawler_capability_profile
from crawler_stack_registry import build_crawler_stack_registry
from paths import CONTROL_CENTER_RUNTIME_ROOT


CRAWLER_ROOT = CONTROL_CENTER_RUNTIME_ROOT / "crawler"


def _write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _goal_requirements(intent: Dict[str, object], challenge: Dict[str, object], selected_plan: Dict[str, object]) -> Dict[str, object]:
    """
    中文注解：
    - 功能：从意图和 challenge 里提炼 crawler 层要满足的抓取要求。
    """
    task_types = {str(item) for item in intent.get("task_types", [])}
    challenge_type = str(challenge.get("challenge_type", "")).strip()
    goal = str(intent.get("goal", "") or "")
    return {
        "goal": goal,
        "task_types": sorted(task_types),
        "likely_platforms": [str(item) for item in intent.get("likely_platforms", []) if str(item).strip()],
        "needs_browser": bool(intent.get("needs_browser")),
        "requires_external_information": bool(intent.get("requires_external_information")),
        "high_volume_hint": any(token in goal.lower() for token in ["批量", "全量", "大量", "bulk", "catalog", "many"]),
        "research_hint": "research" in {str(item).lower() for item in selected_plan.get("skills", [])} or "研究" in goal,
        "strong_js_hint": challenge_type in {"javascript_render_required", "browser_required"} or any(
            token in goal.lower() for token in ["动态", "渲染", "javascript", "js"]
        ),
        "anti_bot_hint": challenge_type in {"rate_limited", "bot_challenge", "login_required"} or any(
            token in goal.lower() for token in ["验证码", "风控", "反爬", "rate limit", "登录后"]
        ),
    }


def _requested_sites(goal: str) -> List[str]:
    goal_lower = str(goal or "").lower()
    sites: List[str] = []
    for site_id, aliases in {
        "amazon": ["amazon", "亚马逊"],
        "walmart": ["walmart", "沃尔玛"],
        "temu": ["temu", "特木"],
        "1688": ["1688", "阿里巴巴", "阿里 1688"],
    }.items():
        if any(alias.lower() in goal_lower for alias in aliases):
            sites.append(site_id)
    return sites


def _project_site_constraints(requested_sites: List[str]) -> Dict[str, object]:
    profile = build_crawler_capability_profile()
    sites = profile.get("sites", []) or []
    site_map = {
        str(site.get("site", "")).strip().lower(): site
        for site in sites
        if str(site.get("site", "")).strip()
    }
    relevant = [site_map[site] for site in requested_sites if site in site_map]
    attention_sites = [site for site in relevant if site.get("readiness") != "production_ready"]
    return {
        "summary": profile.get("summary", {}) or {},
        "feedback": profile.get("feedback", {}) or {},
        "relevant_sites": relevant,
        "attention_sites": attention_sites,
        "recommended_project_actions": profile.get("recommended_project_actions", []) or [],
    }


def _requested_tools(goal: str) -> List[str]:
    goal_lower = str(goal or "").lower()
    requested: List[str] = []
    for tool_id, aliases in {
        "crawl4ai": ["crawl4ai"],
        "direct_http": ["direct-http", "direct http", "http_static", "http static", "httpx"],
        "curl_cffi": ["curl_cffi", "curl-cffi"],
        "playwright": ["playwright"],
        "playwright_stealth": ["playwright_stealth", "playwright-stealth", "playwright stealth"],
        "scrapy_cffi": ["scrapy", "scrapy_cffi", "scrapy-cffi", "scrapy + curl_cffi", "scrapy+curl_cffi"],
        "agent_browser": ["agent-browser", "agent browser", "agent_browser", "local-agent-browser-cli"],
        "crawlee": ["crawlee"],
    }.items():
        if any(alias in goal_lower for alias in aliases):
            requested.append(tool_id)
    if not requested and any(token in goal_lower for token in ["7个工具", "7 tools", "七个工具", "all known tools", "all tools", "所有已知工具", "全部工具", "首次", "第一次"]):
        return [
            "crawl4ai",
            "direct_http",
            "curl_cffi",
            "playwright",
            "playwright_stealth",
            "scrapy_cffi",
            "agent_browser",
        ]
    return requested


def _execution_mode(goal: str, requirements: Dict[str, object], requested_sites: List[str], requested_tools: List[str]) -> str:
    goal_lower = str(goal or "").lower()
    if len(requested_sites) >= 2 and (len(requested_tools) >= 3 or "工具" in goal or "tool" in goal_lower or "matrix" in goal_lower or "测试" in goal):
        return "site_tool_matrix_probe"
    if requirements.get("research_hint"):
        return "adaptive_research_crawl"
    return "adaptive_fetch"


def _score_stack(stack: Dict[str, object], requirements: Dict[str, object], site_constraints: Dict[str, object]) -> Dict[str, object]:
    """
    中文注解：
    - 功能：对候选抓取栈做启发式评分，优先选择“成本最低但足够完成目标”的路线。
    """
    score = 0.0
    rationale: List[str] = []
    stack_id = str(stack.get("stack_id", ""))
    stack_tools = {str(item).strip().lower() for item in stack.get("tools", []) if str(item).strip()}

    if stack_id == "official_api":
        if requirements.get("requires_external_information"):
            score += 6
            rationale.append("外部数据任务先试官方接口最稳")
        if not requirements.get("needs_browser"):
            score += 2
    elif stack_id == "http_static":
        if not requirements.get("strong_js_hint"):
            score += 7
            rationale.append("目标更像静态/轻量抓取，适合 HTTP 层")
        if requirements.get("high_volume_hint"):
            score += 2
    elif stack_id == "scrapy_cffi":
        if requirements.get("high_volume_hint"):
            score += 8
            rationale.append("存在批量信号，适合 Scrapy 调度")
        if not requirements.get("strong_js_hint"):
            score += 2
    elif stack_id == "crawlee_flow":
        if requirements.get("high_volume_hint") or requirements.get("needs_browser"):
            score += 6
            rationale.append("需要流程化站点遍历或混合抓取")
    elif stack_id == "crawl4ai_extract":
        if requirements.get("research_hint"):
            score += 7
            rationale.append("目标偏 research / 内容提取")
        if requirements.get("requires_external_information"):
            score += 2
    elif stack_id == "playwright_stealth":
        if requirements.get("strong_js_hint"):
            score += 8
            rationale.append("检测到强 JS/动态渲染信号")
        if requirements.get("anti_bot_hint"):
            score += 4
            rationale.append("有风控/反爬信号，浏览器栈成功率更高")
    elif stack_id == "authorized_session":
        if requirements.get("anti_bot_hint"):
            score += 3
        if requirements.get("needs_browser"):
            score += 1

    if requirements.get("needs_browser") is False and stack_id in {"playwright_stealth", "authorized_session"}:
        score -= 3
        rationale.append("当前目标不应过早升级到高成本浏览器/授权层")
    if requirements.get("strong_js_hint") and stack_id in {"http_static", "scrapy_cffi"}:
        score -= 4
        rationale.append("强 JS 场景下纯 HTTP 栈成功率较低")

    relevant_sites = site_constraints.get("relevant_sites", []) or []
    for site in relevant_sites:
        selected_tool = str(site.get("selected_tool", "")).strip().lower()
        readiness = str(site.get("readiness", "")).strip()
        access_posture = str(site.get("access_posture", "")).strip()
        route_preference_strength = str(site.get("route_preference_strength", "none")).strip().lower()
        blocked = {
            str(item).strip().lower()
            for item in site.get("primary_limitations", [])
            if str(item).strip().startswith("blocked_tools:")
        }
        selected_matches = selected_tool and (
            selected_tool in stack_tools or
            (selected_tool == "local-agent-browser-cli" and stack_id == "authorized_session")
        )
        if readiness == "production_ready" and selected_matches and route_preference_strength == "strong":
            score += 8
            rationale.append(f"{site.get('site', '')} 当前生产可用，优先沿已验证工具路线")
        elif readiness == "production_ready" and selected_matches and route_preference_strength == "guarded":
            score += 3
            rationale.append(f"{site.get('site', '')} 当前存在多份执行证据分歧，仅保守参考已验证路线")
        if access_posture == "governed_authenticated_ready" and stack_id == "authorized_session":
            score += 8
            rationale.append(f"{site.get('site', '')} 已具备受治理授权态可用性，优先走 authorized_session")
        elif readiness == "attention_required" and site.get("authenticated_supported") and stack_id == "authorized_session":
            score += 6
            rationale.append(f"{site.get('site', '')} 当前更适合升级到授权态链路")
        blocked_text = " ".join(blocked)
        if blocked_text:
            if stack_id == "http_static" and any(token in blocked_text for token in ["curl-cffi", "direct-http-html"]):
                score -= 5
                rationale.append(f"{site.get('site', '')} 的轻量 HTTP 路线当前已知不稳")
            if stack_id == "crawl4ai_extract" and "crawl4ai-cli" in blocked_text:
                score -= 4
                rationale.append(f"{site.get('site', '')} 的 crawl4ai 路线当前已知受阻")
            if stack_id == "playwright_stealth" and "playwright" in blocked_text:
                score -= 4
                rationale.append(f"{site.get('site', '')} 的 Playwright 路线当前已知受阻")

    summary = site_constraints.get("summary", {}) or {}
    feedback = site_constraints.get("feedback", {}) or {}
    coverage_status = str(feedback.get("coverage_status", "")).strip().lower()
    if float(summary.get("width_score", 0) or 0) < 60 and stack_id == "official_api":
        score += 1
        rationale.append("全局抓取宽度偏低时，先保守尝试官方/结构化入口")
    if float(summary.get("depth_score", 0) or 0) < 50 and stack_id == "authorized_session":
        score += 2
        rationale.append("全局抓取深度偏低时，授权态更可能补齐关键字段")
    if coverage_status == "thin":
        if stack_id in {"official_api", "http_static", "crawl4ai_extract"}:
            score += 2
            rationale.append("项目反馈覆盖偏薄时，优先保留可验证的低风险抓取链")
        if stack_id in {"playwright_stealth", "authorized_session"}:
            score -= 2
            rationale.append("项目反馈覆盖偏薄时，暂缓过早升级高成本抓取链")
    elif coverage_status == "strong":
        if stack_id in {"authorized_session", "playwright_stealth"} and requirements.get("anti_bot_hint"):
            score += 1
            rationale.append("项目反馈覆盖稳定，可更积极利用高能力抓取链")

    return {
        "stack_id": stack_id,
        "score": round(score, 2),
        "rationale": rationale,
        "tools": stack.get("tools", []),
        "risk_level": stack.get("risk_level", "medium"),
        "class": stack.get("class", ""),
    }


def build_crawler_plan(
    task_id: str,
    intent: Dict[str, object],
    selected_plan: Dict[str, object],
    domain_profile: Dict[str, object],
    fetch_route: Dict[str, object],
    challenge: Dict[str, object],
) -> Dict[str, object]:
    """
    中文注解：
    - 功能：构建 crawler layer 计划包。
    - 输出：包括需求、评分、主抓取栈、回退栈、结果合同和复盘要求。
    """
    requirements = _goal_requirements(intent, challenge, selected_plan)
    requested_sites = _requested_sites(requirements.get("goal", ""))
    requested_tools = _requested_tools(requirements.get("goal", ""))
    site_constraints = _project_site_constraints(requested_sites)
    registry = build_crawler_stack_registry()
    scores = [_score_stack(stack, requirements, site_constraints) for stack in registry.get("stacks", [])]
    ranked = sorted(scores, key=lambda item: (item.get("score", 0.0), item.get("stack_id", "")), reverse=True)
    selected = ranked[0] if ranked else {}
    payload = {
        "task_id": task_id,
        "enabled": bool(intent.get("requires_external_information") or "web" in intent.get("task_types", []) or "data" in intent.get("task_types", [])),
        "execution_mode": _execution_mode(str(requirements.get("goal", "")), requirements, requested_sites, requested_tools),
        "requirements": requirements,
        "requested_sites": requested_sites,
        "requested_tools": requested_tools,
        "project_site_constraints": site_constraints,
        "project_feedback": site_constraints.get("feedback", {}) or {},
        "selected_stack": selected,
        "fallback_stacks": [item.get("stack_id", "") for item in ranked[1:4]],
        "scores": ranked,
        "fetch_route_hint": fetch_route,
        "domain_profile": {
            "domains": domain_profile.get("domains", []),
            "default_fetch_ladder": domain_profile.get("default_fetch_ladder", []),
        },
        "loop_contract": {
            "judge_then_iterate": True,
            "consumer_feedback_required_when_unsatisfied": True,
            "retro_required_before_done": True,
            "doctor_must_monitor_until_retro_complete": True,
        },
        "result_contract": {
            "must_return_structured_data": True,
            "must_explain_coverage_and_gaps": True,
            "must_mark_unmet_requirements": True,
        },
        "retro": {
            "required": True,
            "focus": ["stack_selection_quality", "data_quality", "coverage_gaps", "site_specific_lessons"],
        },
    }
    _write_json(CRAWLER_ROOT / f"{task_id}.json", payload)
    return payload


def main() -> int:
    import argparse

    parser = argparse.ArgumentParser(description="Build crawler layer plan for a task")
    parser.add_argument("--task-id", required=True)
    parser.add_argument("--intent-json", required=True)
    parser.add_argument("--selected-plan-json", required=True)
    parser.add_argument("--domain-profile-json", required=True)
    parser.add_argument("--fetch-route-json", required=True)
    parser.add_argument("--challenge-json", required=True)
    args = parser.parse_args()
    print(
        json.dumps(
            build_crawler_plan(
                args.task_id,
                json.loads(args.intent_json),
                json.loads(args.selected_plan_json),
                json.loads(args.domain_profile_json),
                json.loads(args.fetch_route_json),
                json.loads(args.challenge_json),
            ),
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
