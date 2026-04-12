#!/usr/bin/env python3
# RULES-FIRST NOTICE:
# Before modifying this file, first read:
# - `JINCLAW_CONSTITUTION.md`
# - `AI_OPTIMIZATION_FRAMEWORK.md`
# Follow the constitution and framework:
# brain-first, one-doctor, fail-closed, evidence-over-narration,
# validate locally, then use the required PR workflow.

from __future__ import annotations

from pathlib import Path
import sys

WORKSPACE_ROOT = Path(__file__).resolve().parents[3]
CHECK_ROOTS = [
    WORKSPACE_ROOT / "tools" / "openmoss",
    WORKSPACE_ROOT / "projects",
]
REQUIRED_DOCS = [
    WORKSPACE_ROOT / "JINCLAW_CONSTITUTION.md",
    WORKSPACE_ROOT / "AI_OPTIMIZATION_FRAMEWORK.md",
]
REQUIRED_DIRECTORY_NOTICES = [
    WORKSPACE_ROOT / "projects" / "RULES_FIRST_NOTICE.md",
    WORKSPACE_ROOT / "projects" / "amazon-product-selection-engine" / "RULES_FIRST_NOTICE.md",
    WORKSPACE_ROOT / "projects" / "jinclaw-governance" / "RULES_FIRST_NOTICE.md",
    WORKSPACE_ROOT / "projects" / "ma-data-workbench" / "RULES_FIRST_NOTICE.md",
    WORKSPACE_ROOT / "projects" / "marketing-automation-demo" / "RULES_FIRST_NOTICE.md",
    WORKSPACE_ROOT / "projects" / "neosgo-growth-engine" / "RULES_FIRST_NOTICE.md",
    WORKSPACE_ROOT / "projects" / "neosgo-marketing-suite" / "RULES_FIRST_NOTICE.md",
    WORKSPACE_ROOT / "projects" / "neosgo-seller-maintenance" / "RULES_FIRST_NOTICE.md",
    WORKSPACE_ROOT / "projects" / "neosgo-seo-geo-engine" / "RULES_FIRST_NOTICE.md",
    WORKSPACE_ROOT / "projects" / "openmoss-openclaw-integration" / "RULES_FIRST_NOTICE.md",
    WORKSPACE_ROOT / "tools" / "openmoss" / "runtime" / "RULES_FIRST_NOTICE.md",
    WORKSPACE_ROOT / "tools" / "openmoss" / "runtime" / "control_center" / "RULES_FIRST_NOTICE.md",
    WORKSPACE_ROOT / "tools" / "openmoss" / "runtime" / "control_center" / "doctor" / "RULES_FIRST_NOTICE.md",
    WORKSPACE_ROOT / "tools" / "openmoss" / "runtime" / "autonomy" / "RULES_FIRST_NOTICE.md",
    WORKSPACE_ROOT / "tools" / "openmoss" / "runtime" / "autonomy" / "tasks" / "RULES_FIRST_NOTICE.md",
    WORKSPACE_ROOT / "tools" / "openmoss" / "runtime" / "autonomy" / "archive" / "RULES_FIRST_NOTICE.md",
]
TARGET_SUFFIXES = {".py", ".sh", ".md"}
NOTICE_MARKER = "RULES-FIRST NOTICE:"
IGNORED_PREFIXES = [
    WORKSPACE_ROOT / "tools" / "openmoss" / "generated_capabilities",
    WORKSPACE_ROOT / "tools" / "openmoss" / "runtime",
]


def _iter_target_files() -> list[Path]:
    items: list[Path] = []
    seen: set[Path] = set()
    for root in CHECK_ROOTS:
        for path in sorted(root.rglob("*")):
            if not path.is_file():
                continue
            if path in seen:
                continue
            if any(part.startswith(".") for part in path.relative_to(root).parts):
                continue
            if path.suffix.lower() not in TARGET_SUFFIXES:
                continue
            if any(path.is_relative_to(prefix) for prefix in IGNORED_PREFIXES):
                continue
            seen.add(path)
            items.append(path)
    return items


def main() -> int:
    errors: list[str] = []
    for path in REQUIRED_DOCS:
        if not path.exists():
            errors.append(f"missing_required_doc:{path.relative_to(WORKSPACE_ROOT)}")
    for path in REQUIRED_DIRECTORY_NOTICES:
        if not path.exists():
            errors.append(f"missing_directory_notice:{path.relative_to(WORKSPACE_ROOT)}")
    for path in _iter_target_files():
        try:
            text = path.read_text(encoding="utf-8")
        except OSError:
            errors.append(f"unreadable_file:{path.relative_to(WORKSPACE_ROOT)}")
            continue
        top_slice = "\n".join(text.splitlines()[:12])
        if NOTICE_MARKER not in top_slice:
            errors.append(f"missing_rules_notice:{path.relative_to(WORKSPACE_ROOT)}")
    if errors:
        print("rules_first_notice_check:FAIL")
        for item in errors:
            print(item)
        return 1
    print("rules_first_notice_check:OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
