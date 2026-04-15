#!/usr/bin/env python3
# RULES-FIRST NOTICE:
# Before modifying this file, first read:
# - `JINCLAW_CONSTITUTION.md`
# - `AI_OPTIMIZATION_FRAMEWORK.md`
# Follow the constitution and framework:
# brain-first, one-doctor, fail-closed, evidence-over-narration,
# validate locally, then use the required PR workflow.
from __future__ import annotations

from pathlib import Path
from typing import Any


DEFAULT_REQUIRED_ARTIFACTS = [
    "report_markdown",
    "report_json",
    "opportunity_registry_json",
    "page_action_plan_json",
    "maintenance_plan_json",
    "maintenance_execution_packet_json",
    "consolidation_plan_json",
    "post_publish_scorecard_json",
    "technical_release_gate_json",
]


def _delivery_ok(deliveries: list[dict[str, Any]]) -> bool:
    if not deliveries:
        return False
    return all(int(item.get("returncode", 1)) == 0 for item in deliveries)


def _artifact_status(artifacts: dict[str, str], required: list[str]) -> tuple[list[dict[str, Any]], list[str]]:
    rows: list[dict[str, Any]] = []
    missing: list[str] = []
    for key in required:
        path = str(artifacts.get(key) or "").strip()
        exists = bool(path) and Path(path).exists()
        rows.append({"key": key, "path": path, "exists": exists})
        if not exists:
            missing.append(key)
    return rows, missing


def build_delivery_proof(
    *,
    result: dict[str, Any],
    artifacts: dict[str, str],
    delivery_contract: dict[str, Any],
    deliveries: list[dict[str, Any]],
) -> dict[str, Any]:
    """生成 SEO/GEO 每轮运行后的可检测交付证明。"""
    required = [
        str(item).strip()
        for item in list(delivery_contract.get("required_artifacts") or DEFAULT_REQUIRED_ARTIFACTS)
        if str(item).strip()
    ]
    artifact_rows, missing_artifacts = _artifact_status(artifacts, required)
    telegram_required = bool(delivery_contract.get("telegram_required", True))
    telegram_ok = _delivery_ok(deliveries)
    scorecard = dict(result.get("post_publish_scorecard") or {})
    maintenance_packet = dict(result.get("maintenance_execution_packet") or {})
    blocked = bool(result.get("blocked"))
    proof_ok = (
        not blocked
        and not missing_artifacts
        and (telegram_ok or not telegram_required)
        and bool(scorecard.get("enabled"))
        and bool(maintenance_packet.get("enabled"))
    )
    next_window = {
        "cadence": delivery_contract.get("cadence", "daily"),
        "launch_agent_label": delivery_contract.get("launch_agent_label", "ai.jinclaw.neosgo-seo-geo-daily"),
        "start_calendar_interval": delivery_contract.get("start_calendar_interval") or {"hour": 6, "minute": 0},
        "continues_after_success": True,
    }
    return {
        "enabled": True,
        "ok": proof_ok,
        "run_id": result.get("run_id"),
        "generated_at": result.get("generated_at"),
        "blocked": blocked,
        "artifact_status": artifact_rows,
        "missing_artifacts": missing_artifacts,
        "telegram_required": telegram_required,
        "telegram_delivery_ok": telegram_ok,
        "delivery_count": len(deliveries),
        "scorecard_ready": bool(scorecard.get("enabled")),
        "dual_truth_ready": bool(scorecard.get("dual_truth_ready")),
        "maintenance_packet_ready": bool(maintenance_packet.get("enabled")),
        "maintenance_ready_action_count": int(maintenance_packet.get("ready_action_count", 0) or 0),
        "next_window": next_window,
        "goal_status": "continuous_delivery_ready" if proof_ok else "needs_attention",
    }
