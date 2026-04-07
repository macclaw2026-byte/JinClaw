#!/usr/bin/env python3

"""
中文说明：
- 文件路径：`tools/openmoss/ops/apply_openclaw_compat_patches.py`
- 文件作用：负责运维脚本中与 `apply_openclaw_compat_patches` 相关的诊断、启动或修复逻辑。
- 顶层函数：patch_file、apply_patches、main。
- 顶层类：无顶层类。
- 阅读建议：先看模块说明，再按函数/类 docstring 顺着主流程理解调用关系。
"""
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
    """
    中文注解：
    - 功能：实现 `patch_file` 对应的处理逻辑。
    - 角色：属于本模块中的对外可见逻辑；私有函数通常服务同文件主流程，公共函数通常作为跨模块入口或能力接口。
    - 调用关系：建议结合本文件的模块说明、调用方以及同名相关辅助函数一起阅读。
    """
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
    """
    中文注解：
    - 功能：实现 `apply_patches` 对应的处理逻辑。
    - 角色：属于本模块中的对外可见逻辑；私有函数通常服务同文件主流程，公共函数通常作为跨模块入口或能力接口。
    - 调用关系：建议结合本文件的模块说明、调用方以及同名相关辅助函数一起阅读。
    """
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
    """
    中文注解：
    - 功能：实现 `main` 对应的处理逻辑。
    - 角色：属于本模块中的对外可见逻辑；私有函数通常服务同文件主流程，公共函数通常作为跨模块入口或能力接口。
    - 调用关系：建议结合本文件的模块说明、调用方以及同名相关辅助函数一起阅读。
    """
    parser = argparse.ArgumentParser(description="Apply local OpenClaw compatibility hotfixes used by JinClaw")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    print(json.dumps(apply_patches(dry_run=args.dry_run), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
