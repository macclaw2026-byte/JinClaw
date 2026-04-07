#!/usr/bin/env python3

from __future__ import annotations

import argparse
import json
import subprocess
from pathlib import Path


PROTECTED_BRANCHES = {"main", "master"}


def _git(repo_root: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", "-C", str(repo_root), *args],
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout.strip()


def _status_entries(repo_root: Path) -> list[dict]:
    lines = _git(repo_root, "status", "--porcelain").splitlines()
    entries = []
    for line in lines:
        if not line.strip():
            continue
        status = line[:2]
        path = line[3:]
        entries.append({"status": status, "path": path})
    return entries


def main() -> int:
    parser = argparse.ArgumentParser(description="Check whether a scoped PR can be prepared cleanly.")
    parser.add_argument("--repo-root", required=True)
    parser.add_argument("--allow-prefix", action="append", default=[])
    args = parser.parse_args()

    repo_root = Path(args.repo_root).expanduser().resolve()
    branch = _git(repo_root, "branch", "--show-current")
    remotes = _git(repo_root, "remote", "-v")
    entries = _status_entries(repo_root)
    allow_prefixes = [prefix.rstrip("/") for prefix in args.allow_prefix]

    outside_scope = []
    inside_scope = []
    for entry in entries:
        path = entry["path"]
        if allow_prefixes and any(path == prefix or path.startswith(prefix + "/") for prefix in allow_prefixes):
            inside_scope.append(entry)
        elif allow_prefixes:
            outside_scope.append(entry)
        else:
            inside_scope.append(entry)

    blockers = []
    warnings = []
    if branch in PROTECTED_BRANCHES:
        blockers.append("protected_branch_checked_out")
    if not remotes:
        blockers.append("missing_git_remote")
    if allow_prefixes and outside_scope:
        blockers.append("worktree_has_out_of_scope_changes")
    if not entries:
        warnings.append("worktree_clean_nothing_to_pr")

    payload = {
        "status": "ready" if not blockers else "blocked",
        "repo_root": str(repo_root),
        "branch": branch,
        "allow_prefixes": allow_prefixes,
        "changed_file_count": len(entries),
        "inside_scope_count": len(inside_scope),
        "outside_scope_count": len(outside_scope),
        "blockers": blockers,
        "warnings": warnings,
        "outside_scope_sample": outside_scope[:20],
        "inside_scope_sample": inside_scope[:20],
    }
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0 if not blockers else 2


if __name__ == "__main__":
    raise SystemExit(main())
