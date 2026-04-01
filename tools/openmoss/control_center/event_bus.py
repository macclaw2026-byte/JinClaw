#!/usr/bin/env python3

"""
中文说明：
- 文件路径：`tools/openmoss/control_center/event_bus.py`
- 文件作用：负责控制中心中与 `event_bus` 相关的编排、分析或决策逻辑。
- 顶层函数：_utc_now_iso、_append_jsonl、publish_event、main。
- 顶层类：无顶层类。
- 阅读建议：先看模块说明，再按函数/类 docstring 顺着主流程理解调用关系。
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

from capability_cloner import clone_capability
from hook_registry import get_registered_hooks
from paths import EVENTS_ROOT


def _utc_now_iso() -> str:
    """
    中文注解：
    - 功能：实现 `_utc_now_iso` 对应的处理逻辑。
    - 角色：属于本模块中的内部辅助逻辑；私有函数通常服务同文件主流程，公共函数通常作为跨模块入口或能力接口。
    - 调用关系：建议结合本文件的模块说明、调用方以及同名相关辅助函数一起阅读。
    """
    return datetime.now(timezone.utc).isoformat()


def _append_jsonl(path: Path, payload: object) -> None:
    """
    中文注解：
    - 功能：实现 `_append_jsonl` 对应的处理逻辑。
    - 角色：属于本模块中的内部辅助逻辑；私有函数通常服务同文件主流程，公共函数通常作为跨模块入口或能力接口。
    - 调用关系：建议结合本文件的模块说明、调用方以及同名相关辅助函数一起阅读。
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(payload, ensure_ascii=False) + "\n")


def _normalize_hook_specs(registered: Dict[str, object]) -> List[Dict[str, object]]:
    hook_specs = list(registered.get("hook_specs", []) or [])
    if hook_specs:
        return hook_specs
    return [
        {
            "name": str(name),
            "phase": "post_execute",
            "priority": 100,
            "blocking": False,
            "idempotent": True,
            "retryable": True,
            "timeout_ms": 1500,
            "failure_policy": "record_and_continue",
            "required_inputs": ["task_id"],
            "emits": [],
        }
        for name in registered.get("hooks", []) or []
        if str(name).strip()
    ]


def _execute_hook(hook_spec: Dict[str, object], task_id: str, payload: Dict[str, object]) -> Dict[str, Any]:
    hook_name = str(hook_spec.get("name", "")).strip()
    result: Dict[str, Any] = {
        "hook_name": hook_name,
        "phase": str(hook_spec.get("phase", "")),
        "priority": int(hook_spec.get("priority", 100)),
        "blocking": bool(hook_spec.get("blocking", False)),
        "failure_policy": str(hook_spec.get("failure_policy", "record_and_continue")),
        "status": "observed",
        "decision": "",
        "artifacts": {},
        "state_patch": {},
        "governance_patch": {},
        "next_actions": [],
        "warnings": [],
        "errors": [],
    }
    if hook_name == "run_capability_clone_pipeline":
        mission = payload.get("mission", {})
        clone = clone_capability(task_id, mission)
        result.update(
            {
                "status": "completed",
                "decision": "capability_clone_pipeline_executed",
                "artifacts": {"clone": clone},
            }
        )
        if clone.get("verification", {}).get("passed"):
            _append_jsonl(
                EVENTS_ROOT / f"{task_id}.jsonl",
                {
                    "at": _utc_now_iso(),
                    "event_type": "capability.clone_verified",
                    "task_id": task_id,
                    "payload": {"task_id": task_id, "clone": clone},
                },
            )
        return result
    if hook_name == "refresh_task_memory_snapshot":
        memory = ((payload.get("governance", {}) or {}).get("memory", {}) or {})
        result.update(
            {
                "status": "completed",
                "decision": "memory_snapshot_checked",
                "artifacts": {
                    "matched_promoted_rules": len(memory.get("matched_promoted_rules", []) or []),
                    "matched_error_recurrence": len(memory.get("matched_error_recurrence", []) or []),
                },
                "governance_patch": {"memory_refreshed": True},
            }
        )
        return result
    if hook_name == "verify_execution_policy_handoff":
        governance = payload.get("governance", {}) or {}
        policy = governance.get("policy", {}) or {}
        approval = governance.get("approval", {}) or {}
        if str(policy.get("risk", "")).strip() in {"high", "critical"} and (approval.get("pending", []) or []):
            result.update(
                {
                    "status": "attention_required",
                    "decision": "execution_policy_requires_review",
                    "state_patch": {"next_action": "await_approval_or_contract_fix"},
                    "warnings": ["critical_or_high_risk_execution_has_pending_approval"],
                    "next_actions": ["await_approval_or_contract_fix"],
                }
            )
            return result
        result.update(
            {
                "status": "completed",
                "decision": "execution_policy_handoff_verified",
                "artifacts": {"policy_risk": str(policy.get("risk", ""))},
            }
        )
        return result
    if hook_name == "monitor_liveness_and_retry_path":
        result.update(
            {
                "status": "completed",
                "decision": "liveness_and_retry_path_reviewed",
                "artifacts": {"blockers": payload.get("blockers", []) or []},
            }
        )
        return result
    if hook_name in {"audit_plan_switch", "route_challenge_response", "promote_cloned_capability", "evaluate_clone_need"}:
        result.update({"status": "completed", "decision": f"{hook_name}_recorded"})
        return result
    return result


