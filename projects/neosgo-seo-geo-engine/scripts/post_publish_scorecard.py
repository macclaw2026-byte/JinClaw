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


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        if value in (None, ""):
            return default
        return float(value)
    except Exception:
        return default


def _discoverability_score(impressions: float, ctr: float, clicks: float) -> float:
    return min(100.0, impressions * 0.12 + ctr * 500.0 + clicks * 2.5)


def _engagement_score(page_views: float, unique_visitors: float, engagement_score: float) -> float:
    return min(100.0, page_views * 0.18 + unique_visitors * 0.25 + engagement_score * 1.6)


def _conversion_score(conversion_rate: float, feedback_score: float) -> float:
    return min(100.0, conversion_rate * 1000.0 + feedback_score * 10.0)


def _freshness_score(freshness_days: int | None) -> float:
    if freshness_days is None:
        return 40.0
    if freshness_days <= 14:
        return 100.0
    if freshness_days <= 30:
        return 82.0
    if freshness_days <= 45:
        return 68.0
    if freshness_days <= 60:
        return 54.0
    if freshness_days <= 90:
        return 36.0
    return 20.0


def _band(aggregate_score: float) -> str:
    if aggregate_score >= 70.0:
        return "strong"
    if aggregate_score >= 45.0:
        return "watch"
    return "weak"


def build_post_publish_scorecard(
    *,
    opportunity_registry: dict[str, Any],
    feedback_summary: dict[str, Any],
    gsc_sync: dict[str, Any],
    analytics_sync: dict[str, Any],
) -> dict[str, Any]:
    """生成 SEO/GEO 的双真源 post-publish 评分卡。"""
    slug_metrics = dict(feedback_summary.get("slug_metrics") or {})
    items = [dict(item) for item in list(opportunity_registry.get("items") or []) if isinstance(item, dict)]
    scorecards: list[dict[str, Any]] = []
    for item in items:
        slug = str(item.get("slug") or "").strip()
        metrics = dict(slug_metrics.get(slug) or {})
        impressions = _safe_float(item.get("impressions") or metrics.get("impressions"))
        ctr = _safe_float(item.get("ctr") or metrics.get("ctr"))
        clicks = _safe_float(item.get("clicks") or metrics.get("clicks"))
        page_views = _safe_float(item.get("page_views") or metrics.get("pageViews"))
        unique_visitors = _safe_float(item.get("unique_visitors") or metrics.get("uniqueVisitors"))
        engagement = _safe_float(item.get("avg_engagement_score") or metrics.get("engagementScore"))
        conversion_rate = _safe_float(item.get("conversion_rate") or metrics.get("conversionRate"))
        feedback_score = _safe_float(metrics.get("feedbackScore"))
        freshness_days = item.get("freshness_days")
        discoverability = round(_discoverability_score(impressions, ctr, clicks), 2)
        engagement_score = round(_engagement_score(page_views, unique_visitors, engagement), 2)
        conversion = round(_conversion_score(conversion_rate, feedback_score), 2)
        freshness = round(_freshness_score(freshness_days if isinstance(freshness_days, int) else None), 2)
        aggregate = round(discoverability * 0.35 + engagement_score * 0.25 + conversion * 0.2 + freshness * 0.2, 2)
        scorecards.append(
            {
                "slug": slug,
                "topic": item.get("topic"),
                "recommended_action": item.get("recommended_action"),
                "discoverability_score": discoverability,
                "engagement_score": engagement_score,
                "conversion_score": conversion,
                "freshness_score": freshness,
                "aggregate_score": aggregate,
                "performance_band": _band(aggregate),
                "dual_truth_ready": bool(gsc_sync.get("ran")) and bool(analytics_sync.get("ran")),
                "evidence": {
                    "clicks": round(clicks, 2),
                    "impressions": round(impressions, 2),
                    "ctr": round(ctr, 4),
                    "page_views": round(page_views, 2),
                    "unique_visitors": round(unique_visitors, 2),
                    "engagement_score": round(engagement, 2),
                    "conversion_rate": round(conversion_rate, 4),
                    "freshness_days": freshness_days,
                },
            }
        )
    scorecards.sort(key=lambda item: (item["aggregate_score"], item["discoverability_score"]), reverse=True)
    weak = [item for item in scorecards if item.get("performance_band") == "weak"]
    watch = [item for item in scorecards if item.get("performance_band") == "watch"]
    strong = [item for item in scorecards if item.get("performance_band") == "strong"]
    return {
        "enabled": True,
        "dual_truth_ready": bool(gsc_sync.get("ran")) and bool(analytics_sync.get("ran")),
        "gsc_ready": bool(gsc_sync.get("ran")),
        "analytics_ready": bool(analytics_sync.get("ran")),
        "item_count": len(scorecards),
        "strong_count": len(strong),
        "watch_count": len(watch),
        "weak_count": len(weak),
        "top_pages": scorecards[:10],
        "weak_pages": weak[:10],
        "items": scorecards,
    }
