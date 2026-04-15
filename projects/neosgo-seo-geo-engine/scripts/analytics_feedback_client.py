#!/usr/bin/env python3
# RULES-FIRST NOTICE:
# Before modifying this file, first read:
# - `JINCLAW_CONSTITUTION.md`
# - `AI_OPTIMIZATION_FRAMEWORK.md`
# Follow the constitution and framework:
# brain-first, one-doctor, fail-closed, evidence-over-narration,
# validate locally, then use the required PR workflow.
import csv
import json
from datetime import date, timedelta
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from neosgo_admin_marketing_api import MarketingApiClient, MarketingApiError


class AnalyticsFeedbackError(RuntimeError):
    pass


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


def _iso_day(days_ago: int) -> str:
    return (date.today() - timedelta(days=days_ago)).isoformat()


def _extract_slug_from_page(page_url: str, site_url: str) -> tuple[str, str]:
    parsed = urlparse(page_url)
    path = parsed.path.rstrip("/")
    if not path and page_url.startswith("/"):
        path = page_url.rstrip("/")
    if not path:
        return "", ""
    segments = [segment for segment in path.split("/") if segment]
    if len(segments) >= 2 and segments[0] == "notes":
        note_slug = segments[1]
        if len(segments) >= 4 and segments[2] == "geo":
            return note_slug, segments[3]
        return note_slug, ""
    return "", ""


def normalize_admin_ops_analytics(payload: dict[str, Any], site_url: str) -> list[dict[str, Any]]:
    """把后台 analytics payload 规范化为可写入 feedback 目录的结构化行。"""
    data = dict(payload.get("data") or {})
    rows = [item for item in list(data.get("topPages") or []) if isinstance(item, dict)]
    normalized: list[dict[str, Any]] = []
    for row in rows:
        page = str(row.get("page") or row.get("path") or "").strip()
        slug, geo_slug = _extract_slug_from_page(page, site_url)
        page_views = _safe_float(row.get("pageViews") or row.get("views"))
        unique_visitors = _safe_float(row.get("uniqueVisitors") or row.get("visitors"))
        avg_active_time = _safe_float(row.get("avgActiveTime") or row.get("averageActiveTime"))
        engagement_score = round(page_views * 0.1 + unique_visitors * 0.2 + avg_active_time * 0.05, 3)
        normalized.append(
            {
                "slug": slug,
                "geoSlug": geo_slug,
                "page": page,
                "pageViews": round(page_views, 2),
                "uniqueVisitors": round(unique_visitors, 2),
                "avgActiveTime": round(avg_active_time, 2),
                "engagementScore": engagement_score,
            }
        )
    return normalized


def write_snapshot(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"rows": rows}, ensure_ascii=False, indent=2), encoding="utf-8")


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    headers = [
        "slug",
        "geoSlug",
        "page",
        "pageViews",
        "uniqueVisitors",
        "avgActiveTime",
        "engagementScore",
    ]
    with path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=headers)
        writer.writeheader()
        for row in rows:
            writer.writerow({key: row.get(key, "") for key in headers})


def sync_analytics_feedback(
    env: dict[str, str],
    feedback_dir: Path,
    run_id: str,
    *,
    client: MarketingApiClient | None = None,
    site_url: str = "https://mc.neosgo.com",
) -> dict[str, Any]:
    """同步后台 analytics 到 feedback 目录，作为 SEO/GEO 的第二真源。"""
    enabled_value = str(env.get("NEOSGO_ANALYTICS_ENABLED", "true")).strip().lower()
    enabled = enabled_value in {"1", "true", "yes", "on"}
    if not enabled:
        return {"enabled": False, "ran": False, "reason": "disabled"}

    lookback_days = _safe_int(env.get("NEOSGO_ANALYTICS_LOOKBACK_DAYS"), 28)
    base_url = str(env.get("NEOSGO_ADMIN_MARKETING_API_BASE") or env.get("NEOSGO_ADMIN_BASE_URL") or "").strip()
    token = str(env.get("NEOSGO_ADMIN_MARKETING_KEY") or env.get("NEOSGO_ADMIN_AUTOMATION_KEY") or "").strip()
    if client is None:
        if not base_url or not token:
            missing: list[str] = []
            if not base_url:
                missing.append("NEOSGO_ADMIN_MARKETING_API_BASE")
            if not token:
                missing.append("NEOSGO_ADMIN_MARKETING_KEY")
            return {"enabled": True, "ran": False, "reason": "missing_credentials", "missing": missing}
        client = MarketingApiClient(base_url=base_url, bearer_token=token)

    start_date = _iso_day(max(lookback_days, 1))
    end_date = _iso_day(1)
    try:
        payload = client.get_admin_ops_analytics(start_date, end_date)
    except MarketingApiError as exc:
        raise AnalyticsFeedbackError(str(exc)) from exc

    rows = normalize_admin_ops_analytics(payload, site_url)
    output_dir = feedback_dir / "analytics" / run_id
    json_path = output_dir / "top-pages.json"
    csv_path = output_dir / "top-pages.csv"
    write_snapshot(json_path, rows)
    write_csv(csv_path, rows)
    data = dict(payload.get("data") or {})
    return {
        "enabled": True,
        "ran": True,
        "site_url": site_url,
        "lookback_days": lookback_days,
        "start_date": start_date,
        "end_date": end_date,
        "page_views_total": round(_safe_float(data.get("pageViews")), 2),
        "unique_visitors_total": round(_safe_float(data.get("uniqueVisitors")), 2),
        "avg_active_time": round(_safe_float(data.get("avgActiveTime") or data.get("averageActiveTime")), 2),
        "snapshots": {
            "top_pages": {
                "row_count": len(rows),
                "json_path": str(json_path),
                "csv_path": str(csv_path),
            }
        },
    }
