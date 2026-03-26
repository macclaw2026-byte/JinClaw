#!/usr/bin/env python3

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict


ACTIVE_STATUSES = {"created", "planning", "running", "waiting_external", "blocked", "recovering", "verifying", "learning"}
TERMINAL_STATUSES = {"completed", "failed"}


def _seconds_since(iso_text: str) -> float:
    if not iso_text:
        return 10**9
    try:
        dt = datetime.fromisoformat(str(iso_text).replace("Z", "+00:00"))
    except ValueError:
        return 10**9
    return max(0.0, (datetime.now(timezone.utc) - dt).total_seconds())


def classify_task_lifecycle(state: Dict[str, Any], *, warm_after_seconds: int = 24 * 3600, archive_after_seconds: int = 30 * 24 * 3600) -> Dict[str, Any]:
    status = str(state.get("status", "unknown")).strip()
    next_action = str(state.get("next_action", "")).strip()
    metadata = state.get("metadata", {}) or {}
    blockers = [str(item).strip() for item in state.get("blockers", []) if str(item).strip()]
    doctor_takeover = metadata.get("doctor_takeover", {}) or {}
    updated_at = str(state.get("last_update_at", "")).strip()
    completed_or_failed_at = str(metadata.get("completion_notice_sent_at", "") or state.get("last_success_at", "") or updated_at).strip()
    age_seconds = _seconds_since(completed_or_failed_at if status in TERMINAL_STATUSES else updated_at)

    quarantine_reasons = {
        "repair_invalid_contract",
        "repair_invalid_state",
        "repair_invalid_execution",
        "contract_quarantine_required",
    }
    quarantine_markers = {
        "contract_quarantined",
        "invalid_contract",
        "invalid_state",
        "isolated_runtime_failure",
    }

    if (
        metadata.get("quarantined") is True
        or next_action in quarantine_reasons
        or any(marker in next_action for marker in quarantine_markers)
        or any(any(marker in blocker for marker in quarantine_markers) for blocker in blockers)
    ):
        tier = "quarantine"
        reason = "quarantine_marker_detected"
    elif doctor_takeover.get("active") is True or status in ACTIVE_STATUSES:
        tier = "active"
        reason = "status_requires_active_supervision"
    elif status in TERMINAL_STATUSES:
        if age_seconds >= archive_after_seconds:
            tier = "archive"
            reason = "terminal_task_aged_out_of_warm_window"
        else:
            tier = "warm"
            reason = "recent_terminal_task_retained_for_reference"
    else:
        tier = "warm"
        reason = "non_terminal_unknown_state_retained_for_reference"

    return {
        "tier": tier,
        "reason": reason,
        "age_seconds": age_seconds,
        "status": status,
        "doctor_takeover_active": doctor_takeover.get("active") is True,
    }

