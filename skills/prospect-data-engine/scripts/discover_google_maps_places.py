#!/usr/bin/env python3

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any
from urllib.parse import quote_plus, urlparse
from urllib.request import Request, urlopen


JINA_PREFIX = "https://r.jina.ai/http://www.google.com/maps/search/"
USER_AGENT = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/135.0 Safari/537.36"
WEBSITE_RE = re.compile(r"^\[.*Website.*\]\((https?://[^)]+)\)$", re.I)
PLACE_LINK_RE = re.compile(r"^\[\]\((https://www\.google\.com/maps/place/[^)]+)\)$", re.I)
RATING_RE = re.compile(r"^\d+(?:\.\d+)?$")
QUERY_ID_SANITIZE_RE = re.compile(r"[^a-z0-9]+")
STATE_GROUPS = {
    "ME": "new_england",
    "NH": "new_england",
    "VT": "new_england",
    "MA": "new_england",
    "RI": "new_england",
    "CT": "new_england",
    "NY": "mid_atlantic",
    "NJ": "mid_atlantic",
    "PA": "mid_atlantic",
    "DE": "mid_atlantic",
    "MD": "mid_atlantic",
    "VA": "south_atlantic",
    "NC": "south_atlantic",
    "SC": "south_atlantic",
    "GA": "south_atlantic",
    "FL": "south_atlantic",
    "WV": "south_atlantic",
    "AL": "south",
    "MS": "south",
    "TN": "south",
    "KY": "south",
    "LA": "south",
    "AR": "south",
    "OK": "south_central",
    "TX": "south_central",
    "OH": "midwest",
    "MI": "midwest",
    "IN": "midwest",
    "IL": "midwest",
    "WI": "midwest",
    "MN": "midwest",
    "IA": "midwest",
    "MO": "midwest",
    "ND": "plains",
    "SD": "plains",
    "NE": "plains",
    "KS": "plains",
    "NM": "mountain",
    "CO": "mountain",
    "WY": "mountain",
    "MT": "mountain",
    "ID": "mountain",
    "UT": "mountain",
    "AZ": "mountain",
    "NV": "mountain",
    "WA": "west_coast",
    "OR": "west_coast",
    "CA": "west_coast",
}
CONTIGUOUS_STATE_NAMES = {
    "AL": "Alabama",
    "AZ": "Arizona",
    "AR": "Arkansas",
    "CA": "California",
    "CO": "Colorado",
    "CT": "Connecticut",
    "DE": "Delaware",
    "FL": "Florida",
    "GA": "Georgia",
    "ID": "Idaho",
    "IL": "Illinois",
    "IN": "Indiana",
    "IA": "Iowa",
    "KS": "Kansas",
    "KY": "Kentucky",
    "LA": "Louisiana",
    "ME": "Maine",
    "MD": "Maryland",
    "MA": "Massachusetts",
    "MI": "Michigan",
    "MN": "Minnesota",
    "MS": "Mississippi",
    "MO": "Missouri",
    "MT": "Montana",
    "NE": "Nebraska",
    "NV": "Nevada",
    "NH": "New Hampshire",
    "NJ": "New Jersey",
    "NM": "New Mexico",
    "NY": "New York",
    "NC": "North Carolina",
    "ND": "North Dakota",
    "OH": "Ohio",
    "OK": "Oklahoma",
    "OR": "Oregon",
    "PA": "Pennsylvania",
    "RI": "Rhode Island",
    "SC": "South Carolina",
    "SD": "South Dakota",
    "TN": "Tennessee",
    "TX": "Texas",
    "UT": "Utah",
    "VT": "Vermont",
    "VA": "Virginia",
    "WA": "Washington",
    "WV": "West Virginia",
    "WI": "Wisconsin",
    "WY": "Wyoming",
}


def _read_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _root_domain(url: str) -> str:
    if not url:
        return ""
    parsed = urlparse(url if "://" in url else f"https://{url}")
    return parsed.netloc.lower().removeprefix("www.")


def _fetch_markdown(query: str) -> str:
    url = JINA_PREFIX + quote_plus(query)
    request = Request(url, headers={"User-Agent": USER_AGENT})
    with urlopen(request, timeout=18) as response:
        return response.read().decode("utf-8", "ignore")


def _safe_query_id(state: str, query: str) -> str:
    slug = QUERY_ID_SANITIZE_RE.sub("-", query.lower()).strip("-")
    return f"google-maps-{state.lower()}-{slug[:80]}"


