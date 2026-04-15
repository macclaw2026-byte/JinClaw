#!/usr/bin/env python3
# RULES-FIRST NOTICE:
# Before modifying this file, first read:
# - `JINCLAW_CONSTITUTION.md`
# - `AI_OPTIMIZATION_FRAMEWORK.md`
# Follow the constitution and framework:
# brain-first, one-doctor, fail-closed, evidence-over-narration,
# validate locally, then use the required PR workflow.
from __future__ import annotations

from typing import Any


def _priority_rank(action: str) -> int:
    mapping = {
        "create": 0,
        "refresh_ctr": 1,
        "build_geo": 2,
        "refresh_content": 3,
        "expand": 4,
        "stabilize_draft": 5,
        "monitor": 6,
    }
    return mapping.get(str(action or "").strip(), 9)


def build_page_action_plan(
    *,
    opportunity_registry: dict[str, Any],
    create_limit: int,
    geo_limit: int,
) -> dict[str, Any]:
    rows = [dict(item) for item in list(opportunity_registry.get("items") or []) if isinstance(item, dict)]
    rows.sort(key=lambda row: (_priority_rank(str(row.get("recommended_action") or "")), -float(row.get("action_score") or 0.0)))

    create_used = 0
    geo_used = 0
    selected: list[dict[str, Any]] = []
    skipped: list[dict[str, Any]] = []
    action_by_slug: dict[str, dict[str, Any]] = {}

    for row in rows:
        slug = str(row.get("slug") or "").strip()
        if not slug:
            continue
        action = str(row.get("recommended_action") or "monitor").strip()
        execute = False
        skip_reason = ""
        if action == "create":
            if create_used < int(create_limit):
                execute = True
                create_used += 1
            else:
                skip_reason = "create_limit_reached"
        elif action == "build_geo":
            if geo_used < int(geo_limit):
                execute = True
                geo_used += 1
            else:
                skip_reason = "geo_limit_reached"
        elif action in {"refresh_ctr", "refresh_content", "expand", "stabilize_draft"}:
            execute = True
        else:
            skip_reason = "monitor_only"

        record = {
            "slug": slug,
            "recommended_action": action,
            "action_score": row.get("action_score", 0),
            "status": row.get("status"),
            "execute_this_run": execute,
            "skip_reason": skip_reason,
        }
        action_by_slug[slug] = record
        if execute:
            selected.append(record)
        else:
            skipped.append(record)

    return {
        "selected_actions": selected,
        "skipped_actions": skipped,
        "action_by_slug": action_by_slug,
        "create_slots_used": create_used,
        "geo_slots_used": geo_used,
    }
