#!/usr/bin/env python3

from __future__ import annotations

import json
import re
from collections import Counter
from pathlib import Path
from typing import Any
from urllib.parse import urljoin, urlparse


QUERY_ID_SANITIZE_RE = re.compile(r"[^a-z0-9]+")
CONTACT_HINT_RE = re.compile(
    r"(contact|about|team|studio|trade|connect|location|locations|inquiry|enquiry|consult)",
    re.I,
)
EMAIL_RE = re.compile(r"([A-Z0-9._%+\-]+@[A-Z0-9.\-]+\.[A-Z]{2,})", re.I)


def read_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def root_domain(url: str) -> str:
    if not url:
        return ""
    parsed = urlparse(url if "://" in url else f"https://{url}")
    return parsed.netloc.lower().removeprefix("www.")


def safe_query_id(state: str, query: str) -> str:
    slug = QUERY_ID_SANITIZE_RE.sub("-", query.lower()).strip("-")
    return f"google-maps-{state.lower()}-{slug[:80]}"


def signal_slug(text: str) -> str:
    return QUERY_ID_SANITIZE_RE.sub("_", str(text or "").strip().lower()).strip("_")


def derive_query_family(keyword: str, explicit: str = "") -> str:
    if explicit.strip():
        return explicit.strip()
    normalized = signal_slug(keyword) or "generic"
    return f"google_maps_{normalized}"


def build_keyword_queries(
    *,
    keyword: str,
    state_code: str,
    state_name: str,
    priority_cities: list[str] | None = None,
    counties: list[str] | None = None,
    base_queries: list[str] | None = None,
    templates: list[str] | None = None,
) -> list[str]:
    seen: set[str] = set()
    queries: list[str] = []

    def add(query: str) -> None:
        normalized = str(query or "").strip()
        if not normalized or normalized in seen:
            return
        seen.add(normalized)
        queries.append(normalized)

    add(f"{keyword} in {state_name}")
    for query in list(base_queries or []):
        add(str(query))

    template_list = list(templates or [])
    for city in list(priority_cities or []):
        for template in template_list:
            add(
                template.format(
                    keyword=keyword,
                    state_code=state_code,
                    state_name=state_name,
                    county="",
                    priority_city=city,
                ).strip()
            )
    for county in list(counties or []):
        for template in template_list:
            add(
                template.format(
                    keyword=keyword,
                    state_code=state_code,
                    state_name=state_name,
                    county=county,
                    priority_city="",
                ).strip()
            )
    return queries


def build_discovery_row(
    *,
    company_name: str,
    website: str,
    source_url: str,
    state: str,
    group: str,
    query: str,
    query_family: str,
    account_type: str,
    persona_type: str,
    generated_from_provider: str,
    category: str = "",
    address: str = "",
    phone: str = "",
    rating: str = "",
    source_confidence: float = 0.8,
) -> dict[str, Any]:
    keyword_slug = query_family.removeprefix("google_maps_")
    return {
        "company_name": company_name,
        "website_root_domain": root_domain(website),
        "website": website,
        "email": "",
        "source_url": source_url,
        "account_type": account_type,
        "persona_type": persona_type,
        "geo": f"{state} / {group}".strip(" /"),
        "signals": [
            "google_maps_search",
            f"google_maps_keyword_{keyword_slug}",
            f"region_{state.lower()}",
            f"query:{query}",
        ],
        "reachability_status": "form_available" if website else "unknown",
        "source_confidence": source_confidence,
        "source_family": "google_maps_places",
        "query_id": safe_query_id(state, query),
        "discovery_query": query,
        "query_family": query_family,
        "generated_from_provider": generated_from_provider,
        "place_url": source_url,
        "rating": rating,
        "category": category,
        "formatted_address": address,
        "phone": phone,
    }