def _flatten_queries(region_plan: list[dict[str, Any]]) -> list[dict[str, str]]:
    flattened: list[dict[str, str]] = []
    for region in region_plan:
        state = str(region.get("state", "")).strip()
        group = str(region.get("group", "")).strip()
        for query in list(region.get("queries", []) or []):
            flattened.append(
                {
                    "state": state,
                    "group": group,
                    "query": str(query),
                }
            )
    return flattened


def _expand_to_contiguous_48(region_plan: list[dict[str, Any]]) -> list[dict[str, Any]]:
    existing_states = {str(item.get("state", "")).strip() for item in region_plan}
    expanded = list(region_plan)
    for state_code, state_name in CONTIGUOUS_STATE_NAMES.items():
        if state_code in existing_states:
            continue
        expanded.append(
            {
                "group": STATE_GROUPS.get(state_code, "nationwide"),
                "state": state_code,
                "queries": [
                    f"interior designer in {state_name}",
                ],
            }
        )
    return expanded


def _select_query_window(items: list[dict[str, str]], start: int, size: int) -> list[dict[str, str]]:
    if not items:
        return []
    if size <= 0 or size >= len(items):
        return list(items)
    selected = []
    for offset in range(size):
        selected.append(items[(start + offset) % len(items)])
    return selected


def _dedupe_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    deduped: list[dict[str, Any]] = []
    seen_keys: set[tuple[str, str, str]] = set()
    for row in rows:
        place_url = str(row.get("place_url") or row.get("source_url") or "").strip().lower()
        company_name = str(row.get("company_name") or "").strip().lower()
        website_root_domain = str(row.get("website_root_domain") or "").strip().lower()
        dedupe_key = (place_url, company_name, website_root_domain)
        if dedupe_key in seen_keys:
            continue
        seen_keys.add(dedupe_key)
        deduped.append(row)
    return sorted(deduped, key=lambda item: (item.get("geo", ""), item.get("company_name", "")))


def _parse_markdown_results(markdown: str, state: str, group: str, query: str) -> list[dict[str, Any]]:
    lines = [line.strip() for line in markdown.splitlines()]
    rows: list[dict[str, Any]] = []
    seen_place_urls: set[str] = set()

    index = 0
    while index < len(lines):
        line = lines[index]
        place_link_match = PLACE_LINK_RE.match(line)
        if not place_link_match:
            index += 1
            continue

        place_url = place_link_match.group(1).strip()
        if place_url in seen_place_urls:
            index += 1
            continue
        seen_place_urls.add(place_url)

        cursor = index + 1
        while cursor < len(lines) and not lines[cursor]:
            cursor += 1
        if cursor >= len(lines):
            break
        company_name = lines[cursor].strip()
        cursor += 1

        rating = ""
        if cursor < len(lines) and RATING_RE.match(lines[cursor]):
            rating = lines[cursor]
            cursor += 1

        category_line = ""
        if cursor < len(lines):
            category_line = lines[cursor].strip()
            cursor += 1

        hours_phone_line = ""
        if cursor < len(lines) and "Directions" not in lines[cursor]:
            hours_phone_line = lines[cursor].strip()
            cursor += 1

        website = ""
        while cursor < len(lines):
            website_match = WEBSITE_RE.match(lines[cursor])
            if website_match:
                website = website_match.group(1).strip()
                cursor += 1
                break
            if PLACE_LINK_RE.match(lines[cursor]):
                break
            cursor += 1

        category = category_line.split("·", 1)[0].strip() if category_line else ""
        address = category_line.split("·", 1)[1].strip() if "·" in category_line else ""
        phone = hours_phone_line.rsplit("·", 1)[-1].strip() if "·" in hours_phone_line else ""

        rows.append(
            {
                "company_name": company_name,
                "website_root_domain": _root_domain(website),
                "website": website,
                "email": "",
                "source_url": place_url,
                "account_type": "designer",
                "persona_type": "founder",
                "geo": f"{state} / {group}".strip(" /"),
                "signals": [
                    "google_maps_interior_designer_search",
                    f"region_{state.lower()}",
                    f"query:{query}",
                ],
                "reachability_status": "form_available" if website else "unknown",
                "source_confidence": 0.94 if website else 0.78,
                "source_family": "google_maps_places",
                "query_id": _safe_query_id(state, query),
                "discovery_query": query,
                "query_family": "google_maps_interior_designer",
                "generated_from_provider": "google_maps_browser_crawler",
                "place_url": place_url,
                "rating": rating,
                "category": category,
                "formatted_address": address,
                "phone": phone,
            }
        )
        index = cursor

    return rows


