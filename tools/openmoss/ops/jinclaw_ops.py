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
- 文件路径：`tools/openmoss/ops/jinclaw_ops.py`
- 文件作用：负责运维诊断、系统体检与运维脚本入口。
- 顶层函数：utc_now、utc_now_iso、run_cmd、parse_json_output、read_json、parse_iso、is_recent、git_summary、gateway_summary、launch_agent_summary、os_uid、runtime_summary、status_payload、doctor_payload、upgrade_check_payload、print_payload、main。
- 顶层类：无顶层类。
- 阅读建议：先看模块说明，再按函数/类 docstring 顺着主流程理解调用关系。
"""
from __future__ import annotations

import argparse
import json
import subprocess
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List


WORKSPACE_ROOT = Path("/Users/mac_claw/.openclaw/workspace")
OPENMOSS_ROOT = WORKSPACE_ROOT / "tools/openmoss"
AUTONOMY_ROOT = OPENMOSS_ROOT / "autonomy"
CONTROL_CENTER_ROOT = OPENMOSS_ROOT / "control_center"
RUNTIME_ROOT = OPENMOSS_ROOT / "runtime"
SELFHEAL_STATE_PATH = RUNTIME_ROOT / "selfheal/state.json"
UPSTREAM_WATCH_STATE_PATH = RUNTIME_ROOT / "upstream_watch/state.json"
UPSTREAM_WATCH_REPORT_PATH = RUNTIME_ROOT / "upstream_watch/reports/latest-report.md"
BRAIN_ROUTES_ROOT = RUNTIME_ROOT / "control_center/brain_routes"
MAIN_LINK_PATH = RUNTIME_ROOT / "autonomy/links/openclaw-main__main.json"
SESSIONS_INDEX_PATH = Path("/Users/mac_claw/.openclaw/agents/main/sessions/sessions.json")
DOCTOR_LAST_RUN_PATH = RUNTIME_ROOT / "control_center/doctor/last_run.json"
UPSTREAM_WATCH_SCRIPT = OPENMOSS_ROOT / "upstream_watch/watch_updates.py"
LAUNCH_AGENTS = {
    "selfheal": "ai.openclaw.selfheal",
    "brain_enforcer": "ai.openclaw.brain-enforcer",
    "autonomy_runtime": "ai.jinclaw.autonomy-runtime",
    "cross_market_arbitrage": "ai.jinclaw.cross-market-arbitrage",
    "crawler_remediation": "ai.jinclaw.crawler-remediation",
    "upstream_watch": "ai.jinclaw.upstream-watch",
}

DOCTOR_REFRESH_MAX_AGE_MINUTES = 30
DOCTOR_REQUIRED_ACQUISITION_CONTRACTS = (
    "field_synthesis_contract",
    "delivery_requirements_contract",
    "source_trust_contract",
    "release_governance_contract",
    "release_disclosure_contract",
    "answer_synthesis_contract",
    "answer_response_contract",
    "response_handoff_contract",
    "execution_truth_contract",
    "objective_completion_contract",
)
DOCTOR_REQUIRED_CONVERSATION_CONTEXT_CONTRACTS = (
    "instruction_envelope_contract",
    "focus_contract",
    "followup_resolution_contract",
    "control_plane_visibility_contract",
)
DOCTOR_REQUIRED_REPLY_PROJECTION_CONTRACTS = (
    "projection_contract_presence",
    "projection_render_parity",
    "receipt_projection_persistence",
)
DOCTOR_REQUIRED_CONVERSATION_EVENT_CONTRACTS = (
    "ingress_event_contract",
    "route_event_contract",
    "reply_event_contract",
    "control_plane_visibility_contract",
)
DOCTOR_REQUIRED_EXECUTION_EVENT_CONTRACTS = (
    "execution_event_contract",
    "execution_handoff_payload_contract",
    "runtime_mode_session_strategy_contract",
    "control_plane_visibility_contract",
)
DOCTOR_REQUIRED_COMPLETION_REFLECTION_CONTRACTS = (
    "outcome_evaluation_contract",
    "outcome_scorecard_contract",
    "reflection_report_contract",
    "authoritative_summary_visibility_contract",
)
DOCTOR_REQUIRED_GOAL_CONTINUATION_CONTRACTS = (
    "goal_continuation_contract",
    "terminal_reopen_gate_contract",
    "authoritative_summary_visibility_contract",
)
DOCTOR_REQUIRED_CAPABILITY_GAP_CONTRACTS = (
    "capability_gap_contract",
    "self_heal_ladder_contract",
    "authoritative_summary_visibility_contract",
)
DOCTOR_REQUIRED_DELIVERY_PLANE_CONTRACTS = (
    "delivery_contract_contract",
    "receipt_delivery_contract_contract",
    "authoritative_summary_visibility_contract",
)
DOCTOR_REQUIRED_SKILL_ACTION_PLANE_CONTRACTS = (
    "skill_action_plane_contract",
    "runtime_prompt_attachment_contract",
    "authoritative_summary_visibility_contract",
)
DOCTOR_REQUIRED_TRANSPORT_BINDING_CONTRACTS = (
    "shared_transport_binding_contract",
    "telegram_binding_delegation_contract",
    "openclaw_main_binding_delegation_contract",
    "event_chain_parity_contract",
)


def utc_now() -> datetime:
    """
    中文注解：
    - 功能：实现 `utc_now` 对应的处理逻辑。
    - 角色：属于本模块中的对外可见逻辑；私有函数通常服务同文件主流程，公共函数通常作为跨模块入口或能力接口。
    - 调用关系：建议结合本文件的模块说明、调用方以及同名相关辅助函数一起阅读。
    """
    return datetime.now(timezone.utc)


def utc_now_iso() -> str:
    """
    中文注解：
    - 功能：实现 `utc_now_iso` 对应的处理逻辑。
    - 角色：属于本模块中的对外可见逻辑；私有函数通常服务同文件主流程，公共函数通常作为跨模块入口或能力接口。
    - 调用关系：建议结合本文件的模块说明、调用方以及同名相关辅助函数一起阅读。
    """
    return utc_now().isoformat()


def run_cmd(command: List[str], timeout: int = 20) -> Dict[str, Any]:
    """
    中文注解：
    - 功能：实现 `run_cmd` 对应的处理逻辑。
    - 角色：属于本模块中的对外可见逻辑；私有函数通常服务同文件主流程，公共函数通常作为跨模块入口或能力接口。
    - 调用关系：建议结合本文件的模块说明、调用方以及同名相关辅助函数一起阅读。
    """
    try:
        proc = subprocess.run(command, capture_output=True, text=True, check=False, timeout=timeout)
    except subprocess.TimeoutExpired as exc:
        return {
            "ok": False,
            "returncode": None,
            "stdout": (exc.stdout or "")[-4000:],
            "stderr": f"timeout after {timeout}s",
        }
    return {
        "ok": proc.returncode == 0,
        "returncode": proc.returncode,
        "stdout": (proc.stdout or "")[-12000:],
        "stderr": (proc.stderr or "")[-4000:],
    }


def parse_json_output(result: Dict[str, Any]) -> Dict[str, Any]:
    """
    中文注解：
    - 功能：实现 `parse_json_output` 对应的处理逻辑。
    - 角色：属于本模块中的对外可见逻辑；私有函数通常服务同文件主流程，公共函数通常作为跨模块入口或能力接口。
    - 调用关系：建议结合本文件的模块说明、调用方以及同名相关辅助函数一起阅读。
    """
    if not result.get("ok"):
        return {}
    try:
        return json.loads(result.get("stdout") or "{}")
    except json.JSONDecodeError:
        return {}


def read_json(path: Path, default: Any) -> Any:
    """
    中文注解：
    - 功能：实现 `read_json` 对应的处理逻辑。
    - 角色：属于本模块中的对外可见逻辑；私有函数通常服务同文件主流程，公共函数通常作为跨模块入口或能力接口。
    - 调用关系：建议结合本文件的模块说明、调用方以及同名相关辅助函数一起阅读。
    """
    if not path.exists():
        return default
    return json.loads(path.read_text(encoding="utf-8"))


def parse_iso(value: str) -> datetime | None:
    """
    中文注解：
    - 功能：实现 `parse_iso` 对应的处理逻辑。
    - 角色：属于本模块中的对外可见逻辑；私有函数通常服务同文件主流程，公共函数通常作为跨模块入口或能力接口。
    - 调用关系：建议结合本文件的模块说明、调用方以及同名相关辅助函数一起阅读。
    """
    if not value:
        return None
    normalized = value.replace("Z", "+00:00")
    try:
        dt = datetime.fromisoformat(normalized)
    except ValueError:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def is_recent(value: str, max_age_minutes: int) -> bool:
    """
    中文注解：
    - 功能：实现 `is_recent` 对应的处理逻辑。
    - 角色：属于本模块中的对外可见逻辑；私有函数通常服务同文件主流程，公共函数通常作为跨模块入口或能力接口。
    - 调用关系：建议结合本文件的模块说明、调用方以及同名相关辅助函数一起阅读。
    """
    dt = parse_iso(value)
    if not dt:
        return False
    return utc_now() - dt <= timedelta(minutes=max_age_minutes)


def git_summary() -> Dict[str, Any]:
    """
    中文注解：
    - 功能：实现 `git_summary` 对应的处理逻辑。
    - 角色：属于本模块中的对外可见逻辑；私有函数通常服务同文件主流程，公共函数通常作为跨模块入口或能力接口。
    - 调用关系：建议结合本文件的模块说明、调用方以及同名相关辅助函数一起阅读。
    """
    branch = run_cmd(["git", "-C", str(WORKSPACE_ROOT), "branch", "--show-current"])
    head = run_cmd(["git", "-C", str(WORKSPACE_ROOT), "rev-parse", "HEAD"])
    remote = run_cmd(["git", "-C", str(WORKSPACE_ROOT), "remote", "-v"])
    status = run_cmd(["git", "-C", str(WORKSPACE_ROOT), "status", "--short"])
    return {
        "branch": (branch.get("stdout") or "").strip(),
        "head": (head.get("stdout") or "").strip(),
        "remote": (remote.get("stdout") or "").strip(),
        "dirty": bool((status.get("stdout") or "").strip()),
        "status_lines": [line for line in (status.get("stdout") or "").splitlines() if line.strip()],
    }


def gateway_summary() -> Dict[str, Any]:
    """
    中文注解：
    - 功能：实现 `gateway_summary` 对应的处理逻辑。
    - 角色：属于本模块中的对外可见逻辑；私有函数通常服务同文件主流程，公共函数通常作为跨模块入口或能力接口。
    - 调用关系：建议结合本文件的模块说明、调用方以及同名相关辅助函数一起阅读。
    """
    status_result = run_cmd(["openclaw", "gateway", "status", "--json"])
    health_result = run_cmd(["openclaw", "gateway", "health", "--json"])
    status = parse_json_output(status_result)
    health = parse_json_output(health_result)
    service_runtime = status.get("service", {}).get("runtime", {})
    rpc = status.get("rpc", {})
    telegram = health.get("channels", {}).get("telegram", {})
    telegram_probe = telegram.get("probe", {}) or {}
    telegram_operational = bool(telegram.get("configured")) and bool(telegram_probe.get("ok"))
    return {
        "service_running": service_runtime.get("status") == "running",
        "rpc_ok": bool(rpc.get("ok")),
        "pid": service_runtime.get("pid"),
        "telegram_configured": bool(telegram.get("configured")),
        "telegram_running": bool(telegram.get("running")),
        "telegram_probe_ok": bool(telegram_probe.get("ok")),
        "telegram_token_source": telegram.get("tokenSource"),
        "telegram_operational": telegram_operational,
        "status_result": status_result,
        "health_result": health_result,
    }


def launch_agent_summary() -> Dict[str, Any]:
    """
    中文注解：
    - 功能：实现 `launch_agent_summary` 对应的处理逻辑。
    - 角色：属于本模块中的对外可见逻辑；私有函数通常服务同文件主流程，公共函数通常作为跨模块入口或能力接口。
    - 调用关系：建议结合本文件的模块说明、调用方以及同名相关辅助函数一起阅读。
    """
    agents: Dict[str, Any] = {}
    for key, label in LAUNCH_AGENTS.items():
        result = run_cmd(["launchctl", "print", f"gui/{os_uid()}/{label}"], timeout=20)
        agents[key] = {
            "label": label,
            "loaded": result.get("ok", False),
            "returncode": result.get("returncode"),
        }
    return agents


def os_uid() -> str:
    """
    中文注解：
    - 功能：实现 `os_uid` 对应的处理逻辑。
    - 角色：属于本模块中的对外可见逻辑；私有函数通常服务同文件主流程，公共函数通常作为跨模块入口或能力接口。
    - 调用关系：建议结合本文件的模块说明、调用方以及同名相关辅助函数一起阅读。
    """
    result = run_cmd(["id", "-u"], timeout=5)
    return (result.get("stdout") or "").strip() or "0"


def runtime_summary() -> Dict[str, Any]:
    """
    中文注解：
    - 功能：实现 `runtime_summary` 对应的处理逻辑。
    - 角色：属于本模块中的对外可见逻辑；私有函数通常服务同文件主流程，公共函数通常作为跨模块入口或能力接口。
    - 调用关系：建议结合本文件的模块说明、调用方以及同名相关辅助函数一起阅读。
    """
    selfheal_state = read_json(SELFHEAL_STATE_PATH, {})
    upstream_watch_state = read_json(UPSTREAM_WATCH_STATE_PATH, {})
    brain_route_count = len(list(BRAIN_ROUTES_ROOT.rglob("*.json"))) if BRAIN_ROUTES_ROOT.exists() else 0
    main_link = read_json(MAIN_LINK_PATH, {})
    return {
        "selfheal_state_exists": SELFHEAL_STATE_PATH.exists(),
        "selfheal_recent": is_recent(selfheal_state.get("last_check_at", ""), 15),
        "selfheal_last_status": selfheal_state.get("last_status", ""),
        "upstream_watch_state_exists": UPSTREAM_WATCH_STATE_PATH.exists(),
        "upstream_watch_recent": is_recent(upstream_watch_state.get("checked_at", ""), 24 * 60 + 30),
        "upstream_watch_report_exists": UPSTREAM_WATCH_REPORT_PATH.exists(),
        "brain_route_count": brain_route_count,
        "main_link_exists": MAIN_LINK_PATH.exists(),
        "main_link_task": main_link.get("task_id", ""),
    }


def _load_session_index() -> Dict[str, Any]:
    """
    中文注解：
    - 功能：读取主 agent 的 sessions 索引，供消息链端到端体检使用。
    - 角色：这是聊天链健康检查的数据入口，统一提供 session key、更新时间和 sessionFile 等元数据。
    - 调用关系：由 `message_pipeline_summary` 调用，不直接参与任务执行。
    """
    return read_json(SESSIONS_INDEX_PATH, {})


def _extract_text_from_content(content: Any) -> str:
    """
    中文注解：
    - 功能：从 OpenClaw transcript message.content 中提取文本，用于判断回复是否真正面向用户。
    - 角色：这是消息质量判断的辅助函数，避免只看到 toolCall/toolResult 就误判成“已经回复”。
    - 调用关系：由 `_session_tail_summary` 调用。
    """
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: List[str] = []
        for item in content:
            if not isinstance(item, dict):
                continue
            if item.get("type") == "text":
                parts.append(str(item.get("text", "")))
        return "\n".join(part for part in parts if part)
    return ""


def _looks_substantive_assistant_text(text: str) -> bool:
    """
    中文注解：
    - 功能：粗略判断 assistant 文本是否属于“真正回复用户”，而不是纯内部状态句或系统噪音。
    - 角色：这是 doctor 的端到端消息链质量判断规则，用来识别“发了但没真正回”。
    - 调用关系：由 `_session_tail_summary` 调用。
    """
    normalized = (text or "").strip()
    if not normalized:
        return False
    low_value_prefixes = (
        "[[reply_to_current]] authoritative task state says",
        "authoritative task state says",
        "[[reply_to_current]] system:",
    )
    lowered = normalized.lower()
    if any(lowered.startswith(prefix) for prefix in low_value_prefixes):
        return False
    return True


def _public_session_tail_summary(summary: Dict[str, Any]) -> Dict[str, Any]:
    """
    中文注解：
    - 功能：返回可公开写入 payload 的会话摘要，剔除内部事件缓存字段。
    - 输入角色：消费 `_session_tail_summary` 的完整结果。
    - 输出角色：提供给 `message_pipeline_summary` 序列化输出，避免泄露内部解析细节。
    """
    return {key: value for key, value in (summary or {}).items() if not str(key).startswith("_")}


def _latest_timed_event(events: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    中文注解：
    - 功能：从事件列表里选出时间最近的一条事件。
    - 输入角色：消费用户/assistant 事件列表。
    - 输出角色：供跨会话消息链对账使用。
    """
    ranked = []
    for event in events:
        dt = parse_iso(str((event or {}).get("timestamp", "")).strip())
        if not dt:
            continue
        ranked.append((dt, event))
    if not ranked:
        return {}
    ranked.sort(key=lambda item: item[0])
    return ranked[-1][1]


