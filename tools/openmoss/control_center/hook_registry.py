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
- 文件路径：`tools/openmoss/control_center/hook_registry.py`
- 文件作用：负责控制中心中与 `hook_registry` 相关的编排、分析或决策逻辑。
- 顶层函数：_write_json、get_registered_hooks、main。
- 顶层类：无顶层类。
- 阅读建议：先看模块说明，再按函数/类 docstring 顺着主流程理解调用关系。
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Dict, List

from paths import HOOKS_ROOT


def _hook(
    name: str,
    *,
    phase: str,
    priority: int = 100,
    blocking: bool = False,
    idempotent: bool = True,
    retryable: bool = True,
    timeout_ms: int = 1500,
    failure_policy: str = "record_and_continue",
    required_inputs: list[str] | None = None,
    emits: list[str] | None = None,
    memory_targets: list[str] | None = None,
    memory_reason: str = "",
) -> Dict[str, object]:
    return {
        "name": name,
        "phase": phase,
        "priority": priority,
        "blocking": blocking,
        "idempotent": idempotent,
        "retryable": retryable,
        "timeout_ms": timeout_ms,
        "failure_policy": failure_policy,
        "required_inputs": required_inputs or ["task_id"],
        "emits": emits or [],
        "memory_targets": memory_targets or [],
        "memory_reason": str(memory_reason or ""),
    }


DEFAULT_HOOKS: Dict[str, List[Dict[str, object]]] = {
    "mission.built": [
        _hook("evaluate_clone_need", phase="pre_decision", emits=["capability.clone_requested"], memory_targets=["task"], memory_reason="mission_decision_review"),
    ],
    "plan.reselected": [
        _hook("audit_plan_switch", phase="pre_decision", emits=["plan.audit_recorded"], memory_targets=["task"], memory_reason="plan_switch_audit"),
    ],
    "challenge.detected": [
        _hook("route_challenge_response", phase="recovery", blocking=True, emits=["challenge.route_selected"], memory_targets=["runtime", "task"], memory_reason="challenge_route_selected"),
    ],
    "capability.clone_requested": [
        _hook("run_capability_clone_pipeline", phase="post_execute", blocking=True, timeout_ms=5000, emits=["capability.clone_verified"], memory_targets=["project", "task"], memory_reason="capability_clone_pipeline"),
    ],
    "capability.clone_verified": [
        _hook("promote_cloned_capability", phase="post_execute", emits=["capability.promoted"], memory_targets=["project"], memory_reason="capability_promoted"),
    ],
    "stage.understand.entered": [
        _hook("refresh_task_memory_snapshot", phase="pre_execute", emits=["memory.snapshot_refreshed"], memory_targets=["runtime", "task"], memory_reason="stage_memory_refresh"),
    ],
    "stage.plan.entered": [
        _hook("refresh_task_memory_snapshot", phase="pre_execute", emits=["memory.snapshot_refreshed"], memory_targets=["runtime", "task"], memory_reason="stage_memory_refresh"),
        _hook("audit_plan_switch", phase="pre_decision", emits=["plan.audit_recorded"], memory_targets=["task"], memory_reason="plan_switch_audit"),
    ],
    "stage.execute.entered": [
        _hook("refresh_task_memory_snapshot", phase="pre_execute", emits=["memory.snapshot_refreshed"], memory_targets=["runtime", "task"], memory_reason="stage_memory_refresh"),
        _hook("verify_execution_policy_handoff", phase="pre_execute", blocking=True, emits=["policy.handoff_verified"], memory_targets=["runtime"], memory_reason="execution_policy_handoff"),
    ],
    "stage.verify.entered": [
        _hook("refresh_task_memory_snapshot", phase="pre_execute", emits=["memory.snapshot_refreshed"], memory_targets=["runtime", "task"], memory_reason="stage_memory_refresh"),
        _hook("verify_execution_policy_handoff", phase="pre_execute", blocking=True, emits=["policy.handoff_verified"], memory_targets=["runtime"], memory_reason="execution_policy_handoff"),
    ],
    "stage.learn.entered": [
        _hook("refresh_task_memory_snapshot", phase="post_execute", emits=["memory.snapshot_refreshed"], memory_targets=["task"], memory_reason="post_stage_memory_refresh"),
    ],
    "stage.execute.pre_execute": [
        _hook("refresh_task_memory_snapshot", phase="pre_execute", emits=["memory.snapshot_refreshed"], memory_targets=["runtime", "task"], memory_reason="stage_memory_refresh"),
        _hook("verify_execution_policy_handoff", phase="pre_execute", blocking=True, emits=["policy.handoff_verified"], memory_targets=["runtime"], memory_reason="execution_policy_handoff"),
    ],
    "stage.verify.pre_execute": [
        _hook("refresh_task_memory_snapshot", phase="pre_execute", emits=["memory.snapshot_refreshed"], memory_targets=["runtime", "task"], memory_reason="stage_memory_refresh"),
        _hook("verify_execution_policy_handoff", phase="pre_execute", blocking=True, emits=["policy.handoff_verified"], memory_targets=["runtime"], memory_reason="execution_policy_handoff"),
    ],
    "stage.execute.waiting": [
        _hook("monitor_liveness_and_retry_path", phase="recovery", emits=["runtime.retry_path_reviewed"], memory_targets=["runtime"], memory_reason="liveness_retry_review"),
    ],
    "recovery.requested": [
        _hook("monitor_liveness_and_retry_path", phase="recovery", blocking=True, emits=["runtime.recovery_reviewed"], memory_targets=["runtime"], memory_reason="liveness_retry_review"),
        _hook("refresh_task_memory_snapshot", phase="recovery", emits=["memory.snapshot_refreshed"], memory_targets=["runtime", "task"], memory_reason="recovery_memory_refresh"),
    ],
    "doctor.escalation": [
        _hook("refresh_task_memory_snapshot", phase="recovery", emits=["memory.snapshot_refreshed"], memory_targets=["runtime", "task"], memory_reason="doctor_memory_refresh"),
        _hook("monitor_liveness_and_retry_path", phase="recovery", emits=["runtime.retry_path_reviewed"], memory_targets=["runtime"], memory_reason="doctor_retry_review"),
    ],
}


