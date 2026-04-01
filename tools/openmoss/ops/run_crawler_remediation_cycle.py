#!/usr/bin/env python3

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
import sys


WORKSPACE_ROOT = Path("/Users/mac_claw/.openclaw/workspace")
CONTROL_CENTER_ROOT = WORKSPACE_ROOT / "tools/openmoss/control_center"
OUTPUT_ROOT = WORKSPACE_ROOT / "output/crawler-remediation"
LATEST_REPORT_PATH = OUTPUT_ROOT / "latest-report.json"

if str(CONTROL_CENTER_ROOT) not in sys.path:
    sys.path.insert(0, str(CONTROL_CENTER_ROOT))

from control_plane_builder import build_control_plane
from crawler_remediation_executor import execute_crawler_remediation_plan
from system_doctor import run_system_doctor


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run project-level crawler remediation cycle.")
    parser.add_argument("--no-start", action="store_true", help="Refresh remediation plan but do not run remediation tasks.")
    parser.add_argument("--skip-doctor", action="store_true", help="Skip doctor refresh after execution.")
    return parser.parse_args()


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def run_cycle(*, start_tasks: bool = True, run_doctor: bool = True) -> dict:
    control_plane_before = build_control_plane()
    execution = execute_crawler_remediation_plan(start_tasks=start_tasks)
    doctor = run_system_doctor() if run_doctor else {}
    control_plane_after = build_control_plane()
    payload = {
        "generated_at": _utc_now_iso(),
        "start_tasks": start_tasks,
        "doctor_ran": run_doctor,
        "before_summary": control_plane_before.get("summary", {}),
        "execution": execution,
        "after_summary": control_plane_after.get("summary", {}),
        "doctor_summary": doctor.get("crawler_health", {}),
    }
    _write_json(LATEST_REPORT_PATH, payload)
    return payload


def main() -> int:
    args = parse_args()
    payload = run_cycle(start_tasks=not args.no_start, run_doctor=not args.skip_doctor)
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