def _first_assistant_event_after(
    events: List[Dict[str, Any]],
    pivot: datetime | None,
    *,
    substantive_only: bool = False,
) -> Dict[str, Any]:
    """
    中文注解：
    - 功能：寻找某个用户消息之后最早出现的 assistant 事件，可选择只看“实质回复”。
    - 输入角色：消费跨会话 assistant 事件与用户时间锚点。
    - 输出角色：供 doctor 判断“有没有真正回复用户”与计算回复时延。
    """
    if pivot is None:
        return {}
    ranked = []
    for event in events:
        if substantive_only and not bool((event or {}).get("substantive")):
            continue
        dt = parse_iso(str((event or {}).get("timestamp", "")).strip())
        if not dt or dt < pivot:
            continue
        ranked.append((dt, event))
    if not ranked:
        return {}
    ranked.sort(key=lambda item: item[0])
    return ranked[0][1]


def _doctor_runtime_summary(*, refresh_policy: str = "if_needed") -> Dict[str, Any]:
    """
    中文注解：
    - 功能：读取 canonical system doctor 最近一次运行摘要，让 ops doctor 也能看到全局医生对新能力的监控结果。
    - 输入角色：消费 `system_doctor.py` 写出的 `doctor/last_run.json`。
    - 输出角色：供 `status_payload` 与 `doctor_payload` 聚合显示 acquisition/integration 健康度。
    """
    payload, refresh = _resolve_doctor_runtime_payload(refresh_policy=refresh_policy)
    if not isinstance(payload, dict):
        payload = {}
    acquisition_health = payload.get("acquisition_health", {}) or {}
    adapter_coverage = acquisition_health.get("adapter_coverage", {}) or {}
    integration_health = payload.get("integration_health", {}) or {}
    acquisition_integration = integration_health.get("acquisition_hand", {}) or {}
    conversation_context = integration_health.get("conversation_context", {}) or {}
    reply_projection = integration_health.get("reply_projection", {}) or {}
    conversation_events = integration_health.get("conversation_events", {}) or {}
    execution_events = integration_health.get("execution_events", {}) or {}
    capability_gap = integration_health.get("capability_gap", {}) or {}
    delivery_plane = integration_health.get("delivery_plane", {}) or {}
    skill_action_plane = integration_health.get("skill_action_plane", {}) or {}
    transport_binding = integration_health.get("transport_binding", {}) or {}
    checked_at = str(payload.get("checked_at", "")).strip()
    return {
        "last_run_exists": DOCTOR_LAST_RUN_PATH.exists(),
        "last_run_path": str(DOCTOR_LAST_RUN_PATH),
        "last_run_at": checked_at,
        "last_run_recent": is_recent(checked_at, DOCTOR_REFRESH_MAX_AGE_MINUTES) if checked_at else False,
        "refresh": refresh,
        "acquisition_health": {
            "enabled": bool(acquisition_health.get("enabled")),
            "sites_total": int(adapter_coverage.get("sites_total", 0) or 0),
            "sites_production_ready": int(adapter_coverage.get("sites_production_ready", 0) or 0),
            "sites_attention_required": int(adapter_coverage.get("sites_attention_required", 0) or 0),
            "sites_governed_ready": int(adapter_coverage.get("sites_governed_ready", 0) or 0),
            "sites_authorized_session_ready": int(adapter_coverage.get("sites_authorized_session_ready", 0) or 0),
            "sites_with_evidence_drift": int(adapter_coverage.get("sites_with_evidence_drift", 0) or 0),
            "available_adapter_total": int(adapter_coverage.get("available_adapter_total", 0) or 0),
            "validation_family_total": int(adapter_coverage.get("validation_family_total", 0) or 0),
            "validation_families": list(adapter_coverage.get("validation_families", []) or []),
            "source_trust_tier_total": int(adapter_coverage.get("source_trust_tier_total", 0) or 0),
            "source_trust_tiers": list(adapter_coverage.get("source_trust_tiers", []) or []),
            "browser_runtime_ready_total": int(adapter_coverage.get("browser_runtime_ready_total", 0) or 0),
            "browser_execution_profiles": list(adapter_coverage.get("browser_execution_profiles", []) or []),
            "field_synthesis_contract": bool(acquisition_integration.get("field_synthesis_contract")),
            "delivery_requirements_contract": bool(acquisition_integration.get("delivery_requirements_contract")),
            "source_trust_contract": bool(acquisition_integration.get("source_trust_contract")),
            "release_governance_contract": bool(acquisition_integration.get("release_governance_contract")),
            "release_disclosure_contract": bool(acquisition_integration.get("release_disclosure_contract")),
            "answer_synthesis_contract": bool(acquisition_integration.get("answer_synthesis_contract")),
            "answer_response_contract": bool(acquisition_integration.get("answer_response_contract")),
            "response_handoff_contract": bool(acquisition_integration.get("response_handoff_contract")),
            "execution_truth_contract": bool(acquisition_integration.get("execution_truth_contract")),
            "browser_execution_contract": bool(acquisition_integration.get("browser_execution_contract")),
            "validation_family_contract": bool(acquisition_integration.get("validation_family_contract")),
            "attention_sites_total": len(acquisition_health.get("attention_sites", []) or []),
            "governed_width_score": float(adapter_coverage.get("governed_width_score", 0.0) or 0.0),
            "effective_width_score": float(adapter_coverage.get("effective_width_score", 0.0) or 0.0),
            "evidence_alignment_score": float(adapter_coverage.get("evidence_alignment_score", 0.0) or 0.0),
            "stability_score": float(adapter_coverage.get("stability_score", 0.0) or 0.0),
            "completion_status": str(adapter_coverage.get("completion_status", "")).strip() or "unknown",
            "completion_score": float(adapter_coverage.get("completion_score", 0.0) or 0.0),
            "goal_reached": bool(adapter_coverage.get("goal_reached")),
            "completion_blocker_total": int(adapter_coverage.get("completion_blocker_total", 0) or 0),
            "objective_completion_contract": bool(acquisition_integration.get("objective_completion_contract")),
        },
        "integration_health": {
            "ok": bool(integration_health.get("ok")),
            "coding_chain": str(integration_health.get("coding_chain", "")).strip(),
            "noncoding_chain": str(integration_health.get("noncoding_chain", "")).strip(),
            "acquisition_chain": str(integration_health.get("acquisition_chain", "")).strip(),
            "conversation_context_chain": str(integration_health.get("conversation_context_chain", "")).strip(),
            "reply_projection_chain": str(integration_health.get("reply_projection_chain", "")).strip(),
            "conversation_event_chain": str(integration_health.get("conversation_event_chain", "")).strip(),
            "execution_event_chain": str(integration_health.get("execution_event_chain", "")).strip(),
            "completion_reflection_chain": str(integration_health.get("completion_reflection_chain", "")).strip(),
            "goal_continuation_chain": str(integration_health.get("goal_continuation_chain", "")).strip(),
            "capability_gap_chain": str(integration_health.get("capability_gap_chain", "")).strip(),
            "delivery_plane_chain": str(integration_health.get("delivery_plane_chain", "")).strip(),
            "skill_action_plane_chain": str(integration_health.get("skill_action_plane_chain", "")).strip(),
            "transport_binding_chain": str(integration_health.get("transport_binding_chain", "")).strip(),
            "conversation_context": {
                "instruction_envelope_contract": bool(conversation_context.get("instruction_envelope_contract")),
                "focus_contract": bool(conversation_context.get("focus_contract")),
                "followup_resolution_contract": bool(conversation_context.get("followup_resolution_contract")),
                "control_plane_visibility_contract": bool(conversation_context.get("control_plane_visibility_contract")),
            },
            "reply_projection": {
                "projection_contract_presence": bool(reply_projection.get("projection_contract_presence")),
                "projection_render_parity": bool(reply_projection.get("projection_render_parity")),
                "receipt_projection_persistence": bool(reply_projection.get("receipt_projection_persistence")),
            },
            "conversation_events": {
                "ingress_event_contract": bool(conversation_events.get("ingress_event_contract")),
                "route_event_contract": bool(conversation_events.get("route_event_contract")),
                "reply_event_contract": bool(conversation_events.get("reply_event_contract")),
                "control_plane_visibility_contract": bool(conversation_events.get("control_plane_visibility_contract")),
            },
            "execution_events": {
                "execution_event_contract": bool(execution_events.get("execution_event_contract")),
                "execution_handoff_payload_contract": bool(execution_events.get("execution_handoff_payload_contract")),
                "runtime_mode_session_strategy_contract": bool(execution_events.get("runtime_mode_session_strategy_contract")),
                "control_plane_visibility_contract": bool(execution_events.get("control_plane_visibility_contract")),
            },
            "completion_reflection": {
                "outcome_evaluation_contract": bool((integration_health.get("completion_reflection", {}) or {}).get("outcome_evaluation_contract")),
                "outcome_scorecard_contract": bool((integration_health.get("completion_reflection", {}) or {}).get("outcome_scorecard_contract")),
                "reflection_report_contract": bool((integration_health.get("completion_reflection", {}) or {}).get("reflection_report_contract")),
                "authoritative_summary_visibility_contract": bool((integration_health.get("completion_reflection", {}) or {}).get("authoritative_summary_visibility_contract")),
            },
            "goal_continuation": {
                "goal_continuation_contract": bool((integration_health.get("goal_continuation", {}) or {}).get("goal_continuation_contract")),
                "terminal_reopen_gate_contract": bool((integration_health.get("goal_continuation", {}) or {}).get("terminal_reopen_gate_contract")),
                "authoritative_summary_visibility_contract": bool((integration_health.get("goal_continuation", {}) or {}).get("authoritative_summary_visibility_contract")),
            },
            "capability_gap": {
                "capability_gap_contract": bool(capability_gap.get("capability_gap_contract")),
                "self_heal_ladder_contract": bool(capability_gap.get("self_heal_ladder_contract")),
                "authoritative_summary_visibility_contract": bool(capability_gap.get("authoritative_summary_visibility_contract")),
            },
            "delivery_plane": {
                "delivery_contract_contract": bool(delivery_plane.get("delivery_contract_contract")),
                "receipt_delivery_contract_contract": bool(delivery_plane.get("receipt_delivery_contract_contract")),
                "authoritative_summary_visibility_contract": bool(delivery_plane.get("authoritative_summary_visibility_contract")),
            },
            "skill_action_plane": {
                "skill_action_plane_contract": bool(skill_action_plane.get("skill_action_plane_contract")),
                "runtime_prompt_attachment_contract": bool(skill_action_plane.get("runtime_prompt_attachment_contract")),
                "authoritative_summary_visibility_contract": bool(skill_action_plane.get("authoritative_summary_visibility_contract")),
            },
            "transport_binding": {
                "shared_transport_binding_contract": bool(transport_binding.get("shared_transport_binding_contract")),
                "telegram_binding_delegation_contract": bool(transport_binding.get("telegram_binding_delegation_contract")),
                "openclaw_main_binding_delegation_contract": bool(transport_binding.get("openclaw_main_binding_delegation_contract")),
                "event_chain_parity_contract": bool(transport_binding.get("event_chain_parity_contract")),
            },
        },
    }


