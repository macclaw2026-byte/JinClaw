#!/usr/bin/env python3

from __future__ import annotations

import json
from pathlib import Path
from typing import Dict, List

from paths import DOMAIN_PROFILES_ROOT


def _write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _build_profile_for_domain(domain: str) -> Dict[str, object]:
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
    import argparse

    parser = argparse.ArgumentParser(description="Build domain-specific fetch profiles for a task")
    parser.add_argument("--task-id", required=True)
    parser.add_argument("--intent-json", required=True)
    args = parser.parse_args()
    print(json.dumps(build_domain_profile(args.task_id, json.loads(args.intent_json)), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
