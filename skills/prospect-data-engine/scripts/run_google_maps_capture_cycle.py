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

    passthrough: list[str] = []
    for flag, value in (
        ("--keyword", args.keyword),
        ("--query-family", args.query_family),
        ("--account-type", args.account_type),
        ("--persona-type", args.persona_type),
    ):
        if value:
            passthrough.extend([flag, value])

    discovery = _run_python(DISCOVERY_SCRIPT, "--project-root", str(project_root), *passthrough)
    enrichment = _run_python(ENRICHMENT_SCRIPT, "--project-root", str(project_root))
    discovery_report = read_json(project_root / "output" / "prospect-data-engine" / "google-maps-discovery-report.json", {})
    enrichment_report = read_json(project_root / "output" / "prospect-data-engine" / "google-maps-email-enrichment-report.json", {})
    payload = {
        "status": "ok" if discovery.get("ok") and enrichment.get("ok") else "partial_failure",
        "project_root": str(project_root),
        "discovery": discovery,
        "enrichment": enrichment,
        "quality": {
            "discovery": discovery_report.get("quality_summary", {}),
            "enrichment": enrichment_report.get("quality_summary", {}),
        },
    }
    write_json(runtime_report_path, payload)
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0 if payload["status"] == "ok" else 1


if __name__ == "__main__":
    raise SystemExit(main())
