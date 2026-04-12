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
- 文件路径：`tools/openmoss/control_center/capability_distiller.py`
- 文件作用：负责控制中心中与 `capability_distiller` 相关的编排、分析或决策逻辑。
- 顶层函数：distill_capability_spec、main。
- 顶层类：无顶层类。
- 阅读建议：先看模块说明，再按函数/类 docstring 顺着主流程理解调用关系。
"""
from __future__ import annotations

import json
from typing import Dict


def distill_capability_spec(task_id: str, behavior_model: Dict[str, object]) -> Dict[str, object]:
    """
    中文注解：
    - 功能：实现 `distill_capability_spec` 对应的处理逻辑。
    - 角色：属于本模块中的对外可见逻辑；私有函数通常服务同文件主流程，公共函数通常作为跨模块入口或能力接口。
    - 调用关系：建议结合本文件的模块说明、调用方以及同名相关辅助函数一起阅读。
    """
    source_plan_id = str(behavior_model.get("source_plan_id", ""))
    capability_name = f"{task_id}-local-capability"
    return {
        "task_id": task_id,
        "capability_name": capability_name,
        "source_plan_id": source_plan_id,
        "purpose": "Replicate the useful external behavior locally with stronger safety, auditability, and verification.",
        "inputs": [
            "goal",
            "trusted_sources",
            "constraints",
        ],
        "outputs": [
            "verified_local_result",
            "structured_evidence",
            "safety_audit_log",
        ],
        "must_preserve": [
            "security boundaries",
            "verification-first execution",
            "rollback readiness",
        ],
        "must_improve": [
            "auditability",
            "local controllability",
            "token efficiency",
        ],
        "behavior_goals": behavior_model.get("behavior_goals", []),
        "challenge_model": behavior_model.get("challenge_model", {}),
        "trust_model": behavior_model.get("trust_model", {}),
    }


def main() -> int:
    """
    中文注解：
    - 功能：实现 `main` 对应的处理逻辑。
    - 角色：属于本模块中的对外可见逻辑；私有函数通常服务同文件主流程，公共函数通常作为跨模块入口或能力接口。
    - 调用关系：建议结合本文件的模块说明、调用方以及同名相关辅助函数一起阅读。
    """
    import argparse

    parser = argparse.ArgumentParser(description="Distill a local capability specification from an extracted behavior model")
    parser.add_argument("--task-id", required=True)
    parser.add_argument("--behavior-json", required=True)
    args = parser.parse_args()
    print(json.dumps(distill_capability_spec(args.task_id, json.loads(args.behavior_json)), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