def _doctor_runtime_payload_complete(payload: Dict[str, Any]) -> bool:
    """
    中文注解：
    - 功能：判断 canonical doctor 最近一次输出是否已经覆盖当前系统要求的核心契约。
    - 输入角色：消费 `doctor/last_run.json` 或刚刷新得到的 doctor payload。
    - 输出角色：供 status/doctor 决定是否需要触发 canonical doctor 刷新，而不是继续展示结构残缺的旧结果。
    """
    if not isinstance(payload, dict):
        return False
    integration = payload.get("integration_health", {}) or {}
    if not isinstance(integration, dict):
        return False
    if not integration.get("single_doctor_rule"):
        return False
    if not str(integration.get("coding_chain", "")).strip():
        return False
    if not str(integration.get("noncoding_chain", "")).strip():
        return False
    if not str(integration.get("acquisition_chain", "")).strip():
        return False
    if not str(integration.get("conversation_context_chain", "")).strip():
        return False
    if not str(integration.get("reply_projection_chain", "")).strip():
        return False
    if not str(integration.get("conversation_event_chain", "")).strip():
        return False
    if not str(integration.get("execution_event_chain", "")).strip():
        return False
    acquisition_hand = integration.get("acquisition_hand", {}) or {}
    if not isinstance(acquisition_hand, dict) or not acquisition_hand:
        return False
    conversation_context = integration.get("conversation_context", {}) or {}
    if not isinstance(conversation_context, dict) or not conversation_context:
        return False
    reply_projection = integration.get("reply_projection", {}) or {}
    if not isinstance(reply_projection, dict) or not reply_projection:
        return False
    conversation_events = integration.get("conversation_events", {}) or {}
    if not isinstance(conversation_events, dict) or not conversation_events:
        return False
    execution_events = integration.get("execution_events", {}) or {}
    if not isinstance(execution_events, dict) or not execution_events:
        return False
    completion_reflection = integration.get("completion_reflection", {}) or {}
    if not isinstance(completion_reflection, dict) or not completion_reflection:
        return False
    goal_continuation = integration.get("goal_continuation", {}) or {}
    if not isinstance(goal_continuation, dict) or not goal_continuation:
        return False
    capability_gap = integration.get("capability_gap", {}) or {}
    if not isinstance(capability_gap, dict) or not capability_gap:
        return False
    delivery_plane = integration.get("delivery_plane", {}) or {}
    if not isinstance(delivery_plane, dict) or not delivery_plane:
        return False
    skill_action_plane = integration.get("skill_action_plane", {}) or {}
    if not isinstance(skill_action_plane, dict) or not skill_action_plane:
        return False
    transport_binding = integration.get("transport_binding", {}) or {}
    if not isinstance(transport_binding, dict) or not transport_binding:
        return False
    return all(name in acquisition_hand for name in DOCTOR_REQUIRED_ACQUISITION_CONTRACTS) and all(
        name in conversation_context for name in DOCTOR_REQUIRED_CONVERSATION_CONTEXT_CONTRACTS
    ) and all(
        name in reply_projection for name in DOCTOR_REQUIRED_REPLY_PROJECTION_CONTRACTS
    ) and all(
        name in conversation_events for name in DOCTOR_REQUIRED_CONVERSATION_EVENT_CONTRACTS
    ) and all(
        name in execution_events for name in DOCTOR_REQUIRED_EXECUTION_EVENT_CONTRACTS
    ) and all(
        name in completion_reflection for name in DOCTOR_REQUIRED_COMPLETION_REFLECTION_CONTRACTS
    ) and all(
        name in goal_continuation for name in DOCTOR_REQUIRED_GOAL_CONTINUATION_CONTRACTS
    ) and all(
        name in capability_gap for name in DOCTOR_REQUIRED_CAPABILITY_GAP_CONTRACTS
    ) and all(
        name in delivery_plane for name in DOCTOR_REQUIRED_DELIVERY_PLANE_CONTRACTS
    ) and all(
        name in skill_action_plane for name in DOCTOR_REQUIRED_SKILL_ACTION_PLANE_CONTRACTS
    ) and all(
        name in transport_binding for name in DOCTOR_REQUIRED_TRANSPORT_BINDING_CONTRACTS
    )