def merge_discovery_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    deduped: list[dict[str, Any]] = []
    seen_keys: set[tuple[str, str, str]] = set()
    for row in rows:
        place_url = str(row.get("place_url") or row.get("source_url") or "").strip().lower()
        company_name = str(row.get("company_name") or "").strip().lower()
        website_root = str(row.get("website_root_domain") or "").strip().lower()
        dedupe_key = (place_url, company_name, website_root)
        if dedupe_key in seen_keys:
            continue
        seen_keys.add(dedupe_key)
        deduped.append(row)
    return sorted(deduped, key=lambda item: (item.get("geo", ""), item.get("company_name", "")))


def discovery_quality_summary(rows: list[dict[str, Any]], query_runs: list[dict[str, Any]]) -> dict[str, Any]:
    provider_counts = Counter(str(item.get("generated_from_provider") or "unknown") for item in rows)
    state_counts = Counter(str(item.get("geo", "")).split("/", 1)[0].strip() for item in rows if str(item.get("geo", "")).strip())
    route_counts = Counter(str(item.get("route") or "unknown") for item in query_runs)
    success_count = sum(1 for item in query_runs if item.get("ok"))
    fallback_count = sum(1 for item in query_runs if item.get("fallback_used"))
    total_queries = len(query_runs)
    with_website = sum(1 for item in rows if str(item.get("website") or "").strip())
    with_phone = sum(1 for item in rows if str(item.get("phone") or "").strip())
    with_address = sum(1 for item in rows if str(item.get("formatted_address") or "").strip())
    return {
        "total_rows": len(rows),
        "total_queries": total_queries,
        "successful_queries": success_count,
        "failed_queries": total_queries - success_count,
        "query_success_rate": round(success_count / total_queries, 4) if total_queries else 0.0,
        "fallback_query_count": fallback_count,
        "provider_counts": dict(provider_counts),
        "state_counts": dict(state_counts),
        "route_counts": dict(route_counts),
        "website_rate": round(with_website / len(rows), 4) if rows else 0.0,
        "phone_rate": round(with_phone / len(rows), 4) if rows else 0.0,
        "address_rate": round(with_address / len(rows), 4) if rows else 0.0,
    }


def extract_candidate_links(
    base_url: str,
    html: str,
    *,
    limit: int = 4,
    extra_hints: list[str] | None = None,
) -> list[str]:
    hints = [hint for hint in list(extra_hints or []) if str(hint).strip()]
    scored: list[tuple[int, str]] = []
    seen: set[str] = set()
    for href in re.findall(r'href=["\']([^"\']+)["\']', html, re.I):
        absolute = urljoin(base_url, href.strip())
        parsed = urlparse(absolute)
        if not parsed.scheme.startswith("http"):
            continue
        if urlparse(base_url).netloc != parsed.netloc:
            continue
        lowered = absolute.lower()
        score = 0
        if CONTACT_HINT_RE.search(lowered):
            score += 3
        if "/contact" in lowered:
            score += 3
        if "/about" in lowered:
            score += 2
        if "/team" in lowered:
            score += 2
        for hint in hints:
            if hint.lower() in lowered:
                score += 1
        if score <= 0:
            continue
        if absolute in seen:
            continue
        seen.add(absolute)
        scored.append((score, absolute))
    scored.sort(key=lambda item: (-item[0], item[1]))
    return [link for _, link in scored[:limit]]


def enrichment_quality_summary(items: list[dict[str, Any]], checked_sites: int, deferred_count: int) -> dict[str, Any]:
    validation_counts = Counter(str(item.get("email_validation_reason") or "unknown") for item in items)
    fit_counts = Counter(str(item.get("website_fit_status") or "unknown") for item in items)
    reachability_counts = Counter(str(item.get("reachability_status") or "unknown") for item in items)
    valid_emails = sum(1 for item in items if str(item.get("email") or "").strip())
    contact_forms = sum(1 for item in items if item.get("contact_form_detected"))
    return {
        "checked_sites": checked_sites,
        "deferred_count": deferred_count,
        "record_count": len(items),
        "validated_email_count": valid_emails,
        "contact_form_detected_count": contact_forms,
        "email_validation_reason_counts": dict(validation_counts),
        "website_fit_status_counts": dict(fit_counts),
        "reachability_status_counts": dict(reachability_counts),
    }

