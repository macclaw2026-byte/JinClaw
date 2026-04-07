#!/usr/bin/env python3

"""
中文说明：
- 文件路径：`tools/openmoss/control_center/domain_profile_store.py`
- 文件作用：负责控制中心中与 `domain_profile_store` 相关的编排、分析或决策逻辑。
- 顶层函数：_write_json、_build_profile_for_domain、build_domain_profile、main。
- 顶层类：无顶层类。
- 阅读建议：先看模块说明，再按函数/类 docstring 顺着主流程理解调用关系。
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Dict, List

from paths import DOMAIN_PROFILES_ROOT


def _write_json(path: Path, payload: object) -> None:
    """
    中文注解：
    - 功能：实现 `_write_json` 对应的处理逻辑。
    - 角色：属于本模块中的内部辅助逻辑；私有函数通常服务同文件主流程，公共函数通常作为跨模块入口或能力接口。
    - 调用关系：建议结合本文件的模块说明、调用方以及同名相关辅助函数一起阅读。
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _build_profile_for_domain(domain: str) -> Dict[str, object]:
    """
    中文注解：
    - 功能：实现 `_build_profile_for_domain` 对应的处理逻辑。
    - 角色：属于本模块中的内部辅助逻辑；私有函数通常服务同文件主流程，公共函数通常作为跨模块入口或能力接口。
    - 调用关系：建议结合本文件的模块说明、调用方以及同名相关辅助函数一起阅读。
    """
    lowered = domain.lower()
    preferred_interfaces = ["official_docs", "public_html"]
    challenge_risk = "medium"
    if any(token in lowered for token in ["amazon.", "walmart.", "shopify."]):
        preferred_interfaces = ["official_api_if_available", "public_html", "browser_render"]
        challenge_risk = "high"
    elif "github." in lowered:
        preferred_interfaces = ["official_api_if_available", "git_raw", "public_html"]
        challenge_risk = "low"
    elif "reddit." in lowered:
        preferred_interfaces = ["public_html", "official_api_if_available"]
        challenge_risk = "medium"
    return {
        "domain": domain,
        "preferred_interfaces": preferred_interfaces,
        "challenge_risk": challenge_risk,
        "preferred_fetch_ladder": [
            "official_api",
            "structured_public_endpoint",
            "static_fetch",
            "crawl4ai",
            "browser_render",
            "authorized_session",
            "human_checkpoint",
        ],
        "notes": [
            "Prefer stable, official, or structured endpoints before browser interaction.",
            "Escalate to authorization or human checkpoint instead of bypassing challenges.",
        ],
    }


def build_domain_profile(task_id: str, intent: Dict[str, object]) -> Dict[str, object]:
    """
    中文注解：
    - 功能：实现 `build_domain_profile` 对应的处理逻辑。
    - 角色：属于本模块中的对外可见逻辑；私有函数通常服务同文件主流程，公共函数通常作为跨模块入口或能力接口。
    - 调用关系：建议结合本文件的模块说明、调用方以及同名相关辅助函数一起阅读。
    """
    domains = [str(item) for item in intent.get("domains", [])]
    platforms = [str(item) for item in intent.get("likely_platforms", [])]
    synthetic_domains: List[str] = []
    platform_map = {
        "amazon": "amazon.com",
        "github": "github.com",
        "telegram": "telegram.org",
        "cloudflare": "cloudflare.com",
        "shopify": "shopify.com",
        "reddit": "reddit.com",
        "walmart": "walmart.com",
    }
    for platform in platforms:
        mapped = platform_map.get(platform)
        if mapped and mapped not in domains:
            synthetic_domains.append(mapped)
    all_domains = domains + synthetic_domains
    profiles = [_build_profile_for_domain(domain) for domain in all_domains]
    payload = {
        "task_id": task_id,
        "domains": all_domains,
        "profiles": profiles,
        "default_fetch_ladder": [
            "official_api",
            "structured_public_endpoint",
            "static_fetch",
            "crawl4ai",
            "browser_render",
            "authorized_session",
            "human_checkpoint",
        ],
    }
    _write_json(DOMAIN_PROFILES_ROOT / f"{task_id}.json", payload)
    return payload


def main() -> int:
    """
    中文注解：
    - 功能：实现 `main` 对应的处理逻辑。
    - 角色：属于本模块中的对外可见逻辑；私有函数通常服务同文件主流程，公共函数通常作为跨模块入口或能力接口。
    - 调用关系：建议结合本文件的模块说明、调用方以及同名相关辅助函数一起阅读。
    """
    import argparse

    parser = argparse.ArgumentParser(description="Build domain-specific fetch profiles for a task")
    parser.add_argument("--task-id", required=True)
    parser.add_argument("--intent-json", required=True)
    args = parser.parse_args()
    print(json.dumps(build_domain_profile(args.task_id, json.loads(args.intent_json)), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