def _import_run_system_doctor():
    """
    中文注解：
    - 功能：延迟导入 canonical doctor，避免普通 status 聚合在模块导入阶段就绑定重依赖。
    - 输入角色：无显式业务输入，只依赖控制中心模块路径。
    - 输出角色：返回 canonical `run_system_doctor` 入口，供 ops doctor 在需要时刷新权威结果。
    """
    import sys

    if str(CONTROL_CENTER_ROOT) not in sys.path:
        sys.path.insert(0, str(CONTROL_CENTER_ROOT))
    from system_doctor import run_system_doctor

    return run_system_doctor


def _run_canonical_doctor_refresh() -> Dict[str, Any]:
    """
    中文注解：
    - 功能：执行一次 canonical doctor 刷新，把 single-doctor 权威结果重新写回 `last_run.json`。
    - 输入角色：无额外操作参数，沿用 canonical doctor 默认治理阈值。
    - 输出角色：供 status/doctor/upgrade-check 在需要时使用 fresh doctor 结果，而不是继续读陈旧缓存。
    """
    try:
        run_system_doctor = _import_run_system_doctor()
    except Exception as exc:
        return {
            "ok": False,
            "payload": {},
            "error": f"import_system_doctor_failed:{exc}",
        }
    try:
        payload = run_system_doctor()
    except Exception as exc:
        return {
            "ok": False,
            "payload": {},
            "error": f"run_system_doctor_failed:{exc}",
        }
    if not isinstance(payload, dict):
        return {
            "ok": False,
            "payload": {},
            "error": "run_system_doctor_returned_non_dict",
        }
    return {
        "ok": True,
        "payload": payload,
        "error": "",
    }


