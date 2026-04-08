#!/usr/bin/env python3

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import Any
from urllib.parse import urlparse
from urllib.request import Request, urlopen


API_URL = "https://places.googleapis.com/v1/places:searchText"
API_KEY_NAMES = ["NEOSGO_GOOGLE_MAPS_API_KEY", "GOOGLE_MAPS_API_KEY"]


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _api_key() -> str:
    for name in API_KEY_NAMES:
        value = os.environ.get(name, "").strip()
        if value:
            return value
    return ""


def _root_domain(url: str) -> str:
    parsed = urlparse(url if "://" in url else f"https://{url}")
    return parsed.netloc.lower().removeprefix("www.")


def _post_json(url: str, payload: dict[str, Any], api_key: str, field_mask: list[str]) -> dict[str, Any]:
    data = json.dumps(payload).encode("utf-8")
    request = Request(
        url,
        data=data,
        method="POST",
        headers={
            "Content-Type": "application/json",
            "X-Goog-Api-Key": api_key,
            "X-Goog-FieldMask": ",".join(field_mask),
            "User-Agent": "JinClaw/1.0",
        },
    )
    with urlopen(request, timeout=30) as response:
        return json.loads(response.read().decode("utf-8"))


def main() -> int:
    parser = argparse.ArgumentParser(description="Discover Google Maps/Places leads for NEOSGO.")
    parser.add_argument("--project-root", required=True)
    args = parser.parse_args()

    project_root = Path(args.project_root).expanduser().resolve()
    config = _read_json(project_root / "config" / "project-config.json")
    capture = ((config.get("prospect_data_engine", {}) or {}).get("google_maps_capture", {}) or {})
    report_path = project_root / "output" / "prospect-data-engine" / "google-maps-discovery-report.json"
    output_path = project_root / "data" / "raw-imports" / "discovered-google-maps-places.json"

    if not capture.get("enabled"):
        _write_json(report_path, {"status": "disabled", "discovered_count": 0, "raw_import_path": str(output_path)})
        print(json.dumps({"status": "disabled", "discovered_count": 0, "raw_import_path": str(output_path)}, ensure_ascii=False, indent=2))
        return 0

    api_key = _api_key()
    if not api_key:
        payload = {
            "status": "blocked_missing_google_maps_api_key",
            "discovered_count": 0,
            "raw_import_path": str(output_path),
        }
        _write_json(report_path, payload)
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return 0

    region_plan = list(capture.get("region_plan", []) or [])
    field_mask = list(capture.get("field_mask", []) or []) or [
        "places.id",
        "places.displayName",
        "places.formattedAddress",
        "places.websiteUri",
        "places.googleMapsUri",
        "places.primaryType",
        "places.types",
        "nextPageToken",
    ]
    page_size = int(capture.get("page_size", 20) or 20)
    max_pages = int(capture.get("max_pages_per_query", 3) or 3)

    results_by_id: dict[str, dict[str, Any]] = {}
    query_runs: list[dict[str, Any]] = []
    failure_count = 0

    for region in region_plan:
        state = str(region.get("state", "")).strip()
        group = str(region.get("group", "")).strip()
        for query in list(region.get("queries", []) or []):
            page_token = ""
            pages_scanned = 0
            query_result_count = 0
            while pages_scanned < max_pages:
                body: dict[str, Any] = {
                    "textQuery": str(query),
                    "pageSize": page_size,
                }
                if page_token:
                    body["pageToken"] = page_token
                try:
                    payload = _post_json(API_URL, body, api_key, field_mask)
                except Exception as exc:  # noqa: BLE001
                    failure_count += 1
                    query_runs.append(
                        {
                            "query": query,
                            "state": state,
                            "group": group,
                            "ok": False,
                            "error": str(exc),
                            "pages_scanned": pages_scanned,
                            "result_count": query_result_count,
                        }
                    )
                    break
                pages_scanned += 1
                places = list(payload.get("places", []) or [])
                query_result_count += len(places)
                for place in places:
                    place_id = str(place.get("id", "")).strip()
                    if not place_id:
                        continue
                    website_uri = str(place.get("websiteUri", "")).strip()
                    results_by_id[place_id] = {
                        "company_name": ((place.get("displayName", {}) or {}).get("text", "")).strip(),
                        "website_root_domain": _root_domain(website_uri) if website_uri else "",
                        "website": website_uri,
                        "email": "",
                        "source_url": str(place.get("googleMapsUri", "")).strip() or website_uri,
                        "account_type": "designer",
                        "persona_type": "founder",
                        "geo": f"{state} / {group}".strip(" /"),
                        "signals": [
                            "google_maps_interior_designer_search",
                            f"region_{state.lower()}",
                            f"query:{query}",
                        ],
                        "reachability_status": "form_available" if website_uri else "unknown",
                        "source_confidence": 0.92 if website_uri else 0.72,
                        "source_family": "google_maps_places",
                        "query_id": f"google-maps-{state.lower()}-{abs(hash(query))}",
                        "discovery_query": query,
                        "query_family": "google_maps_interior_designer",
                        "generated_from_provider": "google_places_api",
                        "place_id": place_id,
                        "formatted_address": str(place.get("formattedAddress", "")).strip(),
                        "primary_type": str(place.get("primaryType", "")).strip(),
                    }
                page_token = str(payload.get("nextPageToken", "")).strip()
                if not page_token:
                    query_runs.append(
                        {
                            "query": query,
                            "state": state,
                            "group": group,
                            "ok": True,
                            "pages_scanned": pages_scanned,
                            "result_count": query_result_count,
                        }
                    )
                    break

    rows = sorted(results_by_id.values(), key=lambda item: (item.get("geo", ""), item.get("company_name", "")))
    _write_json(output_path, {"items": rows})
    report = {
        "status": "ok",
        "query_count": sum(len(region.get("queries", []) or []) for region in region_plan),
        "discovered_count": len(rows),
        "failure_count": failure_count,
        "raw_import_path": str(output_path),
        "queries": query_runs,
    }
    _write_json(report_path, report)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
