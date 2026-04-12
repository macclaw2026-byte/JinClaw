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
- 文件路径：`tools/openmoss/control_center/authorized_session_manager.py`
- 文件作用：负责控制中心中与 `authorized_session_manager` 相关的编排、分析或决策逻辑。
- 顶层函数：_write_json、build_authorized_session_plan、main。
- 顶层类：无顶层类。
- 阅读建议：先看模块说明，再按函数/类 docstring 顺着主流程理解调用关系。
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Dict

from paths import AUTHORIZED_SESSIONS_ROOT


def _write_json(path: Path, payload: object) -> None:
    """
    中文注解：
    - 功能：实现 `_write_json` 对应的处理逻辑。
    - 角色：属于本模块中的内部辅助逻辑；私有函数通常服务同文件主流程，公共函数通常作为跨模块入口或能力接口。
    - 调用关系：建议结合本文件的模块说明、调用方以及同名相关辅助函数一起阅读。
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def build_authorized_session_plan(task_id: str, intent: Dict[str, object], challenge: Dict[str, object]) -> Dict[str, object]:
    """
    中文注解：
    - 功能：实现 `build_authorized_session_plan` 对应的处理逻辑。
    - 角色：属于本模块中的对外可见逻辑；私有函数通常服务同文件主流程，公共函数通常作为跨模块入口或能力接口。
    - 调用关系：建议结合本文件的模块说明、调用方以及同名相关辅助函数一起阅读。
    """
    needs_authorized_session = challenge.get("recommended_route") == "authorized_session" or challenge.get("challenge_type") in {
        "authorization_required",
        "waf_or_access_block",
    }
    payload = {
        "task_id": task_id,
        "needs_authorized_session": needs_authorized_session,
        "approval_required": needs_authorized_session,
        "governance_type": "authorized_session",
        "risk": "high" if needs_authorized_session else "low",
        "session_mode": "isolated_reviewed_context" if needs_authorized_session else "not_required",
        "rules": [
            "Never reuse broad browser auth state without explicit approval.",
            "Use an isolated reviewed context for any authorized session.",
            "Do not persist credentials into general workspace outputs.",
        ],
        "triggers": {
            "challenge_type": challenge.get("challenge_type", "none"),
            "needs_browser": bool(intent.get("needs_browser")),
        },
    }
    _write_json(AUTHORIZED_SESSIONS_ROOT / f"{task_id}.json", payload)
    return payload


def main() -> int:
    """
    中文注解：
    - 功能：实现 `main` 对应的处理逻辑。
    - 角色：属于本模块中的对外可见逻辑；私有函数通常服务同文件主流程，公共函数通常作为跨模块入口或能力接口。
    - 调用关系：建议结合本文件的模块说明、调用方以及同名相关辅助函数一起阅读。
    """
    import argparse

    parser = argparse.ArgumentParser(description="Build an authorized-session handling plan")
    parser.add_argument("--task-id", required=True)
    parser.add_argument("--intent-json", required=True)
    parser.add_argument("--challenge-json", required=True)
    args = parser.parse_args()
    print(
        json.dumps(
            build_authorized_session_plan(args.task_id, json.loads(args.intent_json), json.loads(args.challenge_json)),
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