def _resolve_doctor_runtime_payload(*, refresh_policy: str) -> tuple[Dict[str, Any], Dict[str, Any]]:
    """
    中文注解：
    - 功能：按策略读取 canonical doctor 结果，并在缓存缺失、过旧或结构残缺时自动对账刷新。
    - 输入角色：`refresh_policy` 决定是否永远刷新，还是只在 missing/stale/incomplete 时刷新。
    - 输出角色：返回 doctor payload 与 refresh 元数据，供 status/doctor 解释结果来源与刷新原因。
    """
    payload = read_json(DOCTOR_LAST_RUN_PATH, {})
    if not isinstance(payload, dict):
        payload = {}
    checked_at = str(payload.get("checked_at", "")).strip()
    payload_complete = _doctor_runtime_payload_complete(payload)
    refresh_reason = ""
    should_refresh = False
    if refresh_policy == "always":
        should_refresh = True
        refresh_reason = "explicit"
    elif not DOCTOR_LAST_RUN_PATH.exists():
        should_refresh = True
        refresh_reason = "missing"
    elif not checked_at or not is_recent(checked_at, DOCTOR_REFRESH_MAX_AGE_MINUTES):
        should_refresh = True
        refresh_reason = "stale"
    elif not payload_complete:
        should_refresh = True
        refresh_reason = "incomplete"

    refresh = {
        "attempted": False,
        "ok": False,
        "reason": refresh_reason,
        "source": "cache",
        "error": "",
        "payload_complete": payload_complete,
    }
    if not should_refresh:
        refresh["ok"] = True
        return payload, refresh

    refresh["attempted"] = True
    refresh_result = _run_canonical_doctor_refresh()
    refresh["ok"] = bool(refresh_result.get("ok"))
    refresh["error"] = str(refresh_result.get("error", "")).strip()
    if refresh["ok"]:
        refreshed_payload = refresh_result.get("payload", {}) or {}
        if isinstance(refreshed_payload, dict):
            payload = refreshed_payload
        refresh["source"] = "canonical_refresh"
        refresh["payload_complete"] = _doctor_runtime_payload_complete(payload)
        return payload, refresh
    return payload, refresh


