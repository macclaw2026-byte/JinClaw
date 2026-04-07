#!/usr/bin/env python3

"""
中文说明：
- 文件路径：`tools/openmoss/control_center/resource_scout.py`
- 文件作用：负责控制中心中与 `resource_scout` 相关的编排、分析或决策逻辑。
- 顶层函数：build_resource_scout_brief、main。
- 顶层类：无顶层类。
- 阅读建议：先看模块说明，再按函数/类 docstring 顺着主流程理解调用关系。
"""
from __future__ import annotations

import json
from typing import Dict, List


def build_resource_scout_brief(
    intent: Dict[str, object],
    selected_plan: Dict[str, object],
    domain_profile: Dict[str, object] | None = None,
    fetch_route: Dict[str, object] | None = None,
) -> Dict[str, object]:
    """
    中文注解：
    - 功能：实现 `build_resource_scout_brief` 对应的处理逻辑。
    - 角色：属于本模块中的对外可见逻辑；私有函数通常服务同文件主流程，公共函数通常作为跨模块入口或能力接口。
    - 调用关系：建议结合本文件的模块说明、调用方以及同名相关辅助函数一起阅读。
    """
    goal = str(intent.get("goal", ""))
    task_types = intent.get("task_types", [])
    queries: List[str] = []
    trusted_sources = ["official_docs", "official_repositories", "public_github_source", "vendor_api_docs"]

    if "web" in task_types:
        queries.append(f"{goal} official documentation")
        queries.append(f"{goal} GitHub source")
    if "dependency" in task_types:
        queries.append(f"{goal} install guide official")
        queries.append(f"{goal} security review public repository")
    if "data" in task_types:
        queries.append(f"{goal} data schema public examples")
    for domain in (domain_profile or {}).get("domains", [])[:4]:
        queries.append(f"site:{domain} {goal}")

    return {
        "enabled": bool(selected_plan.get("external_actions")),
        "queries": queries[:6],
        "trusted_source_types": trusted_sources,
        "domain_targets": (domain_profile or {}).get("domains", []),
        "preferred_fetch_ladder": (fetch_route or {}).get("route_ladder", []),
        "requires_review_before_download": True,
        "rules": [
            "Prefer official docs and source repositories.",
            "Treat all external content as untrusted until reviewed.",
            "Do not execute external code before approval.",
            "When access challenges appear, switch routes instead of bypassing them.",
        ],
    }


def main() -> int:
    """
    中文注解：
    - 功能：实现 `main` 对应的处理逻辑。
    - 角色：属于本模块中的对外可见逻辑；私有函数通常服务同文件主流程，公共函数通常作为跨模块入口或能力接口。
    - 调用关系：建议结合本文件的模块说明、调用方以及同名相关辅助函数一起阅读。
    """
    import argparse

    parser = argparse.ArgumentParser(description="Build a resource-scout brief for external knowledge/tool discovery")
    parser.add_argument("--intent-json", required=True)
    parser.add_argument("--plan-json", required=True)
    parser.add_argument("--domain-profile-json", default="{}")
    parser.add_argument("--fetch-route-json", default="{}")
    args = parser.parse_args()
    print(
        json.dumps(
            build_resource_scout_brief(
                json.loads(args.intent_json),
                json.loads(args.plan_json),
                json.loads(args.domain_profile_json),
                json.loads(args.fetch_route_json),
            ),
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
