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
- 文件路径：`tools/openmoss/control_center/governance_runtime.py`
- 文件作用：把 policy、hooks、memory 三类治理信息合成一份统一执行封包，供 mission loop、runtime prompt、doctor/receipt 复用。
- 顶层函数：build_governance_bundle、build_policy_bundle、build_hook_bundle、build_memory_bundle。
- 设计意图：解决治理信息分散在多个模块中、上下文签名不一致、执行链读取口径不统一的问题。
"""
from __future__ import annotations

import json
from pathlib import Path
from copy import deepcopy
from typing import Any, Dict, List

from approval_gate import review_plan
from authorized_session_manager import build_authorized_session_plan
from crawler_capability_profile import build_crawler_capability_profile
from hook_registry import get_registered_hooks
from human_checkpoint import build_human_checkpoint
from memory_pipeline_runtime import build_memory_layers
from memory_pipeline_store import persist_memory_pipeline
from memory_writeback_runtime import build_memory_writeback_policy, load_memory_writeback
from permission_decision_runtime import build_permission_decision_bundle
from paths import MEMORY_ROOT, POLICY_ROOT, SYSTEM_SNAPSHOT_PATH
from security_policy import assess_plan_risk, classify_external_action, default_security_policy


LEARNING_ROOT = Path("/Users/mac_claw/.openclaw/workspace/tools/openmoss/runtime/autonomy/learning")


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


def _deep_merge(base: Dict[str, Any], patch: Dict[str, Any]) -> Dict[str, Any]:
    merged = deepcopy(base)
    for key, value in (patch or {}).items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = _deep_merge(merged.get(key, {}), value)
        else:
            merged[key] = value
    return merged


def _normalize_action_type(tool_name: str) -> str:
    lowered = str(tool_name or "").strip().lower()
    if lowered in {"web", "search", "crawl4ai", "scrapy", "httpx", "curl_cffi", "selectolax"}:
        return "public_read"
    if lowered in {"browser", "agent-browser", "playwright", "playwright_stealth"}:
        return "sensitive_browser_state"
    if lowered in {"authorized_session"}:
        return "authorized_session"
    if lowered in {"pip", "uv", "npm", "pnpm", "brew"}:
        return "dependency_install"
    if lowered in {"python", "bash", "sh", "node"}:
        return "external_code_execution"
    if lowered in {"human_checkpoint"}:
        return "human_checkpoint"
    return "public_read"


def _iter_external_actions(contract: Dict[str, Any], mission: Dict[str, Any]) -> List[Dict[str, Any]]:
    actions: List[Dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    for tool in contract.get("allowed_tools", []) or []:
        action_type = _normalize_action_type(str(tool))
        key = (action_type, str(tool))
        if key in seen:
            continue
        seen.add(key)
        actions.append({"type": action_type, "tool": str(tool)})
    crawler = mission.get("crawler", {}) or {}
    selected_stack = crawler.get("selected_stack", {}) or {}
    for tool in selected_stack.get("tools", []) or []:
        action_type = _normalize_action_type(str(tool))
        key = (action_type, str(tool))
        if key in seen:
            continue
        seen.add(key)
        actions.append({"type": action_type, "tool": str(tool), "source": "crawler.selected_stack"})
    if (mission.get("authorized_session", {}) or {}).get("needs_authorized_session"):
        key = ("authorized_session", "authorized_session")
        if key not in seen:
            seen.add(key)
            actions.append({"type": "authorized_session", "tool": "authorized_session", "source": "authorized_session_plan"})
    if (mission.get("human_checkpoint", {}) or {}).get("required"):
        key = ("human_checkpoint", "human_checkpoint")
        if key not in seen:
            seen.add(key)
            actions.append({"type": "human_checkpoint", "tool": "human_checkpoint", "source": "human_checkpoint"})
    return actions


def build_policy_bundle(task_id: str, contract: Dict[str, Any], state: Dict[str, Any], mission: Dict[str, Any]) -> Dict[str, Any]:
    external_actions = _iter_external_actions(contract, mission)
    plan = {"external_actions": external_actions}
    assessed = assess_plan_risk(plan)
    approval = mission.get("approval", {}) or {}
    bundle = {
        "task_id": task_id,
        "risk": assessed.get("risk", "low"),
        "actions": [
            {
                **row,
                "action_id": f"{task_id}:{row.get('type', 'external')}:{index}",
                **classify_external_action(str(row.get("type", ""))),
            }
            for index, row in enumerate(external_actions, start=1)
        ],
        "pending_approvals": approval.get("pending", []),
        "approved_actions": approval.get("approved", []),
        "current_stage": state.get("current_stage", ""),
        "next_action": state.get("next_action", ""),
    }
    _write_json(POLICY_ROOT / f"{task_id}.json", bundle)
    return bundle


def build_security_bundle(task_id: str, contract: Dict[str, Any], mission: Dict[str, Any]) -> Dict[str, Any]:
    external_actions = _iter_external_actions(contract, mission)
    policy = default_security_policy()
    assessed = assess_plan_risk({"external_actions": external_actions})
    bundle = {
        "task_id": task_id,
        "principle": policy.get("principle", ""),
        "forbidden_actions": policy.get("forbidden_actions", []),
        "network_allow_patterns": policy.get("network_allow_patterns", []),
        "review_levels": policy.get("review_levels", {}),
        "overall_risk": assessed.get("risk", "low"),
    }
    return bundle


def build_approval_bundle(task_id: str, mission: Dict[str, Any]) -> Dict[str, Any]:
    approval = mission.get("approval", {}) or {}
    selected_plan = mission.get("selected_plan", {}) or {}
    if not approval and selected_plan:
        approval = review_plan(task_id, selected_plan)
    return {
        "task_id": task_id,
        "overall_risk": approval.get("overall_risk", ""),
        "pending": approval.get("pending", []),
        "approved": approval.get("approved", []),
        "decisions": approval.get("decisions", {}),
    }


def build_authorized_session_bundle(task_id: str, mission: Dict[str, Any]) -> Dict[str, Any]:
    payload = mission.get("authorized_session", {}) or build_authorized_session_plan(
        task_id,
        mission.get("intent", {}) or {},
        mission.get("challenge", {}) or {},
    )
    return payload


def build_human_checkpoint_bundle(task_id: str, mission: Dict[str, Any]) -> Dict[str, Any]:
    payload = mission.get("human_checkpoint", {}) or build_human_checkpoint(
        task_id,
        mission.get("challenge", {}) or {},
    )
    return payload


def build_hook_bundle(task_id: str, stage_name: str, state: Dict[str, Any]) -> Dict[str, Any]:
    event_types = [
        "mission.built",
        f"stage.{stage_name}.entered" if stage_name else "",
        f"stage.{stage_name}.waiting" if stage_name and state.get("status") == "waiting_external" else "",
        "challenge.detected" if state.get("blockers") else "",
    ]
    hooks: List[Dict[str, Any]] = []
    for event_type in [item for item in event_types if item]:
        registered = get_registered_hooks(event_type)
        hooks.append(registered)
    return {
        "task_id": task_id,
        "stage_name": stage_name,
        "registered": hooks,
        "last_effects": (state.get("metadata", {}) or {}).get("last_hook_effects", {}) or {},
        "warnings": (state.get("metadata", {}) or {}).get("hook_warnings", []) or [],
        "errors": (state.get("metadata", {}) or {}).get("hook_errors", []) or [],
        "next_actions": (state.get("metadata", {}) or {}).get("hook_next_actions", []) or [],
    }


def _load_task_summary(task_id: str) -> Dict[str, Any]:
    return _read_json(LEARNING_ROOT / "task_summaries" / f"{task_id}.json", {})


def _load_promoted_rules() -> Dict[str, Any]:
    return _read_json(LEARNING_ROOT / "promoted_rules.json", {"rules": []})


def _load_error_recurrence() -> Dict[str, Any]:
    return _read_json(LEARNING_ROOT / "error_recurrence.json", {"errors": {}})


def _load_plan_history_profile(plan_id: str, task_types: List[str], risk_level: str) -> Dict[str, Any]:
    from plan_history import load_history_profile

    return load_history_profile(plan_id, task_types=task_types, risk_level=risk_level)


def build_memory_bundle(task_id: str, contract: Dict[str, Any], state: Dict[str, Any], mission: Dict[str, Any]) -> Dict[str, Any]:
    task_summary = _load_task_summary(task_id)
    promoted = _load_promoted_rules()
    recurrence = _load_error_recurrence()
    blockers = [str(item).strip().lower() for item in (state.get("blockers", []) or []) if str(item).strip()]
    matched_rules = []
    matched_recurrence = []
    for blocker in blockers:
        for rule in promoted.get("rules", []):
            if str(rule.get("error_key", "")).strip() and str(rule.get("error_key", "")) in blocker:
                matched_rules.append(rule)
        for key, value in (recurrence.get("errors", {}) or {}).items():
            if str(key).strip() and str(key) in blocker:
                matched_recurrence.append({"error_key": key, **(value or {})})
    selected_plan = mission.get("selected_plan", {}) or {}
    intent = mission.get("intent", {}) or {}
    history_profile = _load_plan_history_profile(
        str(selected_plan.get("plan_id", "")),
        task_types=[str(item) for item in intent.get("task_types", []) if str(item).strip()],
        risk_level=str(intent.get("risk_level", "")),
    ) if selected_plan.get("plan_id") else {}
    layers = build_memory_layers(
        task_id=task_id,
        task_summary=task_summary,
        matched_promoted_rules=matched_rules,
        matched_error_recurrence=matched_recurrence,
        plan_history_profile=history_profile,
        state=state,
    )
    persisted = persist_memory_pipeline(task_id, layers)
    writeback_policy = build_memory_writeback_policy(task_id, state, mission)
    metadata_writeback = (state.get("metadata", {}) or {}).get("memory_writeback", {}) or {}
    file_writeback = load_memory_writeback(task_id)
    if int(file_writeback.get("entries_total", 0) or 0) >= int(metadata_writeback.get("entries_total", 0) or 0):
        writeback_state = {**metadata_writeback, **file_writeback}
    else:
        writeback_state = metadata_writeback
    bundle = {
        "task_summary": task_summary,
        "matched_promoted_rules": matched_rules[:5],
        "matched_error_recurrence": matched_recurrence[:5],
        "plan_history_profile": history_profile,
        "layers": layers,
        "persisted": persisted,
        "writeback_policy": writeback_policy,
        "writeback_state": writeback_state,
    }
    _write_json(MEMORY_ROOT / f"{task_id}.json", bundle)
    return bundle


def build_crawler_project_bundle(task_id: str, contract: Dict[str, Any], mission: Dict[str, Any]) -> Dict[str, Any]:
    profile = build_crawler_capability_profile()
    summary = profile.get("summary", {}) or {}
    sites = profile.get("sites", []) or []
    goal_parts = [
        str(contract.get("user_goal", "")).strip().lower(),
        json.dumps(mission.get("crawler", {}) or {}, ensure_ascii=False).lower(),
        json.dumps(mission.get("intent", {}) or {}, ensure_ascii=False).lower(),
    ]
    goal_blob = " ".join(part for part in goal_parts if part)
    attention_sites = [site for site in sites if site.get("readiness") == "attention_required"]
    relevant_sites = [
        site
        for site in sites
        if str(site.get("site", "")).strip().lower() and str(site.get("site", "")).strip().lower() in goal_blob
    ]
    relevant_attention = [site for site in attention_sites if site in relevant_sites]
    if not relevant_attention and relevant_sites:
        relevant_attention = [
            site for site in relevant_sites if site.get("readiness") not in {"production_ready", "governed_ready"}
        ]
    if not relevant_attention and not relevant_sites:
        relevant_attention = attention_sites[:3]
    recommended_actions = profile.get("recommended_project_actions", []) or []
    health_status = "healthy"
    if float(summary.get("width_score", 0) or 0) < 60 or float(summary.get("stability_score", 0) or 0) < 60:
        health_status = "degraded"
    if float(summary.get("width_score", 0) or 0) < 40 or float(summary.get("depth_score", 0) or 0) < 40:
        health_status = "critical"
    return {
        "task_id": task_id,
        "health_status": health_status,
        "summary": summary,
        "relevant_sites": [
            {
                "site": site.get("site", ""),
                "readiness": site.get("readiness", ""),
                "selected_tool": site.get("selected_tool", ""),
                "primary_limitations": site.get("primary_limitations", []),
            }
            for site in relevant_sites[:5]
        ],
        "attention_sites": [
            {
                "site": site.get("site", ""),
                "readiness": site.get("readiness", ""),
                "primary_limitations": site.get("primary_limitations", []),
            }
            for site in relevant_attention[:5]
        ],
        "recommended_project_actions": recommended_actions[:5],
    }


def build_project_control_bundle() -> Dict[str, Any]:
    snapshot = _read_json(SYSTEM_SNAPSHOT_PATH, {}) or {}
    summary = (snapshot.get("summary", {}) or {}) if isinstance(snapshot, dict) else {}
    scheduler_policy = (snapshot.get("project_scheduler_policy", {}) or {}) if isinstance(snapshot, dict) else {}
    scheduler_states = (snapshot.get("scheduler_states", {}) or {}) if isinstance(snapshot, dict) else {}
    return {
        "generated_at": snapshot.get("generated_at", ""),
        "summary": {
            "processes_running": summary.get("processes_running", 0),
            "processes_total": summary.get("processes_total", 0),
            "crawler_sites_total": summary.get("crawler_sites_total", 0),
            "crawler_sites_ready": summary.get("crawler_sites_ready", 0),
            "crawler_width_score": summary.get("crawler_width_score", 0),
            "crawler_breadth_score": summary.get("crawler_breadth_score", 0),
            "crawler_depth_score": summary.get("crawler_depth_score", 0),
            "crawler_stability_score": summary.get("crawler_stability_score", 0),
            "crawler_trend_direction": summary.get("crawler_trend_direction", "unknown"),
            "crawler_feedback_coverage_status": summary.get("crawler_feedback_coverage_status", "unknown"),
            "memory_writeback_tasks_total": summary.get("memory_writeback_tasks_total", 0),
        },
        "scheduler_policy": scheduler_policy,
        "scheduler_modes": {
            "crawler_remediation": ((scheduler_policy.get("crawler_remediation", {}) or {}).get("recommended_mode", "")),
            "seller_bulk": ((scheduler_policy.get("seller_bulk", {}) or {}).get("recommended_mode", "")),
            "cross_market_arbitrage": ((scheduler_policy.get("cross_market_arbitrage", {}) or {}).get("recommended_mode", "")),
        },
        "scheduler_states": scheduler_states,
    }


def _build_doctor_coverage_bundle() -> Dict[str, Any]:
    return {
        "single_doctor_rule": True,
        "authoritative_doctor": "tools/openmoss/control_center/system_doctor.py",
        "required_for_stable_promotion": [
            "doctor_coverage_registered",
            "targeted_tests_present",
            "governance_runtime_updated",
        ],
        "registered_integrations": [
            {
                "name": "jinclaw-gstack-compatibility",
                "required_files": [
                    "compat/gstack/README.md",
                    "compat/gstack/intake-assessment.md",
                    "compat/gstack/capability-map.md",
                    "compat/gstack/routing-policy.md",
                    "compat/gstack/prompts/jinclaw-gstack-lite.md",
                    "tools/openmoss/control_center/coding_session_adapter.py",
                    "tools/openmoss/control_center/acp_dispatch_builder.py",
                ],
                "doctor_checks": [
                    "file_presence",
                    "prompt_integrity",
                    "coding_chain_continuity",
                    "noncoding_anti_pollution",
                ],
                "primary_monitor": "system_doctor.integration_health.gstack",
                "backstop_monitor": "tests/test_single_doctor_architecture.py",
                "delayed_verification": "tools/openmoss/runtime/control_center/doctor/last_run.json",
            },
            {
                "name": "acquisition-hand",
                "required_files": [
                    "tools/openmoss/control_center/acquisition_hand_builder.py",
                    "tools/openmoss/control_center/acquisition_adapter_registry.py",
                    "tools/openmoss/control_center/acquisition_result_normalizer.py",
                    "tools/openmoss/control_center/challenge_classifier.py",
                    "tools/openmoss/control_center/crawler_probe_runner.py",
                    "tools/openmoss/control_center/task_status_snapshot.py",
                ],
                "doctor_checks": [
                    "package_contract_presence",
                    "stage_context_continuity",
                    "dispatch_prompt_injection",
                    "task_status_snapshot_visibility",
                    "doctor_runtime_summary",
                ],
                "primary_monitor": "system_doctor.integration_health.acquisition_hand",
                "backstop_monitor": "tools/openmoss/ops/jinclaw_ops.py:doctor_runtime",
                "delayed_verification": "tools/openmoss/runtime/control_center/doctor/last_run.json#acquisition_health",
            },
            {
                "name": "conversation-context-kernel",
                "required_files": [
                    "tools/openmoss/control_center/conversation_context.py",
                    "tools/openmoss/control_center/brain_router.py",
                    "tools/openmoss/control_center/route_guardrails.py",
                    "tools/openmoss/autonomy/telegram_binding.py",
                    "tools/openmoss/control_center/brain_enforcer.py",
                    "tools/openmoss/control_center/control_plane_builder.py",
                ],
                "doctor_checks": [
                    "instruction_envelope_presence",
                    "conversation_focus_persistence",
                    "followup_resolution_recovery",
                    "control_plane_focus_visibility",
                ],
                "primary_monitor": "system_doctor.integration_health.conversation_context",
                "backstop_monitor": "tools/openmoss/runtime/control_center/control_plane/conversation_focus_registry.json",
                "delayed_verification": "tools/openmoss/runtime/control_center/doctor/last_run.json#integration_health.conversation_context",
            },
            {
                "name": "reply-projection-kernel",
                "required_files": [
                    "tools/openmoss/control_center/response_policy_engine.py",
                    "tools/openmoss/control_center/task_receipt_engine.py",
                    "tools/openmoss/control_center/task_status_snapshot.py",
                    "tools/openmoss/autonomy/telegram_binding.py",
                    "tools/openmoss/autonomy/action_executor.py",
                ],
                "doctor_checks": [
                    "projection_contract_presence",
                    "projection_render_parity",
                    "receipt_projection_persistence",
                ],
                "primary_monitor": "system_doctor.integration_health.reply_projection",
                "backstop_monitor": "tools/openmoss/runtime/control_center/doctor/last_run.json#integration_health.reply_projection",
                "delayed_verification": "tools/openmoss/runtime/control_center/doctor/last_run.json#integration_health.reply_projection",
            },
            {
                "name": "conversation-event-kernel",
                "required_files": [
                    "tools/openmoss/control_center/conversation_events.py",
                    "tools/openmoss/autonomy/telegram_binding.py",
                    "tools/openmoss/control_center/brain_router.py",
                    "tools/openmoss/control_center/task_receipt_engine.py",
                    "tools/openmoss/control_center/control_plane_builder.py",
                ],
                "doctor_checks": [
                    "ingress_event_persistence",
                    "route_event_persistence",
                    "reply_event_persistence",
                    "control_plane_event_visibility",
                ],
                "primary_monitor": "system_doctor.integration_health.conversation_events",
                "backstop_monitor": "tools/openmoss/runtime/control_center/control_plane/conversation_event_registry.json",
                "delayed_verification": "tools/openmoss/runtime/control_center/doctor/last_run.json#integration_health.conversation_events",
            },
            {
                "name": "execution-event-kernel",
                "required_files": [
                    "tools/openmoss/control_center/conversation_events.py",
                    "tools/openmoss/autonomy/action_executor.py",
                    "tools/openmoss/control_center/task_status_snapshot.py",
                    "tools/openmoss/control_center/control_plane_builder.py",
                ],
                "doctor_checks": [
                    "execution_event_persistence",
                    "execution_handoff_snapshot_contract",
                    "runtime_mode_session_strategy_contract",
                    "control_plane_execution_visibility",
                ],
                "primary_monitor": "system_doctor.integration_health.execution_events",
                "backstop_monitor": "tools/openmoss/runtime/control_center/control_plane/conversation_event_registry.json",
                "delayed_verification": "tools/openmoss/runtime/control_center/doctor/last_run.json#integration_health.execution_events",
            },
            {
                "name": "completion-reflection-kernel",
                "required_files": [
                    "tools/openmoss/autonomy/runtime_service.py",
                    "tools/openmoss/control_center/control_center_schemas.py",
                    "tools/openmoss/control_center/task_status_snapshot.py",
                    "tools/openmoss/control_center/system_doctor.py",
                ],
                "doctor_checks": [
                    "outcome_evaluation_contract",
                    "reflection_report_contract",
                    "authoritative_summary_visibility",
                ],
                "primary_monitor": "system_doctor.integration_health.completion_reflection",
                "backstop_monitor": "tools/openmoss/runtime/control_center/doctor/last_run.json#integration_health.completion_reflection",
                "delayed_verification": "tools/openmoss/runtime/control_center/doctor/last_run.json#integration_health.completion_reflection",
            }
        ],
    }


def build_governance_bundle(task_id: str, stage_name: str, contract: Dict[str, Any], state: Dict[str, Any], mission: Dict[str, Any]) -> Dict[str, Any]:
    security = build_security_bundle(task_id, contract, mission)
    policy = build_policy_bundle(task_id, contract, state, mission)
    approval = build_approval_bundle(task_id, mission)
    authorized_session = build_authorized_session_bundle(task_id, mission)
    human_checkpoint = build_human_checkpoint_bundle(task_id, mission)
    crawler_project = build_crawler_project_bundle(task_id, contract, mission)
    hooks = build_hook_bundle(task_id, stage_name, state)
    bundle = {
        "security": security,
        "policy": policy,
        "approval": approval,
        "authorized_session": authorized_session,
        "human_checkpoint": human_checkpoint,
        "permission_decision": build_permission_decision_bundle(
            task_id=task_id,
            stage_name=stage_name,
            security=security,
            policy=policy,
            approval=approval,
            authorized_session=authorized_session,
            human_checkpoint=human_checkpoint,
            hooks=hooks,
        ),
        "crawler_project": crawler_project,
        "project_control": build_project_control_bundle(),
        "doctor_coverage": _build_doctor_coverage_bundle(),
        "hooks": hooks,
        "memory": build_memory_bundle(task_id, contract, state, mission),
    }
    runtime_patch = ((state.get("metadata", {}) or {}).get("governance_runtime", {}) or {})
    if runtime_patch:
        bundle = _deep_merge(bundle, runtime_patch)
    bundle["runtime_patch"] = runtime_patch
    return bundle


if __name__ == "__main__":
    raise SystemExit(0)
