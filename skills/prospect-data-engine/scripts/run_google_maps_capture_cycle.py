#!/usr/bin/env python3

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

from google_maps_capture_core import read_json, write_json


SCRIPT_DIR = Path(__file__).resolve().parent
DISCOVERY_SCRIPT = SCRIPT_DIR / "discover_google_maps_places.py"
ENRICHMENT_SCRIPT = SCRIPT_DIR / "enrich_google_maps_website_contacts.py"
WORKSPACE_ROOT = Path("/Users/mac_claw/.openclaw/workspace")

if str(WORKSPACE_ROOT) not in sys.path:
    sys.path.insert(0, str(WORKSPACE_ROOT))

from tools.openmoss.ops.local_data_platform_bridge import sync_marketing_suite


def _slugify(value: str) -> str:
    return "".join(ch.lower() if ch.isalnum() else "_" for ch in str(value or "")).strip("_")


def _load_capture_lanes(capture: dict[str, object]) -> list[dict[str, str]]:
    """从配置中读取 lane 定义；兼容旧版单 lane 配置。"""
    raw_lanes = list(capture.get("lanes", []) or [])
    lanes: list[dict[str, str]] = []
    for raw in raw_lanes:
        lane = dict(raw or {})
        keyword = str(lane.get("keyword") or "").strip()
        if not keyword:
            continue
        query_family = str(lane.get("query_family") or "").strip() or f"google_maps_{_slugify(keyword)}"
        lane_key = str(lane.get("lane_key") or "").strip() or query_family.removeprefix("google_maps_") or _slugify(keyword)
        lanes.append(
            {
                "lane_key": lane_key,
                "keyword": keyword,
                "query_family": query_family,
                "account_type": str(lane.get("account_type") or capture.get("account_type") or "business").strip() or "business",
                "persona_type": str(lane.get("persona_type") or capture.get("persona_type") or "operator").strip() or "operator",
            }
        )
    if lanes:
        return lanes
    keyword = str(capture.get("keyword") or "business").strip() or "business"
    query_family = str(capture.get("query_family") or "").strip() or f"google_maps_{_slugify(keyword)}"
    return [
        {
            "lane_key": query_family.removeprefix("google_maps_") or _slugify(keyword),
            "keyword": keyword,
            "query_family": query_family,
            "account_type": str(capture.get("account_type") or "business").strip() or "business",
            "persona_type": str(capture.get("persona_type") or "operator").strip() or "operator",
        }
    ]


def _lane_quality_snapshot(items: list[dict[str, object]]) -> dict[str, dict[str, object]]:
    lane_stats: dict[str, dict[str, object]] = {}
    for item in items:
        lane_key = str(item.get("query_family") or item.get("source_family") or "unknown").strip() or "unknown"
        bucket = lane_stats.setdefault(
            lane_key,
            {
                "lane_key": lane_key,
                "record_count": 0,
                "approved_count": 0,
                "pending_batch_count": 0,
                "review_count": 0,
                "reject_count": 0,
                "validated_email_count": 0,
                "contact_form_detected_count": 0,
            },
        )
        bucket["record_count"] += 1
        fit_status = str(item.get("website_fit_status") or "").strip()
        if fit_status == "approved":
            bucket["approved_count"] += 1
        elif fit_status == "pending_batch":
            bucket["pending_batch_count"] += 1
        elif fit_status == "review":
            bucket["review_count"] += 1
        elif fit_status == "reject":
            bucket["reject_count"] += 1
        if str(item.get("email") or "").strip():
            bucket["validated_email_count"] += 1
        if bool(item.get("contact_form_detected")):
            bucket["contact_form_detected_count"] += 1
    return lane_stats


