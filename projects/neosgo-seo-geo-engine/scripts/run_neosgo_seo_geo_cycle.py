#!/usr/bin/env python3
# RULES-FIRST NOTICE:
# Before modifying this file, first read:
# - `JINCLAW_CONSTITUTION.md`
# - `AI_OPTIMIZATION_FRAMEWORK.md`
# Follow the constitution and framework:
# brain-first, one-doctor, fail-closed, evidence-over-narration,
# validate locally, then use the required PR workflow.
import argparse
import csv
import json
import os
import subprocess
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from neosgo_admin_marketing_api import MarketingApiClient, MarketingApiError
from google_search_console_client import GoogleSearchConsoleError, sync_gsc_feedback
from consolidation_planner import build_consolidation_plan
from opportunity_registry import build_opportunity_registry
from page_action_decider import build_page_action_plan
from maintenance_planner import build_maintenance_plan
from technical_release_gate import evaluate_release_gate


ROOT = Path("/Users/mac_claw/.openclaw/workspace/projects/neosgo-seo-geo-engine")
CONFIG_PATH = ROOT / "config" / "strategy.json"
STATE_PATH = ROOT / "runtime" / "state.json"
OUTPUT_DIR = ROOT / "output"
FEEDBACK_DIR = ROOT / "runtime" / "feedback"
SECRET_ENV_PATH = Path("/Users/mac_claw/.openclaw/secrets/neosgo-marketing.env")
OPENCLAW_BIN = "/opt/homebrew/bin/openclaw"
DEFAULT_CHAT = "8528973600"
DEFAULT_BASE_URL = "https://mc.neosgo.com"
DEFAULT_PATH = "/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin"


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


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


def _normalize_signature_value(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, float):
        return f"{value:.6f}"
    if isinstance(value, int):
        return f"{float(value):.6f}"
    text = str(value).strip()
    if not text:
        return ""
    try:
        return f"{float(text):.6f}"
    except Exception:
        return text


def _slugify_geo(target: dict[str, Any]) -> str:
    city = str(target.get("city") or "").strip().lower().replace(" ", "-")
    state = str(target.get("state") or "").strip().lower()
    parts = [part for part in [city, state] if part]
    return "-".join(parts)


def _load_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default


def _load_env_file(path: Path) -> dict[str, str]:
    data: dict[str, str] = {}
    if not path.exists():
        return data
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        data[key.strip()] = value.strip()
    return data


def _subprocess_env() -> dict[str, str]:
    env = os.environ.copy()
    env["PATH"] = f"{DEFAULT_PATH}:{env.get('PATH', '')}".strip(":")
    return env


def _send_to_telegram(chat_id: str, text: str, attachments: list[Path]) -> list[dict[str, Any]]:
    deliveries: list[dict[str, Any]] = []
    text_proc = subprocess.run(
        [OPENCLAW_BIN, "message", "send", "--channel", "telegram", "--target", chat_id, "--message", text, "--json"],
        capture_output=True,
        text=True,
        timeout=120,
        env=_subprocess_env(),
    )
    deliveries.append({"kind": "text", "returncode": text_proc.returncode, "stdout": text_proc.stdout, "stderr": text_proc.stderr})
    for attachment in attachments:
        proc = subprocess.run(
            [OPENCLAW_BIN, "message", "send", "--channel", "telegram", "--target", chat_id, "--media", str(attachment), "--force-document", "--json"],
            capture_output=True,
            text=True,
            timeout=180,
            env=_subprocess_env(),
        )
        deliveries.append({"kind": "media", "path": str(attachment), "returncode": proc.returncode, "stdout": proc.stdout, "stderr": proc.stderr})
    return deliveries


