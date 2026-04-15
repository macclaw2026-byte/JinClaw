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


def _scorecard_map(scorecard: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {
        str(item.get("slug") or "").strip(): dict(item)
        for item in list(scorecard.get("items") or []) if isinstance(item, dict) and str(item.get("slug") or "").strip()
    }


def build_maintenance_execution_packet(
    *,
    maintenance_plan: dict[str, Any],
    post_publish_scorecard: dict[str, Any],
    consolidation_plan: dict[str, Any],
) -> dict[str, Any]:
    """把周/月维护计划转成当前 run 可以直接消费的执行包。"""
    scorecard_by_slug = _scorecard_map(post_publish_scorecard)
    merge_candidates = {
        str(item.get("slug") or "").strip(): dict(item)
        for item in list(consolidation_plan.get("merge_candidates") or []) if isinstance(item, dict)
    }
    redirect_candidates = {
        str(item.get("slug") or "").strip(): dict(item)
        for item in list(consolidation_plan.get("redirect_candidates") or []) if isinstance(item, dict)
    }
    prune_candidates = {
        str(item.get("slug") or "").strip(): dict(item)
        for item in list(consolidation_plan.get("prune_candidates") or []) if isinstance(item, dict)
    }

    ready_actions: list[dict[str, Any]] = []
    deferred_actions: list[dict[str, Any]] = []

    for window, actions in (
        ("weekly", list(maintenance_plan.get("weekly_actions") or [])),
        ("monthly", list(maintenance_plan.get("monthly_actions") or [])),
    ):
        due = bool(maintenance_plan.get(f"{window}_due"))
        for action in actions:
            action_type = str(action.get("type") or "").strip()
            slugs = [str(slug).strip() for slug in list(action.get("slugs") or []) if str(slug).strip()]
            packet_row = {
                "window": window,
                "type": action_type,
                "count": int(action.get("count") or len(slugs)),
                "slugs": slugs,
                "priority": "normal",
                "evidence": [],
            }
            for slug in slugs[:10]:
                score_row = dict(scorecard_by_slug.get(slug) or {})
                if score_row:
                    packet_row["evidence"].append(
                        {
                            "slug": slug,
                            "band": score_row.get("performance_band"),
                            "aggregate_score": score_row.get("aggregate_score"),
                            "recommended_action": score_row.get("recommended_action"),
                        }
                    )
            if action_type == "merge_or_prune_review":
                packet_row["priority"] = "high"
                packet_row["merge_candidates"] = [merge_candidates[slug] for slug in slugs if slug in merge_candidates][:10]
                packet_row["prune_candidates"] = [prune_candidates[slug] for slug in slugs if slug in prune_candidates][:10]
            elif action_type == "ctr_packaging_review":
                packet_row["priority"] = "high"
                packet_row["redirect_candidates"] = [redirect_candidates[slug] for slug in slugs if slug in redirect_candidates][:10]
            elif action_type in {"stale_content_refresh_review", "geo_gap_cluster_review"}:
                packet_row["priority"] = "medium"

            if due:
                ready_actions.append(packet_row)
            else:
                deferred_actions.append(packet_row)

    ready_actions.sort(key=lambda item: (0 if item.get("priority") == "high" else 1, item.get("window"), item.get("type")))
    return {
        "enabled": True,
        "weekly_due": bool(maintenance_plan.get("weekly_due")),
        "monthly_due": bool(maintenance_plan.get("monthly_due")),
        "ready_action_count": len(ready_actions),
        "deferred_action_count": len(deferred_actions),
        "ready_actions": ready_actions,
        "deferred_actions": deferred_actions,
    }