def summarize_hook_effects(event_result: Dict[str, object]) -> Dict[str, Any]:
    emitted_hooks = list(event_result.get("emitted_hooks", []) or [])
    state_patch: Dict[str, Any] = {}
    governance_patch: Dict[str, Any] = {}
    next_actions: List[str] = []
    warnings: List[str] = []
    errors: List[str] = []
    decisions: List[str] = []
    attention_required = False
    for item in emitted_hooks:
        if str(item.get("status", "")).strip() in {"attention_required", "failed"}:
            attention_required = True
        for key, value in (item.get("state_patch", {}) or {}).items():
            state_patch[str(key)] = value
        for key, value in (item.get("governance_patch", {}) or {}).items():
            governance_patch[str(key)] = value
        next_actions.extend([str(value) for value in item.get("next_actions", []) or [] if str(value).strip()])
        warnings.extend([str(value) for value in item.get("warnings", []) or [] if str(value).strip()])
        errors.extend([str(value) for value in item.get("errors", []) or [] if str(value).strip()])
        if str(item.get("decision", "")).strip():
            decisions.append(str(item.get("decision", "")).strip())
    return {
        "attention_required": attention_required,
        "state_patch": state_patch,
        "governance_patch": governance_patch,
        "next_actions": next_actions,
        "warnings": sorted(set(warnings)),
        "errors": sorted(set(errors)),
        "decisions": decisions,
    }


def publish_event(event_type: str, payload: Dict[str, object]) -> Dict[str, object]:
    """
    中文注解：
    - 功能：实现 `publish_event` 对应的处理逻辑。
    - 角色：属于本模块中的对外可见逻辑；私有函数通常服务同文件主流程，公共函数通常作为跨模块入口或能力接口。
    - 调用关系：建议结合本文件的模块说明、调用方以及同名相关辅助函数一起阅读。
    """
    task_id = str(payload.get("task_id", "global"))
    record = {
        "at": _utc_now_iso(),
        "event_type": event_type,
        "task_id": task_id,
        "payload": payload,
    }
    _append_jsonl(EVENTS_ROOT / f"{task_id}.jsonl", record)
    registered = get_registered_hooks(event_type)
    emitted_hooks = []
    for hook_spec in sorted(_normalize_hook_specs(registered), key=lambda item: int(item.get("priority", 100))):
        emitted_hooks.append(_execute_hook(hook_spec, task_id, payload))
    record["emitted_hooks"] = emitted_hooks
    _append_jsonl(
        EVENTS_ROOT / f"{task_id}.jsonl",
        {
            "at": _utc_now_iso(),
            "event_type": f"{event_type}.hooks",
            "task_id": task_id,
            "hook_names": registered.get("hooks", []),
            "emitted_hooks": emitted_hooks,
        },
    )
    return {
        "recorded": True,
        "event_type": event_type,
        "task_id": task_id,
        "hook_names": registered.get("hooks", []),
        "emitted_hooks": emitted_hooks,
    }


def main() -> int:
    """
    中文注解：
    - 功能：实现 `main` 对应的处理逻辑。
    - 角色：属于本模块中的对外可见逻辑；私有函数通常服务同文件主流程，公共函数通常作为跨模块入口或能力接口。
    - 调用关系：建议结合本文件的模块说明、调用方以及同名相关辅助函数一起阅读。
    """
    import argparse

    parser = argparse.ArgumentParser(description="Publish a control-center event and trigger registered hooks")
    parser.add_argument("--event-type", required=True)
    parser.add_argument("--payload-json", required=True)
    args = parser.parse_args()
    print(json.dumps(publish_event(args.event_type, json.loads(args.payload_json)), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
