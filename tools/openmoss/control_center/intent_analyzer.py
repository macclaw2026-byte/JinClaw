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
- 文件路径：`tools/openmoss/control_center/intent_analyzer.py`
- 文件作用：负责识别目标意图、风险与能力需求。
- 顶层函数：_classify_task_types、analyze_intent、main。
- 顶层类：无顶层类。
- 阅读建议：先看模块说明，再按函数/类 docstring 顺着主流程理解调用关系。
"""
from __future__ import annotations

import json
import re
from typing import Dict, List


DOMAIN_RE = re.compile(r"\b(?:[A-Za-z0-9-]+\.)+[A-Za-z]{2,}\b")


def _classify_task_types(goal: str) -> List[str]:
    """
    中文注解：
    - 功能：实现 `_classify_task_types` 对应的处理逻辑。
    - 角色：属于本模块中的内部辅助逻辑；私有函数通常服务同文件主流程，公共函数通常作为跨模块入口或能力接口。
    - 调用关系：建议结合本文件的模块说明、调用方以及同名相关辅助函数一起阅读。
    """
    normalized = goal.lower()
    task_types = []
    if any(
        token in normalized
        for token in [
            "crawl",
            "scrape",
            "browser",
            "website",
            "telegram",
            "search",
            "web",
            "amazon",
            "网页",
            "后台",
            "上传",
            "登录",
            "seller",
            "draft",
        ]
    ):
        task_types.append("web")
    if any(token in normalized for token in ["data", "analyze", "analysis", "report", "csv", "json", "dashboard", "分析", "报告", "数据"]):
        task_types.append("data")
    if any(token in normalized for token in ["code", "build", "implement", "fix", "debug", "refactor", "test", "搭建", "实现", "修复"]):
        task_types.append("code")
    if any(token in normalized for token in ["install", "dependency", "package", "tool", "library", "安装", "依赖", "插件", "工具"]):
        task_types.append("dependency")
    if any(
        token in normalized
        for token in ["image", "img", "photo", "scene", "render", "sdxl", "flux", "图片", "场景图", "出图", "灯具", "产品图", "生成图"]
    ):
        task_types.append("image")
    if any(token in normalized for token in ["seller", "shopify", "listing", "product", "draft", "上架", "商品", "草稿"]):
        task_types.append("marketplace")
    return task_types or ["general"]


def analyze_intent(goal: str, *, source: str = "manual") -> Dict[str, object]:
    """
    中文注解：
    - 功能：实现 `analyze_intent` 对应的处理逻辑。
    - 角色：属于本模块中的对外可见逻辑；私有函数通常服务同文件主流程，公共函数通常作为跨模块入口或能力接口。
    - 调用关系：建议结合本文件的模块说明、调用方以及同名相关辅助函数一起阅读。
    """
    normalized = goal.strip()
    lowered = normalized.lower()
    task_types = _classify_task_types(normalized)
    requires_external_information = any(
        token in lowered
        for token in [
            "search",
            "web",
            "online",
            "internet",
            "telegram",
            "amazon",
            "website",
            "github",
            "download",
            "install",
            "api",
            "后台",
            "seller",
            "上传",
        ]
    )
    may_download = any(token in lowered for token in ["download", "install", "dependency", "package", "tool"])
    may_execute_external_code = any(token in lowered for token in ["install", "run script", "execute", "dependency"])
    needs_browser = any(
        token in lowered
        for token in ["browser", "website", "page", "click", "telegram web", "seller", "后台", "上传", "draft", "登录", "页面"]
    )
    needs_verification = True
    hard_constraints = [
        "Never break local security boundaries.",
        "Protect device, data, and network first.",
        "Use only reasonable, safe means to solve the task.",
    ]
    done_definition = "Goal verified, blockers resolved, security boundaries preserved, and final checkpoint written"
    nouns = re.findall(r"[A-Za-z][A-Za-z0-9_-]{2,}", normalized)
    domains = DOMAIN_RE.findall(normalized)
    likely_platforms = [
        token
        for token in ["amazon", "github", "telegram", "cloudflare", "shopify", "reddit", "walmart", "seller", "neosgo", "temu"]
        if token in lowered
    ]
    return {
        "source": source,
        "goal": normalized,
        "task_types": task_types,
        "keywords": nouns[:20],
        "domains": domains[:10],
        "likely_platforms": likely_platforms,
        "requires_external_information": requires_external_information,
        "may_download_artifacts": may_download,
        "may_execute_external_code": may_execute_external_code,
        "needs_browser": needs_browser,
        "needs_verification": needs_verification,
        "hard_constraints": hard_constraints,
        "done_definition": done_definition,
        "risk_level": "high" if may_download or may_execute_external_code else "medium" if requires_external_information else "low",
    }


def main() -> int:
    """
    中文注解：
    - 功能：实现 `main` 对应的处理逻辑。
    - 角色：属于本模块中的对外可见逻辑；私有函数通常服务同文件主流程，公共函数通常作为跨模块入口或能力接口。
    - 调用关系：建议结合本文件的模块说明、调用方以及同名相关辅助函数一起阅读。
    """
    import argparse

    parser = argparse.ArgumentParser(description="Analyze a user instruction into a structured mission intent")
    parser.add_argument("--goal", required=True)
    parser.add_argument("--source", default="manual")
    args = parser.parse_args()
    print(json.dumps(analyze_intent(args.goal, source=args.source), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
