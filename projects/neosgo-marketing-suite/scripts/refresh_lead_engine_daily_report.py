#!/usr/bin/env python3
# RULES-FIRST NOTICE:
# Before modifying this file, first read:
# - `JINCLAW_CONSTITUTION.md`
# - `AI_OPTIMIZATION_FRAMEWORK.md`
# Follow the constitution and framework:
# brain-first, one-doctor, fail-closed, evidence-over-narration,
# validate locally, then use the required PR workflow.
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import textwrap
from datetime import datetime, timezone
from pathlib import Path


WORKSPACE_ROOT = Path(__file__).resolve().parents[3]
PROJECT_ROOT = WORKSPACE_ROOT / "projects" / "neosgo-marketing-suite"
DEFAULT_DB_PATH = WORKSPACE_ROOT / "data" / "neosgo_leads.duckdb"
DEFAULT_DUCKDB_PYTHON = WORKSPACE_ROOT / "projects" / "ma-data-workbench" / ".venv" / "bin" / "python"
BUILD_SQL_PATH = WORKSPACE_ROOT / "skills" / "neosgo-lead-engine" / "scripts" / "build_lead_engine_views.sql"
DAILY_REPORT_SCRIPT = WORKSPACE_ROOT / "skills" / "neosgo-lead-engine" / "scripts" / "generate_daily_report.py"
METRICS_SCRIPT = PROJECT_ROOT / "scripts" / "read_lead_engine_metrics.py"
DEFAULT_REPORT_PATH = PROJECT_ROOT / "output" / "prospect-data-engine" / "lead-engine-daily-report-latest.md"
DEFAULT_METRICS_PATH = PROJECT_ROOT / "runtime" / "prospect-data-engine" / "lead-engine-metrics-latest.json"
DEFAULT_PROBE_TIMEOUT_SECONDS = 30
DEFAULT_REFRESH_TIMEOUT_SECONDS = 1800
DEFAULT_REFRESH_THREADS = 4
DEFAULT_REFRESH_MEMORY_LIMIT = "8GB"
DEFAULT_REFRESH_PRESERVE_INSERTION_ORDER = False


def _candidate_pythons(explicit: str | None) -> list[Path]:
    candidates: list[Path] = []
    for value in (
        explicit,
        os.environ.get("NEOSGO_DUCKDB_PYTHON"),
        str(DEFAULT_DUCKDB_PYTHON),
        sys.executable,
    ):
        if not value:
            continue
        path = Path(value).expanduser()
        if path.exists() and path not in candidates:
            candidates.append(path)
    return candidates


def _supports_duckdb(python_path: Path) -> bool:
    proc = subprocess.run(
        [str(python_path), "-c", "import duckdb"],
        capture_output=True,
        text=True,
        check=False,
    )
    return proc.returncode == 0


def _choose_duckdb_python(explicit: str | None) -> Path:
    candidates = _candidate_pythons(explicit)
    for candidate in candidates:
        if _supports_duckdb(candidate):
            return candidate
    searched = ", ".join(str(path) for path in candidates) or "<none>"
    raise SystemExit(f"no DuckDB-capable Python interpreter found; checked: {searched}")


def _format_duckdb_error(stdout: str, stderr: str, db_path: Path, fallback: str) -> str:
    detail = stderr.strip() or stdout.strip() or fallback
    if "Could not set lock on file" in detail:
        return f"lead-engine database is locked by another process; retry after the current job releases {db_path}"
    return detail


def _assert_db_accessible(duckdb_python: Path, db_path: Path) -> None:
    program = textwrap.dedent(
        """
        from pathlib import Path
        import sys

        import duckdb

        db_path = Path(sys.argv[1])
        con = duckdb.connect(str(db_path), read_only=True)
        con.execute("select 1").fetchone()
        con.close()
        """
    )
    try:
        proc = subprocess.run(
            [str(duckdb_python), "-c", program, str(db_path)],
            capture_output=True,
            text=True,
            check=False,
            timeout=DEFAULT_PROBE_TIMEOUT_SECONDS,
        )
    except subprocess.TimeoutExpired as exc:
        raise SystemExit(f"timed out probing lead-engine database after {DEFAULT_PROBE_TIMEOUT_SECONDS}s") from exc
    if proc.returncode != 0:
        raise SystemExit(_format_duckdb_error(proc.stdout, proc.stderr, db_path, "database probe failed"))


def _refresh_views(
    duckdb_python: Path,
    db_path: Path,
    sql_path: Path,
    threads: int,
    memory_limit: str,
    preserve_insertion_order: bool,
) -> None:
    if not db_path.exists():
        raise SystemExit(f"missing lead-engine database: {db_path}")
    if not sql_path.exists():
        raise SystemExit(f"missing lead-engine SQL definition: {sql_path}")
    program = textwrap.dedent(
        """
        from pathlib import Path
        import sys

        import duckdb

        db_path = Path(sys.argv[1])
        sql_path = Path(sys.argv[2])
        threads = int(sys.argv[3])
        memory_limit = sys.argv[4]
        preserve_insertion_order = sys.argv[5].lower() == "true"
        con = duckdb.connect(str(db_path))
        con.execute(f"SET threads={threads}")
        con.execute(f"SET memory_limit='{memory_limit}'")
        con.execute(f"SET preserve_insertion_order={'true' if preserve_insertion_order else 'false'}")
        con.execute(sql_path.read_text(encoding="utf-8"))
        con.close()
        """
    )
    try:
        proc = subprocess.run(
            [
                str(duckdb_python),
                "-c",
                program,
                str(db_path),
                str(sql_path),
                str(threads),
                memory_limit,
                "true" if preserve_insertion_order else "false",
            ],
            capture_output=True,
            text=True,
            check=False,
            timeout=DEFAULT_REFRESH_TIMEOUT_SECONDS,
        )
    except subprocess.TimeoutExpired as exc:
        raise SystemExit(f"timed out refreshing lead-engine views after {DEFAULT_REFRESH_TIMEOUT_SECONDS}s") from exc
    if proc.returncode != 0:
        raise SystemExit(_format_duckdb_error(proc.stdout, proc.stderr, db_path, "view refresh failed"))