def _existing_notes_by_slug(payload: Any) -> dict[str, dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    if isinstance(payload, list):
        rows = [item for item in payload if isinstance(item, dict)]
    elif isinstance(payload, dict):
        for key in ("items", "rows", "data", "notes"):
            value = payload.get(key)
            if isinstance(value, list):
                rows = [item for item in value if isinstance(item, dict)]
                break
    out: dict[str, dict[str, Any]] = {}
    for row in rows:
        slug = str(row.get("slug") or "").strip()
        if slug:
            out[slug] = row
    return out


def _variant_rows(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, list):
        return [item for item in payload if isinstance(item, dict)]
    if isinstance(payload, dict):
        for key in ("items", "rows", "data", "variants"):
            value = payload.get(key)
            if isinstance(value, list):
                return [item for item in value if isinstance(item, dict)]
    return []


def _lookup_variant_by_target(client: MarketingApiClient, note_id: str, geo_slug: str, target: dict[str, Any]) -> dict[str, Any]:
    rows = _variant_rows(client.list_geo_variants(note_id))
    target_city = str(target.get("city") or "").strip().lower()
    target_state = str(target.get("state") or "").strip().lower()
    for row in rows:
        row_slug = str(row.get("geoSlug") or row.get("slug") or "").strip()
        if row_slug == geo_slug:
            return row
        row_city = str(row.get("city") or "").strip().lower()
        row_state = str(row.get("state") or "").strip().lower()
        if target_city and target_state and row_city == target_city and row_state == target_state:
            return row
    return {}


def _lookup_note_by_slug(client: MarketingApiClient, slug: str) -> dict[str, Any]:
    payload = client.list_design_notes()
    return _existing_notes_by_slug(payload).get(slug, {})


def _topic_family_from_item(item: dict[str, Any]) -> str:
    return str(item.get("topic_key") or item.get("slug") or "general").strip()


def _is_designer_daily_item(item: dict[str, Any]) -> bool:
    track = str(item.get("contentTrack") or "").strip().lower()
    audience = str(item.get("targetAudience") or "").strip().lower()
    return track == "designer_daily" or "interior designer" in audience


def _local_calendar_date(tz_name: str) -> str:
    try:
        from zoneinfo import ZoneInfo

        return str(datetime.now(ZoneInfo(tz_name)).date())
    except Exception:
        return str(datetime.now().date())


def _load_feedback_rows(config: dict[str, Any]) -> tuple[list[dict[str, Any]], list[str]]:
    ingestion = config.get("feedback_ingestion") or {}
    issues: list[str] = []
    if not ingestion.get("enabled", True):
        return [], issues
    rows: list[dict[str, Any]] = []
    search_paths = [Path(path) for path in ingestion.get("search_paths") or [str(FEEDBACK_DIR)]]
    for base in search_paths:
        if not base.exists():
            continue
        for path in sorted(base.rglob("*")):
            if not path.is_file():
                continue
            suffix = path.suffix.lower()
            try:
                if suffix == ".json":
                    payload = json.loads(path.read_text(encoding="utf-8"))
                    if isinstance(payload, list):
                        for item in payload:
                            if isinstance(item, dict):
                                item.setdefault("_source", str(path))
                                rows.append(item)
                    elif isinstance(payload, dict):
                        has_collection_key = any(key in payload for key in ("items", "rows", "data"))
                        items = payload.get("items")
                        if not isinstance(items, list):
                            items = payload.get("rows")
                        if not isinstance(items, list):
                            items = payload.get("data")
                        if isinstance(items, list):
                            for item in items:
                                if isinstance(item, dict):
                                    item.setdefault("_source", str(path))
                                    rows.append(item)
                        elif not has_collection_key:
                            payload.setdefault("_source", str(path))
                            rows.append(payload)
                elif suffix == ".csv":
                    with path.open("r", encoding="utf-8", newline="") as fh:
                        reader = csv.DictReader(fh)
                        for row in reader:
                            item = dict(row)
                            item["_source"] = str(path)
                            rows.append(item)
            except Exception as exc:
                issues.append(f"feedback_load_failed:{path}:{exc}")
    accepted_fields = [str(field).strip() for field in (ingestion.get("accepted_fields") or []) if str(field).strip()]
    signature_fields = accepted_fields + ["geoSlug", "query", "page", "country", "topic_key", "topicFamily"]
    deduped: list[dict[str, Any]] = []
    seen: set[tuple[tuple[str, str], ...]] = set()
    for row in rows:
        signature: list[tuple[str, str]] = []
        for field in signature_fields:
            signature.append((field, _normalize_signature_value(row.get(field))))
        key = tuple(signature)
        if key in seen:
            continue
        seen.add(key)
        deduped.append(row)
    return deduped, issues


def _infer_topic_from_query(query: str, config: dict[str, Any]) -> str:
    text = str(query or "").strip().lower()
    if not text:
        return "general"
    families = ((config.get("research_framework") or {}).get("topic_families") or [])
    best_topic = "general"
    best_score = 0
    for family in families:
        key = str(family.get("key") or "").strip()
        if not key:
            continue
        score = 0
        label = str(family.get("label") or "").strip().lower()
        if label and label in text:
            score += 3
        if key.replace("-", " ") in text or key in text:
            score += 2
        for signal in family.get("signals") or []:
            signal_text = str(signal or "").strip().lower()
            if not signal_text:
                continue
            if signal_text in text:
                score += 4
            else:
                signal_tokens = [token for token in signal_text.replace("/", " ").split() if token]
                matched = sum(1 for token in signal_tokens if token in text)
                score += matched
        if score > best_score:
            best_score = score
            best_topic = key
    return best_topic


def _summarize_feedback(rows: list[dict[str, Any]], backlog: list[dict[str, Any]], config: dict[str, Any]) -> dict[str, Any]:
    by_slug: dict[str, dict[str, Any]] = defaultdict(lambda: {
        "clicks": 0.0,
        "impressions": 0.0,
        "feedbackScore": 0.0,
        "conversionRate": 0.0,
        "samples": 0,
    })
    by_topic: dict[str, dict[str, Any]] = defaultdict(lambda: {
        "clicks": 0.0,
        "impressions": 0.0,
        "feedbackScore": 0.0,
        "conversionRate": 0.0,
        "samples": 0,
        "queryClicks": 0.0,
        "queryImpressions": 0.0,
        "querySamples": 0,
    })
    by_query_topic: dict[str, dict[str, Any]] = defaultdict(lambda: {
        "clicks": 0.0,
        "impressions": 0.0,
        "samples": 0,
        "top_queries": defaultdict(float),
    })
    unmatched_pages: dict[str, dict[str, Any]] = defaultdict(lambda: {
        "clicks": 0.0,
        "impressions": 0.0,
        "samples": 0,
    })
    slug_to_topic = {str(item.get("slug")): _topic_family_from_item(item) for item in backlog}
    matched_slug_rows = 0
    unmatched_slug_rows = 0
    for row in rows:
        slug = str(row.get("slug") or "").strip()
        query = str(row.get("query") or "").strip()
        page = str(row.get("page") or "").strip()
        query_topic = _infer_topic_from_query(query, config)
        if slug and slug in slug_to_topic:
            matched_slug_rows += 1
        else:
            unmatched_slug_rows += 1
        topic = slug_to_topic.get(slug) or str(row.get("topic_key") or row.get("topicFamily") or "").strip() or query_topic or "general"
        clicks = _safe_float(row.get("clicks"))
        impressions = _safe_float(row.get("impressions"))
        ctr = _safe_float(row.get("ctr"))
        feedback_score = _safe_float(row.get("feedbackScore"))
        conversion_rate = _safe_float(row.get("conversionRate"))
        if ctr <= 0 and clicks > 0 and impressions > 0:
            ctr = clicks / impressions
        target_slug = by_slug[slug]
        target_slug["clicks"] += clicks
        target_slug["impressions"] += impressions
        target_slug["feedbackScore"] += feedback_score
        target_slug["conversionRate"] += conversion_rate
        target_slug["samples"] += 1
        target_topic = by_topic[topic]
        target_topic["clicks"] += clicks
        target_topic["impressions"] += impressions
        target_topic["feedbackScore"] += feedback_score
        target_topic["conversionRate"] += conversion_rate
        target_topic["samples"] += 1
        if query:
            target_topic["queryClicks"] += clicks
            target_topic["queryImpressions"] += impressions
            target_topic["querySamples"] += 1
            target_query_topic = by_query_topic[query_topic]
            target_query_topic["clicks"] += clicks
            target_query_topic["impressions"] += impressions
            target_query_topic["samples"] += 1
            target_query_topic["top_queries"][query] += clicks if clicks > 0 else max(impressions * 0.05, 0.01)
        if page and (not slug or slug not in slug_to_topic):
            unmatched_page = unmatched_pages[page]
            unmatched_page["clicks"] += clicks
            unmatched_page["impressions"] += impressions
            unmatched_page["samples"] += 1
    top_topics = sorted(
        (
            {
                "topic": key,
                "clicks": round(value["clicks"], 2),
                "impressions": round(value["impressions"], 2),
                "avg_feedback_score": round(value["feedbackScore"] / value["samples"], 3) if value["samples"] else 0.0,
                "avg_conversion_rate": round(value["conversionRate"] / value["samples"], 4) if value["samples"] else 0.0,
                "query_clicks": round(value["queryClicks"], 2),
                "query_impressions": round(value["queryImpressions"], 2),
            }
            for key, value in by_topic.items()
        ),
        key=lambda item: (item["query_clicks"], item["clicks"], item["avg_feedback_score"], item["avg_conversion_rate"]),
        reverse=True,
    )
    top_query_topics = sorted(
        (
            {
                "topic": key,
                "clicks": round(value["clicks"], 2),
                "impressions": round(value["impressions"], 2),
                "samples": value["samples"],
                "top_queries": [query for query, _score in sorted(value["top_queries"].items(), key=lambda item: item[1], reverse=True)[:5]],
            }
            for key, value in by_query_topic.items()
        ),
        key=lambda item: (item["clicks"], item["impressions"], item["samples"]),
        reverse=True,
    )
    top_unmatched_pages = sorted(
        (
            {
                "page": page,
                "clicks": round(value["clicks"], 2),
                "impressions": round(value["impressions"], 2),
                "samples": value["samples"],
            }
            for page, value in unmatched_pages.items()
        ),
        key=lambda item: (item["clicks"], item["impressions"], item["samples"], item["page"]),
        reverse=True,
    )
    return {
        "row_count": len(rows),
        "matched_slug_rows": matched_slug_rows,
        "unmatched_slug_rows": unmatched_slug_rows,
        "slug_metrics": by_slug,
        "topic_metrics": by_topic,
        "top_topics": top_topics[:10],
        "top_query_topics": top_query_topics[:10],
        "top_unmatched_pages": top_unmatched_pages[:10],
    }


def _summarize_run_history(state: dict[str, Any]) -> dict[str, Any]:
    runs = [item for item in state.get("runs", []) if isinstance(item, dict)]
    if not runs:
        return {"run_count": 0, "avg_writes": 0.0, "avg_gaps": 0.0, "recent_failures": 0}
    avg_writes = sum(_safe_float(item.get("writes_count")) for item in runs) / len(runs)
    avg_gaps = sum(_safe_float(item.get("gap_count")) for item in runs) / len(runs)
    recent_failures = sum(1 for item in runs[-5:] if item.get("blocked"))
    return {
        "run_count": len(runs),
        "avg_writes": round(avg_writes, 2),
        "avg_gaps": round(avg_gaps, 2),
        "recent_failures": recent_failures,
    }


def _build_inventory_summary(
    notes_by_slug: dict[str, dict[str, Any]],
    backlog: list[dict[str, Any]],
    client: Optional[MarketingApiClient] = None,
) -> dict[str, Any]:
    coverage_by_topic: dict[str, dict[str, Any]] = defaultdict(lambda: {"note_count": 0, "geo_count": 0, "revision_count": 0})
    slug_to_topic = {str(item.get("slug")): _topic_family_from_item(item) for item in backlog}
    for slug, note in notes_by_slug.items():
        topic = slug_to_topic.get(slug) or "general"
        coverage_by_topic[topic]["note_count"] += 1
        count_payload = note.get("_count") or {}
        coverage_by_topic[topic]["geo_count"] += _safe_int(count_payload.get("geoVariants"))
        coverage_by_topic[topic]["revision_count"] += _safe_int(count_payload.get("revisions"))
        if client and note.get("id") and _safe_int(count_payload.get("revisions")) == 0:
            try:
                revisions = client.list_design_note_revisions(str(note["id"]))
                rows = revisions.get("items") if isinstance(revisions, dict) else revisions
                if isinstance(rows, list):
                    coverage_by_topic[topic]["revision_count"] += len(rows)
            except Exception:
                pass
    return {
        "existing_note_count": len(notes_by_slug),
        "coverage_by_topic": coverage_by_topic,
    }


def _should_publish_note(note: dict[str, Any]) -> bool:
    return str(note.get("status") or "").upper() == "DRAFT"


def _should_publish_variant(variant: dict[str, Any]) -> bool:
    return str(variant.get("status") or "").upper() == "DRAFT"


def _variant_exists_for_target(existing_rows: list[dict[str, Any]], target: dict[str, Any]) -> tuple[bool, dict[str, Any]]:
    target_city = str(target.get("city") or "").strip().lower()
    target_state = str(target.get("state") or "").strip().lower()
    target_geo_slug = _slugify_geo(target)
    for row in existing_rows:
        row_slug = str(row.get("geoSlug") or row.get("slug") or "").strip().lower()
        row_city = str(row.get("city") or "").strip().lower()
        row_state = str(row.get("state") or "").strip().lower()
        if target_city and target_state and row_city == target_city and row_state == target_state:
            return True, row
        if target_geo_slug and row_slug == target_geo_slug:
            return True, row
    return False, {}


def _build_market_research(config: dict[str, Any], feedback_summary: dict[str, Any], inventory_summary: dict[str, Any]) -> dict[str, Any]:
    framework = config.get("research_framework") or {}
    topic_families = framework.get("topic_families") or []
    coverage = inventory_summary.get("coverage_by_topic") or {}
    topic_metrics = feedback_summary.get("topic_metrics") or {}
    candidates: list[dict[str, Any]] = []
    for family in topic_families:
        key = str(family.get("key") or "").strip()
        inv = coverage.get(key) or {}
        perf = topic_metrics.get(key) or {}
        note_gap = max(0, 2 - _safe_int(inv.get("note_count")))
        geo_gap = max(0, 6 - _safe_int(inv.get("geo_count")))
        clicks = _safe_float(perf.get("clicks"))
        feedback_score = _safe_float(perf.get("feedbackScore"))
        query_clicks = _safe_float(perf.get("queryClicks"))
        query_impressions = _safe_float(perf.get("queryImpressions"))
        query_topic = next((item for item in (feedback_summary.get("top_query_topics") or []) if item.get("topic") == key), {})
        score = round(note_gap * 2.0 + geo_gap * 0.5 + clicks * 0.1 + feedback_score * 0.5 + query_clicks * 0.15 + query_impressions * 0.01, 2)
        candidates.append(
            {
                "topic": key,
                "label": family.get("label"),
                "signals": family.get("signals") or [],
                "note_gap": note_gap,
                "geo_gap": geo_gap,
                "historical_clicks": round(clicks, 2),
                "historical_feedback_score": round(feedback_score, 2),
                "query_clicks": round(query_clicks, 2),
                "query_impressions": round(query_impressions, 2),
                "top_queries": query_topic.get("top_queries") or [],
                "research_score": score,
            }
        )
    candidates.sort(key=lambda item: item["research_score"], reverse=True)
    return {
        "goal": framework.get("goal"),
        "top_research_candidates": candidates[:10],
        "geo_clusters": framework.get("geo_clusters") or [],
    }


def _build_adaptive_profile(config: dict[str, Any], feedback_summary: dict[str, Any], inventory_summary: dict[str, Any], research_summary: dict[str, Any], history_summary: dict[str, Any]) -> dict[str, Any]:
    weights = ((config.get("adaptive_feedback") or {}).get("weights") or {})
    topic_metrics = feedback_summary.get("topic_metrics") or {}
    coverage = inventory_summary.get("coverage_by_topic") or {}
    topic_priority: list[dict[str, Any]] = []
    for family in config.get("research_framework", {}).get("topic_families", []):
        key = str(family.get("key") or "").strip()
        perf = topic_metrics.get(key) or {}
        inv = coverage.get(key) or {}
        clicks = _safe_float(perf.get("clicks"))
        ctr = _safe_float(perf.get("ctr"))
        feedback_score = _safe_float(perf.get("feedbackScore"))
        conversion_rate = _safe_float(perf.get("conversionRate"))
        query_clicks = _safe_float(perf.get("queryClicks"))
        query_impressions = _safe_float(perf.get("queryImpressions"))
        gap_urgency = max(0, 2 - _safe_int(inv.get("note_count")))
        fresh_geo_need = max(0, 6 - _safe_int(inv.get("geo_count")))
        score = (
            clicks * _safe_float(weights.get("clicks"), 3.0)
            + ctr * _safe_float(weights.get("ctr"), 2.0) * 100
            + feedback_score * _safe_float(weights.get("feedbackScore"), 2.5)
            + conversion_rate * _safe_float(weights.get("conversionRate"), 3.0) * 100
            + query_clicks * 1.5
            + query_impressions * 0.05
            + gap_urgency * _safe_float(weights.get("gapUrgency"), 1.5)
            + fresh_geo_need * _safe_float(weights.get("freshGeoNeed"), 1.5)
        )
        topic_priority.append(
            {
                "topic": key,
                "adaptive_score": round(score, 2),
                "gap_urgency": gap_urgency,
                "fresh_geo_need": fresh_geo_need,
                "historical_clicks": round(clicks, 2),
                "feedback_score": round(feedback_score, 2),
                "query_clicks": round(query_clicks, 2),
                "query_impressions": round(query_impressions, 2),
            }
        )
    topic_priority.sort(key=lambda item: item["adaptive_score"], reverse=True)
    primary_focus = topic_priority[0]["topic"] if topic_priority else "pendant"
    return {
        "primary_focus_topic": primary_focus,
        "topic_priority": topic_priority,
        "history_context": history_summary,
        "research_lead_topic": (research_summary.get("top_research_candidates") or [{}])[0].get("topic"),
    }


def _rank_backlog(backlog: list[dict[str, Any]], adaptive_profile: dict[str, Any], feedback_summary: dict[str, Any], inventory_summary: dict[str, Any]) -> list[dict[str, Any]]:
    score_by_topic = {item["topic"]: item["adaptive_score"] for item in adaptive_profile.get("topic_priority", [])}
    coverage = inventory_summary.get("coverage_by_topic") or {}
    ranked: list[dict[str, Any]] = []
    for item in backlog:
        topic = _topic_family_from_item(item)
        inv = coverage.get(topic) or {}
        note_gap = max(0, 1 - _safe_int(inv.get("note_count")))
        geo_gap = max(0, 6 - _safe_int(inv.get("geo_count")))
        score = round(_safe_float(score_by_topic.get(topic)) + note_gap * 10 + geo_gap, 2)
        enriched = dict(item)
        enriched["_adaptive_score"] = score
        ranked.append(enriched)
    ranked.sort(key=lambda item: item["_adaptive_score"], reverse=True)
    return ranked


def _build_iteration_plan(
    backlog: list[dict[str, Any]],
    notes_by_slug: dict[str, dict[str, Any]],
    feedback_summary: dict[str, Any],
    gsc_sync: dict[str, Any],
    history_summary: dict[str, Any],
) -> dict[str, Any]:
    slug_metrics = feedback_summary.get("slug_metrics") or {}
    topic_metrics = feedback_summary.get("topic_metrics") or {}
    plans: list[dict[str, Any]] = []
    gsc_ready = bool(gsc_sync.get("ran"))
    for item in backlog:
        slug = str(item.get("slug") or "").strip()
        topic = _topic_family_from_item(item)
        note = notes_by_slug.get(slug) or {}
        status = str(note.get("status") or "").upper()
        note_perf = slug_metrics.get(slug) or {}
        topic_perf = topic_metrics.get(topic) or {}
        clicks = _safe_float(note_perf.get("clicks"))
        impressions = _safe_float(note_perf.get("impressions"))
        query_impressions = _safe_float(topic_perf.get("queryImpressions"))
        revisions = _safe_int(((note.get("_count") or {}).get("revisions")))

        if status != "PUBLISHED":
            action = "publish_or_fix_blocker"
            reason = "The note is not fully live yet, so performance work should wait until publication is stable."
        elif gsc_ready and impressions <= 0 and query_impressions <= 0:
            action = "monitor_indexing_and_internal_links"
            reason = "The page is live and GSC is connected, but there is still no search visibility. The right move is to keep strengthening discoverability and let indexing catch up."
        elif impressions > 0 and clicks <= 0:
            action = "improve_ctr_packaging"
            reason = "Google is showing the page, but users are not clicking yet. Title, description, and SERP promise should be sharpened first."
        elif clicks > 0:
            action = "expand_supporting_sections_and_internal_links"
            reason = "The page already has search demand. The next job is to deepen usefulness, support more related intents, and guide readers further into the site."
        else:
            action = "stabilize_and_watch"
            reason = "The page is live, but there is not enough signal yet to justify heavier changes."

        plans.append(
            {
                "slug": slug,
                "topic": topic,
                "status": status or "UNKNOWN",
                "revisions": revisions,
                "clicks": round(clicks, 2),
                "impressions": round(impressions, 2),
                "topic_query_impressions": round(query_impressions, 2),
                "next_action": action,
                "reason": reason,
            }
        )

    priorities = sorted(
        plans,
        key=lambda item: (
            0 if item["next_action"] == "improve_ctr_packaging" else
            1 if item["next_action"] == "expand_supporting_sections_and_internal_links" else
            2 if item["next_action"] == "monitor_indexing_and_internal_links" else
            3
        )
    )
    return {
        "history_context": history_summary,
        "gsc_ready": gsc_ready,
        "note_iteration_priorities": priorities,
    }


def _compose_research_brief(
    backlog_item: dict[str, Any],
    config: dict[str, Any],
    market_research: dict[str, Any],
    adaptive_profile: dict[str, Any],
) -> dict[str, Any]:
    topic = _topic_family_from_item(backlog_item)
    research_rows = market_research.get("top_research_candidates") or []
    research_row = next((row for row in research_rows if row.get("topic") == topic), {})
    competitor_framework = (config.get("competitor_gap_framework") or {}).get("topic_gaps") or {}
    competitor_topic = competitor_framework.get(topic) or {}
    commerce_angles = (config.get("site_positioning") or {}).get("commerce_angles") or []
    audience = str(backlog_item.get("targetAudience") or "Homeowners and trade buyers")
    intent_keyword = str(backlog_item.get("intentKeyword") or "")
    primary_focus = adaptive_profile.get("primary_focus_topic")
    if _is_designer_daily_item(backlog_item):
        return {
            "topic": topic,
            "audience": audience,
            "intent_keyword": intent_keyword,
            "reader_problem": f'The reader is an interior designer who needs a confident, specification-ready answer to "{intent_keyword}" without creating client confusion or procurement drift.',
            "content_promise": f"Give a reusable professional framework for {backlog_item.get('title')}, not a generic inspiration article.",
            "commercial_bridge": commerce_angles[:4],
            "research_signals": research_row.get("signals") or backlog_item.get("tradeSignals") or [],
            "competitor_strengths": competitor_topic.get("common_competitor_strengths") or [],
            "competitor_gaps": competitor_topic.get("common_competitor_gaps") or [],
            "competitor_reference_urls": competitor_topic.get("reference_urls") or [],
            "angle": "trade_advisory_brief",
            "must_answer": [
                "What decision is the designer actually trying to make on a live project?",
                "What specification or coordination mistakes create downstream friction?",
                "What should be locked before the client presentation or quote review?",
                "What is the clearest next step inside Neosgo for a trade buyer?",
            ],
        }
    return {
        "topic": topic,
        "audience": audience,
        "intent_keyword": intent_keyword,
        "reader_problem": f'The reader wants a confident answer to "{intent_keyword}" without making an expensive lighting mistake.',
        "content_promise": f"Give a clear decision framework for {backlog_item.get('title')}, not just surface tips.",
        "commercial_bridge": commerce_angles[:3],
        "research_signals": research_row.get("signals") or [],
        "competitor_strengths": competitor_topic.get("common_competitor_strengths") or [],
        "competitor_gaps": competitor_topic.get("common_competitor_gaps") or [],
        "competitor_reference_urls": competitor_topic.get("reference_urls") or [],
        "angle": "decision_guide" if topic != primary_focus else "priority_reference_guide",
        "must_answer": [
            "What decision is the reader actually trying to make?",
            "What mistakes create bad visual proportion or poor functionality?",
            "What practical rule of thumb helps them choose with confidence?",
            "What should the reader browse next on Neosgo?"
        ],
    }


def _build_seo_packaging(backlog_item: dict[str, Any], research_brief: dict[str, Any], config: dict[str, Any]) -> dict[str, str]:
    topic = _topic_family_from_item(backlog_item)
    brand = str((config.get("site_positioning") or {}).get("brand_name") or "Neosgo Lighting").strip()
    title = str(backlog_item.get("title") or "").strip()
    quick_answer = str(backlog_item.get("quickAnswer") or "").strip()
    topic_queries = research_brief.get("competitor_gaps") or []

    if _is_designer_daily_item(backlog_item):
        seo_title = str(backlog_item.get("seoTitle") or title or "").strip()
        seo_description = str(backlog_item.get("seoDescription") or backlog_item.get("description") or "").strip()
        quick = quick_answer
    elif topic == "pendant":
        seo_title = "Kitchen Island Pendant Spacing: Size, Height & Layout Guide"
        seo_description = "A clear guide to island pendant size, spacing, and hanging height, with the mistakes that make a kitchen feel crowded or under-scaled."
        quick = "For most kitchen islands, the right pendant layout comes from balancing fixture width, island length, and visual breathing room, not from using a spacing formula alone."
    elif topic == "bathroom":
        seo_title = "Bathroom Vanity Light Size Guide: Mirror Width & Placement"
        seo_description = "Learn how to size vanity lighting around mirror width, mounting height, and flattering facial light so the bathroom feels balanced instead of harsh."
        quick = "The right vanity light should relate to mirror width, sit at a flattering height, and create even facial illumination without glare or awkward shadow."
    elif topic == "chandelier":
        seo_title = "Dining Room Chandelier Size Guide: Diameter, Height & Scale"
        seo_description = "Use this guide to choose chandelier diameter, hanging height, and visual weight so the fixture feels right for the table and the room."
        quick = "A dining chandelier should feel centered to the table, visually proportionate to the room, and low enough to create intimacy without blocking sightlines."
    elif topic == "living-room":
        seo_title = "Living Room Layered Lighting Guide: Layout, Balance & Mistakes"
        seo_description = "A practical layered-lighting guide for living rooms, covering ambient, task, and accent lighting without making the room feel flat or overdone."
        quick = "The strongest living room lighting plans combine ambient, task, and accent layers so the room feels calm, useful, and visually balanced at different times of day."
    else:
        seo_title = str(backlog_item.get("seoTitle") or title or "").strip()
        seo_description = str(backlog_item.get("seoDescription") or "").strip()
        quick = quick_answer

    if seo_title and brand and brand.lower() not in seo_title.lower():
        seo_title = f"{seo_title} | {brand}"
    if not seo_description:
        seo_description = str(backlog_item.get("seoDescription") or "").strip()
    if not quick:
        quick = quick_answer

    packaging_notes: list[str] = []
    if topic_queries:
        packaging_notes.append("Uses problem-aware phrasing drawn from recurring SERP weak spots.")
    if _is_designer_daily_item(backlog_item):
        packaging_notes.append("Targets trade readers with specification-ready, client-safe language instead of retail-style inspiration copy.")
    packaging_notes.append("Prioritizes decision clarity and stronger click intent over generic category wording.")
    return {
        "seoTitle": seo_title,
        "seoDescription": seo_description,
        "quickAnswer": quick,
        "packagingRationale": " ".join(packaging_notes),
    }


def _contains_pattern(text: str, pattern: str) -> bool:
    return pattern.lower() in text.lower()


def _editorial_quality_gate(backlog_item: dict[str, Any], research_brief: dict[str, Any], config: dict[str, Any]) -> dict[str, Any]:
    framework = config.get("editorial_framework") or {}
    sections = backlog_item.get("sections") or []
    section_text = "\n".join(
        f"{str(item.get('heading') or '')}\n{str(item.get('body') or '')}" for item in sections if isinstance(item, dict)
    )
    faq = backlog_item.get("faq") or []
    quick_answer = str(backlog_item.get("quickAnswer") or "")
    intent_keyword = str(backlog_item.get("intentKeyword") or "")
    internal_link_map = config.get("internal_link_map") or {}
    topic_key = str(backlog_item.get("topic_key") or "")

    intent_alignment = 22 if intent_keyword and quick_answer else 12
    decision_utility = min(22, 8 + len(sections) * 4 + len(faq) * 2)
    professional_depth = 18 if len(sections) >= 4 else 10 + len(sections) * 2
    readability_and_flow = 18 if len(quick_answer.split()) >= 8 and len(sections) >= 3 else 10
    brand_linkage = 20 if topic_key in internal_link_map else 10

    required_patterns = backlog_item.get("requiredPatterns") or framework.get("required_section_patterns") or []
    matched_patterns = sum(1 for pattern in required_patterns if _contains_pattern(section_text, pattern))
    if required_patterns:
        professional_depth += min(6, matched_patterns)
        readability_and_flow += min(4, matched_patterns // 2)

    if _is_designer_daily_item(backlog_item):
        designer_markers = ("project", "specification", "client", "procurement", "lead time", "finish", "trade")
        matched_markers = sum(1 for marker in designer_markers if _contains_pattern(section_text, marker))
        decision_utility += min(6, matched_markers)
        professional_depth += min(8, matched_markers)
        if any("/trade-program" == str(link.get("href") or "").strip() for link in (backlog_item.get("internalLinks") or [])):
            brand_linkage = max(brand_linkage, 20)

    total = min(100, intent_alignment + decision_utility + professional_depth + readability_and_flow + brand_linkage)
    threshold = _safe_int(backlog_item.get("qualityThreshold") or ((framework.get("quality_gate") or {}).get("minimum_score")), 78)
    return {
        "score": total,
        "passed": total >= threshold,
        "threshold": threshold,
        "dimensions": {
            "intent_alignment": intent_alignment,
            "decision_utility": decision_utility,
            "professional_depth": professional_depth,
            "readability_and_flow": readability_and_flow,
            "brand_linkage": brand_linkage,
        },
        "matched_required_patterns": matched_patterns,
        "research_brief_summary": {
            "topic": research_brief.get("topic"),
            "angle": research_brief.get("angle"),
            "reader_problem": research_brief.get("reader_problem"),
        },
    }


def _ensure_editorial_sections(backlog_item: dict[str, Any], research_brief: dict[str, Any]) -> list[dict[str, Any]]:
    existing = [dict(item) for item in (backlog_item.get("sections") or []) if isinstance(item, dict)]
    headings = " ".join(str(item.get("heading") or "") for item in existing).lower()
    additions: list[dict[str, Any]] = []
    if _is_designer_daily_item(backlog_item):
        if "real project" not in headings and "project" not in headings:
            additions.append(
                {
                    "heading": "Why this matters on a real project",
                    "body": f"{research_brief.get('reader_problem')} The goal is to protect design clarity, quoting accuracy, and client confidence at the same time.",
                }
            )
        if "specification" not in headings and "spec" not in headings:
            additions.append(
                {
                    "heading": "Specification checkpoints to lock early",
                    "body": "Clarify fixture role, intended visual weight, finish direction, mounting assumptions, and replacement risk before the selection reaches a client-facing schedule.",
                }
            )
        if "client" not in headings:
            additions.append(
                {
                    "heading": "How to discuss the choice with clients",
                    "body": "Frame the recommendation around room function, visual proportion, finish compatibility, and the tradeoffs the client is avoiding by making the decision now instead of during procurement.",
                }
            )
        if "procurement" not in headings and "vendor" not in headings:
            additions.append(
                {
                    "heading": "Procurement and coordination notes",
                    "body": "Before final approval, confirm finish naming, dimensional assumptions, lead-time sensitivity, replacement options, and any installation dependencies that could create avoidable change orders.",
                }
            )
        if "next" not in headings:
            additions.append(
                {
                    "heading": "What to do next",
                    "body": "Use the article to narrow the specification logic first, then move into the Neosgo trade program and catalog to compare viable options with fewer reselection loops.",
                }
            )
        return existing + additions
    if "why" not in headings:
        additions.append(
            {
                "heading": "Why this decision matters",
                "body": f"{research_brief.get('reader_problem')} The goal is to help the reader make a proportionate, practical, and design-aware choice."
            }
        )
    if "mistake" not in headings:
        additions.append(
            {
                "heading": "Common mistakes to avoid",
                "body": "Most bad outcomes come from judging scale in isolation, copying a fixture size without considering room context, or treating spacing and hanging height as afterthoughts."
            }
        )
    if "choose" not in headings:
        additions.append(
            {
                "heading": "How to choose with confidence",
                "body": "Work from the room, the key surface or focal point, and the visual role the fixture needs to play. The goal is not only correct dimensions, but a result that feels proportionate, intentional, and easy to live with."
            }
        )
    if "next" not in headings:
        additions.append(
            {
                "heading": "What to do next",
                "body": "After using this guide to narrow the right scale and visual direction, the next step is to compare finishes, silhouettes, and room-fit options inside the relevant Neosgo collection."
            }
        )
    return existing + additions


def _related_note_links(backlog_item: dict[str, Any], config: dict[str, Any]) -> list[dict[str, str]]:
    current_slug = str(backlog_item.get("slug") or "").strip()
    current_topic = _topic_family_from_item(backlog_item)
    links: list[dict[str, str]] = []
    for candidate in config.get("note_backlog") or []:
        if not isinstance(candidate, dict):
            continue
        slug = str(candidate.get("slug") or "").strip()
        if not slug or slug == current_slug:
            continue
        topic = _topic_family_from_item(candidate)
        same_cluster = (
            current_topic in {"pendant", "chandelier"} and topic in {"pendant", "chandelier"}
        ) or (
            current_topic in {"bathroom", "living-room"} and topic in {"bathroom", "living-room"}
        )
        if same_cluster:
            links.append(
                {
                    "label": str(candidate.get("title") or "").strip(),
                    "href": f"/notes/{slug}",
                }
            )
    return links[:2]


def _ensure_related_guides_section(backlog_item: dict[str, Any], config: dict[str, Any]) -> list[dict[str, Any]]:
    sections = [dict(item) for item in (backlog_item.get("sections") or []) if isinstance(item, dict)]
    headings = " ".join(str(item.get("heading") or "") for item in sections).lower()
    if "related guides on neosgo" in headings:
        return sections
    related_links = _related_note_links(backlog_item, config)
    if not related_links:
        return sections
    body = "Readers often compare this decision with closely related lighting questions before they buy. " + " ".join(
        f"{item['label']}: https://neosgo.com{item['href']}" for item in related_links
    )
    sections.append(
        {
            "heading": "Related guides on Neosgo",
            "body": body,
        }
    )
    return sections


def _build_note_internal_links(backlog_item: dict[str, Any], config: dict[str, Any]) -> list[dict[str, str]]:
    topic_key = str(backlog_item.get("topic_key") or "").strip()
    links = config.get("internal_link_map") or {}
    internal_links = [
        {"label": str(item.get("label") or "").strip(), "href": str(item.get("href") or "").strip()}
        for item in (backlog_item.get("customInternalLinks") or [])
        if isinstance(item, dict) and str(item.get("label") or "").strip() and str(item.get("href") or "").strip()
    ]
    if topic_key and topic_key in links:
        default_label = str(backlog_item.get("primaryInternalLinkLabel") or "").strip()
        if not default_label:
            default_label = "Explore the Trade Program" if _is_designer_daily_item(backlog_item) else "Browse related collection"
        internal_links.append({"label": default_label, "href": links[topic_key]})
    if "trade-program" in links:
        internal_links.append({"label": "Explore the Trade Program", "href": links["trade-program"]})
    internal_links.extend(_related_note_links(backlog_item, config))
    deduped: list[dict[str, str]] = []
    seen: set[tuple[str, str]] = set()
    for item in internal_links:
        key = (item["label"], item["href"])
        if key in seen:
            continue
        seen.add(key)
        deduped.append(item)
    return deduped[:4]


def _note_payload(backlog_item: dict[str, Any], config: dict[str, Any]) -> dict[str, Any]:
    internal_links = _build_note_internal_links(backlog_item, config)
    return {
        "slug": backlog_item["slug"],
        "title": backlog_item["title"],
        "description": backlog_item["description"],
        "intentKeyword": backlog_item["intentKeyword"],
        "quickAnswer": backlog_item["quickAnswer"],
        "seoTitle": backlog_item["seoTitle"],
        "seoDescription": backlog_item["seoDescription"],
        "targetAudience": backlog_item["targetAudience"],
        "funnelStage": backlog_item["funnelStage"],
        "sections": backlog_item["sections"],
        "faq": backlog_item["faq"],
        "internalLinks": internal_links,
    }


def _prepare_item_for_publish(
    item: dict[str, Any],
    config: dict[str, Any],
    market_research: dict[str, Any],
    adaptive_profile: dict[str, Any],
) -> dict[str, Any]:
    brief = _compose_research_brief(item, config, market_research, adaptive_profile)
    enriched = dict(item)
    enriched["sections"] = _ensure_editorial_sections(item, brief)
    enriched["sections"] = _ensure_related_guides_section(enriched, config)
    seo_packaging = _build_seo_packaging(enriched, brief, config)
    enriched["quickAnswer"] = seo_packaging["quickAnswer"]
    enriched["seoTitle"] = seo_packaging["seoTitle"]
    enriched["seoDescription"] = seo_packaging["seoDescription"]
    enriched["internalLinks"] = _build_note_internal_links(enriched, config)
    review = _editorial_quality_gate(enriched, brief, config)
    enriched["_research_brief"] = brief
    enriched["_seo_packaging"] = seo_packaging
    enriched["_editorial_review"] = review
    return enriched


def _note_seo_patch_needed(note: dict[str, Any], backlog_item: dict[str, Any]) -> dict[str, Any]:
    patch: dict[str, Any] = {}
    for field in ("seoTitle", "seoDescription", "quickAnswer"):
        desired = str(backlog_item.get(field) or "").strip()
        current = str(note.get(field) or "").strip()
        if desired and desired != current:
            patch[field] = desired
    desired_sections = backlog_item.get("sections") or []
    current_sections = note.get("sections") or []
    if desired_sections and desired_sections != current_sections:
        patch["sections"] = desired_sections
    desired_links = backlog_item.get("internalLinks") or []
    current_links = note.get("internalLinks") or []
    if desired_links != current_links:
        patch["internalLinks"] = desired_links
    return patch


def _build_geo_seo_packaging(note: dict[str, Any], target: dict[str, Any], config: dict[str, Any]) -> dict[str, str]:
    city = str(target.get("city") or "").strip()
    state = str(target.get("state") or "").strip()
    location_label = city if city else state
    brand = str((config.get("site_positioning") or {}).get("brand_name") or "Neosgo Lighting").strip()
    note_slug = str(note.get("slug") or "").strip()
    base_intent = str(note.get("intentKeyword") or "").strip()

    if note_slug == "kitchen-island-pendant-light-spacing-guide":
        seo_title = f"Kitchen Island Pendant Spacing in {location_label}: Size & Height Guide"
        seo_description = f"A {location_label}-focused guide to kitchen island pendant size, spacing, and hanging height, with practical advice on what makes a layout feel balanced."
        quick = f"In {location_label}, the best island pendant layouts come from balancing fixture width, island length, and breathing room rather than relying on one spacing formula."
    elif note_slug == "bathroom-vanity-light-size-guide":
        seo_title = f"Bathroom Vanity Light Size in {location_label}: Mirror Width & Placement"
        seo_description = f"A {location_label}-focused vanity lighting guide covering mirror width, mounting height, and how to avoid harsh or under-scaled bathroom light."
        quick = f"In {location_label}, the right vanity light should relate to mirror width, mount at a flattering height, and create even facial light without glare."
    elif note_slug == "dining-room-chandelier-size-guide":
        seo_title = f"Dining Room Chandelier Size in {location_label}: Diameter & Height Guide"
        seo_description = f"A {location_label}-focused chandelier sizing guide for choosing diameter, hanging height, and visual weight that fit both the table and the room."
        quick = f"In {location_label}, a dining chandelier should feel proportionate to the table and room while hanging low enough to create intimacy without obstructing views."
    elif note_slug == "living-room-layered-lighting-guide":
        seo_title = f"Living Room Layered Lighting in {location_label}: Layout & Balance Guide"
        seo_description = f"A {location_label}-focused guide to ambient, task, and accent lighting for living rooms that need warmth, balance, and better day-to-night usability."
        quick = f"In {location_label}, strong living room lighting plans combine ambient, task, and accent layers so the room feels balanced, useful, and visually calm."
    else:
        seo_title = f"{str(note.get('title') or '').strip()} in {location_label}"
        seo_description = f"Localized guidance for {location_label} based on {base_intent or 'this design note'}."
        quick = str(note.get("quickAnswer") or "").strip()

    if seo_title and brand and brand.lower() not in seo_title.lower():
        seo_title = f"{seo_title} | {brand}"
    return {
        "seoTitle": seo_title,
        "seoDescription": seo_description,
        "quickAnswer": quick,
    }


def _build_geo_localization_context(note: dict[str, Any], target: dict[str, Any]) -> dict[str, Any]:
    city = str(target.get("city") or "").strip()
    state = str(target.get("state") or "").strip()
    note_slug = str(note.get("slug") or "").strip()

    city_profiles: dict[str, dict[str, str]] = {
        "Providence": {
            "style": "older homes, compact rooms, and renovation-heavy layouts often reward fixtures with warmth, visual restraint, and strong proportional discipline",
            "priority": "keeping scale comfortable in older room envelopes while still giving the fixture enough presence",
        },
        "Boston": {
            "style": "condos, brownstones, and design-led remodels often favor clean silhouettes, tighter scale control, and finishes that bridge historic detail with modern restraint",
            "priority": "choosing fixtures that feel intentional in compact rooms without reading heavy",
        },
        "New Haven": {
            "style": "mixed historic and academic-adjacent housing stock often benefits from lighting that feels composed, practical, and not overly ornate",
            "priority": "balancing architectural character with simpler, well-scaled fixtures",
        },
        "Manchester": {
            "style": "family homes and renovation projects often respond well to fixtures that are clear in function, visually calm, and easy to live with over time",
            "priority": "making sure the fixture feels useful and proportionate rather than overly decorative",
        },
        "Portland": {
            "style": "coastal New England interiors often suit softer finishes, natural textures, and lighting that feels warm without becoming casual or under-scaled",
            "priority": "keeping rooms bright and open while preserving a relaxed but refined tone",
        },
        "Burlington": {
            "style": "smaller homes and design-aware renovations often work best with warm, unfussy fixtures that add character without visual clutter",
            "priority": "protecting openness and visual lightness in compact spaces",
        },
        "New York": {
            "style": "apartments and high-design projects often require tighter scale decisions, strong visual editing, and fixtures that deliver impact without crowding the room",
            "priority": "making every inch count while still creating a finished look",
        },
        "Los Angeles": {
            "style": "open-plan homes and design-forward remodels often support larger silhouettes, cleaner lines, and more sculptural lighting choices",
            "priority": "using scale and placement to create presence without losing airiness",
        },
        "Austin": {
            "style": "modern residential projects often lean toward warm minimalism, practical layouts, and a softer mix of metal, wood, and natural texture",
            "priority": "keeping the fixture clean and current without making the room feel cold",
        },
        "Miami": {
            "style": "bright interiors and hospitality-influenced residential spaces often favor crisp silhouettes, stronger contrast, and lighting that reads clearly against sunlit rooms",
            "priority": "choosing fixtures that still feel substantial in bright, reflective spaces",
        },
    }
    state_defaults: dict[str, dict[str, str]] = {
        "RI": {"style": "New England homes often benefit from warmer finishes and careful scale control", "priority": "keeping lighting proportional in renovation-led rooms"},
        "MA": {"style": "design-led New England interiors often prefer restraint, balance, and compact-friendly scale", "priority": "protecting visual breathing room"},
        "CT": {"style": "refined residential interiors often call for composed fixtures and clear room hierarchy", "priority": "balancing function with architectural fit"},
        "NH": {"style": "practical residential projects often reward calm, durable, and well-scaled lighting", "priority": "avoiding overstatement while improving usability"},
        "ME": {"style": "coastal and renovation-heavy homes often suit warm, natural, and visually lighter lighting", "priority": "adding presence without heaviness"},
        "VT": {"style": "smaller, design-aware homes often benefit from simple fixtures with warmth and clarity", "priority": "maintaining openness and proportion"},
        "NY": {"style": "high-density interiors often need tighter scale control and stronger visual editing", "priority": "making compact spaces feel intentional"},
        "CA": {"style": "design-led homes often support cleaner silhouettes and stronger statement lighting", "priority": "balancing sculptural presence with openness"},
        "TX": {"style": "modern residential projects often want warmth, practicality, and a clear contemporary point of view", "priority": "keeping decisions current and livable"},
        "FL": {"style": "bright residential spaces often need fixtures with enough definition to hold the room visually", "priority": "maintaining clarity in high-light environments"},
    }
    profile = city_profiles.get(city) or state_defaults.get(state) or {
        "style": f"{city or state} projects often reward lighting that is balanced, practical, and visually intentional",
        "priority": "keeping scale, function, and finish in sync with the room",
    }

    if note_slug == "kitchen-island-pendant-light-spacing-guide":
        local_tip = f"In {city}, island lighting usually looks strongest when pendant width and spacing are judged against both countertop length and surrounding openness, especially where {profile['style']}."
        mistakes = "The most common miss is using pendants that are individually attractive but collectively too large, too close, or too low for the island composition."
    elif note_slug == "bathroom-vanity-light-size-guide":
        local_tip = f"In {city}, vanity lighting decisions usually work best when mirror width, mounting height, and facial light quality are treated as one composition, especially where {profile['style']}."
        mistakes = "The most common miss is choosing a fixture only by vanity width and forgetting how glare, shadow, and mirror scale affect the final experience."
    elif note_slug == "dining-room-chandelier-size-guide":
        local_tip = f"In {city}, chandelier decisions are strongest when the fixture is judged in relation to the table first and the room second, especially where {profile['style']}."
        mistakes = "The most common miss is following a formula mechanically and ending up with a chandelier that is technically acceptable but visually timid or oversized."
    else:
        local_tip = f"In {city}, layered lighting usually feels best when the room is planned for mood, task use, and evening comfort together, especially where {profile['style']}."
        mistakes = "The most common miss is relying too heavily on one overhead source and then trying to fix comfort with scattered lamps later."

    return {
        "style_context": profile["style"],
        "local_priority": profile["priority"],
        "local_tip": local_tip,
        "mistakes": mistakes,
    }


def _geo_internal_links(note: dict[str, Any], target: dict[str, Any], config: dict[str, Any]) -> list[dict[str, str]]:
    topic = _topic_family_from_item(note)
    links = config.get("internal_link_map") or {}
    out: list[dict[str, str]] = []
    if topic and topic in links:
        out.append({"label": "Browse the matching collection", "href": links[topic]})
    if topic == "pendant" and "kitchen" in links:
        out.append({"label": "Explore kitchen lighting", "href": links["kitchen"]})
    if topic == "bathroom" and "wall-sconce" in links:
        out.append({"label": "View bathroom wall sconces", "href": links["wall-sconce"]})
    if topic == "chandelier" and "dining" in links:
        out.append({"label": "Explore dining room lighting", "href": links["dining"]})
    if topic == "living-room" and "living-room" in links:
        out.append({"label": "Explore living room lighting", "href": links["living-room"]})
    if "trade-program" in links:
        out.append({"label": "See the Trade Program", "href": links["trade-program"]})
    city = str(target.get("city") or "").strip()
    slug = str(note.get("slug") or "").strip()
    if city and slug:
        out.append({"label": f"Read the base guide", "href": f"/notes/{slug}"})
    deduped = []
    seen = set()
    for item in out:
        key = (item["label"], item["href"])
        if key in seen:
            continue
        seen.add(key)
        deduped.append(item)
    return deduped[:4]


def _geo_variant_seo_patch_needed(variant: dict[str, Any], packaging: dict[str, str]) -> dict[str, Any]:
    patch: dict[str, Any] = {}
    for field in ("seoTitle", "seoDescription", "quickAnswer"):
        desired = str(packaging.get(field) or "").strip()
        current = str(variant.get(field) or "").strip()
        if desired and desired != current:
            patch[field] = desired
    return patch


def _geo_variant_content_patch_needed(variant: dict[str, Any], payload: dict[str, Any]) -> dict[str, Any]:
    patch = _geo_variant_seo_patch_needed(variant, payload)
    desired_sections = payload.get("sections") or []
    desired_faq = payload.get("faq") or []
    current_sections = variant.get("sections") or []
    current_faq = variant.get("faq") or []
    current_internal_links = variant.get("internalLinks") or []
    if desired_sections and desired_sections != current_sections:
        patch["sections"] = desired_sections
    if desired_faq != current_faq:
        patch["faq"] = desired_faq
    desired_internal_links = payload.get("internalLinks") or []
    if desired_internal_links != current_internal_links:
        patch["internalLinks"] = desired_internal_links
    return patch


def _geo_variant_payload(note: dict[str, Any], target: dict[str, Any], config: dict[str, Any]) -> dict[str, Any]:
    city = str(target.get("city") or "").strip()
    state = str(target.get("state") or "").strip()
    title = str(note.get("title") or "").strip()
    description = str(note.get("description") or "").strip()
    geo_packaging = _build_geo_seo_packaging(note, target, config)
    geo_context = _build_geo_localization_context(note, target)
    return {
        "geoLabel": target["geoLabel"],
        "city": city,
        "state": state,
        "geoGroup": target["geoGroup"],
        "title": f"{title} in {city}" if city else f"{title} in {state}",
        "description": f"{description} Localized for {city}, {state}." if city else f"{description} Localized for {state}.",
        "intentKeyword": f"{city.lower()} {note.get('intentKeyword','')}".strip() if city else f"{state.lower()} {note.get('intentKeyword','')}".strip(),
        "quickAnswer": geo_packaging.get("quickAnswer") or (f"{note.get('quickAnswer','')} This version is localized for {city}, {state}." if city else note.get("quickAnswer", "")),
        "seoTitle": geo_packaging.get("seoTitle"),
        "seoDescription": geo_packaging.get("seoDescription"),
        "sections": [
            {
                "heading": f"What works well in {city or state} projects?",
                "body": geo_context["local_tip"]
            },
            {
                "heading": f"What to prioritize in {city or state}",
                "body": f"In {city or state}, the key priority is {geo_context['local_priority']}. That usually means making scale and finish decisions in relation to the room rather than treating the fixture as an isolated object."
            },
            {
                "heading": f"Common mistakes in {city or state}",
                "body": geo_context["mistakes"]
            }
        ],
        "faq": [
            {
                "q": f"Should this choice feel different in {city or state}?",
                "a": f"Yes. The underlying sizing logic stays the same, but finish, visual weight, and how much presence the fixture should carry often shift with the kinds of spaces and renovation styles common in {city or state}."
            }
        ],
        "internalLinks": _geo_internal_links(note, target, config),
    }


def _public_note_url(config: dict[str, Any], slug: str) -> str:
    base = str((config.get("site_positioning") or {}).get("website_url") or "https://neosgo.com").rstrip("/")
    return f"{base}/notes/{slug}"


def _public_geo_url(config: dict[str, Any], note_slug: str, geo_slug: str) -> str:
    base = str((config.get("site_positioning") or {}).get("website_url") or "https://neosgo.com").rstrip("/")
    return f"{base}/notes/{note_slug}/geo/{geo_slug}"


def _pick_designer_daily_candidate(
    program: dict[str, Any],
    notes_by_slug: dict[str, dict[str, Any]],
) -> tuple[dict[str, Any], dict[str, Any], int, int]:
    queue = [dict(item) for item in (program.get("article_queue") or []) if isinstance(item, dict)]
    remaining = 0
    published = 0
    candidate: dict[str, Any] = {}
    existing_note: dict[str, Any] = {}
    for item in queue:
        slug = str(item.get("slug") or "").strip()
        if not slug:
            continue
        note = notes_by_slug.get(slug) or {}
        status = str(note.get("status") or "").upper()
        if status == "PUBLISHED":
            published += 1
            continue
        remaining += 1
        if not candidate:
            candidate = item
            existing_note = note
    return candidate, existing_note, len(queue), remaining


def run_cycle() -> dict[str, Any]:
    config = _load_json(CONFIG_PATH, {})
    state = _load_json(STATE_PATH, {"runs": [], "adaptive_profile": {}, "last_market_research": {}, "feedback_history": []})
    env = _load_env_file(SECRET_ENV_PATH)
    base_url = env.get("NEOSGO_ADMIN_MARKETING_API_BASE") or DEFAULT_BASE_URL
    token = env.get("NEOSGO_ADMIN_MARKETING_KEY", "")
    report_chat = env.get("NEOSGO_SEO_GEO_TELEGRAM_CHAT") or str(config.get("report_chat_id") or DEFAULT_CHAT)

    run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    output_base = OUTPUT_DIR / run_id
    output_base.mkdir(parents=True, exist_ok=True)
    FEEDBACK_DIR.mkdir(parents=True, exist_ok=True)

    result: dict[str, Any] = {
        "run_id": run_id,
        "generated_at": _now_iso(),
        "mode": str(config.get("mode") or "draft_only"),
        "publish_allowed": bool(config.get("publish_allowed", False)),
        "api_base_url": base_url,
        "blocked": False,
        "missing_requirements": [],
        "workflow_order": [
            "sync_google_search_console",
            "ingest_history_and_feedback",
            "distill_feedback",
            "market_research",
            "adaptive_strategy_selection",
            "content_execution",
            "report_and_state_writeback",
        ],
        "historical_feedback": {},
        "gsc_sync": {},
        "history_summary": {},
        "market_research": {},
        "adaptive_profile": {},
        "iteration_plan": {},
        "opportunity_registry": {},
        "page_action_plan": {},
        "maintenance_plan": {},
        "consolidation_plan": {},
        "research_briefs": [],
        "seo_packaging_reviews": [],
        "geo_seo_packaging_reviews": [],
        "editorial_reviews": [],
        "technical_release_gates": [],
        "designer_daily_program": {},
        "summary": {},
        "writes": [],
        "gaps": [],
        "deliveries": [],
    }

    if not SECRET_ENV_PATH.exists():
        result["blocked"] = True
        result["missing_requirements"].append("missing_secret_file:/Users/mac_claw/.openclaw/secrets/neosgo-marketing.env")
    if not token:
        result["blocked"] = True
        result["missing_requirements"].append("missing_secret:NEOSGO_ADMIN_MARKETING_KEY")

    backlog = config.get("note_backlog") or []
    try:
        result["gsc_sync"] = sync_gsc_feedback(env, FEEDBACK_DIR, run_id)
    except GoogleSearchConsoleError as exc:
        result["gsc_sync"] = {"enabled": True, "ran": False, "reason": "sync_failed"}
        result["missing_requirements"].append(f"gsc_sync_failed:{exc}")
    feedback_rows, feedback_issues = _load_feedback_rows(config)
    result["historical_feedback"] = _summarize_feedback(feedback_rows, backlog, config)
    result["history_summary"] = _summarize_run_history(state)
    if feedback_issues:
        result["missing_requirements"].extend(feedback_issues)

    if not result["blocked"]:
        client = MarketingApiClient(base_url=base_url, bearer_token=token)
        try:
            notes_payload = client.list_design_notes()
            notes_by_slug = _existing_notes_by_slug(notes_payload)
            inventory_summary = _build_inventory_summary(notes_by_slug, backlog, client)
            geo_targets = sorted(config.get("geo_targets") or [], key=lambda item: int(item.get("priority", 9999)))
            result["opportunity_registry"] = build_opportunity_registry(
                backlog=backlog,
                notes_by_slug=notes_by_slug,
                feedback_summary=result["historical_feedback"],
                geo_targets=geo_targets,
            )
            result["page_action_plan"] = build_page_action_plan(
                opportunity_registry=result["opportunity_registry"],
                create_limit=int(config.get("daily_create_limit", 2) or 2),
                geo_limit=int(config.get("daily_geo_variant_limit", 4) or 4),
            )
            result["maintenance_plan"] = build_maintenance_plan(
                opportunity_registry=result["opportunity_registry"],
                state=state,
            )
            result["consolidation_plan"] = build_consolidation_plan(result["opportunity_registry"])
            result["market_research"] = _build_market_research(config, result["historical_feedback"], inventory_summary)
            result["adaptive_profile"] = _build_adaptive_profile(
                config,
                result["historical_feedback"],
                inventory_summary,
                result["market_research"],
                result["history_summary"],
            )
            result["iteration_plan"] = _build_iteration_plan(
                backlog,
                notes_by_slug,
                result["historical_feedback"],
                result.get("gsc_sync") or {},
                result["history_summary"],
            )

            ranked_backlog = _rank_backlog(backlog, result["adaptive_profile"], result["historical_feedback"], inventory_summary)
            note_release_gates: dict[str, dict[str, Any]] = {}
            enhanced_backlog: list[dict[str, Any]] = []
            for item in ranked_backlog:
                enriched = _prepare_item_for_publish(item, config, result["market_research"], result["adaptive_profile"])
                brief = enriched["_research_brief"]
                seo_packaging = enriched["_seo_packaging"]
                review = enriched["_editorial_review"]
                note_payload = _note_payload(enriched, config)
                release_gate = evaluate_release_gate(note_payload, config, kind="note")
                note_release_gates[str(item.get("slug") or "").strip()] = release_gate
                enhanced_backlog.append(enriched)
                result["research_briefs"].append({"slug": item.get("slug"), **brief})
                result["seo_packaging_reviews"].append(
                    {
                        "slug": item.get("slug"),
                        "seoTitle": seo_packaging.get("seoTitle"),
                        "seoDescription": seo_packaging.get("seoDescription"),
                        "quickAnswer": seo_packaging.get("quickAnswer"),
                        "packagingRationale": seo_packaging.get("packagingRationale"),
                    }
                )
                result["editorial_reviews"].append({"slug": item.get("slug"), **review})
                result["technical_release_gates"].append({"slug": item.get("slug"), **release_gate})

            create_limit = int(config.get("daily_create_limit", 2) or 2)
            geo_limit = int(config.get("daily_geo_variant_limit", 4) or 4)
            created = 0
            created_variants = 0
            backfill_published_notes = 0
            backfill_published_variants = 0
            publish_blocked_count = 0
            action_by_slug = dict((result.get("page_action_plan") or {}).get("action_by_slug") or {})

            for item in enhanced_backlog:
                slug = str(item.get("slug") or "").strip()
                if not slug:
                    continue
                action_plan_row = dict(action_by_slug.get(slug) or {})
                if not action_plan_row.get("execute_this_run"):
                    continue
                note_gate = dict(note_release_gates.get(slug) or {})
                note = notes_by_slug.get(slug)
                if not note:
                    result["gaps"].append(
                        {
                            "type": "missing_note",
                            "slug": slug,
                            "title": item.get("title"),
                            "adaptive_score": item.get("_adaptive_score", 0),
                        }
                    )
                    if created < create_limit:
                        payload = _note_payload(item, config)
                        write = client.create_design_note(payload)
                        resolved = write if isinstance(write, dict) and write.get("id") else _lookup_note_by_slug(client, slug)
                        note = resolved if isinstance(resolved, dict) and resolved else (write if isinstance(write, dict) else {})
                        note_id_for_publish = str((note or {}).get("id") or "").strip()
                        publish_result: dict[str, Any] = {}
                        final_status = (note or write or {}).get("status", "DRAFT")
                        if config.get("publish_allowed") and note_id_for_publish and note_gate.get("passed"):
                            publish_result = client.publish_design_note(note_id_for_publish)
                            final_status = publish_result.get("status", final_status)
                        elif config.get("publish_allowed") and note_id_for_publish and not note_gate.get("passed"):
                            publish_blocked_count += 1
                        result["writes"].append(
                            {
                                "kind": "design_note_create",
                                "slug": slug,
                                "topic": _topic_family_from_item(item),
                                "adaptive_score": item.get("_adaptive_score", 0),
                                "editorial_score": ((item.get("_editorial_review") or {}).get("score")),
                                "release_gate_passed": note_gate.get("passed", False),
                                "release_gate_blockers": note_gate.get("blocking_items", []),
                                "status": final_status,
                                "id": (note or write or {}).get("id"),
                                "published": bool(config.get("publish_allowed") and note_id_for_publish and note_gate.get("passed")),
                                "publish_result": publish_result if publish_result else None,
                                "public_url": _public_note_url(config, slug),
                            }
                        )
                        created += 1
                if not note:
                    continue
                note_id = str(note.get("id") or "").strip()
                if not note_id:
                    continue
                seo_patch = _note_seo_patch_needed(note, item)
                if seo_patch:
                    updated_note = client.update_design_note(note_id, seo_patch)
                    for key, value in seo_patch.items():
                        note[key] = value
                    result["writes"].append(
                        {
                            "kind": "design_note_seo_refresh",
                            "note_id": note_id,
                            "slug": slug,
                            "status": updated_note.get("status", note.get("status")),
                            "patched_fields": sorted(seo_patch.keys()),
                            "seoTitle": seo_patch.get("seoTitle"),
                            "seoDescription": seo_patch.get("seoDescription"),
                            "quickAnswer": seo_patch.get("quickAnswer"),
                            "public_url": _public_note_url(config, slug),
                        }
                    )
                if config.get("publish_allowed") and _should_publish_note(note) and note_gate.get("passed"):
                    publish_result = client.publish_design_note(note_id)
                    note["status"] = publish_result.get("status", note.get("status"))
                    note["publishedAt"] = publish_result.get("publishedAt", note.get("publishedAt"))
                    result["writes"].append(
                        {
                            "kind": "design_note_publish_backfill",
                            "note_id": note_id,
                            "slug": slug,
                            "status": note.get("status"),
                            "published": True,
                            "publish_result": publish_result,
                            "public_url": _public_note_url(config, slug),
                        }
                    )
                    backfill_published_notes += 1
                elif config.get("publish_allowed") and _should_publish_note(note) and not note_gate.get("passed"):
                    publish_blocked_count += 1
                    result["gaps"].append(
                        {
                            "type": "note_release_gate_blocked",
                            "slug": slug,
                            "blocking_items": note_gate.get("blocking_items", []),
                        }
                    )
                variants = _variant_rows(client.list_geo_variants(note_id))
                existing_geo_slugs = {
                    str(row.get("geoSlug") or row.get("slug") or "").strip(): row
                    for row in variants
                    if str(row.get("geoSlug") or row.get("slug") or "").strip()
                }
                if config.get("publish_allowed"):
                    for existing_slug, existing_variant in existing_geo_slugs.items():
                        geo_gate: dict[str, Any] = {"passed": True, "blocking_items": []}
                        matched_target = next(
                            (
                                target for target in geo_targets
                                if str(target.get("city") or "").strip().lower() == str(existing_variant.get("city") or "").strip().lower()
                                and str(target.get("state") or "").strip().lower() == str(existing_variant.get("state") or "").strip().lower()
                            ),
                            None,
                        )
                        if matched_target:
                            geo_payload = _geo_variant_payload(note, matched_target, config)
                            geo_gate = evaluate_release_gate(geo_payload, config, kind="geo_variant")
                            result["technical_release_gates"].append(
                                {
                                    "slug": slug,
                                    "geo_slug": existing_slug,
                                    **geo_gate,
                                }
                            )
                            result["geo_seo_packaging_reviews"].append(
                                {
                                    "note_slug": slug,
                                    "geo_slug": existing_slug,
                                    "seoTitle": geo_payload.get("seoTitle"),
                                    "seoDescription": geo_payload.get("seoDescription"),
                                    "quickAnswer": geo_payload.get("quickAnswer"),
                                }
                            )
                            geo_patch = _geo_variant_content_patch_needed(existing_variant, geo_payload)
                            if geo_patch:
                                updated_variant = client.update_geo_variant(note_id, str(existing_variant.get("id") or existing_variant.get("variantId")), geo_patch)
                                for key, value in geo_patch.items():
                                    existing_variant[key] = value
                                result["writes"].append(
                                    {
                                        "kind": "geo_variant_seo_refresh",
                                        "note_id": note_id,
                                        "note_slug": slug,
                                        "variantId": str(existing_variant.get("id") or existing_variant.get("variantId") or ""),
                                        "geo_slug": existing_slug,
                                        "status": updated_variant.get("status", existing_variant.get("status")),
                                        "patched_fields": sorted(geo_patch.keys()),
                                        "seoTitle": geo_patch.get("seoTitle"),
                                        "seoDescription": geo_patch.get("seoDescription"),
                                        "quickAnswer": geo_patch.get("quickAnswer"),
                                        "public_url": _public_geo_url(config, slug, existing_slug),
                                }
                            )
                        variant_id = str(existing_variant.get("id") or existing_variant.get("variantId") or "").strip()
                        if not variant_id or not _should_publish_variant(existing_variant):
                            continue
                        if not geo_gate.get("passed"):
                            publish_blocked_count += 1
                            result["gaps"].append(
                                {
                                    "type": "geo_release_gate_blocked",
                                    "note_slug": slug,
                                    "geo_slug": existing_slug,
                                    "blocking_items": geo_gate.get("blocking_items", []),
                                }
                            )
                            continue
                        publish_result = client.publish_geo_variant(note_id, variant_id)
                        existing_variant["status"] = publish_result.get("status", existing_variant.get("status"))
                        existing_variant["publishedAt"] = publish_result.get("publishedAt", existing_variant.get("publishedAt"))
                        result["writes"].append(
                            {
                                "kind": "geo_variant_publish_backfill",
                                "note_id": note_id,
                                "note_slug": slug,
                                "variantId": variant_id,
                                "geo_slug": existing_slug,
                                "status": existing_variant.get("status"),
                                "published": True,
                                "publish_result": publish_result,
                                "public_url": _public_geo_url(config, slug, existing_slug),
                            }
                        )
                        backfill_published_variants += 1
                for target in geo_targets:
                    geo_slug = _slugify_geo(target)
                    if not geo_slug:
                        continue
                    exists_for_target, matched_variant = _variant_exists_for_target(variants, target)
                    if not exists_for_target:
                        result["gaps"].append(
                            {
                                "type": "missing_geo_variant",
                                "note_slug": slug,
                                "geo_slug": geo_slug,
                                "state": target.get("state"),
                            }
                        )
                        if created_variants < geo_limit:
                            payload = _geo_variant_payload(item, target, config)
                            geo_gate = evaluate_release_gate(payload, config, kind="geo_variant")
                            result["technical_release_gates"].append(
                                {
                                    "slug": slug,
                                    "geo_slug": geo_slug,
                                    **geo_gate,
                                }
                            )
                            write = client.create_geo_variant(note_id, payload)
                            resolved_variant = (
                                write
                                if isinstance(write, dict) and (write.get("variantId") or write.get("id"))
                                else _lookup_variant_by_target(client, note_id, geo_slug, target)
                            )
                            variant_id = (resolved_variant or write).get("variantId") or (resolved_variant or write).get("id")
                            final_status = (resolved_variant or write).get("status", "DRAFT")
                            publish_result: dict[str, Any] = {}
                            if config.get("publish_allowed") and variant_id and geo_gate.get("passed"):
                                publish_result = client.publish_geo_variant(note_id, str(variant_id))
                                final_status = publish_result.get("status", final_status)
                            elif config.get("publish_allowed") and variant_id and not geo_gate.get("passed"):
                                publish_blocked_count += 1
                            result["writes"].append(
                                {
                                    "kind": "geo_variant_create",
                                    "note_id": note_id,
                                    "note_slug": slug,
                                    "variantId": variant_id,
                                    "geo_slug": write.get("geoSlug") or geo_slug,
                                    "state": target.get("state"),
                                    "status": final_status,
                                    "release_gate_passed": geo_gate.get("passed", False),
                                    "release_gate_blockers": geo_gate.get("blocking_items", []),
                                    "published": bool(config.get("publish_allowed") and variant_id and geo_gate.get("passed")),
                                    "publish_result": publish_result if publish_result else None,
                                    "public_url": _public_geo_url(config, slug, write.get("geoSlug") or geo_slug),
                                }
                            )
                            result["geo_seo_packaging_reviews"].append(
                                {
                                    "note_slug": slug,
                                    "geo_slug": write.get("geoSlug") or geo_slug,
                                    "seoTitle": payload.get("seoTitle"),
                                    "seoDescription": payload.get("seoDescription"),
                                    "quickAnswer": payload.get("quickAnswer"),
                                }
                            )
                            created_variants += 1
                            variants = _variant_rows(client.list_geo_variants(note_id))
                            existing_geo_slugs = {
                                str(row.get("geoSlug") or row.get("slug") or "").strip(): row
                                for row in variants
                                if str(row.get("geoSlug") or row.get("slug") or "").strip()
                            }
                    elif config.get("publish_allowed") and _should_publish_variant(matched_variant):
                        variant_id = str(matched_variant.get("id") or matched_variant.get("variantId") or "").strip()
                        if variant_id:
                            geo_payload = _geo_variant_payload(note, target, config)
                            geo_gate = evaluate_release_gate(geo_payload, config, kind="geo_variant")
                            result["technical_release_gates"].append(
                                {
                                    "slug": slug,
                                    "geo_slug": geo_slug,
                                    **geo_gate,
                                }
                            )
                            if not geo_gate.get("passed"):
                                publish_blocked_count += 1
                                result["gaps"].append(
                                    {
                                        "type": "geo_release_gate_blocked",
                                        "note_slug": slug,
                                        "geo_slug": geo_slug,
                                        "blocking_items": geo_gate.get("blocking_items", []),
                                    }
                                )
                                continue
                            publish_result = client.publish_geo_variant(note_id, variant_id)
                            matched_slug = str(matched_variant.get("geoSlug") or matched_variant.get("slug") or geo_slug)
                            result["writes"].append(
                                {
                                    "kind": "geo_variant_publish_match",
                                    "note_id": note_id,
                                    "note_slug": slug,
                                    "variantId": variant_id,
                                    "geo_slug": matched_slug,
                                    "state": target.get("state"),
                                    "status": publish_result.get("status", matched_variant.get("status")),
                                    "published": True,
                                    "publish_result": publish_result,
                                    "public_url": _public_geo_url(config, slug, matched_slug),
                                }
                            )
            designer_program = dict(config.get("designer_daily_program") or {})
            designer_status: dict[str, Any] = {
                "enabled": bool(designer_program.get("enabled")),
            }
            if designer_status["enabled"]:
                timezone_name = str(designer_program.get("state_timezone") or "America/Los_Angeles")
                today_local = _local_calendar_date(timezone_name)
                program_state = dict(state.get("designer_daily_program") or {})
                candidate, existing_note, queue_total, remaining_queue = _pick_designer_daily_candidate(designer_program, notes_by_slug)
                designer_status.update(
                    {
                        "timezone": timezone_name,
                        "today_local": today_local,
                        "queue_total": queue_total,
                        "remaining_queue": remaining_queue,
                        "already_published_today": program_state.get("last_published_date") == today_local,
                    }
                )
                if designer_status["already_published_today"]:
                    designer_status["skipped_reason"] = "already_published_today"
                elif not candidate:
                    designer_status["skipped_reason"] = "queue_exhausted"
                else:
                    prepared = _prepare_item_for_publish(candidate, config, result["market_research"], result["adaptive_profile"])
                    brief = prepared["_research_brief"]
                    seo_packaging = prepared["_seo_packaging"]
                    review = prepared["_editorial_review"]
                    slug = str(prepared.get("slug") or "").strip()
                    result["research_briefs"].append({"slug": slug, **brief})
                    result["seo_packaging_reviews"].append(
                        {
                            "slug": slug,
                            "seoTitle": seo_packaging.get("seoTitle"),
                            "seoDescription": seo_packaging.get("seoDescription"),
                            "quickAnswer": seo_packaging.get("quickAnswer"),
                            "packagingRationale": seo_packaging.get("packagingRationale"),
                        }
                    )
                    result["editorial_reviews"].append({"slug": slug, **review})
                    designer_status.update(
                        {
                            "selected_slug": slug,
                            "editorial_score": review.get("score"),
                            "quality_passed": review.get("passed"),
                        }
                    )
                    if not review.get("passed"):
                        designer_status["skipped_reason"] = "quality_gate_failed"
                    else:
                        note = existing_note if existing_note else {}
                        note_id = str(note.get("id") or "").strip()
                        if not note:
                            payload = _note_payload(prepared, config)
                            write = client.create_design_note(payload)
                            resolved = write if isinstance(write, dict) and write.get("id") else _lookup_note_by_slug(client, slug)
                            note = resolved if isinstance(resolved, dict) and resolved else (write if isinstance(write, dict) else {})
                            note_id = str((note or {}).get("id") or "").strip()
                            result["writes"].append(
                                {
                                    "kind": "designer_daily_note_create",
                                    "slug": slug,
                                    "topic": _topic_family_from_item(prepared),
                                    "editorial_score": review.get("score"),
                                    "status": (note or write or {}).get("status", "DRAFT"),
                                    "id": (note or write or {}).get("id"),
                                    "public_url": _public_note_url(config, slug),
                                }
                            )
                        if note and note_id:
                            seo_patch = _note_seo_patch_needed(note, prepared)
                            if seo_patch:
                                updated_note = client.update_design_note(note_id, seo_patch)
                                for key, value in seo_patch.items():
                                    note[key] = value
                                result["writes"].append(
                                    {
                                        "kind": "designer_daily_note_refresh",
                                        "note_id": note_id,
                                        "slug": slug,
                                        "status": updated_note.get("status", note.get("status")),
                                        "patched_fields": sorted(seo_patch.keys()),
                                        "public_url": _public_note_url(config, slug),
                                    }
                                )
                            publish_result: dict[str, Any] = {}
                            final_status = note.get("status", "DRAFT")
                            if config.get("publish_allowed") and _should_publish_note(note):
                                publish_result = client.publish_design_note(note_id)
                                note["status"] = publish_result.get("status", note.get("status"))
                                note["publishedAt"] = publish_result.get("publishedAt", note.get("publishedAt"))
                                final_status = note.get("status", final_status)
                                result["writes"].append(
                                    {
                                        "kind": "designer_daily_note_publish",
                                        "note_id": note_id,
                                        "slug": slug,
                                        "status": final_status,
                                        "published": True,
                                        "publish_result": publish_result,
                                        "public_url": _public_note_url(config, slug),
                                    }
                                )
                            notes_by_slug[slug] = note
                            designer_status.update(
                                {
                                    "status": final_status,
                                    "published": final_status == "PUBLISHED",
                                    "public_url": _public_note_url(config, slug),
                                }
                            )
                            state["designer_daily_program"] = {
                                **program_state,
                                "timezone": timezone_name,
                                "last_selected_date": today_local,
                                "last_selected_slug": slug,
                                "last_published_date": today_local if final_status == "PUBLISHED" else program_state.get("last_published_date"),
                            }
            result["designer_daily_program"] = designer_status
            result["summary"] = {
                "existing_note_count": inventory_summary.get("existing_note_count", 0),
                "backlog_note_count": len(backlog),
                "feedback_row_count": result["historical_feedback"].get("row_count", 0),
                "opportunity_item_count": (result.get("opportunity_registry") or {}).get("item_count", 0),
                "selected_action_count": len((result.get("page_action_plan") or {}).get("selected_actions", [])),
                "skipped_action_count": len((result.get("page_action_plan") or {}).get("skipped_actions", [])),
                "writes_count": len(result["writes"]),
                "gap_count": len(result["gaps"]),
                "merge_candidate_count": len((result.get("consolidation_plan") or {}).get("merge_candidates", [])),
                "redirect_candidate_count": len((result.get("consolidation_plan") or {}).get("redirect_candidates", [])),
                "prune_candidate_count": len((result.get("consolidation_plan") or {}).get("prune_candidates", [])),
                "published_note_backfills": backfill_published_notes,
                "published_variant_backfills": backfill_published_variants,
                "editorial_pass_count": sum(1 for row in result["editorial_reviews"] if row.get("passed")),
                "technical_release_gate_pass_count": sum(1 for row in result["technical_release_gates"] if row.get("passed")),
                "technical_release_gate_fail_count": sum(1 for row in result["technical_release_gates"] if not row.get("passed")),
                "publish_blocked_count": publish_blocked_count,
                "weekly_maintenance_due": bool((result.get("maintenance_plan") or {}).get("weekly_due")),
                "monthly_maintenance_due": bool((result.get("maintenance_plan") or {}).get("monthly_due")),
                "geo_priority_order": [target.get("state") for target in geo_targets],
                "primary_focus_topic": result["adaptive_profile"].get("primary_focus_topic"),
                "research_lead_topic": result["adaptive_profile"].get("research_lead_topic"),
                "designer_queue_remaining": (result.get("designer_daily_program") or {}).get("remaining_queue", 0),
                "designer_selected_slug": (result.get("designer_daily_program") or {}).get("selected_slug"),
            }
        except MarketingApiError as exc:
            result["blocked"] = True
            result["missing_requirements"].append(str(exc))

    md_lines = [
        "# Neosgo SEO + GEO daily report",
        "",
        f"- Generated at: {result['generated_at']}",
        f"- Mode: {result['mode']}",
        f"- Publish allowed: {result['publish_allowed']}",
        f"- API base: {result['api_base_url']}",
        f"- Blocked: {result['blocked']}",
        f"- Workflow order: {' -> '.join(result['workflow_order'])}",
    ]
    if result["missing_requirements"]:
        md_lines.extend(["", "## Missing requirements / issues"])
        md_lines.extend([f"- {item}" for item in result["missing_requirements"]])
    md_lines.extend(
        [
            "",
            "## Summary",
            f"- Existing notes: {(result.get('summary') or {}).get('existing_note_count', 0)}",
            f"- Backlog notes: {(result.get('summary') or {}).get('backlog_note_count', 0)}",
            f"- Historical feedback rows loaded: {(result.get('summary') or {}).get('feedback_row_count', 0)}",
            f"- Opportunity items: {(result.get('summary') or {}).get('opportunity_item_count', 0)}",
            f"- Selected actions: {(result.get('summary') or {}).get('selected_action_count', 0)}",
            f"- Skipped actions: {(result.get('summary') or {}).get('skipped_action_count', 0)}",
            f"- GSC sync: {((result.get('gsc_sync') or {}).get('reason') or ('ok' if (result.get('gsc_sync') or {}).get('ran') else 'not_run'))}",
            f"- Primary focus topic: {(result.get('summary') or {}).get('primary_focus_topic', 'n/a')}",
            f"- Research lead topic: {(result.get('summary') or {}).get('research_lead_topic', 'n/a')}",
            f"- Editorial pass count: {(result.get('summary') or {}).get('editorial_pass_count', 0)}",
            f"- Technical release gate pass count: {(result.get('summary') or {}).get('technical_release_gate_pass_count', 0)}",
            f"- Technical release gate fail count: {(result.get('summary') or {}).get('technical_release_gate_fail_count', 0)}",
            f"- Publish blocked by gate: {(result.get('summary') or {}).get('publish_blocked_count', 0)}",
            f"- Weekly maintenance due: {(result.get('summary') or {}).get('weekly_maintenance_due', False)}",
            f"- Monthly maintenance due: {(result.get('summary') or {}).get('monthly_maintenance_due', False)}",
            f"- Writes this run: {(result.get('summary') or {}).get('writes_count', 0)}",
            f"- Merge candidates: {(result.get('summary') or {}).get('merge_candidate_count', 0)}",
            f"- Redirect candidates: {(result.get('summary') or {}).get('redirect_candidate_count', 0)}",
            f"- Prune candidates: {(result.get('summary') or {}).get('prune_candidate_count', 0)}",
            f"- Published note backfills: {(result.get('summary') or {}).get('published_note_backfills', 0)}",
            f"- Published GEO backfills: {(result.get('summary') or {}).get('published_variant_backfills', 0)}",
            f"- Remaining gaps: {(result.get('summary') or {}).get('gap_count', 0)}",
            f"- Designer queue remaining: {(result.get('summary') or {}).get('designer_queue_remaining', 0)}",
            f"- Designer selection: {(result.get('summary') or {}).get('designer_selected_slug') or 'none'}",
            f"- Geo priority order: {', '.join((result.get('summary') or {}).get('geo_priority_order', []))}",
        ]
    )
    md_lines.extend(["", "## Historical feedback distillation"])
    hist = result.get("historical_feedback") or {}
    md_lines.append(f"- Feedback rows loaded: {hist.get('row_count', 0)}")
    md_lines.append(f"- Matched note/GEO rows: {hist.get('matched_slug_rows', 0)}")
    md_lines.append(f"- Unmatched rows: {hist.get('unmatched_slug_rows', 0)}")
    for item in hist.get("top_topics", [])[:5]:
        md_lines.append(f"- Topic `{item['topic']}` | clicks={item['clicks']} | query_clicks={item.get('query_clicks', 0)} | feedback={item['avg_feedback_score']} | conversion={item['avg_conversion_rate']}")
    if hist.get("top_query_topics"):
        md_lines.append("- Query-led topic signals:")
        for item in hist.get("top_query_topics", [])[:5]:
            md_lines.append(
                f"  - `{item['topic']}` | query_clicks={item['clicks']} | query_impressions={item['impressions']} | top_queries={', '.join(item.get('top_queries') or [])}"
            )
    if hist.get("top_unmatched_pages"):
        md_lines.append("- Unmatched pages seen in feedback:")
        for item in hist.get("top_unmatched_pages", [])[:5]:
            md_lines.append(
                f"  - `{item['page']}` | clicks={item['clicks']} | impressions={item['impressions']} | samples={item['samples']}"
            )

    md_lines.extend(["", "## Google Search Console sync"])
    gsc_sync = result.get("gsc_sync") or {}
    if gsc_sync.get("ran"):
        md_lines.append(
            f"- Site: {gsc_sync.get('site_url')} | lookback={gsc_sync.get('lookback_days')}d | {gsc_sync.get('start_date')} -> {gsc_sync.get('end_date')}"
        )
        for label, info in (gsc_sync.get("snapshots") or {}).items():
            md_lines.append(f"- {label}: rows={info.get('row_count', 0)}")
    else:
        md_lines.append(f"- Not synced: {gsc_sync.get('reason', 'not_configured')}")

    md_lines.extend(["", "## Market research"])
    market = result.get("market_research") or {}
    if market.get("top_research_candidates"):
        for item in market["top_research_candidates"][:5]:
            md_lines.append(
                f"- Topic `{item['topic']}` | score={item['research_score']} | note_gap={item['note_gap']} | geo_gap={item['geo_gap']} | clicks={item['historical_clicks']} | query_clicks={item.get('query_clicks', 0)}"
            )
            if item.get("top_queries"):
                md_lines.append(f"  top_queries: {', '.join(item.get('top_queries')[:3])}")
    else:
        md_lines.append("- No research candidates computed.")

    md_lines.extend(["", "## Research briefs"])
    if result.get("research_briefs"):
        for item in (result.get("research_briefs") or [])[:5]:
            md_lines.append(
                f"- `{item.get('slug')}` | topic={item.get('topic')} | angle={item.get('angle')} | problem={item.get('reader_problem')}"
            )
            if item.get("competitor_gaps"):
                md_lines.append(f"  competitor gaps: {', '.join(item.get('competitor_gaps')[:3])}")
    else:
        md_lines.append("- No research briefs built.")

    md_lines.extend(["", "## SEO packaging"])
    if result.get("seo_packaging_reviews"):
        for item in (result.get("seo_packaging_reviews") or [])[:5]:
            md_lines.append(f"- `{item.get('slug')}`")
            md_lines.append(f"  seoTitle: {item.get('seoTitle')}")
            md_lines.append(f"  seoDescription: {item.get('seoDescription')}")
            md_lines.append(f"  quickAnswer: {item.get('quickAnswer')}")
    else:
        md_lines.append("- No SEO packaging reviews computed.")

    md_lines.extend(["", "## GEO SEO packaging"])
    if result.get("geo_seo_packaging_reviews"):
        for item in (result.get("geo_seo_packaging_reviews") or [])[:8]:
            md_lines.append(f"- `{item.get('note_slug')}` / `{item.get('geo_slug')}`")
            md_lines.append(f"  seoTitle: {item.get('seoTitle')}")
            md_lines.append(f"  seoDescription: {item.get('seoDescription')}")
            md_lines.append(f"  quickAnswer: {item.get('quickAnswer')}")
    else:
        md_lines.append("- No GEO SEO packaging reviews computed.")

    md_lines.extend(["", "## Adaptive strategy"])
    profile = result.get("adaptive_profile") or {}
    for item in profile.get("topic_priority", [])[:5]:
        md_lines.append(
            f"- Topic `{item['topic']}` | adaptive_score={item['adaptive_score']} | gap_urgency={item['gap_urgency']} | fresh_geo_need={item['fresh_geo_need']} | query_clicks={item.get('query_clicks', 0)}"
        )

    md_lines.extend(["", "## Iteration plan"])
    iteration_plan = result.get("iteration_plan") or {}
    if iteration_plan.get("note_iteration_priorities"):
        for item in iteration_plan.get("note_iteration_priorities", [])[:6]:
            md_lines.append(
                f"- `{item['slug']}` | action={item['next_action']} | impressions={item['impressions']} | clicks={item['clicks']} | topic_query_impressions={item['topic_query_impressions']}"
            )
            md_lines.append(f"  reason: {item['reason']}")
    else:
        md_lines.append("- No iteration priorities computed.")

    md_lines.extend(["", "## Editorial quality gate"])
    if result.get("editorial_reviews"):
        for item in (result.get("editorial_reviews") or [])[:5]:
            dims = item.get("dimensions") or {}
            md_lines.append(
                f"- `{item.get('slug')}` | score={item.get('score')} | passed={item.get('passed')} | intent={dims.get('intent_alignment')} | utility={dims.get('decision_utility')} | depth={dims.get('professional_depth')}"
            )
    else:
        md_lines.append("- No editorial reviews computed.")

    md_lines.extend(["", "## Opportunity registry"])
    if (result.get("opportunity_registry") or {}).get("top_actions"):
        for item in (result.get("opportunity_registry") or {}).get("top_actions", [])[:8]:
            md_lines.append(
                f"- `{item['slug']}` | action={item['recommended_action']} | score={item['action_score']} | status={item['status']} | clicks={item['clicks']} | impressions={item['impressions']} | geo_gap={item['geo_gap']}"
            )
    else:
        md_lines.append("- No opportunity registry rows computed.")

    md_lines.extend(["", "## Page action plan"])
    if (result.get("page_action_plan") or {}).get("selected_actions"):
        for item in (result.get("page_action_plan") or {}).get("selected_actions", [])[:10]:
            md_lines.append(
                f"- `{item['slug']}` | action={item['recommended_action']} | score={item['action_score']} | execute={item['execute_this_run']}"
            )
    else:
        md_lines.append("- No page actions selected.")

    md_lines.extend(["", "## Technical release gate"])
    if result.get("technical_release_gates"):
        for item in (result.get("technical_release_gates") or [])[:10]:
            md_lines.append(
                f"- `{item.get('slug')}`{(' / ' + str(item.get('geo_slug'))) if item.get('geo_slug') else ''} | kind={item.get('kind')} | passed={item.get('passed')} | score={item.get('score')}"
            )
            if item.get("blocking_items"):
                md_lines.append(f"  blockers: {', '.join(item.get('blocking_items')[:6])}")
    else:
        md_lines.append("- No technical release gates computed.")

    md_lines.extend(["", "## Maintenance plan"])
    maintenance_plan = result.get("maintenance_plan") or {}
    md_lines.append(f"- Weekly due: {maintenance_plan.get('weekly_due', False)}")
    md_lines.append(f"- Monthly due: {maintenance_plan.get('monthly_due', False)}")
    for item in maintenance_plan.get("weekly_actions", []):
        md_lines.append(f"- Weekly action `{item.get('type')}` | count={item.get('count')} | slugs={', '.join(item.get('slugs', [])[:5])}")
    for item in maintenance_plan.get("monthly_actions", []):
        md_lines.append(f"- Monthly action `{item.get('type')}` | count={item.get('count')} | slugs={', '.join(item.get('slugs', [])[:5])}")

    md_lines.extend(["", "## Consolidation plan"])
    consolidation_plan = result.get("consolidation_plan") or {}
    md_lines.append(f"- Topic clusters: {consolidation_plan.get('topic_cluster_count', 0)}")
    for item in consolidation_plan.get("merge_candidates", [])[:8]:
        md_lines.append(
            f"- Merge review `{item.get('slug')}` -> `{item.get('target_slug')}` | topic={item.get('topic')} | clicks={item.get('clicks')} | impressions={item.get('impressions')}"
        )
    for item in consolidation_plan.get("redirect_candidates", [])[:8]:
        md_lines.append(
            f"- Redirect review `{item.get('slug')}` -> `{item.get('target_slug')}` | topic={item.get('topic')} | impressions={item.get('impressions')}"
        )
    for item in consolidation_plan.get("prune_candidates", [])[:8]:
        md_lines.append(
            f"- Prune review `{item.get('slug')}` | topic={item.get('topic')} | freshness_days={item.get('freshness_days')} | impressions={item.get('impressions')}"
        )

    md_lines.extend(["", "## Interior Designer Daily Article"])
    designer_program = result.get("designer_daily_program") or {}
    md_lines.append(f"- Enabled: {designer_program.get('enabled', False)}")
    if designer_program.get("enabled"):
        md_lines.append(f"- Timezone: {designer_program.get('timezone')}")
        md_lines.append(f"- Today local: {designer_program.get('today_local')}")
        md_lines.append(f"- Queue total: {designer_program.get('queue_total', 0)}")
        md_lines.append(f"- Remaining queue: {designer_program.get('remaining_queue', 0)}")
        md_lines.append(f"- Already published today: {designer_program.get('already_published_today', False)}")
        md_lines.append(f"- Selected slug: {designer_program.get('selected_slug') or 'none'}")
        md_lines.append(f"- Quality score: {designer_program.get('editorial_score', 'n/a')}")
        md_lines.append(f"- Quality passed: {designer_program.get('quality_passed', False)}")
        md_lines.append(f"- Status: {designer_program.get('status') or 'not_run'}")
        md_lines.append(f"- Public URL: {designer_program.get('public_url') or 'n/a'}")
        if designer_program.get("skipped_reason"):
            md_lines.append(f"- Skipped reason: {designer_program.get('skipped_reason')}")

    md_lines.extend(["", "## Writes"])
    if result["writes"]:
        for item in result["writes"]:
            md_lines.append(f"- {json.dumps(item, ensure_ascii=False)}")
    else:
        md_lines.append("- No writes this run.")
    md_lines.extend(["", "## Gaps"])
    if result["gaps"]:
        for item in result["gaps"][:20]:
            md_lines.append(f"- {json.dumps(item, ensure_ascii=False)}")
    else:
        md_lines.append("- No content gaps detected in current backlog scope.")

    md_path = output_base / "report.md"
    json_path = output_base / "report.json"
    opportunity_registry_path = output_base / "opportunity-registry.json"
    action_plan_path = output_base / "page-action-plan.json"
    maintenance_plan_path = output_base / "maintenance-plan.json"
    consolidation_plan_path = output_base / "consolidation-plan.json"
    technical_release_gate_path = output_base / "technical-release-gates.json"
    md_path.write_text("\n".join(md_lines) + "\n", encoding="utf-8")
    json_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    opportunity_registry_path.write_text(json.dumps(result.get("opportunity_registry") or {}, ensure_ascii=False, indent=2), encoding="utf-8")
    action_plan_path.write_text(json.dumps(result.get("page_action_plan") or {}, ensure_ascii=False, indent=2), encoding="utf-8")
    maintenance_plan_path.write_text(json.dumps(result.get("maintenance_plan") or {}, ensure_ascii=False, indent=2), encoding="utf-8")
    consolidation_plan_path.write_text(json.dumps(result.get("consolidation_plan") or {}, ensure_ascii=False, indent=2), encoding="utf-8")
    technical_release_gate_path.write_text(json.dumps(result.get("technical_release_gates") or [], ensure_ascii=False, indent=2), encoding="utf-8")

    state.setdefault("runs", []).append(
        {
            "run_id": run_id,
            "generated_at": result["generated_at"],
            "blocked": result["blocked"],
            "writes_count": (result.get("summary") or {}).get("writes_count", 0),
            "gap_count": (result.get("summary") or {}).get("gap_count", 0),
            "primary_focus_topic": (result.get("summary") or {}).get("primary_focus_topic"),
            "research_lead_topic": (result.get("summary") or {}).get("research_lead_topic"),
            "feedback_row_count": (result.get("summary") or {}).get("feedback_row_count", 0),
            "report_markdown": str(md_path),
            "report_json": str(json_path),
            "opportunity_registry_json": str(opportunity_registry_path),
            "page_action_plan_json": str(action_plan_path),
            "maintenance_plan_json": str(maintenance_plan_path),
            "consolidation_plan_json": str(consolidation_plan_path),
            "technical_release_gate_json": str(technical_release_gate_path),
        }
    )
    state["runs"] = state["runs"][-30:]
    state["adaptive_profile"] = result.get("adaptive_profile") or {}
    state["last_market_research"] = result.get("market_research") or {}
    state["last_iteration_plan"] = result.get("iteration_plan") or {}
    state["last_opportunity_registry"] = {
        "item_count": (result.get("opportunity_registry") or {}).get("item_count", 0),
        "top_actions": (result.get("opportunity_registry") or {}).get("top_actions", [])[:5],
    }
    state["last_page_action_plan"] = {
        "selected_actions": (result.get("page_action_plan") or {}).get("selected_actions", [])[:10],
        "skipped_actions": (result.get("page_action_plan") or {}).get("skipped_actions", [])[:10],
    }
    state["last_consolidation_plan"] = {
        "merge_candidates": (result.get("consolidation_plan") or {}).get("merge_candidates", [])[:10],
        "redirect_candidates": (result.get("consolidation_plan") or {}).get("redirect_candidates", [])[:10],
        "prune_candidates": (result.get("consolidation_plan") or {}).get("prune_candidates", [])[:10],
    }
    state["maintenance_state"] = {
        **dict(state.get("maintenance_state") or {}),
        "last_weekly_run_at": result["generated_at"] if (result.get("maintenance_plan") or {}).get("weekly_due") else (dict(state.get("maintenance_state") or {}).get("last_weekly_run_at")),
        "last_monthly_run_at": result["generated_at"] if (result.get("maintenance_plan") or {}).get("monthly_due") else (dict(state.get("maintenance_state") or {}).get("last_monthly_run_at")),
    }
    state["last_technical_release_gate_summary"] = {
        "pass_count": (result.get("summary") or {}).get("technical_release_gate_pass_count", 0),
        "fail_count": (result.get("summary") or {}).get("technical_release_gate_fail_count", 0),
        "publish_blocked_count": (result.get("summary") or {}).get("publish_blocked_count", 0),
    }
    state["last_feedback_summary"] = {
        "row_count": hist.get("row_count", 0),
        "matched_slug_rows": hist.get("matched_slug_rows", 0),
        "unmatched_slug_rows": hist.get("unmatched_slug_rows", 0),
        "top_topics": hist.get("top_topics", [])[:5],
        "top_unmatched_pages": hist.get("top_unmatched_pages", [])[:5],
    }
    if result.get("designer_daily_program"):
        state["designer_daily_program"] = {
            **dict(state.get("designer_daily_program") or {}),
            **{
                key: value
                for key, value in (result.get("designer_daily_program") or {}).items()
                if key in {"enabled", "timezone", "last_selected_date", "last_selected_slug", "last_published_date"}
            },
        }
    state["last_updated_at"] = result["generated_at"]
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    STATE_PATH.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")

    summary_text = (
        "Neosgo SEO + GEO daily report\n"
        f"Blocked: {result['blocked']}\n"
        f"Focus: {(result.get('summary') or {}).get('primary_focus_topic', 'n/a')}\n"
        f"Writes: {(result.get('summary') or {}).get('writes_count', 0)}\n"
        f"Gaps: {(result.get('summary') or {}).get('gap_count', 0)}"
    )
    result["deliveries"] = _send_to_telegram(report_chat, summary_text, [md_path, json_path])
    return result


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--force", action="store_true")
    args = ap.parse_args()
    result = run_cycle()
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
