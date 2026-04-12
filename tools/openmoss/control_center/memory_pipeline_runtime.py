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
- 文件路径：`tools/openmoss/control_center/memory_pipeline_runtime.py`
- 文件作用：把项目/会话/任务/运行态记忆统一整理成分层 memory pipeline，供 governance 与 snapshot 复用。
- 顶层函数：build_memory_layers。
- 顶层类：无顶层类。
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List

from crawler_capability_profile import build_crawler_capability_profile
from paths import CRAWLER_REMEDIATION_EXECUTION_PATH, CRAWLER_REMEDIATION_PLAN_PATH


LINKS_ROOT = Path("/Users/mac_claw/.openclaw/workspace/tools/openmoss/runtime/autonomy/links")


def _read_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return default


def _session_layer(task_id: str) -> Dict[str, Any]:
    links: List[Dict[str, Any]] = []
    if LINKS_ROOT.exists():
        for path in sorted(LINKS_ROOT.glob("*.json")):
            payload = _read_json(path, {})
            if not payload:
                continue
            related_ids = {
                str(payload.get("task_id", "")).strip(),
                str(payload.get("lineage_root_task_id", "")).strip(),
                str(payload.get("predecessor_task_id", "")).strip(),
            }
            if task_id not in related_ids:
                continue
            links.append(
                {
                    "provider": payload.get("provider", ""),
                    "conversation_id": payload.get("conversation_id", ""),
                    "session_key": payload.get("session_key", ""),
                    "updated_at": payload.get("updated_at", ""),
                }
            )
    latest_link = links[0] if links else {}
    return {
        "active_link_count": len(links),
        "latest_link": latest_link,
        "links": links[:3],
    }


def _project_layer() -> Dict[str, Any]:
    profile = build_crawler_capability_profile()
    execution = _read_json(CRAWLER_REMEDIATION_EXECUTION_PATH, {"items": []}) or {"items": []}
    plan = _read_json(CRAWLER_REMEDIATION_PLAN_PATH, {"items": []}) or {"items": []}
    summary = profile.get("summary", {}) or {}
    priority_actions = profile.get("priority_actions", []) or []
    return {
        "crawler_health": {
            "width_score": summary.get("width_score", 0.0),
            "breadth_score": summary.get("breadth_score", 0.0),
            "depth_score": summary.get("depth_score", 0.0),
            "stability_score": summary.get("stability_score", 0.0),
            "sites_production_ready": summary.get("sites_production_ready", 0),
            "sites_attention_required": summary.get("sites_attention_required", 0),
        },
        "crawler_priority_actions": priority_actions[:5],
        "crawler_remediation_plan_total": len(plan.get("items", []) or []),
        "crawler_remediation_execution_total": len(execution.get("items", []) or []),
    }


def _runtime_layer(state: Dict[str, Any]) -> Dict[str, Any]:
    metadata = state.get("metadata", {}) or {}
    return {
        "blockers": state.get("blockers", []) or [],
        "active_execution": metadata.get("active_execution", {}) or {},
        "waiting_external": metadata.get("waiting_external", {}) or {},
        "hook_warnings": metadata.get("hook_warnings", []) or [],
        "hook_errors": metadata.get("hook_errors", []) or [],
        "hook_next_actions": metadata.get("hook_next_actions", []) or [],
        "permission_runtime": metadata.get("governance_runtime", {}) or {},
    }


def build_memory_layers(
    *,
    task_id: str,
    task_summary: Dict[str, Any],
    matched_promoted_rules: List[Dict[str, Any]],
    matched_error_recurrence: List[Dict[str, Any]],
    plan_history_profile: Dict[str, Any],
    state: Dict[str, Any],
) -> Dict[str, Any]:
    session = _session_layer(task_id)
    project = _project_layer()
    task = {
        "task_summary": task_summary,
        "matched_promoted_rules": matched_promoted_rules[:5],
        "matched_error_recurrence": matched_error_recurrence[:5],
        "plan_history_profile": plan_history_profile,
    }
    runtime = _runtime_layer(state)
    return {
        "session": session,
        "project": project,
        "task": task,
        "runtime": runtime,
        "summary": {
            "session_linked": bool(session.get("active_link_count")),
            "project_attention_sites": int((project.get("crawler_health", {}) or {}).get("sites_attention_required", 0) or 0),
            "task_rule_matches": len(task.get("matched_promoted_rules", []) or []),
            "runtime_blockers": len(runtime.get("blockers", []) or []),
        },
    }
