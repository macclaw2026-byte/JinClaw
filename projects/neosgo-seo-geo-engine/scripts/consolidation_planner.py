#!/usr/bin/env python3
# RULES-FIRST NOTICE:
# Before modifying this file, first read:
# - `JINCLAW_CONSTITUTION.md`
# - `AI_OPTIMIZATION_FRAMEWORK.md`
# Follow the constitution and framework:
# brain-first, one-doctor, fail-closed, evidence-over-narration,
# validate locally, then use the required PR workflow.
from __future__ import annotations

from collections import defaultdict
from typing import Any


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        if value in (None, ""):
            return default
        return float(value)
    except Exception:
        return default


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        if value in (None, ""):
            return default
        return int(float(value))
    except Exception:
        return default


def build_consolidation_plan(opportunity_registry: dict[str, Any]) -> dict[str, Any]:
    rows = [dict(item) for item in list(opportunity_registry.get("items") or []) if isinstance(item, dict)]
    by_topic: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        if not row.get("note_exists"):
            continue
        topic = str(row.get("topic") or "general").strip()
        by_topic[topic].append(row)

    merge_candidates: list[dict[str, Any]] = []
    redirect_candidates: list[dict[str, Any]] = []
    prune_candidates: list[dict[str, Any]] = []

    for topic, topic_rows in by_topic.items():
        topic_rows.sort(
            key=lambda row: (
                _safe_float(row.get("clicks"), 0.0),
                _safe_float(row.get("impressions"), 0.0),
                _safe_float(row.get("action_score"), 0.0),
            ),
            reverse=True,
        )
        primary = topic_rows[0] if topic_rows else {}
        for row in topic_rows[1:]:
            clicks = _safe_float(row.get("clicks"))
            impressions = _safe_float(row.get("impressions"))
            freshness_days = row.get("freshness_days")
            if freshness_days is None:
                freshness_days = 0
            freshness_days = _safe_int(freshness_days)
            if clicks <= 0 and impressions <= 20 and freshness_days >= 60:
                prune_candidates.append(
                    {
                        "slug": row.get("slug"),
                        "topic": topic,
                        "reason": "low_signal_and_stale",
                        "freshness_days": freshness_days,
                        "clicks": clicks,
                        "impressions": impressions,
                    }
                )
                continue
            if clicks <= 0 and impressions >= 20:
                redirect_candidates.append(
                    {
                        "slug": row.get("slug"),
                        "topic": topic,
                        "target_slug": primary.get("slug"),
                        "reason": "visibility_without_clicks",
                        "clicks": clicks,
                        "impressions": impressions,
                    }
                )
                continue
            if primary and primary.get("slug") != row.get("slug"):
                merge_candidates.append(
                    {
                        "slug": row.get("slug"),
                        "topic": topic,
                        "target_slug": primary.get("slug"),
                        "reason": "secondary_topic_cluster_member",
                        "clicks": clicks,
                        "impressions": impressions,
                    }
                )

    return {
        "topic_cluster_count": len(by_topic),
        "merge_candidates": merge_candidates,
        "redirect_candidates": redirect_candidates,
        "prune_candidates": prune_candidates,
    }
