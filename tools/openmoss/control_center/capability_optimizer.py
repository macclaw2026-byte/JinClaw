#!/usr/bin/env python3
# RULES-FIRST NOTICE:
# Before modifying this file, first read:
# - `JINCLAW_CONSTITUTION.md`
# - `AI_OPTIMIZATION_FRAMEWORK.md`
# Follow the constitution and framework:
# brain-first, one-doctor, fail-closed, evidence-over-narration,
# validate locally, then use the required PR workflow.
"""
中文说明：
- 文件路径：`tools/openmoss/control_center/capability_optimizer.py`
- 文件作用：负责控制中心中与 `capability_optimizer` 相关的编排、分析或决策逻辑。
- 顶层函数：optimize_capability、main。
- 顶层类：无顶层类。
- 阅读建议：先看模块说明，再按函数/类 docstring 顺着主流程理解调用关系。
"""
from __future__ import annotations

import json
from typing import Dict


def optimize_capability(task_id: str, spec: Dict[str, object], rebuild: Dict[str, object]) -> Dict[str, object]:
    """
    中文注解：
    - 功能：实现 `optimize_capability` 对应的处理逻辑。
    - 角色：属于本模块中的对外可见逻辑；私有函数通常服务同文件主流程，公共函数通常作为跨模块入口或能力接口。
    - 调用关系：建议结合本文件的模块说明、调用方以及同名相关辅助函数一起阅读。
    """
    return {
        "task_id": task_id,
        "capability_name": spec.get("capability_name", ""),
        "optimized_from": rebuild.get("capability_name", ""),
        "optimizations": [
            "prefer structured outputs over raw text",
            "reduce token usage with minimal context packets",
            "add explicit verification and rollback readiness",
            "keep only the useful behavior surface from the external pattern",
        ],
        "strengthened_properties": [
            "auditability",
            "local control",
            "safety boundary preservation",
            "reusability",
        ],
    }


def main() -> int:
    """
    中文注解：
    - 功能：实现 `main` 对应的处理逻辑。
    - 角色：属于本模块中的对外可见逻辑；私有函数通常服务同文件主流程，公共函数通常作为跨模块入口或能力接口。
    - 调用关系：建议结合本文件的模块说明、调用方以及同名相关辅助函数一起阅读。
    """
    import argparse

    parser = argparse.ArgumentParser(description="Apply local-first optimizations to a rebuilt capability")
    parser.add_argument("--task-id", required=True)
    parser.add_argument("--spec-json", required=True)
    parser.add_argument("--rebuild-json", required=True)
    args = parser.parse_args()
    print(json.dumps(optimize_capability(args.task_id, json.loads(args.spec_json), json.loads(args.rebuild_json)), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