def _session_tail_summary(session_file: Path) -> Dict[str, Any]:
    """
    中文注解：
    - 功能：分析单个会话 transcript 尾部，找出最近用户消息、最近 assistant 回复，以及是否存在内部执行流污染。
    - 角色：这是端到端消息链体检的核心解析器，直接回答“用户发消息后有没有收到真正回复”。
    - 调用关系：由 `message_pipeline_summary` 调用。
    """
    if not session_file.exists():
        return {
            "exists": False,
            "latest_user_at": "",
            "latest_assistant_at": "",
            "assistant_after_latest_user": False,
            "assistant_substantive_after_latest_user": False,
            "internal_flow_leak_detected": False,
            "assistant_preview": "",
            "latest_substantive_assistant_at": "",
            "_user_events": [],
            "_assistant_events": [],
        }
    latest_user_at = ""
    latest_assistant_at = ""
    latest_substantive_assistant_at = ""
    assistant_after_latest_user = False
    assistant_substantive_after_latest_user = False
    internal_flow_leak_detected = False
    pending_internal_flow = False
    assistant_preview = ""
    user_events: List[Dict[str, Any]] = []
    assistant_events: List[Dict[str, Any]] = []
    try:
        lines = session_file.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        lines = []
    for raw in lines[-80:]:
        try:
            obj = json.loads(raw)
        except json.JSONDecodeError:
            continue
        if obj.get("type") != "message":
            continue
        message = obj.get("message") or {}
        role = message.get("role")
        timestamp = obj.get("timestamp") or ""
        content = message.get("content")
        if role == "user":
            latest_user_at = timestamp or latest_user_at
            user_events.append({"timestamp": timestamp})
            assistant_after_latest_user = False
            assistant_substantive_after_latest_user = False
            internal_flow_leak_detected = False
            pending_internal_flow = False
            assistant_preview = ""
            continue
        if role != "assistant":
            continue
        latest_assistant_at = timestamp or latest_assistant_at
        text = _extract_text_from_content(content)
        preview = text.strip().replace("\n", " ")[:240]
        contains_tool_call = isinstance(content, list) and any(
            isinstance(item, dict) and item.get("type") == "toolCall" for item in content
        )
        if contains_tool_call:
            pending_internal_flow = True
        substantive = _looks_substantive_assistant_text(text)
        assistant_events.append(
            {
                "timestamp": timestamp,
                "substantive": substantive,
                "contains_tool_call": contains_tool_call,
                "preview": preview,
            }
        )
        if latest_user_at and (not latest_assistant_at or (timestamp and timestamp >= latest_user_at)):
            assistant_after_latest_user = True
            assistant_preview = preview
            if substantive:
                assistant_substantive_after_latest_user = True
                latest_substantive_assistant_at = timestamp or latest_substantive_assistant_at
                pending_internal_flow = False
    internal_flow_leak_detected = pending_internal_flow and not assistant_substantive_after_latest_user
    return {
        "exists": True,
        "latest_user_at": latest_user_at,
        "latest_assistant_at": latest_assistant_at,
        "latest_substantive_assistant_at": latest_substantive_assistant_at,
        "assistant_after_latest_user": assistant_after_latest_user,
        "assistant_substantive_after_latest_user": assistant_substantive_after_latest_user,
        "internal_flow_leak_detected": internal_flow_leak_detected,
        "assistant_preview": assistant_preview,
        "_user_events": user_events,
        "_assistant_events": assistant_events,
    }


def _telegram_key_is_production(key: str) -> bool:
    normalized = str(key or "").strip().lower()
    if ":telegram:" not in normalized:
        return False
    noisy_tokens = ("smoke", "test", "brain-router", "brain-first")
    return not any(token in normalized for token in noisy_tokens)


