#!/usr/bin/env python3
# RULES-FIRST NOTICE:
# Before modifying this file, first read:
# - `JINCLAW_CONSTITUTION.md`
# - `AI_OPTIMIZATION_FRAMEWORK.md`
# Follow the constitution and framework:
# brain-first, one-doctor, fail-closed, evidence-over-narration,
# validate locally, then use the required PR workflow.
from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path
from typing import Any


LOCAL_DATA_PLATFORM_ROOT = Path(os.environ.get("LOCAL_DATA_PLATFORM_ROOT", "/Users/mac_claw/local-data-platform"))
LOCAL_DATA_PLATFORM_PYTHON = Path(
    os.environ.get(
        "LOCAL_DATA_PLATFORM_PYTHON",
        str(LOCAL_DATA_PLATFORM_ROOT / ".venv" / "bin" / "python"),
    )
)
LOCAL_DATA_PLATFORM_SYNC_SCRIPT = Path(
    os.environ.get(
        "LOCAL_DATA_PLATFORM_SYNC_SCRIPT",
        str(LOCAL_DATA_PLATFORM_ROOT / "scripts" / "openclaw_platform_sync.py"),
    )
)


def _bridge_available() -> bool:
    return LOCAL_DATA_PLATFORM_PYTHON.exists() and LOCAL_DATA_PLATFORM_SYNC_SCRIPT.exists()


def _run_sync(command: str, *, timeout: int = 600, **kwargs: Any) -> dict[str, Any]:
    if not _bridge_available():
        return {
            "ok": False,
            "status": "bridge_unavailable",
            "python": str(LOCAL_DATA_PLATFORM_PYTHON),
            "script": str(LOCAL_DATA_PLATFORM_SYNC_SCRIPT),
        }
    argv = [str(LOCAL_DATA_PLATFORM_PYTHON), str(LOCAL_DATA_PLATFORM_SYNC_SCRIPT), command]
    for key, value in kwargs.items():
        if value in (None, ""):
            continue
        argv.extend([f"--{key.replace('_', '-')}", str(value)])
    proc = subprocess.run(
        argv,
        capture_output=True,
        text=True,
        timeout=timeout,
        check=False,
        env=os.environ.copy(),
    )
    stdout = proc.stdout.strip()
    try:
        payload = json.loads(stdout) if stdout else {}
    except json.JSONDecodeError:
        payload = {"stdout": stdout}
    payload.setdefault("returncode", proc.returncode)
    if proc.stderr.strip():
        payload["stderr"] = proc.stderr.strip()
    return payload


def sync_crawler_site(*, workspace_root: Path, site: str) -> dict[str, Any]:
    return _run_sync("sync-crawler-site", workspace_root=str(workspace_root), site=site, timeout=300)


def sync_marketing_suite(*, project_root: Path) -> dict[str, Any]:
    return _run_sync("sync-marketing-suite", project_root=str(project_root), timeout=900)


def sync_seo_geo(*, project_root: Path) -> dict[str, Any]:
    return _run_sync("sync-seo-geo", project_root=str(project_root), timeout=900)


def migrate_openclaw_data(*, workspace_root: Path) -> dict[str, Any]:
    return _run_sync("migrate-all", workspace_root=str(workspace_root), timeout=1800)


def cleanup_openclaw_data(*, workspace_root: Path) -> dict[str, Any]:
    return _run_sync("cleanup-openclaw", workspace_root=str(workspace_root), timeout=1800)


def flush_local_data_platform_spool() -> dict[str, Any]:
    return _run_sync("flush-spool", timeout=1800)
