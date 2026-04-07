#!/usr/bin/env python3
import csv
import json
import ssl
import urllib.error
import urllib.parse
import urllib.request
from datetime import date, timedelta
from pathlib import Path
from typing import Any


TOKEN_URL = "https://oauth2.googleapis.com/token"
SEARCH_ANALYTICS_URL = "https://searchconsole.googleapis.com/webmasters/v3/sites/{site}/searchAnalytics/query"


class GoogleSearchConsoleError(RuntimeError):
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


def _request_json(url: str, payload: dict[str, Any], headers: dict[str, str]) -> dict[str, Any]:
    body = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(url, data=body, headers=headers, method="POST")
    ctx = ssl.create_default_context()
    try:
        with urllib.request.urlopen(req, timeout=60, context=ctx) as resp:
            raw = resp.read().decode("utf-8")
            return json.loads(raw) if raw else {}
    except urllib.error.HTTPError as exc:
        details = exc.read().decode("utf-8", errors="ignore")
        raise GoogleSearchConsoleError(f"http_{exc.code}:{details}") from exc
    except urllib.error.URLError as exc:
        raise GoogleSearchConsoleError(f"network_error:{exc}") from exc


def refresh_access_token(client_id: str, client_secret: str, refresh_token: str) -> dict[str, Any]:
    payload = {
        "client_id": client_id,
        "client_secret": client_secret,
        "refresh_token": refresh_token,
        "grant_type": "refresh_token",
    }
    data = urllib.parse.urlencode(payload).encode("utf-8")
    req = urllib.request.Request(TOKEN_URL, data=data, headers={"Content-Type": "application/x-www-form-urlencoded"}, method="POST")
    ctx = ssl.create_default_context()
    try:
        with urllib.request.urlopen(req, timeout=60, context=ctx) as resp:
            raw = resp.read().decode("utf-8")
            return json.loads(raw) if raw else {}
    except urllib.error.HTTPError as exc:
        details = exc.read().decode("utf-8", errors="ignore")
        raise GoogleSearchConsoleError(f"token_http_{exc.code}:{details}") from exc
    except urllib.error.URLError as exc:
        raise GoogleSearchConsoleError(f"token_network_error:{exc}") from exc


def query_search_analytics(
    site_url: str,
    access_token: str,
    dimensions: list[str],
    start_date: str,
    end_date: str,
    row_limit: int = 250,
) -> dict[str, Any]:
    site = urllib.parse.quote(site_url, safe="")
    url = SEARCH_ANALYTICS_URL.format(site=site)
    payload = {
        "startDate": start_date,
        "endDate": end_date,
        "dimensions": dimensions,
        "rowLimit": row_limit,
        "dataState": "final",
    }
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json",
    }
    return _request_json(url, payload, headers)


def _extract_slug_from_page(page_url: str, site_url: str) -> tuple[str, str]:
    parsed = urllib.parse.urlparse(page_url)
    path = parsed.path.rstrip("/")
    if not path:
        return "", ""
    segments = [segment for segment in path.split("/") if segment]
    if len(segments) >= 2 and segments[0] == "notes":
        note_slug = segments[1]
        if len(segments) >= 4 and segments[2] == "geo":
            geo_slug = segments[3]
            return note_slug, geo_slug
        return note_slug, ""
    return "", ""


def normalize_gsc_rows(payload: dict[str, Any], site_url: str, dimensions: list[str]) -> list[dict[str, Any]]:
    rows = payload.get("rows") or []
    out: list[dict[str, Any]] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        keys = row.get("keys") or []
        dim_map: dict[str, Any] = {}
        for idx, dim in enumerate(dimensions):
            dim_map[dim] = keys[idx] if idx < len(keys) else ""
        page = str(dim_map.get("page") or "")
        slug, geo_slug = _extract_slug_from_page(page, site_url)
        out.append(
            {
                "slug": slug,
                "geoSlug": geo_slug,
                "query": str(dim_map.get("query") or ""),
                "page": page,
                "country": str(dim_map.get("country") or ""),
                "clicks": _safe_float(row.get("clicks")),
                "impressions": _safe_float(row.get("impressions")),
                "ctr": _safe_float(row.get("ctr")),
                "avgPosition": _safe_float(row.get("position")),
                "feedbackScore": round(_safe_float(row.get("clicks")) * 0.6 + _safe_float(row.get("ctr")) * 40.0, 3),
            }
        )
    return out


def write_snapshot(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"rows": rows}, ensure_ascii=False, indent=2), encoding="utf-8")


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    headers = [
        "slug",
        "geoSlug",
        "query",
        "page",
        "country",
        "clicks",
        "impressions",
        "ctr",
        "avgPosition",
        "feedbackScore",
    ]
    with path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=headers)
        writer.writeheader()
        for row in rows:
            writer.writerow({key: row.get(key, "") for key in headers})


def sync_gsc_feedback(env: dict[str, str], feedback_dir: Path, run_id: str) -> dict[str, Any]:
    enabled = str(env.get("NEOSGO_GSC_ENABLED", "false")).strip().lower() in {"1", "true", "yes", "on"}
    if not enabled:
        return {"enabled": False, "ran": False, "reason": "disabled"}

    client_id = str(env.get("NEOSGO_GSC_CLIENT_ID") or "").strip()
    client_secret = str(env.get("NEOSGO_GSC_CLIENT_SECRET") or "").strip()
    refresh_token = str(env.get("NEOSGO_GSC_REFRESH_TOKEN") or "").strip()
    site_url = str(env.get("NEOSGO_GSC_SITE_URL") or "").strip()
    lookback_days = _safe_int(env.get("NEOSGO_GSC_LOOKBACK_DAYS"), 28)
    row_limit = _safe_int(env.get("NEOSGO_GSC_ROW_LIMIT"), 250)

    missing = []
    if not client_id:
        missing.append("NEOSGO_GSC_CLIENT_ID")
    if not client_secret:
        missing.append("NEOSGO_GSC_CLIENT_SECRET")
    if not refresh_token:
        missing.append("NEOSGO_GSC_REFRESH_TOKEN")
    if not site_url:
        missing.append("NEOSGO_GSC_SITE_URL")
    if missing:
        return {"enabled": True, "ran": False, "reason": "missing_credentials", "missing": missing}

    token_payload = refresh_access_token(client_id, client_secret, refresh_token)
    access_token = str(token_payload.get("access_token") or "").strip()
    if not access_token:
        raise GoogleSearchConsoleError("missing_access_token_after_refresh")

    start_date = _iso_day(max(lookback_days, 1))
    end_date = _iso_day(1)

    dimension_sets = {
        "pages": ["page"],
        "queries": ["query"],
        "countries": ["country"],
        "page_queries": ["page", "query"],
    }
    output_dir = feedback_dir / "gsc" / run_id
    result: dict[str, Any] = {
        "enabled": True,
        "ran": True,
        "site_url": site_url,
        "lookback_days": lookback_days,
        "start_date": start_date,
        "end_date": end_date,
        "snapshots": {},
    }

    for label, dimensions in dimension_sets.items():
        payload = query_search_analytics(site_url, access_token, dimensions, start_date, end_date, row_limit=row_limit)
        rows = normalize_gsc_rows(payload, site_url, dimensions)
        json_path = output_dir / f"{label}.json"
        csv_path = output_dir / f"{label}.csv"
        write_snapshot(json_path, rows)
        write_csv(csv_path, rows)
        result["snapshots"][label] = {
            "row_count": len(rows),
            "dimensions": dimensions,
            "json_path": str(json_path),
            "csv_path": str(csv_path),
        }
    return result
