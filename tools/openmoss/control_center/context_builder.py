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
- 文件路径：`tools/openmoss/control_center/context_builder.py`
- 文件作用：负责为 AI 执行阶段整理上下文包。
- 顶层函数：_load_json、build_stage_context、main。
- 顶层类：无顶层类。
- 阅读建议：先看模块说明，再按函数/类 docstring 顺着主流程理解调用关系。
"""
from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Dict

from cache_store import cache_get, cache_put
from crawler_capability_profile import build_crawler_capability_profile
from governance_runtime import build_governance_bundle
from htn_planner import build_htn_tree, select_htn_focus_by_cursor
from topology_mapper import build_topology
from fractal_decomposer import select_loop_focus
from fractal_decomposer import build_fractal_loops
from paths import APPROVALS_ROOT, MISSIONS_ROOT, SUMMARIES_ROOT


def _load_json(path: Path) -> Dict[str, object]:
    """
    中文注解：
    - 功能：实现 `_load_json` 对应的处理逻辑。
    - 角色：属于本模块中的内部辅助逻辑；私有函数通常服务同文件主流程，公共函数通常作为跨模块入口或能力接口。
    - 调用关系：建议结合本文件的模块说明、调用方以及同名相关辅助函数一起阅读。
    """
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def build_stage_context(task_id: str, stage_name: str, contract: Dict[str, object], state: Dict[str, object]) -> Dict[str, object]:
    """
    中文注解：
    - 功能：实现 `build_stage_context` 对应的处理逻辑。
    - 角色：属于本模块中的对外可见逻辑；私有函数通常服务同文件主流程，公共函数通常作为跨模块入口或能力接口。
    - 调用关系：建议结合本文件的模块说明、调用方以及同名相关辅助函数一起阅读。
    """
    cache_key = f"{task_id}:{stage_name}"
    mission = _load_json(MISSIONS_ROOT / f"{task_id}.json")
    summary = _load_json(SUMMARIES_ROOT / f"{task_id}.json")
    live_approval = _load_json(APPROVALS_ROOT / f"{task_id}.json")
    selected_plan = mission.get("selected_plan", {})
    topology = mission.get("topology", {}) or build_topology(mission.get("intent", {}), selected_plan)
    fractal = mission.get("fractal_loops", {}) or build_fractal_loops(mission.get("intent", {}), selected_plan, topology)
    htn = mission.get("htn", {}) or build_htn_tree(mission.get("intent", {}), selected_plan, topology, fractal)
    crawler = mission.get("crawler", {}) or {}
    crawler_capability_profile = build_crawler_capability_profile()
    crawler_tools = []
    selected_stack = crawler.get("selected_stack", {}) or {}
    crawler_tools.extend([str(item) for item in selected_stack.get("tools", []) if str(item).strip()])
    fallback_ids = {str(item) for item in crawler.get("fallback_stacks", []) if str(item).strip()}
    for row in crawler.get("scores", []) or []:
        if str(row.get("stack_id", "")).strip() not in fallback_ids:
            continue
        crawler_tools.extend([str(item) for item in row.get("tools", []) if str(item).strip()])
    merged_allowed_tools = sorted(
        dict.fromkeys([str(item) for item in contract.get("allowed_tools", []) if str(item).strip()] + crawler_tools)
    )
    stage_contract = next((item for item in contract.get("stages", []) if item.get("name") == stage_name), {})
    stage_state = state.get("stages", {}).get(stage_name, {})
    stage_attempts = int(stage_state.get("attempts", 0) or 0)
    subtask_cursor = int(stage_state.get("subtask_cursor", max(stage_attempts - 1, 0)) or 0)
    fractal_focus = select_loop_focus(fractal, stage_name, stage_attempts)
    htn_focus = select_htn_focus_by_cursor(htn, stage_name, subtask_cursor)
    governance = build_governance_bundle(task_id, stage_name, contract, state, mission)
    signature = json.dumps(
        {
            "task_id": task_id,
            "stage_name": stage_name,
            "goal": contract.get("user_goal", ""),
            "done_definition": contract.get("done_definition", ""),
            "selected_plan": selected_plan,
            "crawler": crawler,
            "crawler_capability_profile": crawler_capability_profile.get("summary", {}),
            "governance": governance,
            "topology": topology,
            "fractal_focus": fractal_focus,
            "htn_focus": htn_focus,
            "state": {
                "current_stage": state.get("current_stage", ""),
                "status": state.get("status", ""),
                "next_action": state.get("next_action", ""),
                "blockers": state.get("blockers", []),
            },
            "summary": {
                "current_stage": summary.get("current_stage", ""),
                "status": summary.get("status", ""),
                "next_action": summary.get("next_action", ""),
                "blockers": summary.get("blockers", []),
                "pending_approvals": summary.get("pending_approvals", live_approval.get("pending", mission.get("approval", {}).get("pending", []))),
            },
        },
        ensure_ascii=False,
        sort_keys=True,
    )
    cached = cache_get("stage_context", cache_key, {})
    if cached and cached.get("signature") == signature:
        cached["cache_hit"] = True
        return cached
    payload = {
        "task_id": task_id,
        "stage_name": stage_name,
        "goal": contract.get("user_goal", ""),
        "stage_goal": stage_contract.get("goal", ""),
        "done_definition": contract.get("done_definition", ""),
        "selected_plan": {
            "plan_id": selected_plan.get("plan_id", ""),
            "label": selected_plan.get("label", ""),
            "summary": selected_plan.get("summary", ""),
            "steps": selected_plan.get("steps", []),
        },
        "topology_focus": {
            "semantic_anchor": topology.get("semantic_anchor", {}),
            "dependency_nodes": topology.get("dependency_nodes", []),
            "verification_nodes": topology.get("verification_nodes", []),
            "risk_nodes": topology.get("risk_nodes", []),
            "coverage_goal": topology.get("coverage_goal", ""),
        },
        "fractal_focus": fractal_focus,
        "htn_focus": htn_focus,
        "subtask_progress": {
            "cursor": subtask_cursor,
            "completed_subtasks": stage_state.get("completed_subtasks", []),
        },
        "milestone_progress": {
            "stats": state.get("metadata", {}).get("milestone_stats", {}),
            "items": state.get("metadata", {}).get("milestone_progress", {}),
        },
        "batch_focus": state.get("metadata", {}).get("batch_focus", {}),
        "browser_target_hint": {
            "last_browser_channel_recovery": state.get("metadata", {}).get("last_browser_channel_recovery", {}),
            "last_listings_overview_navigation": state.get("metadata", {}).get("last_listings_overview_navigation", {}),
        },
        "crawler": crawler,
        "crawler_capability_profile": {
            "summary": crawler_capability_profile.get("summary", {}),
            "recommended_project_actions": crawler_capability_profile.get("recommended_project_actions", []),
            "sites": crawler_capability_profile.get("sites", []),
        },
        "governance": governance,
        "summary": {
            "current_stage": state.get("current_stage", "") or summary.get("current_stage", ""),
            "status": state.get("status", "") or summary.get("status", ""),
            "next_action": state.get("next_action", "") or summary.get("next_action", ""),
            "blockers": state.get("blockers", []) or summary.get("blockers", []),
            "pending_approvals": summary.get("pending_approvals", live_approval.get("pending", mission.get("approval", {}).get("pending", []))),
        },
        "allowed_tools": merged_allowed_tools,
        "coding_methodology": mission.get("coding_methodology", {}) or contract.get("metadata", {}).get("control_center", {}).get("coding_methodology", {}),
        "signature": signature,
        "cache_hit": False,
    }
    cache_put("stage_context", cache_key, payload)
    return payload


def main() -> int:
    """
    中文注解：
    - 功能：实现 `main` 对应的处理逻辑。
    - 角色：属于本模块中的对外可见逻辑；私有函数通常服务同文件主流程，公共函数通常作为跨模块入口或能力接口。
    - 调用关系：建议结合本文件的模块说明、调用方以及同名相关辅助函数一起阅读。
    """
    import argparse

    parser = argparse.ArgumentParser(description="Build a minimal stage context packet for execution")
    parser.add_argument("--task-id", required=True)
    parser.add_argument("--stage-name", required=True)
    parser.add_argument("--contract-json", required=True)
    parser.add_argument("--state-json", required=True)
    args = parser.parse_args()
    print(json.dumps(build_stage_context(args.task_id, args.stage_name, json.loads(args.contract_json), json.loads(args.state_json)), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
