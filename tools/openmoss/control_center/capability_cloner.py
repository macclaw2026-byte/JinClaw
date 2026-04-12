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
- 文件路径：`tools/openmoss/control_center/capability_cloner.py`
- 文件作用：负责控制中心中与 `capability_cloner` 相关的编排、分析或决策逻辑。
- 顶层函数：_write_json、clone_capability、main。
- 顶层类：无顶层类。
- 阅读建议：先看模块说明，再按函数/类 docstring 顺着主流程理解调用关系。
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Dict

from behavior_extractor import extract_behavior_model
from capability_distiller import distill_capability_spec
from capability_optimizer import optimize_capability
from equivalence_verifier import verify_capability_equivalence
from local_rebuilder import rebuild_local_capability
from paths import CAPABILITY_CLONES_ROOT
from promotion_gate import promote_capability


def _write_json(path: Path, payload: object) -> None:
    """
    中文注解：
    - 功能：实现 `_write_json` 对应的处理逻辑。
    - 角色：属于本模块中的内部辅助逻辑；私有函数通常服务同文件主流程，公共函数通常作为跨模块入口或能力接口。
    - 调用关系：建议结合本文件的模块说明、调用方以及同名相关辅助函数一起阅读。
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def clone_capability(task_id: str, mission: Dict[str, object]) -> Dict[str, object]:
    """
    中文注解：
    - 功能：实现 `clone_capability` 对应的处理逻辑。
    - 角色：属于本模块中的对外可见逻辑；私有函数通常服务同文件主流程，公共函数通常作为跨模块入口或能力接口。
    - 调用关系：建议结合本文件的模块说明、调用方以及同名相关辅助函数一起阅读。
    """
    behavior = extract_behavior_model(task_id, mission)
    spec = distill_capability_spec(task_id, behavior)
    rebuild = rebuild_local_capability(task_id, spec)
    verification = verify_capability_equivalence(task_id, spec, rebuild)
    optimization = optimize_capability(task_id, spec, rebuild)
    promotion = promote_capability(task_id, spec, rebuild, verification, optimization)
    payload = {
        "task_id": task_id,
        "behavior_model": behavior,
        "spec": spec,
        "rebuild": rebuild,
        "verification": verification,
        "optimization": optimization,
        "promotion": promotion,
    }
    _write_json(CAPABILITY_CLONES_ROOT / f"{task_id}.json", payload)
    return payload


def main() -> int:
    """
    中文注解：
    - 功能：实现 `main` 对应的处理逻辑。
    - 角色：属于本模块中的对外可见逻辑；私有函数通常服务同文件主流程，公共函数通常作为跨模块入口或能力接口。
    - 调用关系：建议结合本文件的模块说明、调用方以及同名相关辅助函数一起阅读。
    """
    import argparse

    parser = argparse.ArgumentParser(description="Clone a useful external or hybrid capability into a stronger local one")
    parser.add_argument("--task-id", required=True)
    parser.add_argument("--mission-json", required=True)
    args = parser.parse_args()
    print(json.dumps(clone_capability(args.task_id, json.loads(args.mission_json)), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
