#!/usr/bin/env python3
# RULES-FIRST NOTICE:
# Before modifying this file, first read:
# - `JINCLAW_CONSTITUTION.md`
# - `AI_OPTIMIZATION_FRAMEWORK.md`
# Follow the constitution and framework:
# brain-first, one-doctor, fail-closed, evidence-over-narration,
# validate locally, then use the required PR workflow.
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any


def _parse_iso(raw: str) -> datetime | None:
    value = str(raw or "").strip()
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def _days_since(raw: str) -> int | None:
    ts = _parse_iso(raw)
    if not ts:
        return None
    return max(0, int((datetime.now(timezone.utc) - ts).total_seconds() // 86400))


def build_maintenance_plan(
    *,
    opportunity_registry: dict[str, Any],
    state: dict[str, Any],
) -> dict[str, Any]:
    rows = [dict(item) for item in list(opportunity_registry.get("items") or []) if isinstance(item, dict)]
    stale_rows = [row for row in rows if row.get("freshness_days") is not None and int(row.get("freshness_days") or 0) >= 45]
    low_ctr_rows = [row for row in rows if float(row.get("impressions") or 0) >= 50 and float(row.get("clicks") or 0) <= 0]
    geo_gap_rows = [row for row in rows if int(row.get("geo_gap") or 0) > 0]

    weekly_last = _days_since(str((state.get("maintenance_state") or {}).get("last_weekly_run_at") or ""))
    monthly_last = _days_since(str((state.get("maintenance_state") or {}).get("last_monthly_run_at") or ""))
    weekly_due = weekly_last is None or weekly_last >= 7
    monthly_due = monthly_last is None or monthly_last >= 30

    weekly_actions: list[dict[str, Any]] = []
    monthly_actions: list[dict[str, Any]] = []

    if weekly_due:
        if low_ctr_rows:
            weekly_actions.append(
                {
                    "type": "ctr_packaging_review",
                    "count": len(low_ctr_rows),
                    "slugs": [row["slug"] for row in low_ctr_rows[:10]],
                }
            )
        if stale_rows:
            weekly_actions.append(
                {
                    "type": "stale_content_refresh_review",
                    "count": len(stale_rows),
                    "slugs": [row["slug"] for row in stale_rows[:10]],
                }
            )
    if monthly_due:
        if geo_gap_rows:
            monthly_actions.append(
                {
                    "type": "geo_gap_cluster_review",
                    "count": len(geo_gap_rows),
                    "slugs": [row["slug"] for row in geo_gap_rows[:10]],
                }
            )
        if stale_rows:
            monthly_actions.append(
                {
                    "type": "merge_or_prune_review",
                    "count": len(stale_rows),
                    "slugs": [row["slug"] for row in stale_rows[:10]],
                }
            )

    return {
        "weekly_due": weekly_due,
        "monthly_due": monthly_due,
        "last_weekly_run_days_ago": weekly_last,
        "last_monthly_run_days_ago": monthly_last,
        "weekly_actions": weekly_actions,
        "monthly_actions": monthly_actions,
    }
