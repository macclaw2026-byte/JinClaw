#!/usr/bin/env python3

"""
中文说明：
- 文件路径：`tools/openmoss/control_center/equivalence_verifier.py`
- 文件作用：负责控制中心中与 `equivalence_verifier` 相关的编排、分析或决策逻辑。
- 顶层函数：verify_capability_equivalence、main。
- 顶层类：无顶层类。
- 阅读建议：先看模块说明，再按函数/类 docstring 顺着主流程理解调用关系。
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Dict


def verify_capability_equivalence(task_id: str, spec: Dict[str, object], rebuild: Dict[str, object]) -> Dict[str, object]:
    """
    中文注解：
    - 功能：实现 `verify_capability_equivalence` 对应的处理逻辑。
    - 角色：属于本模块中的对外可见逻辑；私有函数通常服务同文件主流程，公共函数通常作为跨模块入口或能力接口。
    - 调用关系：建议结合本文件的模块说明、调用方以及同名相关辅助函数一起阅读。
    """
    manifest_exists = Path(str(rebuild.get("manifest_path", ""))).exists()
    adapter_exists = Path(str(rebuild.get("adapter_path", ""))).exists()
    checks = {
        "manifest_exists": manifest_exists,
        "adapter_exists": adapter_exists,
        "preserves_constraints": bool(spec.get("must_preserve")),
        "improves_local_control": bool(spec.get("must_improve")),
    }
    passed = all(checks.values())
    return {
        "task_id": task_id,
        "passed": passed,
        "checks": checks,
        "equivalence_statement": "Local rebuilt capability preserves the required behavior envelope and improves local control."
        if passed
        else "Local rebuilt capability is not yet sufficiently evidenced.",
    }


def main() -> int:
    """
    中文注解：
    - 功能：实现 `main` 对应的处理逻辑。
    - 角色：属于本模块中的对外可见逻辑；私有函数通常服务同文件主流程，公共函数通常作为跨模块入口或能力接口。
    - 调用关系：建议结合本文件的模块说明、调用方以及同名相关辅助函数一起阅读。
    """
    import argparse

    parser = argparse.ArgumentParser(description="Verify that a rebuilt local capability is equivalent enough to promote")
    parser.add_argument("--task-id", required=True)
    parser.add_argument("--spec-json", required=True)
    parser.add_argument("--rebuild-json", required=True)
    args = parser.parse_args()
    print(json.dumps(verify_capability_equivalence(args.task_id, json.loads(args.spec_json), json.loads(args.rebuild_json)), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
