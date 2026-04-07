#!/usr/bin/env python3

"""
中文说明：
- 文件路径：`tools/openmoss/control_center/promotion_gate.py`
- 文件作用：负责控制中心中与 `promotion_gate` 相关的编排、分析或决策逻辑。
- 顶层函数：_write_json、promote_capability、main。
- 顶层类：无顶层类。
- 阅读建议：先看模块说明，再按函数/类 docstring 顺着主流程理解调用关系。
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Dict

from paths import PROMOTED_CAPABILITIES_ROOT


def _write_json(path: Path, payload: object) -> None:
    """
    中文注解：
    - 功能：实现 `_write_json` 对应的处理逻辑。
    - 角色：属于本模块中的内部辅助逻辑；私有函数通常服务同文件主流程，公共函数通常作为跨模块入口或能力接口。
    - 调用关系：建议结合本文件的模块说明、调用方以及同名相关辅助函数一起阅读。
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def promote_capability(task_id: str, spec: Dict[str, object], rebuild: Dict[str, object], verification: Dict[str, object], optimization: Dict[str, object]) -> Dict[str, object]:
    """
    中文注解：
    - 功能：实现 `promote_capability` 对应的处理逻辑。
    - 角色：属于本模块中的对外可见逻辑；私有函数通常服务同文件主流程，公共函数通常作为跨模块入口或能力接口。
    - 调用关系：建议结合本文件的模块说明、调用方以及同名相关辅助函数一起阅读。
    """
    promoted = bool(verification.get("passed", False))
    payload = {
        "task_id": task_id,
        "capability_name": spec.get("capability_name", ""),
        "promoted": promoted,
        "rebuild_root": rebuild.get("root", ""),
        "verification": verification,
        "optimization": optimization,
        "status": "promoted" if promoted else "blocked",
    }
    _write_json(PROMOTED_CAPABILITIES_ROOT / f"{task_id}.json", payload)
    return payload


def main() -> int:
    """
    中文注解：
    - 功能：实现 `main` 对应的处理逻辑。
    - 角色：属于本模块中的对外可见逻辑；私有函数通常服务同文件主流程，公共函数通常作为跨模块入口或能力接口。
    - 调用关系：建议结合本文件的模块说明、调用方以及同名相关辅助函数一起阅读。
    """
    import argparse

    parser = argparse.ArgumentParser(description="Promote a verified local capability into the registry")
    parser.add_argument("--task-id", required=True)
    parser.add_argument("--spec-json", required=True)
    parser.add_argument("--rebuild-json", required=True)
    parser.add_argument("--verification-json", required=True)
    parser.add_argument("--optimization-json", required=True)
    args = parser.parse_args()
    print(
        json.dumps(
            promote_capability(
                args.task_id,
                json.loads(args.spec_json),
                json.loads(args.rebuild_json),
                json.loads(args.verification_json),
                json.loads(args.optimization_json),
            ),
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
