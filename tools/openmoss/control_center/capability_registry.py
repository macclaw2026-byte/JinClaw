#!/usr/bin/env python3

"""
中文说明：
- 文件路径：`tools/openmoss/control_center/capability_registry.py`
- 文件作用：负责控制中心中与 `capability_registry` 相关的编排、分析或决策逻辑。
- 顶层函数：_safe_read_text、_detect_skill_tags、_scan_skills、_scan_scripts、_scan_tools、_scan_generated_capabilities、_scan_promoted_capabilities、build_capability_registry、main。
- 顶层类：无顶层类。
- 阅读建议：先看模块说明，再按函数/类 docstring 顺着主流程理解调用关系。
"""
from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Dict, List

from paths import GENERATED_CAPABILITIES_ROOT, PROMOTED_CAPABILITIES_ROOT, SKILLS_ROOT, TOOLS_ROOT, WORKSPACE_ROOT


def _safe_read_text(path: Path) -> str:
    """
    中文注解：
    - 功能：实现 `_safe_read_text` 对应的处理逻辑。
    - 角色：属于本模块中的内部辅助逻辑；私有函数通常服务同文件主流程，公共函数通常作为跨模块入口或能力接口。
    - 调用关系：建议结合本文件的模块说明、调用方以及同名相关辅助函数一起阅读。
    """
    try:
        return path.read_text(encoding="utf-8")
    except OSError:
        return ""


def _detect_skill_tags(name: str, body: str) -> List[str]:
    """
    中文注解：
    - 功能：实现 `_detect_skill_tags` 对应的处理逻辑。
    - 角色：属于本模块中的内部辅助逻辑；私有函数通常服务同文件主流程，公共函数通常作为跨模块入口或能力接口。
    - 调用关系：建议结合本文件的模块说明、调用方以及同名相关辅助函数一起阅读。
    """
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
    """
    中文注解：
    - 功能：实现 `_scan_skills` 对应的处理逻辑。
    - 角色：属于本模块中的内部辅助逻辑；私有函数通常服务同文件主流程，公共函数通常作为跨模块入口或能力接口。
    - 调用关系：建议结合本文件的模块说明、调用方以及同名相关辅助函数一起阅读。
    """
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
    """
    中文注解：
    - 功能：实现 `_scan_scripts` 对应的处理逻辑。
    - 角色：属于本模块中的内部辅助逻辑；私有函数通常服务同文件主流程，公共函数通常作为跨模块入口或能力接口。
    - 调用关系：建议结合本文件的模块说明、调用方以及同名相关辅助函数一起阅读。
    """
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
    """
    中文注解：
    - 功能：实现 `_scan_tools` 对应的处理逻辑。
    - 角色：属于本模块中的内部辅助逻辑；私有函数通常服务同文件主流程，公共函数通常作为跨模块入口或能力接口。
    - 调用关系：建议结合本文件的模块说明、调用方以及同名相关辅助函数一起阅读。
    """
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
    for binary, aliases in {
        "python": ["scrapy"],
        "node": ["crawlee"],
    }.items():
        tools.append(
            {
                "name": binary,
                "path": shutil.which(binary) or "",
                "exists": bool(shutil.which(binary)),
                "provides": aliases,
            }
        )
    for package_name in ["curl_cffi", "playwright", "playwright_stealth", "httpx", "selectolax"]:
        try:
            __import__(package_name)
            exists = True
        except Exception:
            exists = False
        tools.append(
            {
                "name": package_name,
                "path": package_name,
                "exists": exists,
                "kind": "python_package",
            }
        )
    return tools


def _scan_generated_capabilities() -> List[Dict[str, object]]:
    """
    中文注解：
    - 功能：实现 `_scan_generated_capabilities` 对应的处理逻辑。
    - 角色：属于本模块中的内部辅助逻辑；私有函数通常服务同文件主流程，公共函数通常作为跨模块入口或能力接口。
    - 调用关系：建议结合本文件的模块说明、调用方以及同名相关辅助函数一起阅读。
    """
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
    """
    中文注解：
    - 功能：实现 `_scan_promoted_capabilities` 对应的处理逻辑。
    - 角色：属于本模块中的内部辅助逻辑；私有函数通常服务同文件主流程，公共函数通常作为跨模块入口或能力接口。
    - 调用关系：建议结合本文件的模块说明、调用方以及同名相关辅助函数一起阅读。
    """
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
    """
    中文注解：
    - 功能：实现 `build_capability_registry` 对应的处理逻辑。
    - 角色：属于本模块中的对外可见逻辑；私有函数通常服务同文件主流程，公共函数通常作为跨模块入口或能力接口。
    - 调用关系：建议结合本文件的模块说明、调用方以及同名相关辅助函数一起阅读。
    """
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
    """
    中文注解：
    - 功能：实现 `main` 对应的处理逻辑。
    - 角色：属于本模块中的对外可见逻辑；私有函数通常服务同文件主流程，公共函数通常作为跨模块入口或能力接口。
    - 调用关系：建议结合本文件的模块说明、调用方以及同名相关辅助函数一起阅读。
    """
    print(json.dumps(build_capability_registry(), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
