#!/usr/bin/env python3

from __future__ import annotations

import argparse
import collections
import json
from pathlib import Path


ACCOUNT_QUERY_TEMPLATES = {
    "designer": [
        {
            "query_family": "official_search",
            "source_family": "official_websites",
            "template": "\"interior design\" lighting {region} trade",
        },
        {
            "query_family": "official_search",
            "source_family": "official_websites",
            "template": "\"design studio\" lighting {region}",
        },
        {
            "query_family": "linkedin_company_page",
            "source_family": "linkedin_company_pages",
            "template": "site:linkedin.com/company \"interior design\" lighting {region}",
        },
        {
            "query_family": "industry_directory",
            "source_family": "trade_directories",
            "template": "\"interior designer\" directory {region} lighting",
        },
    ],
    "contractor": [
        {
            "query_family": "official_search",
            "source_family": "official_websites",
            "template": "\"general contractor\" lighting {region}",
        },
        {
            "query_family": "official_search",
            "source_family": "official_websites",
            "template": "\"contractor\" residential lighting {region}",
        },
        {
            "query_family": "linkedin_company_page",
            "source_family": "linkedin_company_pages",
            "template": "site:linkedin.com/company \"general contractor\" {region}",
        },
        {
            "query_family": "industry_directory",
            "source_family": "trade_directories",
            "template": "\"general contractor\" directory {region}",
        },
    ],
    "builder": [
        {
            "query_family": "official_search",
            "source_family": "official_websites",
            "template": "\"home builder\" lighting {region}",
        },
        {
            "query_family": "official_search",
            "source_family": "official_websites",
            "template": "\"custom builder\" lighting {region}",
        },
        {
            "query_family": "linkedin_company_page",
            "source_family": "linkedin_company_pages",
            "template": "site:linkedin.com/company \"custom home builder\" {region}",
        },
        {
            "query_family": "industry_directory",
            "source_family": "association_lists",
            "template": "\"home builder\" directory {region}",
        },
    ],
    "electrician": [
        {
            "query_family": "official_search",
            "source_family": "official_websites",
            "template": "\"electrical contractor\" lighting {region}",
        },
        {
            "query_family": "official_search",
            "source_family": "official_websites",
            "template": "\"electrician\" residential commercial {region}",
        },
        {
            "query_family": "linkedin_company_page",
            "source_family": "linkedin_company_pages",
            "template": "site:linkedin.com/company \"electrical contractor\" {region}",
        },
        {
            "query_family": "industry_directory",
            "source_family": "trade_directories",
            "template": "\"electrician\" directory {region}",
        },
    ],
    "distributor": [
        {
            "query_family": "official_search",
            "source_family": "official_websites",
            "template": "\"lighting distributor\" {region}",
        },
        {
            "query_family": "official_search",
            "source_family": "official_websites",
            "template": "\"lighting wholesaler\" {region}",
        },
        {
            "query_family": "linkedin_company_page",
            "source_family": "linkedin_company_pages",
            "template": "site:linkedin.com/company \"lighting distributor\" {region}",
        },
        {
            "query_family": "industry_directory",
            "source_family": "trade_directories",
            "template": "\"lighting distributor\" directory {region}",
        },
    ],
    "dealer": [
        {
            "query_family": "official_search",
            "source_family": "official_websites",
            "template": "\"lighting dealer\" {region}",
        },
        {
            "query_family": "official_search",
            "source_family": "official_websites",
            "template": "\"lighting showroom\" dealer {region}",
        },
        {
            "query_family": "linkedin_company_page",
            "source_family": "linkedin_company_pages",
            "template": "site:linkedin.com/company \"lighting dealer\" {region}",
        },
        {
            "query_family": "google_business_profile",
            "source_family": "google_business_profile",
            "template": "site:google.com/maps \"lighting showroom\" {region}",
        },
    ],
    "showroom": [
        {
            "query_family": "official_search",
            "source_family": "official_websites",
            "template": "\"lighting showroom\" {region}",
        },
        {
            "query_family": "official_search",
            "source_family": "official_websites",
            "template": "\"lighting gallery\" {region}",
        },
        {
            "query_family": "linkedin_company_page",
            "source_family": "linkedin_company_pages",
            "template": "site:linkedin.com/company \"lighting showroom\" {region}",
        },
        {
            "query_family": "google_business_profile",
            "source_family": "google_business_profile",
            "template": "site:google.com/maps \"lighting showroom\" {region}",
        },
    ],
    "lighting": [
        {
            "query_family": "official_search",
            "source_family": "official_websites",
            "template": "\"lighting company\" {region}",
        },
        {
            "query_family": "official_search",
            "source_family": "official_websites",
            "template": "\"architectural lighting\" {region}",
        },
        {
            "query_family": "linkedin_company_page",
            "source_family": "linkedin_company_pages",
            "template": "site:linkedin.com/company \"architectural lighting\" {region}",
        },
        {
            "query_family": "google_business_profile",
            "source_family": "google_business_profile",
            "template": "site:google.com/maps \"lighting store\" {region}",
        },
    ],
}


