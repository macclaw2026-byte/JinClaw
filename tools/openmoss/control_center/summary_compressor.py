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
- 文件路径：`tools/openmoss/control_center/summary_compressor.py`
- 文件作用：负责控制中心中与 `summary_compressor` 相关的编排、分析或决策逻辑。
- 顶层函数：_utc_now_iso、_write_json、compress_mission、main。
- 顶层类：无顶层类。
- 阅读建议：先看模块说明，再按函数/类 docstring 顺着主流程理解调用关系。
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict

from paths import SUMMARIES_ROOT


def _utc_now_iso() -> str:
    """
    中文注解：
    - 功能：实现 `_utc_now_iso` 对应的处理逻辑。
    - 角色：属于本模块中的内部辅助逻辑；私有函数通常服务同文件主流程，公共函数通常作为跨模块入口或能力接口。
    - 调用关系：建议结合本文件的模块说明、调用方以及同名相关辅助函数一起阅读。
    """
    return datetime.now(timezone.utc).isoformat()


def _write_json(path: Path, payload) -> None:
    """
    中文注解：
    - 功能：实现 `_write_json` 对应的处理逻辑。
    - 角色：属于本模块中的内部辅助逻辑；私有函数通常服务同文件主流程，公共函数通常作为跨模块入口或能力接口。
    - 调用关系：建议结合本文件的模块说明、调用方以及同名相关辅助函数一起阅读。
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def compress_mission(task_id: str, mission: Dict[str, object], state: Dict[str, object]) -> Dict[str, object]:
    """
    中文注解：
    - 功能：实现 `compress_mission` 对应的处理逻辑。
    - 角色：属于本模块中的对外可见逻辑；私有函数通常服务同文件主流程，公共函数通常作为跨模块入口或能力接口。
    - 调用关系：建议结合本文件的模块说明、调用方以及同名相关辅助函数一起阅读。
    """
    intent = mission.get("intent", {})
    selected_plan = mission.get("selected_plan", {})
    approval = mission.get("approval", {})
    summary = {
        "task_id": task_id,
        "updated_at": _utc_now_iso(),
        "goal": intent.get("goal", ""),
        "task_types": intent.get("task_types", []),
        "selected_plan_id": selected_plan.get("plan_id", ""),
        "selected_plan_summary": selected_plan.get("summary", ""),
        "selected_plan_steps": selected_plan.get("steps", []),
        "pending_approvals": approval.get("pending", []),
        "approved_actions": approval.get("approved", []),
        "current_stage": state.get("current_stage", ""),
        "status": state.get("status", ""),
        "next_action": state.get("next_action", ""),
        "blockers": state.get("blockers", []),
    }
    _write_json(SUMMARIES_ROOT / f"{task_id}.json", summary)
    return summary


def main() -> int:
    """
    中文注解：
    - 功能：实现 `main` 对应的处理逻辑。
    - 角色：属于本模块中的对外可见逻辑；私有函数通常服务同文件主流程，公共函数通常作为跨模块入口或能力接口。
    - 调用关系：建议结合本文件的模块说明、调用方以及同名相关辅助函数一起阅读。
    """
    import argparse

    parser = argparse.ArgumentParser(description="Compress mission/state into a minimal control-center summary")
    parser.add_argument("--task-id", required=True)
    parser.add_argument("--mission-json", required=True)
    parser.add_argument("--state-json", required=True)
    args = parser.parse_args()
    print(json.dumps(compress_mission(args.task_id, json.loads(args.mission_json), json.loads(args.state_json)), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
