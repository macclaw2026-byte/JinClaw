#!/usr/bin/env python3

from __future__ import annotations

import argparse
import json
from pathlib import Path


OPENCLAW_DIST_ROOT = Path("/opt/homebrew/lib/node_modules/openclaw/dist")
TARGET_PATTERNS = (
    "reply-*.js",
    "plugin-sdk/thread-bindings-*.js",
)

REPLACEMENTS = (
    (
        "typeof entry.totalTokens === \"number\" ? entry.totalTokens : void 0",
        "typeof entry?.totalTokens === \"number\" ? entry.totalTokens : void 0",
    ),
    (
        "if (typeof entry.totalTokens === \"number\" && Number.isFinite(entry.totalTokens)) return entry.totalTokens;",
        "if (typeof entry?.totalTokens === \"number\" && Number.isFinite(entry.totalTokens)) return entry.totalTokens;",
    ),
)


def patch_file(path: Path, *, dry_run: bool = False) -> dict:
    original = path.read_text(encoding="utf-8")
    patched = original
    changes = []
    for old, new in REPLACEMENTS:
        count = patched.count(old)
        if count > 0:
            patched = patched.replace(old, new)
            changes.append({"from": old, "to": new, "count": count})
    if not changes:
        return {"path": str(path), "patched": False, "changes": []}
    if not dry_run:
        path.write_text(patched, encoding="utf-8")
    return {"path": str(path), "patched": True, "changes": changes}


def apply_patches(*, dry_run: bool = False) -> dict:
    results = []
    for pattern in TARGET_PATTERNS:
        for path in sorted(OPENCLAW_DIST_ROOT.glob(pattern)):
            results.append(patch_file(path, dry_run=dry_run))
    return {
        "root": str(OPENCLAW_DIST_ROOT),
        "dry_run": dry_run,
        "results": results,
        "patched_files": [item["path"] for item in results if item.get("patched")],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Apply local OpenClaw compatibility hotfixes used by JinClaw")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    print(json.dumps(apply_patches(dry_run=args.dry_run), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