def message_pipeline_summary() -> Dict[str, Any]:
    """
    中文注解：
    - 功能：汇总 Telegram -> 主会话 -> assistant 回复 这条端到端消息链的健康状态。
    - 角色：这是这次新增的“消息链自检”层，用于发现用户发消息后无人实质回复、或内部执行流污染会话的问题。
    - 调用关系：由 `status_payload` 与 `doctor_payload` 调用。
    """
    sessions = _load_session_index()
    telegram_keys = [key for key in sessions.keys() if ":telegram:" in key]
    production_telegram_keys = [key for key in telegram_keys if _telegram_key_is_production(key)]
    latest_telegram_key = ""
    latest_telegram_updated_at = 0
    selected_keys = production_telegram_keys or telegram_keys
    for key in selected_keys:
        updated_at = int((sessions.get(key) or {}).get("updatedAt") or 0)
        if updated_at >= latest_telegram_updated_at:
            latest_telegram_updated_at = updated_at
            latest_telegram_key = key
    main_session = sessions.get("agent:main:main") or {}
    main_session_file = Path(main_session.get("sessionFile") or "")
    main_tail = _session_tail_summary(main_session_file) if main_session_file else {}
    latest_telegram = sessions.get(latest_telegram_key) or {}
    latest_telegram_file = Path(latest_telegram.get("sessionFile") or "")
    telegram_tail = _session_tail_summary(latest_telegram_file) if latest_telegram_file else {}
    scoped_user_events: List[Dict[str, Any]] = []
    scoped_assistant_events: List[Dict[str, Any]] = []
    for source_name, tail in (("telegram", telegram_tail), ("main", main_tail)):
        for event in tail.get("_user_events", []) or []:
            scoped_user_events.append({**event, "session": source_name})
        for event in tail.get("_assistant_events", []) or []:
            scoped_assistant_events.append({**event, "session": source_name})

    latest_user_event = _latest_timed_event(scoped_user_events)
    latest_user_iso = str(latest_user_event.get("timestamp", "")).strip()
    latest_user_dt = parse_iso(latest_user_iso)
    first_assistant_after_user = _first_assistant_event_after(scoped_assistant_events, latest_user_dt)
    first_substantive_after_user = _first_assistant_event_after(
        scoped_assistant_events,
        latest_user_dt,
        substantive_only=True,
    )
    latest_assistant_event = _latest_timed_event(scoped_assistant_events)
    latest_assistant_iso = str(latest_assistant_event.get("timestamp", "")).strip()
    reply_gap_seconds = None
    reply_event = first_substantive_after_user or first_assistant_after_user
    reply_dt = parse_iso(str(reply_event.get("timestamp", "")).strip())
    if latest_user_dt and reply_dt:
        reply_gap_seconds = int((reply_dt - latest_user_dt).total_seconds())
    user_wait_seconds = None
    if latest_user_dt:
        user_wait_seconds = int((utc_now() - latest_user_dt).total_seconds())
    internal_flow_leak_detected = bool(
        latest_user_dt
        and any(
            bool((event or {}).get("contains_tool_call"))
            and parse_iso(str((event or {}).get("timestamp", "")).strip())
            and parse_iso(str((event or {}).get("timestamp", "")).strip()) >= latest_user_dt
            for event in scoped_assistant_events
        )
        and not first_substantive_after_user
    )
    latest_user_source = str(latest_user_event.get("session", "")).strip()
    reply_source = str(reply_event.get("session", "")).strip()
    return {
        "sessions_index_exists": SESSIONS_INDEX_PATH.exists(),
        "telegram_session_count": len(telegram_keys),
        "latest_telegram_key": latest_telegram_key,
        "latest_telegram_updated_at": latest_telegram_updated_at,
        "main_session_file": str(main_session_file) if main_session_file else "",
        "latest_user_at": latest_user_iso,
        "latest_assistant_at": latest_assistant_iso,
        "user_wait_seconds": user_wait_seconds,
        "reply_gap_seconds": reply_gap_seconds,
        "assistant_after_latest_user": bool(first_assistant_after_user),
        "assistant_substantive_after_latest_user": bool(first_substantive_after_user),
        "internal_flow_leak_detected": internal_flow_leak_detected,
        "assistant_preview": str((first_substantive_after_user or first_assistant_after_user).get("preview", "")).strip(),
        "latest_user_source_session": latest_user_source,
        "reply_source_session": reply_source,
        "cross_session_reply_detected": bool(
            latest_user_source and reply_source and latest_user_source != reply_source and first_substantive_after_user
        ),
        "telegram_tail": _public_session_tail_summary(telegram_tail),
        "main_tail": _public_session_tail_summary(main_tail),
    }


def status_payload(*, refresh_doctor: bool = False) -> Dict[str, Any]:
    """
    中文注解：
    - 功能：实现 `status_payload` 对应的处理逻辑。
    - 角色：属于本模块中的对外可见逻辑；私有函数通常服务同文件主流程，公共函数通常作为跨模块入口或能力接口。
    - 调用关系：建议结合本文件的模块说明、调用方以及同名相关辅助函数一起阅读。
    """
    control_plane_summary = {}
    scheduler_policy = {}
    try:
        import sys

        if str(CONTROL_CENTER_ROOT) not in sys.path:
            sys.path.insert(0, str(CONTROL_CENTER_ROOT))
        from control_plane_builder import build_control_plane

        control_plane = build_control_plane()
        control_plane_summary = (control_plane.get("system_snapshot", {}) or {}).get("summary", {}) or {}
        scheduler_policy = control_plane.get("project_scheduler_policy", {}) or {}
        if control_plane.get("crawler_remediation_scheduler_state"):
            scheduler_policy["crawler_remediation_state"] = control_plane.get("crawler_remediation_scheduler_state", {}) or {}
        if control_plane.get("seller_bulk_scheduler_state"):
            scheduler_policy["seller_bulk_state"] = control_plane.get("seller_bulk_scheduler_state", {}) or {}
        if control_plane.get("cross_market_arbitrage_scheduler_state"):
            scheduler_policy["cross_market_arbitrage_state"] = control_plane.get("cross_market_arbitrage_scheduler_state", {}) or {}
    except Exception as exc:
        scheduler_policy = {"error": str(exc)}
    return {
        "checked_at": utc_now_iso(),
        "workspace": str(WORKSPACE_ROOT),
        "git": git_summary(),
        "gateway": gateway_summary(),
        "launch_agents": launch_agent_summary(),
        "runtime": runtime_summary(),
        "message_pipeline": message_pipeline_summary(),
        "doctor_runtime": _doctor_runtime_summary(
            refresh_policy="always" if refresh_doctor else "if_needed"
        ),
        "control_plane_summary": control_plane_summary,
        "project_scheduler_policy": scheduler_policy,
    }


