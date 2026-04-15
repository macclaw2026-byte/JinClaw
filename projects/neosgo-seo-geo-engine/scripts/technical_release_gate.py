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


PLACEHOLDER_TERMS = (
    "lorem ipsum",
    "todo",
    "placeholder",
    "tbd",
    "coming soon",
)


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        if value in (None, ""):
            return default
        return int(float(value))
    except Exception:
        return default


def _contains_placeholder(text: str) -> bool:
    lowered = str(text or "").lower()
    return any(term in lowered for term in PLACEHOLDER_TERMS)


def _gate_config(config: dict[str, Any]) -> dict[str, Any]:
    return dict(config.get("technical_release_gate") or {})


def evaluate_release_gate(payload: dict[str, Any], config: dict[str, Any], *, kind: str) -> dict[str, Any]:
    gate = _gate_config(config)
    min_sections = _safe_int(gate.get("min_sections"), 4 if kind == "note" else 3)
    min_internal_links = _safe_int(gate.get("min_internal_links"), 2)
    max_seo_title_length = _safe_int(gate.get("max_seo_title_length"), 80)
    max_seo_description_length = _safe_int(gate.get("max_seo_description_length"), 180)

    sections = [item for item in list(payload.get("sections") or []) if isinstance(item, dict)]
    internal_links = [item for item in list(payload.get("internalLinks") or []) if isinstance(item, dict)]
    quick_answer = str(payload.get("quickAnswer") or "").strip()
    seo_title = str(payload.get("seoTitle") or "").strip()
    seo_description = str(payload.get("seoDescription") or "").strip()
    title = str(payload.get("title") or "").strip()

    checks = {
        "title_present": bool(title),
        "seo_title_present": bool(seo_title),
        "seo_description_present": bool(seo_description),
        "quick_answer_present": bool(quick_answer),
        "section_count_ok": len(sections) >= min_sections,
        "internal_links_ok": len(internal_links) >= min_internal_links,
        "seo_title_length_ok": len(seo_title) <= max_seo_title_length if seo_title else False,
        "seo_description_length_ok": len(seo_description) <= max_seo_description_length if seo_description else False,
        "no_placeholder_text": not any(
            _contains_placeholder(
                " ".join(
                    [
                        title,
                        seo_title,
                        seo_description,
                        quick_answer,
                        *[str(item.get("heading") or "") for item in sections],
                        *[str(item.get("body") or "") for item in sections],
                    ]
                )
            )
            for _ in [0]
        ),
    }

    if kind == "geo_variant":
        city = str(payload.get("city") or "").strip()
        state = str(payload.get("state") or "").strip()
        geo_label = str(payload.get("geoLabel") or "").strip()
        section_blob = " ".join(f"{item.get('heading','')} {item.get('body','')}" for item in sections)
        location_tokens = [token for token in (city, state, geo_label) if token]
        checks["geo_identity_present"] = bool(location_tokens)
        checks["geo_localization_present"] = any(token.lower() in section_blob.lower() for token in location_tokens)

    blocking_items = [name for name, ok in checks.items() if not ok]
    score = round(sum(1 for ok in checks.values() if ok) / max(1, len(checks)) * 100, 2)
    return {
        "kind": kind,
        "passed": not blocking_items,
        "score": score,
        "checks": checks,
        "blocking_items": blocking_items,
        "required_min_sections": min_sections,
        "required_min_internal_links": min_internal_links,
    }