def _run_python(script: Path, *args: str) -> dict[str, object]:
    completed = subprocess.run(
        [sys.executable, str(script), *args],
        capture_output=True,
        text=True,
        check=False,
    )
    stdout = completed.stdout.strip()
    payload: dict[str, object] = {}
    if stdout:
        try:
            payload = json.loads(stdout)
        except json.JSONDecodeError:
            payload = {"stdout": stdout}
    return {
        "ok": completed.returncode == 0,
        "returncode": completed.returncode,
        "stdout": stdout,
        "stderr": completed.stderr.strip(),
        "payload": payload,
        "script": str(script),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the reusable Google Maps discovery + enrichment cycle.")
    parser.add_argument("--project-root", required=True)
    parser.add_argument("--keyword")
    parser.add_argument("--query-family")
    parser.add_argument("--account-type")
    parser.add_argument("--persona-type")
    args = parser.parse_args()

    project_root = Path(args.project_root).expanduser().resolve()
    runtime_report_path = project_root / "output" / "prospect-data-engine" / "google-maps-capture-cycle-report.json"
    config = read_json(project_root / "config" / "project-config.json", {})
    capture = ((config.get("prospect_data_engine", {}) or {}).get("google_maps_capture", {}) or {})
    lanes = _load_capture_lanes(capture)

    passthrough: list[str] = []
    for flag, value in (
        ("--keyword", args.keyword),
        ("--query-family", args.query_family),
        ("--account-type", args.account_type),
        ("--persona-type", args.persona_type),
    ):
        if value:
            passthrough.extend([flag, value])

    lane_results: list[dict[str, object]] = []
    for lane in lanes:
        lane_passthrough = list(passthrough)
        if not args.keyword:
            lane_passthrough.extend(["--keyword", lane["keyword"]])
        if not args.query_family:
            lane_passthrough.extend(["--query-family", lane["query_family"]])
        if not args.account_type:
            lane_passthrough.extend(["--account-type", lane["account_type"]])
        if not args.persona_type:
            lane_passthrough.extend(["--persona-type", lane["persona_type"]])
        discovery = _run_python(DISCOVERY_SCRIPT, "--project-root", str(project_root), *lane_passthrough)
        lane_results.append(
            {
                "lane_key": lane["lane_key"],
                "keyword": lane["keyword"],
                "query_family": lane["query_family"],
                "account_type": lane["account_type"],
                "persona_type": lane["persona_type"],
                "discovery": discovery,
            }
        )

    enrichment = _run_python(ENRICHMENT_SCRIPT, "--project-root", str(project_root))
    enrichment_report = read_json(project_root / "output" / "prospect-data-engine" / "google-maps-email-enrichment-report.json", {})
    discovery_items = list(read_json(project_root / "data" / "raw-imports" / "discovered-google-maps-places.json", {}).get("items", []) or [])
    enriched_items = list(read_json(project_root / "data" / "raw-imports" / "discovered-google-maps-validated-contacts.json", {}).get("items", []) or [])
    aggregate_discovery_payload = {
        "status": "ok" if all(bool((lane.get("discovery") or {}).get("ok")) for lane in lane_results) else "partial_failure",
        "capture_mode": "google_maps_multi_lane_capture",
        "lane_count": len(lane_results),
        "discovered_count": len(discovery_items),
        "query_count": sum(int(((lane.get("discovery") or {}).get("payload") or {}).get("query_count", 0) or 0) for lane in lane_results),
        "scheduled_query_count": sum(int(((lane.get("discovery") or {}).get("payload") or {}).get("scheduled_query_count", 0) or 0) for lane in lane_results),
        "new_rows_this_run": sum(int(((lane.get("discovery") or {}).get("payload") or {}).get("new_rows_this_run", 0) or 0) for lane in lane_results),
        "failure_count": sum(int(((lane.get("discovery") or {}).get("payload") or {}).get("failure_count", 0) or 0) for lane in lane_results),
        "lanes": [
            {
                "lane_key": lane["lane_key"],
                "keyword": lane["keyword"],
                "query_family": lane["query_family"],
                "account_type": lane["account_type"],
                "persona_type": lane["persona_type"],
                "status": str(((lane.get("discovery") or {}).get("payload") or {}).get("status") or ""),
                "discovered_count": int(((lane.get("discovery") or {}).get("payload") or {}).get("discovered_count", 0) or 0),
                "new_rows_this_run": int(((lane.get("discovery") or {}).get("payload") or {}).get("new_rows_this_run", 0) or 0),
                "scheduled_query_count": int(((lane.get("discovery") or {}).get("payload") or {}).get("scheduled_query_count", 0) or 0),
                "failure_count": int(((lane.get("discovery") or {}).get("payload") or {}).get("failure_count", 0) or 0),
            }
            for lane in lane_results
        ],
    }
    aggregate_discovery = {
        "ok": all(bool((lane.get("discovery") or {}).get("ok")) for lane in lane_results),
        "returncode": 0 if all(bool((lane.get("discovery") or {}).get("ok")) for lane in lane_results) else 1,
        "stdout": json.dumps(aggregate_discovery_payload, ensure_ascii=False, indent=2),
        "stderr": "\n".join(
            str((lane.get("discovery") or {}).get("stderr") or "").strip()
            for lane in lane_results
            if str((lane.get("discovery") or {}).get("stderr") or "").strip()
        ),
        "payload": aggregate_discovery_payload,
        "script": str(DISCOVERY_SCRIPT),
    }
    lane_quality = _lane_quality_snapshot(enriched_items)
    payload = {
        "status": "ok" if aggregate_discovery.get("ok") and enrichment.get("ok") else "partial_failure",
        "project_root": str(project_root),
        "discovery": aggregate_discovery,
        "enrichment": enrichment,
        "lanes": [
            {
                **lane,
                "quality": {
                    "discovery": dict((((lane.get("discovery") or {}).get("payload") or {}).get("quality_summary") or {})),
                    "enrichment": dict(lane_quality.get(str(lane["query_family"]), {}) or {}),
                },
            }
            for lane in lane_results
        ],
        "quality": {
            "discovery": aggregate_discovery_payload,
            "enrichment": enrichment_report.get("quality_summary", {}),
            "lanes": lane_quality,
        },
    }
    write_json(runtime_report_path, payload)
    payload["data_platform_sync"] = sync_marketing_suite(project_root=project_root)
    write_json(runtime_report_path, payload)
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0 if payload["status"] == "ok" else 1


if __name__ == "__main__":
    raise SystemExit(main())