def doctor_payload(*, refresh_doctor: bool = True) -> Dict[str, Any]:
    """
    中文注解：
    - 功能：实现 `doctor_payload` 对应的处理逻辑。
    - 角色：属于本模块中的对外可见逻辑；私有函数通常服务同文件主流程，公共函数通常作为跨模块入口或能力接口。
    - 调用关系：建议结合本文件的模块说明、调用方以及同名相关辅助函数一起阅读。

    Single-doctor rule:
    - JinClaw only has one canonical doctor payload path.
    - New subsystem monitoring should aggregate into this payload rather than creating a peer doctor authority.
    """
    payload = status_payload(refresh_doctor=refresh_doctor)
    issues: List[str] = []
    warnings: List[str] = []

    if not payload["gateway"]["service_running"]:
        issues.append("openclaw_gateway_not_running")
    if not payload["gateway"]["rpc_ok"]:
        issues.append("openclaw_gateway_rpc_unhealthy")

    for key, agent in payload["launch_agents"].items():
        if not agent["loaded"]:
            issues.append(f"launch_agent_missing:{key}")

    runtime = payload["runtime"]
    message_pipeline = payload["message_pipeline"]
    doctor_runtime = payload.get("doctor_runtime", {}) or {}
    refresh = doctor_runtime.get("refresh", {}) or {}
    if not runtime["selfheal_state_exists"]:
        issues.append("selfheal_state_missing")
    elif not runtime["selfheal_recent"]:
        warnings.append("selfheal_not_recent")

    if not runtime["upstream_watch_state_exists"]:
        issues.append("upstream_watch_state_missing")
    elif not runtime["upstream_watch_recent"]:
        warnings.append("upstream_watch_not_recent")

    if not runtime["main_link_exists"]:
        issues.append("main_session_link_missing")
    if runtime["brain_route_count"] == 0:
        warnings.append("no_brain_routes_recorded_yet")

    if payload["gateway"]["telegram_configured"] and not payload["gateway"]["telegram_probe_ok"]:
        issues.append("telegram_probe_unhealthy")
    if not (CONTROL_CENTER_ROOT / "brain_router.py").exists():
        issues.append("brain_router_missing")
    if not (CONTROL_CENTER_ROOT / "brain_enforcer.py").exists():
        issues.append("brain_enforcer_missing")
    if not (AUTONOMY_ROOT / "runtime_service.py").exists():
        issues.append("autonomy_runtime_missing")

    if not message_pipeline["sessions_index_exists"]:
        issues.append("sessions_index_missing")
    if payload["gateway"]["telegram_operational"] and message_pipeline["telegram_session_count"] == 0:
        warnings.append("telegram_operational_but_no_telegram_sessions")
    if (
        payload["gateway"]["telegram_operational"]
        and message_pipeline["latest_user_at"]
        and message_pipeline["user_wait_seconds"] is not None
        and message_pipeline["user_wait_seconds"] > 180
        and not message_pipeline["assistant_substantive_after_latest_user"]
    ):
        issues.append("telegram_user_message_without_substantive_reply")
    if message_pipeline["internal_flow_leak_detected"]:
        warnings.append("main_session_contains_internal_tool_flow")
    if not doctor_runtime.get("last_run_exists"):
        warnings.append("system_doctor_last_run_missing")
    elif not doctor_runtime.get("last_run_recent"):
        warnings.append("system_doctor_last_run_not_recent")
    if refresh_doctor and refresh.get("attempted") and not refresh.get("ok"):
        issues.append("system_doctor_refresh_failed")
    if doctor_runtime.get("last_run_exists") and not ((doctor_runtime.get("integration_health", {}) or {}).get("ok")):
        warnings.append("system_doctor_integration_health_attention")

    payload["issues"] = issues
    payload["warnings"] = warnings
    payload["scheduler"] = payload.get("project_scheduler_policy", {}) or {}
    payload["ok"] = not issues
    return payload


def upgrade_check_payload(*, refresh_doctor: bool = True) -> Dict[str, Any]:
    """
    中文注解：
    - 功能：实现 `upgrade_check_payload` 对应的处理逻辑。
    - 角色：属于本模块中的对外可见逻辑；私有函数通常服务同文件主流程，公共函数通常作为跨模块入口或能力接口。
    - 调用关系：建议结合本文件的模块说明、调用方以及同名相关辅助函数一起阅读。
    """
    watch_run = run_cmd(["python3", str(UPSTREAM_WATCH_SCRIPT), "--once"], timeout=60)
    watch_run_payload = parse_json_output(watch_run)
    doctor = doctor_payload(refresh_doctor=refresh_doctor)
    upstream_watch_state = read_json(UPSTREAM_WATCH_STATE_PATH, {})
    changed: List[Dict[str, Any]] = []
    for repo_id, snapshot in (upstream_watch_state.get("repos") or {}).items():
        changed.append(
            {
                "id": repo_id,
                "repo": snapshot.get("repo", ""),
                "latest_release": (snapshot.get("latest_release") or {}).get("tag_name", ""),
                "pushed_at": snapshot.get("pushed_at", ""),
            }
        )
    return {
        "checked_at": utc_now_iso(),
        "watch_run": {
            "ok": watch_run.get("ok"),
            "returncode": watch_run.get("returncode"),
            "stdout": watch_run.get("stdout"),
            "stderr": watch_run.get("stderr"),
            "fetch_mode": watch_run_payload.get("fetch_mode", ""),
            "degraded": bool(watch_run_payload.get("degraded")),
            "degraded_sources": watch_run_payload.get("degraded_sources") or [],
            "repo_count": watch_run_payload.get("repo_count"),
        },
        "doctor": doctor,
        "git": git_summary(),
        "upstream_report_path": str(UPSTREAM_WATCH_REPORT_PATH),
        "tracked_upstreams": changed,
    }


def print_payload(payload: Dict[str, Any]) -> None:
    """
    中文注解：
    - 功能：实现 `print_payload` 对应的处理逻辑。
    - 角色：属于本模块中的对外可见逻辑；私有函数通常服务同文件主流程，公共函数通常作为跨模块入口或能力接口。
    - 调用关系：建议结合本文件的模块说明、调用方以及同名相关辅助函数一起阅读。
    """
    print(json.dumps(payload, ensure_ascii=False, indent=2))


def main() -> int:
    """
    中文注解：
    - 功能：实现 `main` 对应的处理逻辑。
    - 角色：属于本模块中的对外可见逻辑；私有函数通常服务同文件主流程，公共函数通常作为跨模块入口或能力接口。
    - 调用关系：建议结合本文件的模块说明、调用方以及同名相关辅助函数一起阅读。
    """
    parser = argparse.ArgumentParser(description="JinClaw local ops commands")
    parser.add_argument("command", choices=["status", "doctor", "upgrade-check"])
    args = parser.parse_args()

    if args.command == "status":
        print_payload(status_payload())
        return 0
    if args.command == "doctor":
        payload = doctor_payload(refresh_doctor=True)
        print_payload(payload)
        return 0 if payload["ok"] else 1
    payload = upgrade_check_payload(refresh_doctor=True)
    print_payload(payload)
    return 0 if payload["doctor"]["ok"] and payload["watch_run"]["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
