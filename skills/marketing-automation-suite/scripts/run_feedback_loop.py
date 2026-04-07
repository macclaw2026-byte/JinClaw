#!/usr/bin/env python3

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path


WORKSPACE_ROOT = Path("/Users/mac_claw/.openclaw/workspace")
VALIDATE_FEEDBACK = WORKSPACE_ROOT / "skills/outreach-feedback-engine/scripts/validate_feedback_events.py"
MERGE_FEEDBACK = WORKSPACE_ROOT / "skills/outreach-feedback-engine/scripts/merge_feedback_events.py"
RUN_SUITE = WORKSPACE_ROOT / "skills/marketing-automation-suite/scripts/run_marketing_suite_cycle.py"
BUILD_TEMPLATE = WORKSPACE_ROOT / "skills/outreach-feedback-engine/scripts/build_feedback_event_template.py"


def _read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _run_python(script: Path, *args: str) -> dict:
    completed = subprocess.run(
        [sys.executable, str(script), *args],
        capture_output=True,
        text=True,
        check=False,
    )
    stdout = completed.stdout.strip()
    payload = {}
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


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate, merge, rerun, and rebuild feedback loop artifacts.")
    parser.add_argument("--project-root", required=True)
    parser.add_argument("--source-template")
    parser.add_argument("--target-feedback")
    parser.add_argument("--archive-template")
    parser.add_argument("--validation-output")
    parser.add_argument("--summary-output")
    args = parser.parse_args()

    project_root = Path(args.project_root).expanduser().resolve()
    source_template = Path(
        args.source_template or project_root / "data" / "feedback-events.template.json"
    ).expanduser()
    target_feedback = Path(
        args.target_feedback or project_root / "data" / "feedback-events.json"
    ).expanduser()
    archive_template = Path(
        args.archive_template or project_root / "data" / "feedback-events.template.archive.json"
    ).expanduser()
    validation_output = Path(
        args.validation_output or project_root / "runtime" / "feedback-loop" / "validation.json"
    ).expanduser()
    summary_output = Path(
        args.summary_output or project_root / "runtime" / "feedback-loop" / "last_run.json"
    ).expanduser()

    validation_result = _run_python(
        VALIDATE_FEEDBACK,
        "--source",
        str(source_template),
        "--output",
        str(validation_output),
    )
    validation_payload = validation_result.get("payload", {})
    completed_count = validation_payload.get("completed_count", 0)

    if not validation_result["ok"]:
        summary = {
            "status": "blocked",
            "ran_at": _utc_now(),
            "project_root": str(project_root),
            "reason": "feedback_validation_failed",
            "validation": validation_result,
        }
        _write_json(summary_output, summary)
        print(json.dumps(summary, ensure_ascii=False, indent=2))
        return 1

    if completed_count == 0:
        summary = {
            "status": "waiting_for_feedback",
            "ran_at": _utc_now(),
            "project_root": str(project_root),
            "reason": "no_completed_feedback_rows",
            "validation": validation_result,
        }
        _write_json(summary_output, summary)
        print(json.dumps(summary, ensure_ascii=False, indent=2))
        return 0

    merge_result = _run_python(
        MERGE_FEEDBACK,
        "--source",
        str(source_template),
        "--target",
        str(target_feedback),
        "--archive",
        str(archive_template),
    )
    if not merge_result["ok"]:
        summary = {
            "status": "blocked",
            "ran_at": _utc_now(),
            "project_root": str(project_root),
            "reason": "feedback_merge_failed",
            "validation": validation_result,
            "merge": merge_result,
        }
        _write_json(summary_output, summary)
        print(json.dumps(summary, ensure_ascii=False, indent=2))
        return 1

    suite_result = _run_python(
        RUN_SUITE,
        "--project-root",
        str(project_root),
    )
    if not suite_result["ok"]:
        summary = {
            "status": "blocked",
            "ran_at": _utc_now(),
            "project_root": str(project_root),
            "reason": "suite_cycle_failed",
            "validation": validation_result,
            "merge": merge_result,
            "suite": suite_result,
        }
        _write_json(summary_output, summary)
        print(json.dumps(summary, ensure_ascii=False, indent=2))
        return 1

    cycle_payload = suite_result.get("payload", {})
    execution_queue_path = (
        cycle_payload.get("artifacts", {}).get("execution_queue_path")
        or project_root / "runtime" / "marketing-automation-suite" / "last_execution_queue.json"
    )
    build_template_result = _run_python(
        BUILD_TEMPLATE,
        "--execution-queue",
        str(execution_queue_path),
        "--output",
        str(source_template),
        "--limit",
        "40",
    )

    summary = {
        "status": "ok" if build_template_result["ok"] else "degraded",
        "ran_at": _utc_now(),
        "project_root": str(project_root),
        "completed_feedback_merged": merge_result.get("payload", {}).get("completed_count", 0),
        "target_feedback_total": merge_result.get("payload", {}).get("target_total", 0),
        "new_cycle_id": cycle_payload.get("cycle_id", ""),
        "new_execution_queue_path": str(execution_queue_path),
        "validation": validation_result,
        "merge": merge_result,
        "suite": suite_result,
        "next_template": build_template_result,
    }
    _write_json(summary_output, summary)
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0 if build_template_result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
