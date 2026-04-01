#!/usr/bin/env python3

"""
中文说明：
- 文件路径：`tools/openmoss/control_center/crawler_remediation_executor.py`
- 文件作用：把项目级 crawler remediation plan 物化为真实 remediation tasks，并输出执行报告。
- 顶层函数：execute_crawler_remediation_plan、main。
- 顶层类：无顶层类。
"""
from __future__ import annotations

import contextlib
import io
import json
import re
from pathlib import Path
from typing import Any, Dict, List

from paths import CRAWLER_REMEDIATION_EXECUTION_PATH, CRAWLER_REMEDIATION_PLAN_PATH

AUTONOMY_DIR = Path("/Users/mac_claw/.openclaw/workspace/tools/openmoss/autonomy")
CONTROL_CENTER_DIR = Path("/Users/mac_claw/.openclaw/workspace/tools/openmoss/control_center")
import sys

for entry in (str(AUTONOMY_DIR), str(CONTROL_CENTER_DIR)):
    if entry not in sys.path:
        sys.path.insert(0, entry)

from manager import TASKS_ROOT, build_args, create_task, read_json as manager_read_json, run_once
from orchestrator import build_control_center_package


def _read_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return default


def _write_json(path: Path, payload: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _slug(text: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", str(text or "").strip().lower())
    return slug.strip("-") or "unknown"


def _task_id_for_item(item: Dict[str, Any]) -> str:
    site = _slug(item.get("site", "") or "project")
    action = _slug(item.get("action", "") or item.get("execution_type", "") or "remediation")
    return f"crawler-remediation-{site}-{action}"


def _task_exists(task_id: str) -> bool:
    return (TASKS_ROOT / task_id / "contract.json").exists()


def _build_goal(item: Dict[str, Any]) -> str:
    goal = str(item.get("goal", "")).strip()
    route = str(item.get("suggested_route", "")).strip()
    tools = [str(tool).strip() for tool in (item.get("suggested_tools", []) or []) if str(tool).strip()]
    targets = [str(target).strip() for target in (item.get("verification_targets", []) or []) if str(target).strip()]
    evidence_inputs = [str(path).strip() for path in (item.get("evidence_inputs", []) or []) if str(path).strip()]
    parts = [goal]
    if route:
        parts.append(f"优先执行路线：{route}。")
    if tools:
        parts.append(f"建议优先工具：{', '.join(tools)}。")
    if targets:
        parts.append(f"验证目标：{'；'.join(targets)}。")
    if evidence_inputs:
        parts.append(f"优先参考证据：{'；'.join(evidence_inputs)}。")
    return " ".join(part for part in parts if part).strip()


def _metadata_for_item(item: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "crawler_remediation": {
            "id": item.get("id", ""),
            "priority": item.get("priority", "medium"),
            "execution_type": item.get("execution_type", ""),
            "site": item.get("site", ""),
            "suggested_route": item.get("suggested_route", ""),
            "suggested_tools": item.get("suggested_tools", []),
            "verification_targets": item.get("verification_targets", []),
            "evidence_inputs": item.get("evidence_inputs", []),
        }
    }


def execute_crawler_remediation_plan(*, start_tasks: bool = True) -> Dict[str, Any]:
    plan = _read_json(CRAWLER_REMEDIATION_PLAN_PATH, {"items": []}) or {"items": []}
    items = plan.get("items", []) or []
    results: List[Dict[str, Any]] = []
    for item in items:
        task_id = _task_id_for_item(item)
        record: Dict[str, Any] = {
            "task_id": task_id,
            "source_remediation_id": item.get("id", ""),
            "site": item.get("site", ""),
            "execution_type": item.get("execution_type", ""),
        }
        if _task_exists(task_id):
            record["status"] = "already_exists"
        else:
            goal = _build_goal(item)
            metadata = _metadata_for_item(item)
            package = build_control_center_package(task_id, goal, source="crawler_remediation_executor")
            package["metadata"] = {
                **(package.get("metadata", {}) or {}),
                **metadata,
            }
            with contextlib.redirect_stdout(io.StringIO()):
                create_task(
                    build_args(
                        task_id=task_id,
                        goal=goal,
                        done_definition=package["done_definition"],
                        stage=[],
                        stage_json=json.dumps(package["stages"], ensure_ascii=False),
                        hard_constraint=package["hard_constraints"],
                        soft_preference=[],
                        allowed_tool=package["allowed_tools"],
                        forbidden_action=[],
                        metadata_json=json.dumps(package["metadata"], ensure_ascii=False),
                    )
                )
            record["status"] = "created"
        if start_tasks:
            with contextlib.redirect_stdout(io.StringIO()):
                run_once(build_args(task_id=task_id))
            record["started"] = True
        state = manager_read_json(TASKS_ROOT / task_id / "state.json", {})
        record["task_state"] = {
            "status": state.get("status", ""),
            "current_stage": state.get("current_stage", ""),
            "next_action": state.get("next_action", ""),
        }
        results.append(record)
    payload = {
        "items_total": len(items),
        "started_total": sum(1 for item in results if item.get("started")),
        "created_total": sum(1 for item in results if item.get("status") == "created"),
        "existing_total": sum(1 for item in results if item.get("status") == "already_exists"),
        "items": results,
    }
    _write_json(CRAWLER_REMEDIATION_EXECUTION_PATH, payload)
    return payload


def main() -> int:
    import argparse

    parser = argparse.ArgumentParser(description="Execute crawler remediation plan into real remediation tasks")
    parser.add_argument("--no-start", action="store_true", help="Create remediation tasks but do not start them.")
    args = parser.parse_args()
    print(json.dumps(execute_crawler_remediation_plan(start_tasks=not args.no_start), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