def _run_daily_report(duckdb_python: Path, db_path: Path, report_path: Path) -> None:
    report_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        proc = subprocess.run(
            [str(duckdb_python), str(DAILY_REPORT_SCRIPT), "--db", str(db_path), "--out", str(report_path)],
            capture_output=True,
            text=True,
            check=False,
            timeout=DEFAULT_REFRESH_TIMEOUT_SECONDS,
        )
    except subprocess.TimeoutExpired as exc:
        raise SystemExit(f"timed out generating daily report after {DEFAULT_REFRESH_TIMEOUT_SECONDS}s") from exc
    if proc.returncode != 0:
        detail = proc.stderr.strip() or proc.stdout.strip() or "daily report generation failed"
        raise SystemExit(detail)


def _parse_json_stdout(stdout: str) -> dict[str, object]:
    payload = stdout.strip()
    if not payload:
        raise SystemExit("metrics collection produced no JSON output")
    for line in reversed(payload.splitlines()):
        candidate = line.strip()
        if candidate.startswith("{"):
            return json.loads(candidate)
    return json.loads(payload)


def _read_metrics(db_path: Path, duckdb_python: Path) -> dict[str, object]:
    proc = subprocess.run(
        [
            sys.executable,
            str(METRICS_SCRIPT),
            "--db",
            str(db_path),
            "--python",
            str(duckdb_python),
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    if proc.returncode != 0:
        detail = proc.stderr.strip() or proc.stdout.strip() or "metrics collection failed"
        raise SystemExit(detail)
    return _parse_json_stdout(proc.stdout)


def main() -> int:
    parser = argparse.ArgumentParser(description="Refresh NEOSGO lead-engine views and the project-local daily report.")
    parser.add_argument("--db", default=str(DEFAULT_DB_PATH), help="Path to neosgo_leads.duckdb")
    parser.add_argument("--python", dest="python_path", help="DuckDB-capable Python interpreter")
    parser.add_argument("--report-out", default=str(DEFAULT_REPORT_PATH), help="Markdown report output path")
    parser.add_argument("--metrics-out", default=str(DEFAULT_METRICS_PATH), help="JSON metrics output path")
    parser.add_argument("--refresh-threads", type=int, default=DEFAULT_REFRESH_THREADS, help="DuckDB threads for heavy refresh")
    parser.add_argument("--refresh-memory-limit", default=DEFAULT_REFRESH_MEMORY_LIMIT, help="DuckDB memory_limit for heavy refresh")
    parser.add_argument(
        "--preserve-insertion-order",
        action=argparse.BooleanOptionalAction,
        default=DEFAULT_REFRESH_PRESERVE_INSERTION_ORDER,
        help="DuckDB preserve_insertion_order setting during heavy refresh",
    )
    args = parser.parse_args()

    db_path = Path(args.db).expanduser()
    report_path = Path(args.report_out).expanduser()
    metrics_path = Path(args.metrics_out).expanduser()
    duckdb_python = _choose_duckdb_python(args.python_path)

    _assert_db_accessible(duckdb_python, db_path)
    _refresh_views(
        duckdb_python,
        db_path,
        BUILD_SQL_PATH,
        threads=args.refresh_threads,
        memory_limit=args.refresh_memory_limit,
        preserve_insertion_order=args.preserve_insertion_order,
    )
    _run_daily_report(duckdb_python, db_path, report_path)
    metrics = _read_metrics(db_path, duckdb_python)

    metrics_payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "duckdb_python": str(duckdb_python),
        "db_path": str(db_path),
        "view_sql_path": str(BUILD_SQL_PATH),
        "report_path": str(report_path),
        "refresh_threads": args.refresh_threads,
        "refresh_memory_limit": args.refresh_memory_limit,
        "preserve_insertion_order": args.preserve_insertion_order,
        "metrics": metrics,
    }
    metrics_path.parent.mkdir(parents=True, exist_ok=True)
    metrics_path.write_text(json.dumps(metrics_payload, ensure_ascii=False, indent=2), encoding="utf-8")

    summary = {
        "report_path": str(report_path),
        "metrics_path": str(metrics_path),
        "raw_contacts": metrics.get("raw_contacts"),
        "deduped_contacts": metrics.get("deduped_contacts"),
        "scored_prospects": metrics.get("scored_prospects"),
        "outreach_queue_pending": metrics.get("outreach_queue_pending"),
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