def _read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _activate_balanced(items: list[dict], max_active: int) -> None:
    by_family: dict[str, collections.deque] = collections.defaultdict(collections.deque)
    for item in items:
        by_family[item.get("query_family", "official_search")].append(item)
        item["enabled"] = False

    family_order = ["official_search", "linkedin_company_page", "industry_directory", "google_business_profile"]
    active_count = 0
    while active_count < max_active:
        progressed = False
        for family in family_order:
            queue = by_family.get(family)
            if not queue:
                continue
            item = queue.popleft()
            if not item.get("enabled"):
                item["enabled"] = True
                active_count += 1
                progressed = True
                if active_count >= max_active:
                    break
        if not progressed:
            break


def main() -> int:
    parser = argparse.ArgumentParser(description="Build generated discovery query recipes from project config.")
    parser.add_argument("--config", required=True)
    parser.add_argument("--manual-queries")
    parser.add_argument("--output", required=True)
    parser.add_argument("--generated-queries", required=True)
    parser.add_argument("--max-active", type=int, default=18)
    args = parser.parse_args()

    config = _read_json(Path(args.config).expanduser())
    manual_query_path = Path(args.manual_queries).expanduser() if args.manual_queries else None
    manual_items = _read_json(manual_query_path).get("items", []) if manual_query_path and manual_query_path.exists() else []

    priority_regions = config.get("project", {}).get("priority_regions", [])
    account_types = config.get("icp", {}).get("account_types", [])
    personas = config.get("icp", {}).get("personas", [])
    primary_persona = personas[0] if personas else "buyer"

    generated_items = []
    seen_queries = {str(item.get("query", "")).strip().lower() for item in manual_items}

    for region_index, region in enumerate(priority_regions):
        for account_type in account_types:
            templates = ACCOUNT_QUERY_TEMPLATES.get(account_type, [])
            for template_index, recipe in enumerate(templates):
                query = recipe["template"].format(region=region)
                normalized = query.strip().lower()
                if not normalized or normalized in seen_queries:
                    continue
                seen_queries.add(normalized)
                query_family = recipe["query_family"]
                source_family = recipe["source_family"]
                query_id = f"{account_type}-{region.lower()}-{query_family}-{template_index + 1}"
                generated_items.append(
                    {
                        "query_id": query_id,
                        "query": query,
                        "account_type": account_type,
                        "persona_type": primary_persona if account_type not in {"designer", "contractor", "builder", "electrician"} else "founder",
                        "geo": region,
                        "query_family": query_family,
                        "source_family": source_family,
                        "signal_hints": ["search_discovery", f"recipe_{account_type}", f"region_{region.lower()}", f"query_family_{query_family}"],
                        "max_results": 5,
                        "enabled": len(generated_items) < args.max_active,
                        "generated": True,
                        "priority_rank": len(generated_items) + 1,
                        "region_rank": region_index + 1,
                        "template_index": template_index + 1,
                    }
                )

    _activate_balanced(generated_items, args.max_active)

    library = {
        "project_id": config.get("project", {}).get("id", ""),
        "manual_query_count": len(manual_items),
        "generated_query_count": len(generated_items),
        "active_generated_query_count": len([item for item in generated_items if item.get("enabled")]),
        "items": generated_items,
    }

    _write_json(Path(args.output).expanduser(), library)
    _write_json(Path(args.generated_queries).expanduser(), {"items": generated_items})
    print(
        json.dumps(
            {
                "status": "ok",
                "generated_query_count": len(generated_items),
                "active_generated_query_count": len([item for item in generated_items if item.get("enabled")]),
                "output": str(Path(args.output).expanduser()),
                "generated_queries_path": str(Path(args.generated_queries).expanduser()),
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
