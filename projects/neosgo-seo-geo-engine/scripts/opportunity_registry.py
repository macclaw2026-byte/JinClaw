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
from datetime import datetime, timezone
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


def _topic_family_from_item(item: dict[str, Any]) -> str:
    return str(item.get("topic_key") or item.get("slug") or "general").strip()


def _days_since(iso_value: str) -> int | None:
    value = str(iso_value or "").strip()
    if not value:
        return None
    try:
        ts = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    now = datetime.now(timezone.utc)
    return max(0, int((now - ts).total_seconds() // 86400))


def _recommended_action(
    *,
    note_exists: bool,
    status: str,
    clicks: float,
    impressions: float,
    geo_gap: int,
    freshness_days: int | None,
) -> str:
    if not note_exists:
        return "create"
    if status != "PUBLISHED":
        return "stabilize_draft"
    if impressions > 0 and clicks <= 0:
        return "refresh_ctr"
    if geo_gap > 0 and clicks > 0:
        return "build_geo"
    if freshness_days is not None and freshness_days >= 45:
        return "refresh_content"
    if clicks > 0:
        return "expand"
    return "monitor"


def build_opportunity_registry(
    *,
    backlog: list[dict[str, Any]],
    notes_by_slug: dict[str, dict[str, Any]],
    feedback_summary: dict[str, Any],
    geo_targets: list[dict[str, Any]],
) -> dict[str, Any]:
    topic_note_counts: dict[str, int] = defaultdict(int)
    for item in backlog:
        topic_note_counts[_topic_family_from_item(item)] += 1

    slug_metrics = dict(feedback_summary.get("slug_metrics") or {})
    topic_metrics = dict(feedback_summary.get("topic_metrics") or {})
    geo_target_count = len([item for item in geo_targets if isinstance(item, dict)])
    registry_items: list[dict[str, Any]] = []

    for item in backlog:
        slug = str(item.get("slug") or "").strip()
        topic = _topic_family_from_item(item)
        note = dict(notes_by_slug.get(slug) or {})
        note_exists = bool(note)
        status = str(note.get("status") or "MISSING").upper()
        note_count_payload = dict(note.get("_count") or {})
        geo_count = _safe_int(note_count_payload.get("geoVariants"))
        revisions = _safe_int(note_count_payload.get("revisions"))
        slug_perf = dict(slug_metrics.get(slug) or {})
        topic_perf = dict(topic_metrics.get(topic) or {})
        clicks = _safe_float(slug_perf.get("clicks"))
        impressions = _safe_float(slug_perf.get("impressions"))
        ctr = _safe_float(slug_perf.get("ctr"))
        if ctr <= 0 and clicks > 0 and impressions > 0:
            ctr = clicks / impressions
        conversions = _safe_float(slug_perf.get("conversionRate"))
        query_impressions = _safe_float(topic_perf.get("queryImpressions"))
        freshness_days = _days_since(str(note.get("updatedAt") or note.get("publishedAt") or note.get("createdAt") or ""))
        geo_gap = max(0, geo_target_count - geo_count) if geo_target_count else 0
        action = _recommended_action(
            note_exists=note_exists,
            status=status,
            clicks=clicks,
            impressions=impressions,
            geo_gap=geo_gap,
            freshness_days=freshness_days,
        )
        action_score = round(
            clicks * 3.0
            + impressions * 0.05
            + conversions * 100.0
            + max(0, geo_gap) * 2.0
            + (8.0 if action == "create" else 6.0 if action == "refresh_ctr" else 5.0 if action == "build_geo" else 3.0 if action == "refresh_content" else 1.0),
            2,
        )
        registry_items.append(
            {
                "slug": slug,
                "topic": topic,
                "title": item.get("title"),
                "note_exists": note_exists,
                "status": status,
                "clicks": round(clicks, 2),
                "impressions": round(impressions, 2),
                "ctr": round(ctr, 4),
                "conversion_rate": round(conversions, 4),
                "topic_query_impressions": round(query_impressions, 2),
                "geo_variant_count": geo_count,
                "geo_gap": geo_gap,
                "revision_count": revisions,
                "freshness_days": freshness_days,
                "topic_note_count": topic_note_counts.get(topic, 0),
                "recommended_action": action,
                "action_score": action_score,
            }
        )

    registry_items.sort(key=lambda row: (row["action_score"], row["impressions"], row["clicks"]), reverse=True)
    return {
        "geo_target_count": geo_target_count,
        "item_count": len(registry_items),
        "items": registry_items,
        "top_actions": registry_items[:10],
    }