def main() -> int:
    parser = argparse.ArgumentParser(description="Discover Google Maps leads for NEOSGO via browser-style crawling, without API keys.")
    parser.add_argument("--project-root", required=True)
    args = parser.parse_args()

    project_root = Path(args.project_root).expanduser().resolve()
    config = _read_json(project_root / "config" / "project-config.json")
    capture = ((config.get("prospect_data_engine", {}) or {}).get("google_maps_capture", {}) or {})
    report_path = project_root / "output" / "prospect-data-engine" / "google-maps-discovery-report.json"
    output_path = project_root / "data" / "raw-imports" / "discovered-google-maps-places.json"
    runtime_state_path = project_root / "runtime" / "prospect-data-engine" / "google-maps-crawl-state.json"
    last_success_path = project_root / "runtime" / "prospect-data-engine" / "google-maps-discovery-last-success.json"
    cached_output = _read_json(output_path)
    cached_items = list(cached_output.get("items", []) or [])

    if not capture.get("enabled"):
        payload = {"status": "disabled", "discovered_count": 0, "raw_import_path": str(output_path)}
        _write_json(report_path, payload)
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return 0

    region_plan = list(capture.get("region_plan", []) or [])
    if str(capture.get("coverage_scope", "contiguous_us_48")).strip().lower() == "contiguous_us_48":
        region_plan = _expand_to_contiguous_48(region_plan)
    flattened_queries = _flatten_queries(region_plan)
    max_queries_per_run = int(capture.get("max_queries_per_run", 8) or 8)
    runtime_state = _read_json(runtime_state_path)
    cursor = int(runtime_state.get("cursor", 0) or 0)
    selected_queries = _select_query_window(flattened_queries, cursor, max_queries_per_run)
    all_rows: list[dict[str, Any]] = []
    seen_keys: set[tuple[str, str]] = set()
    query_runs: list[dict[str, Any]] = []
    failure_count = 0

    for item in selected_queries:
        state = item["state"]
        group = item["group"]
        query = item["query"]
        try:
            markdown = _fetch_markdown(query)
            parsed_rows = _parse_markdown_results(markdown, state, group, query)
            deduped_rows = []
            for row in parsed_rows:
                dedupe_key = (row.get("company_name", "").strip().lower(), row.get("website_root_domain", "").strip().lower())
                if dedupe_key in seen_keys:
                    continue
                seen_keys.add(dedupe_key)
                deduped_rows.append(row)
                all_rows.append(row)
            query_runs.append(
                {
                    "query": query,
                    "state": state,
                    "group": group,
                    "ok": True,
                    "result_count": len(deduped_rows),
                }
            )
        except Exception as exc:  # noqa: BLE001
            failure_count += 1
            query_runs.append(
                {
                    "query": query,
                    "state": state,
                    "group": group,
                    "ok": False,
                    "error": str(exc),
                    "result_count": 0,
                }
            )

    rows = _dedupe_rows([*cached_items, *all_rows])
    status = "ok"
    used_cached_results = False
    cached_last_success = _read_json(last_success_path)
    cached_last_success_items = list(cached_last_success.get("items", []) or [])
    if not all_rows and failure_count:
        if cached_items:
            rows = cached_items
            status = "rate_limited_using_cached_results"
            used_cached_results = True
        elif cached_last_success_items:
            rows = cached_last_success_items
            status = "rate_limited_using_last_success"
            used_cached_results = True
    if not rows and cached_items and failure_count:
        rows = cached_items
        status = "rate_limited_using_cached_results"
        used_cached_results = True

    _write_json(output_path, {"items": rows})
    if rows:
        _write_json(last_success_path, {"items": rows})
    next_cursor = (cursor + len(selected_queries)) % len(flattened_queries) if flattened_queries else 0
    _write_json(
        runtime_state_path,
        {
            "cursor": next_cursor,
            "last_cursor_start": cursor,
            "last_run_query_count": len(selected_queries),
            "total_query_count": len(flattened_queries),
        },
    )
    report = {
        "status": status,
        "query_count": len(flattened_queries),
        "scheduled_query_count": len(selected_queries),
        "cursor_start": cursor,
        "cursor_next": next_cursor,
        "discovered_count": len(rows),
        "failure_count": failure_count,
        "raw_import_path": str(output_path),
        "queries": query_runs,
        "capture_mode": "browser_crawler_via_google_maps_html",
        "used_cached_results": used_cached_results,
    }
    _write_json(report_path, report)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
