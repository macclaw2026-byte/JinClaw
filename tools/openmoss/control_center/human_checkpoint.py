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
- 文件路径：`tools/openmoss/control_center/human_checkpoint.py`
- 文件作用：负责控制中心中与 `human_checkpoint` 相关的编排、分析或决策逻辑。
- 顶层函数：_write_json、build_human_checkpoint、main。
- 顶层类：无顶层类。
- 阅读建议：先看模块说明，再按函数/类 docstring 顺着主流程理解调用关系。
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Dict

from paths import HUMAN_CHECKPOINTS_ROOT


def _write_json(path: Path, payload: object) -> None:
    """
    中文注解：
    - 功能：实现 `_write_json` 对应的处理逻辑。
    - 角色：属于本模块中的内部辅助逻辑；私有函数通常服务同文件主流程，公共函数通常作为跨模块入口或能力接口。
    - 调用关系：建议结合本文件的模块说明、调用方以及同名相关辅助函数一起阅读。
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def build_human_checkpoint(task_id: str, challenge: Dict[str, object]) -> Dict[str, object]:
    """
    中文注解：
    - 功能：实现 `build_human_checkpoint` 对应的处理逻辑。
    - 角色：属于本模块中的对外可见逻辑；私有函数通常服务同文件主流程，公共函数通常作为跨模块入口或能力接口。
    - 调用关系：建议结合本文件的模块说明、调用方以及同名相关辅助函数一起阅读。
    """
    needed = challenge.get("recommended_route") == "human_checkpoint" or challenge.get("challenge_type") == "human_verification_required"
    payload = {
        "task_id": task_id,
        "required": needed,
        "governance_type": "human_checkpoint",
        "risk": "medium" if needed else "low",
        "checkpoint_reason": challenge.get("challenge_type", "none"),
        "resume_condition": "human verification completed and execution can safely resume" if needed else "not_required",
        "instructions": [
            "Pause automated progression at the checkpoint.",
            "Let a human complete the verification or challenge step.",
            "Resume the task from the verified page or post-checkpoint state only.",
        ] if needed else [],
    }
    _write_json(HUMAN_CHECKPOINTS_ROOT / f"{task_id}.json", payload)
    return payload


def main() -> int:
    """
    中文注解：
    - 功能：实现 `main` 对应的处理逻辑。
    - 角色：属于本模块中的对外可见逻辑；私有函数通常服务同文件主流程，公共函数通常作为跨模块入口或能力接口。
    - 调用关系：建议结合本文件的模块说明、调用方以及同名相关辅助函数一起阅读。
    """
    import argparse

    parser = argparse.ArgumentParser(description="Create a human checkpoint for challenge-gated tasks")
    parser.add_argument("--task-id", required=True)
    parser.add_argument("--challenge-json", required=True)
    args = parser.parse_args()
    print(json.dumps(build_human_checkpoint(args.task_id, json.loads(args.challenge_json)), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
