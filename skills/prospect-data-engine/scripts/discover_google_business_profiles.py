#!/usr/bin/env python3

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from urllib.parse import quote_plus, unquote, urlparse


MAP_HOSTS = {"google.com", "www.google.com"}


WORKSPACE_ROOT = Path("/Users/mac_claw/.openclaw/workspace")
if str(WORKSPACE_ROOT) not in sys.path:
    sys.path.insert(0, str(WORKSPACE_ROOT))

from tools.openmoss.ops.local_data_platform_bridge import sync_marketing_suite


def _read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _infer_company_name(url: str) -> str:
    parsed = urlparse(url)
    path = unquote(parsed.path or "").strip("/")
    tail = path.split("/")[-1] if path else parsed.netloc
    tail = tail.replace("+", " ").replace("-", " ")
    tail = re.sub(r"^place/", "", tail)
    return re.sub(r"\s+", " ", tail).strip().title()


def main() -> int:
    parser = argparse.ArgumentParser(description="Normalize Google Business Profile-like discovery targets into raw imports.")
    parser.add_argument("--project-root", required=True)
    args = parser.parse_args()

    project_root = Path(args.project_root).expanduser().resolve()
    generated_targets_path = project_root / "data" / "discovery-targets.generated.json"
    generated_targets = _read_json(generated_targets_path).get("items", []) if generated_targets_path.exists() else []
    generated_queries_path = project_root / "data" / "discovery-queries.generated.json"
    generated_queries = _read_json(generated_queries_path).get("items", []) if generated_queries_path.exists() else []
    targets = []
    for item in generated_targets:
        if not item.get("enabled"):
            continue
        if item.get("source_family") != "google_business_profile":
            continue
        parsed = urlparse(item.get("target_url", ""))
        host = parsed.netloc.lower()
        if host not in MAP_HOSTS:
            continue
        if "/maps" not in (parsed.path or "") and "/search" not in (parsed.path or ""):
            continue
        targets.append(item)

    if not targets:
        for item in generated_queries:
            if not item.get("enabled"):
                continue
            if item.get("source_family") != "google_business_profile":
                continue
            query = item.get("query", "").strip()
            if not query:
                continue
            targets.append(
                {
                    "target_url": f"https://www.google.com/maps/search/{quote_plus(query)}",
                    "target_id": f"gbp-synth-{item.get('query_id', '')}",
                    "account_type": item.get("account_type", ""),
                    "persona_type": item.get("persona_type", ""),
                    "geo": item.get("geo", ""),
                    "query_id": item.get("query_id"),
                    "generated_from_query": query,
                    "query_family": item.get("query_family"),
                    "source_family": "google_business_profile",
                    "signal_hints": list(item.get("signal_hints", [])) + ["gbp_synthesized_target"],
                    "enabled": True,
                }
            )

    discovered = []
    for target in targets:
        discovered.append(
            {
                "source_url": target.get("target_url", ""),
                "company_name": _infer_company_name(target.get("target_url", "")),
                "website_root_domain": "",
                "account_type": target.get("account_type", ""),
                "persona_type": target.get("persona_type", ""),
                "geo": target.get("geo", ""),
                "signals": list(target.get("signal_hints", [])) + ["gbp_discovery"],
                "email": "",
                "full_name": "",
                "reachability_status": "unknown",
                "source_confidence": 0.66,
                "query_id": target.get("query_id"),
                "discovery_query": target.get("generated_from_query"),
                "query_family": target.get("query_family"),
                "source_family": "google_business_profile",
                "target_id": target.get("target_id"),
            }
        )

    output_path = project_root / "data" / "raw-imports" / "discovered-google-business-profiles.json"
    _write_json(output_path, {"items": discovered})
    report = {
        "enabled_target_count": len(targets),
        "discovered_count": len(discovered),
        "failure_count": 0,
        "raw_import_path": str(output_path),
    }
    report_path = project_root / "output" / "prospect-data-engine" / "google-business-profile-discovery-report.json"
    _write_json(report_path, report)
    sync_result = sync_marketing_suite(project_root=project_root)
    report["data_platform_sync"] = sync_result
    _write_json(report_path, report)
    result = {
        "status": "ok",
        "enabled_target_count": len(targets),
        "discovered_count": len(discovered),
        "failure_count": 0,
        "raw_import_path": str(output_path),
        "data_platform_sync": sync_result,
    }
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
