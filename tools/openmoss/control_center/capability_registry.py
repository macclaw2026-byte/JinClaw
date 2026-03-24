#!/usr/bin/env python3

from __future__ import annotations

import json
from pathlib import Path
from typing import Dict, List

from paths import GENERATED_CAPABILITIES_ROOT, PROMOTED_CAPABILITIES_ROOT, SKILLS_ROOT, TOOLS_ROOT, WORKSPACE_ROOT


def _safe_read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except OSError:
        return ""


def _detect_skill_tags(name: str, body: str) -> List[str]:
    normalized = f"{name}\n{body}".lower()
    tags = []
    rules = {
        "browser": ["browser", "page", "snapshot", "screenshot"],
        "research": ["research", "source", "web", "documentation", "search"],
        "security": ["security", "audit", "sensitive", "risk", "safe"],
        "recovery": ["recovery", "repair", "retry", "fallback"],
        "learning": ["learning", "retrofit", "evolution", "monitoring"],
        "data": ["data", "report", "json", "csv", "analysis"],
        "marketplace": ["amazon", "walmart", "marketplace", "product"],
    }
    for tag, needles in rules.items():
        if any(needle in normalized for needle in needles):
            tags.append(tag)
    return sorted(tags)


def _scan_skills() -> List[Dict[str, object]]:
    skills = []
    if not SKILLS_ROOT.exists():
        return skills
    for skill_dir in sorted(SKILLS_ROOT.iterdir()):
        if not skill_dir.is_dir():
            continue
        skill_file = skill_dir / "SKILL.md"
        if not skill_file.exists():
            continue
        body = _safe_read_text(skill_file)
        skills.append(
            {
                "name": skill_dir.name,
                "path": str(skill_file),
                "tags": _detect_skill_tags(skill_dir.name, body),
            }
        )
    return skills


def _scan_scripts() -> List[Dict[str, object]]:
    scripts = []
    if not SKILLS_ROOT.exists():
        return scripts
    for path in sorted(SKILLS_ROOT.glob("**/scripts/*")):
        if path.is_file():
            scripts.append(
                {
                    "name": path.name,
                    "path": str(path),
                    "parent_skill": path.parts[-3] if len(path.parts) >= 3 else "",
                }
            )
    return scripts


def _scan_tools() -> List[Dict[str, object]]:
    tools = []
    for candidate in [
        TOOLS_ROOT / "agent-browser-local",
        TOOLS_ROOT / "crawl4ai",
        TOOLS_ROOT / "openmoss",
    ]:
        tools.append(
            {
                "name": candidate.name,
                "path": str(candidate),
                "exists": candidate.exists(),
            }
        )
    return tools


def _scan_generated_capabilities() -> List[Dict[str, object]]:
    capabilities = []
    if not GENERATED_CAPABILITIES_ROOT.exists():
        return capabilities
    for candidate in sorted(GENERATED_CAPABILITIES_ROOT.iterdir()):
        manifest = candidate / "manifest.json"
        if candidate.is_dir() and manifest.exists():
            payload = json.loads(manifest.read_text(encoding="utf-8"))
            capabilities.append(
                {
                    "name": payload.get("capability_name", candidate.name),
                    "path": str(candidate),
                    "purpose": payload.get("purpose", ""),
                    "generated": True,
                }
            )
    return capabilities


def _scan_promoted_capabilities() -> List[Dict[str, object]]:
    promoted = []
    if not PROMOTED_CAPABILITIES_ROOT.exists():
        return promoted
    for path in sorted(PROMOTED_CAPABILITIES_ROOT.glob("*.json")):
        payload = json.loads(path.read_text(encoding="utf-8"))
        if payload.get("promoted"):
            promoted.append(
                {
                    "task_id": payload.get("task_id", ""),
                    "name": payload.get("capability_name", ""),
                    "status": payload.get("status", ""),
                    "rebuild_root": payload.get("rebuild_root", ""),
                }
            )
    return promoted


def build_capability_registry() -> Dict[str, object]:
    skills = _scan_skills()
    scripts = _scan_scripts()
    tools = _scan_tools()
    generated_capabilities = _scan_generated_capabilities()
    promoted_capabilities = _scan_promoted_capabilities()
    tags = sorted({tag for skill in skills for tag in skill.get("tags", [])} | ({"generated-capability"} if generated_capabilities else set()))
    return {
        "workspace_root": str(WORKSPACE_ROOT),
        "skills": skills,
        "scripts": scripts,
        "tools": tools,
        "generated_capabilities": generated_capabilities,
        "promoted_capabilities": promoted_capabilities,
        "skill_count": len(skills),
        "script_count": len(scripts),
        "tool_count": len(tools),
        "generated_capability_count": len(generated_capabilities),
        "promoted_capability_count": len(promoted_capabilities),
        "capability_tags": tags,
    }


def main() -> int:
    print(json.dumps(build_capability_registry(), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
