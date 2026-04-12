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
from pathlib import Path


WORKSPACE_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_DB_PATH = WORKSPACE_ROOT / "data" / "neosgo_leads.duckdb"
DEFAULT_DUCKDB_PYTHON = WORKSPACE_ROOT / "projects" / "ma-data-workbench" / ".venv" / "bin" / "python"
DEFAULT_TIMEOUT_SECONDS = 30


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


def _format_duckdb_error(stdout: str, stderr: str, db_path: Path) -> str:
    detail = stderr.strip() or stdout.strip() or "unknown DuckDB metrics failure"
    if "Could not set lock on file" in detail:
        return f"lead-engine database is locked by another process; retry after the current job releases {db_path}"
    return detail


def _collect_metrics(duckdb_python: Path, db_path: Path) -> dict[str, object]:
    if not db_path.exists():
        raise SystemExit(f"missing lead-engine database: {db_path}")
    program = textwrap.dedent(
        """
        from __future__ import annotations

        from datetime import datetime, timezone
        from pathlib import Path
        import json
        import sys

        import duckdb

        db_path = Path(sys.argv[1])
        con = duckdb.connect(str(db_path), read_only=True)
        metrics = {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "db_path": str(db_path),
            "raw_contacts": con.execute("select count(*) from raw_contacts").fetchone()[0],
            "deduped_contacts": con.execute("select count(*) from deduped_contacts").fetchone()[0],
            "scored_prospects": con.execute("select count(*) from scored_prospects").fetchone()[0],
            "outreach_queue_pending": con.execute("select count(*) from outreach_queue where status='pending'").fetchone()[0],
            "top_segments": [
                {"segment_primary": segment, "count": count}
                for segment, count in con.execute(
                    "select segment_primary, count(*) as c from scored_prospects group by 1 order by c desc limit 8"
                ).fetchall()
            ],
            "major_blockers": {
                "missing_email_or_website_in_deduped": con.execute(
                    "select count(*) from deduped_contacts where has_valid_email = 0 or has_website = 0"
                ).fetchone()[0],
                "non_target_industry_patterns_in_deduped": con.execute(
                    "select count(*) from deduped_contacts "
                    "where lower(coalesce(industry,'')) not like '%design%' "
                    "and lower(coalesce(industry,'')) not like '%architect%' "
                    "and lower(coalesce(industry,'')) not like '%contractor%' "
                    "and lower(coalesce(industry,'')) not like '%builder%' "
                    "and lower(coalesce(industry,'')) not like '%electric%' "
                    "and lower(coalesce(industry,'')) not like '%lighting%' "
                    "and lower(coalesce(industry,'')) not like '%furniture%' "
                    "and lower(coalesce(industry,'')) not like '%property management%' "
                    "and lower(coalesce(industry,'')) not like '%hotel%' "
                    "and lower(coalesce(industry,'')) not like '%motels%' "
                    "and lower(coalesce(industry,'')) not like '%hospitality%' "
                    "and lower(coalesce(industry,'')) not like '%real estate%' "
                    "and lower(coalesce(industry,'')) not like '%brokerage%' "
                    "and lower(coalesce(industry,'')) not like '%cabinet%' "
                    "and lower(coalesce(industry,'')) not like '%kitchen%'"
                ).fetchone()[0],
                "sa_without_campaign_variant": con.execute(
                    "select count(*) from outreach_ready_leads l "
                    "where fit_tier in ('S','A') "
                    "and not exists ("
                    "  select 1 from campaign_variants cv "
                    "  where cv.segment_primary = l.segment_primary "
                    "    and cv.channel = 'email' "
                    "    and cv.active_flag"
                    ")"
                ).fetchone()[0],
            },
        }
        con.close()
        print(json.dumps(metrics, ensure_ascii=False))
        """
    )
    try:
        proc = subprocess.run(
            [str(duckdb_python), "-c", program, str(db_path)],
            capture_output=True,
            text=True,
            check=False,
            timeout=DEFAULT_TIMEOUT_SECONDS,
        )
    except subprocess.TimeoutExpired as exc:
        raise SystemExit(f"timed out collecting lead-engine metrics after {DEFAULT_TIMEOUT_SECONDS}s") from exc
    if proc.returncode != 0:
        raise SystemExit(_format_duckdb_error(proc.stdout, proc.stderr, db_path))
    stdout = proc.stdout.strip()
    if not stdout:
        raise SystemExit("DuckDB metrics command produced no JSON output")
    for line in reversed(stdout.splitlines()):
        candidate = line.strip()
        if candidate.startswith("{"):
            return json.loads(candidate)
    return json.loads(stdout)


def main() -> int:
    parser = argparse.ArgumentParser(description="Read the current NEOSGO lead-engine metrics snapshot.")
    parser.add_argument("--db", default=str(DEFAULT_DB_PATH), help="Path to neosgo_leads.duckdb")
    parser.add_argument("--python", dest="python_path", help="DuckDB-capable Python interpreter")
    parser.add_argument("--pretty", action="store_true", help="Pretty-print JSON output")
    args = parser.parse_args()

    duckdb_python = _choose_duckdb_python(args.python_path)
    metrics = _collect_metrics(duckdb_python, Path(args.db).expanduser())
    metrics["duckdb_python"] = str(duckdb_python)
    indent = 2 if args.pretty else None
    print(json.dumps(metrics, ensure_ascii=False, indent=indent))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