def _write_json(path: Path, payload: object) -> None:
    """
    中文注解：
    - 功能：实现 `_write_json` 对应的处理逻辑。
    - 角色：属于本模块中的内部辅助逻辑；私有函数通常服务同文件主流程，公共函数通常作为跨模块入口或能力接口。
    - 调用关系：建议结合本文件的模块说明、调用方以及同名相关辅助函数一起阅读。
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def get_registered_hooks(event_type: str) -> Dict[str, object]:
    """
    中文注解：
    - 功能：实现 `get_registered_hooks` 对应的处理逻辑。
    - 角色：属于本模块中的对外可见逻辑；私有函数通常服务同文件主流程，公共函数通常作为跨模块入口或能力接口。
    - 调用关系：建议结合本文件的模块说明、调用方以及同名相关辅助函数一起阅读。
    """
    hook_specs = DEFAULT_HOOKS.get(event_type, [])
    payload = {
        "event_type": event_type,
        "hooks": [str(item.get("name", "")) for item in hook_specs if str(item.get("name", "")).strip()],
        "hook_specs": hook_specs,
    }
    _write_json(HOOKS_ROOT / f"{event_type.replace('.', '_')}.json", payload)
    return payload


def main() -> int:
    """
    中文注解：
    - 功能：实现 `main` 对应的处理逻辑。
    - 角色：属于本模块中的对外可见逻辑；私有函数通常服务同文件主流程，公共函数通常作为跨模块入口或能力接口。
    - 调用关系：建议结合本文件的模块说明、调用方以及同名相关辅助函数一起阅读。
    """
    import argparse

    parser = argparse.ArgumentParser(description="Inspect registered control-center hooks for an event")
    parser.add_argument("--event-type", required=True)
    args = parser.parse_args()
    print(json.dumps(get_registered_hooks(args.event_type), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
