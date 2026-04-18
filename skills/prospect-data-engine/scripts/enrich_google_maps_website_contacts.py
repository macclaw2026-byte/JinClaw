#!/usr/bin/env python3

from __future__ import annotations

import argparse
import json
import re
import socket
import sys
from pathlib import Path
from typing import Any
from urllib.parse import urljoin, urlparse
from urllib.request import Request, urlopen

from google_maps_capture_core import (
    enrichment_quality_summary,
    extract_candidate_links,
    read_json,
    root_domain,
    write_json,
)


WORKSPACE_ROOT = Path("/Users/mac_claw/.openclaw/workspace")
if str(WORKSPACE_ROOT) not in sys.path:
    sys.path.insert(0, str(WORKSPACE_ROOT))

from tools.openmoss.ops.local_data_platform_bridge import sync_marketing_suite


EMAIL_RE = re.compile(r"([A-Z0-9._%+\-]+@[A-Z0-9.\-]+\.[A-Z]{2,})", re.I)
FORM_HINT_RE = re.compile(r"(contact|quote|project|inquiry|enquiry|consult|trade|partner)", re.I)
BLOCKED_EMAIL_PREFIXES = {"noreply", "no-reply", "donotreply", "do-not-reply", "example"}
BLOCKED_EMAIL_PATTERNS = ("sentry", "user@domain.com")
APPROVED_WEBSITE_TERMS = (
    "interior design",
    "interior designer",
    "residential interiors",
    "commercial interiors",
    "hospitality design",
    "space planning",
    "furnishings",
    "lighting design",
    "decorative lighting",
    "kitchen and bath",
    "kitchen & bath",
)
REVIEW_WEBSITE_TERMS = (
    "home decor",
    "staging",
    "design studio",
    "custom home",
    "renovation",
    "builder",
)
REJECT_WEBSITE_TERMS = (
    "landscape design",
    "landscaping",
    "painting services",
    "paint contractor",
    "floral design",
    "event florist",
    "digital magazine",
    "publisher",
    "property management",
    "organized home",
    "home organizing",
)
APPROVED_WEBSITE_TERMS_BY_ACCOUNT_TYPE = {
    "designer": APPROVED_WEBSITE_TERMS,
    "contractor": (
        "general contractor",
        "general contracting",
        "design build",
        "design-build",
        "construction company",
        "home builder",
        "custom home builder",
        "remodeling",
        "renovation",
        "residential construction",
        "commercial construction",
    ),
}
REVIEW_WEBSITE_TERMS_BY_ACCOUNT_TYPE = {
    "designer": REVIEW_WEBSITE_TERMS,
    "contractor": (
        "kitchen remodel",
        "bath remodel",
        "construction management",
        "custom homes",
        "builder",
        "contractor",
    ),
}
REJECT_WEBSITE_TERMS_BY_ACCOUNT_TYPE = {
    "designer": REJECT_WEBSITE_TERMS,
    "contractor": (
        "landscape contractor",
        "roofing contractor",
        "painting contractor",
        "paving contractor",
        "hvac contractor",
        "plumbing contractor",
        "electrical contractor",
    ),
}


def _read_json(path: Path) -> dict[str, Any]:
    return read_json(path, {})


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    write_json(path, payload)


def _priority_regions(config: dict[str, Any]) -> list[str]:
    project = dict(config.get("project", {}) or {})
    regions = []
    for item in list(project.get("priority_regions", []) or []):
        region = str(item).strip().upper()
        if region and region not in regions:
            regions.append(region)
    return regions


def _fetch_html(url: str) -> str:
    request = Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urlopen(request, timeout=8) as response:
        return response.read().decode("utf-8", "ignore")


def _website_root_domain(url: str) -> str:
    return root_domain(url)


def _record_key(item: dict[str, Any]) -> str:
    return str(item.get("source_url") or item.get("place_url") or item.get("website") or item.get("company_name") or "").strip()


def _lane_key(item: dict[str, Any]) -> str:
    return str(item.get("query_family") or item.get("account_type") or item.get("source_family") or "unknown").strip() or "unknown"


def _lane_label(item: dict[str, Any]) -> str:
    query_family = str(item.get("query_family") or "").strip()
    if query_family == "google_maps_interior_designer":
        return "interior designer"
    if query_family == "google_maps_general_contractor":
        return "general contractor"
    return query_family or str(item.get("account_type") or item.get("source_family") or "unknown")


def _fetch_required(previous: dict[str, Any], website: str) -> bool:
    if not website:
        return False
    validation_reason = str(previous.get("email_validation_reason", "") or "").strip()
    if validation_reason in {"domain_match", "domain_resolves"}:
        return False
    if bool(previous.get("contact_form_detected", False)):
        return False
    return True


def _select_enrichment_batch(
    ordered_items: list[dict[str, Any]],
    previous_output: dict[str, dict[str, Any]],
    runtime_state: dict[str, Any],
    *,
    max_sites_per_run: int,
) -> tuple[set[str], dict[str, int], dict[str, Any]]:
    """按 lane 轮转挑选本轮要抓的网站，避免 pending_batch 长期卡在同一批。"""
    if max_sites_per_run <= 0:
        return set(), dict(runtime_state.get("lane_cursors") or {}), {"selected_count": 0, "lane_stats": {}}

    ordered_by_lane: dict[str, list[dict[str, Any]]] = {}
    lane_order: list[str] = []
    for item in ordered_items:
        website = str(item.get("website", "")).strip()
        key = _record_key(item)
        previous = dict(previous_output.get(key, {}) or {})
        if not _fetch_required(previous, website):
            continue
        lane = _lane_key(item)
        if lane not in ordered_by_lane:
            ordered_by_lane[lane] = []
            lane_order.append(lane)
        ordered_by_lane[lane].append(item)

    lane_cursors = {str(key): int(value or 0) for key, value in dict(runtime_state.get("lane_cursors") or {}).items()}
    next_lane_cursors = dict(lane_cursors)
    selected_keys: set[str] = set()
    selected_websites: set[str] = set()
    lane_selected: dict[str, int] = {}
    active_lanes = [lane for lane in lane_order if ordered_by_lane.get(lane)]

    while active_lanes and len(selected_keys) < max_sites_per_run:
        made_progress = False
        for lane in list(active_lanes):
            items = ordered_by_lane.get(lane, [])
            if not items:
                active_lanes.remove(lane)
                continue
            cursor = next_lane_cursors.get(lane, 0) % len(items)
            chosen_index = None
            for offset in range(len(items)):
                index = (cursor + offset) % len(items)
                item = items[index]
                key = _record_key(item)
                website = str(item.get("website", "")).strip()
                if key in selected_keys or (website and website in selected_websites):
                    continue
                chosen_index = index
                break
            if chosen_index is None:
                active_lanes.remove(lane)
                continue
            item = items[chosen_index]
            key = _record_key(item)
            website = str(item.get("website", "")).strip()
            selected_keys.add(key)
            if website:
                selected_websites.add(website)
            next_lane_cursors[lane] = (chosen_index + 1) % len(items)
            lane_selected[lane] = lane_selected.get(lane, 0) + 1
            made_progress = True
            if len(selected_keys) >= max_sites_per_run:
                break
        if not made_progress:
            break

    return selected_keys, next_lane_cursors, {"selected_count": len(selected_keys), "lane_stats": lane_selected}


def _lane_quality_snapshot(items: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    lane_stats: dict[str, dict[str, Any]] = {}
    for item in items:
        lane_key = str(item.get("query_family") or item.get("lead_source_key") or item.get("source_family") or "unknown").strip() or "unknown"
        bucket = lane_stats.setdefault(
            lane_key,
            {
                "lane_key": lane_key,
                "record_count": 0,
                "approved_count": 0,
                "pending_batch_count": 0,
                "review_count": 0,
                "reject_count": 0,
                "validated_email_count": 0,
                "contact_form_detected_count": 0,
            },
        )
        bucket["record_count"] += 1
        fit_status = str(item.get("website_fit_status") or "").strip()
        if fit_status == "approved":
            bucket["approved_count"] += 1
        elif fit_status == "pending_batch":
            bucket["pending_batch_count"] += 1
        elif fit_status == "review":
            bucket["review_count"] += 1
        elif fit_status == "reject":
            bucket["reject_count"] += 1
        if str(item.get("email") or "").strip():
            bucket["validated_email_count"] += 1
        if bool(item.get("contact_form_detected")):
            bucket["contact_form_detected_count"] += 1
    return lane_stats


def _email_is_realish(email: str, website_domain: str) -> tuple[bool, str]:
    email = email.strip().lower()
    if not EMAIL_RE.fullmatch(email):
        return False, "syntax_invalid"
    local, _, domain = email.partition("@")
    if local in BLOCKED_EMAIL_PREFIXES:
        return False, "blocked_prefix"
    if any(pattern in email for pattern in BLOCKED_EMAIL_PATTERNS):
        return False, "blocked_pattern"
    try:
        socket.getaddrinfo(domain, None)
    except OSError:
        return False, "domain_unresolvable"
    if website_domain and (domain == website_domain or domain.endswith(f".{website_domain}")):
        return True, "domain_match"
    return True, "domain_resolves"


def _website_fit_assessment(page_html_map: dict[str, str], *, account_type: str = "", query_family: str = "") -> tuple[str, list[str]]:
    corpus = "\n".join(page_html_map.values()).lower()
    normalized_account_type = str(account_type or "").strip().lower()
    if not normalized_account_type and "contractor" in str(query_family or "").lower():
        normalized_account_type = "contractor"
    approved_terms = APPROVED_WEBSITE_TERMS_BY_ACCOUNT_TYPE.get(normalized_account_type, APPROVED_WEBSITE_TERMS)
    review_terms = REVIEW_WEBSITE_TERMS_BY_ACCOUNT_TYPE.get(normalized_account_type, REVIEW_WEBSITE_TERMS)
    reject_terms = REJECT_WEBSITE_TERMS_BY_ACCOUNT_TYPE.get(normalized_account_type, REJECT_WEBSITE_TERMS)
    approved_hits = [term for term in approved_terms if term in corpus]
    reject_hits = [term for term in reject_terms if term in corpus]
    review_hits = [term for term in review_terms if term in corpus]
    if approved_hits and not reject_hits:
        return "approved", approved_hits[:5]
    if reject_hits and not approved_hits:
        return "reject", reject_hits[:5]
    if approved_hits and reject_hits:
        return "review", [f"mixed:{approved_hits[0]}", f"mixed:{reject_hits[0]}"]
    if review_hits:
        return "review", review_hits[:5]
    return "unknown", []


def _detect_contact_form(page_html_map: dict[str, str]) -> tuple[bool, str, list[str]]:
    for page, html in page_html_map.items():
        lowered = html.lower()
        signals: list[str] = []
        if (
            "<form" not in lowered
            and "hubspot-form" not in lowered
            and "wpforms" not in lowered
            and "formspree" not in lowered
            and "sqs-block-form" not in lowered
            and "squarespace-form" not in lowered
            and "form-block" not in lowered
        ):
            continue
        if "newsletter" in lowered and "<textarea" not in lowered and not FORM_HINT_RE.search(page):
            continue
        if "<form" in lowered:
            signals.append("html_form_tag")
        if "sqs-block-form" in lowered:
            signals.append("squarespace_form_block")
        if "squarespace-form" in lowered:
            signals.append("squarespace_form_component")
        if "form-block" in lowered:
            signals.append("generic_form_block")
        if "type=\"email\"" in lowered or "type='email'" in lowered:
            signals.append("email_field")
        if "<textarea" in lowered:
            signals.append("textarea_field")
        if "name=\"message\"" in lowered or "name='message'" in lowered or "placeholder=\"message" in lowered or "placeholder='message" in lowered:
            signals.append("message_field")
        if "name=\"subject\"" in lowered or "name='subject'" in lowered:
            signals.append("subject_field")
        if "formsubmitbuttontext" in lowered or "\"submit\":\"submit\"" in lowered or ">send<" in lowered:
            signals.append("submit_control_hint")
        if "\"firstname\"" in lowered or "\"lastname\"" in lowered:
            signals.append("name_fields")
        if "inquiry" in lowered or "enquiry" in lowered or "project details" in lowered:
            signals.append("inquiry_language")
        if "hubspot" in lowered:
            signals.append("hubspot_form")
        if "formspree" in lowered:
            signals.append("formspree")
        if "wpforms" in lowered:
            signals.append("wpforms")
        if FORM_HINT_RE.search(page):
            signals.append("contact_like_url")
        if (
            "textarea_field" in signals
            or "message_field" in signals
            or "subject_field" in signals
            or "inquiry_language" in signals
            or (
                "contact_like_url" in signals
                and (
                    "email_field" in signals
                    or "squarespace_form_block" in signals
                    or "squarespace_form_component" in signals
                    or "generic_form_block" in signals
                )
            )
            or (
                "submit_control_hint" in signals
                and (
                    "squarespace_form_block" in signals
                    or "squarespace_form_component" in signals
                    or "generic_form_block" in signals
                )
                and ("textarea_field" in signals or "name_fields" in signals or "email_field" in signals)
            )
        ):
            return True, page, signals[:6]
    return False, "", []


def main() -> int:
    parser = argparse.ArgumentParser(description="Visit websites from Google Maps places and extract validated emails.")
    parser.add_argument("--project-root", required=True)
    parser.add_argument("--max-sites-per-run", type=int, default=0)
    parser.add_argument("--max-pages-per-site", type=int, default=0)
    parser.add_argument("--contact-link-limit", type=int, default=0)
    args = parser.parse_args()

    project_root = Path(args.project_root).expanduser().resolve()
    config = _read_json(project_root / "config" / "project-config.json")
    capture = ((config.get("prospect_data_engine", {}) or {}).get("google_maps_capture", {}) or {})
    source_path = project_root / "data" / "raw-imports" / "discovered-google-maps-places.json"
    report_path = project_root / "output" / "prospect-data-engine" / "google-maps-email-enrichment-report.json"
    output_path = project_root / "data" / "raw-imports" / "discovered-google-maps-validated-contacts.json"
    runtime_state_path = project_root / "runtime" / "prospect-data-engine" / "google-maps-email-enrichment-state.json"
    max_sites_per_run = int(args.max_sites_per_run or capture.get("email_enrichment_max_sites_per_run", 40) or 40)
    max_pages_per_site = int(args.max_pages_per_site or capture.get("max_pages_per_site", 4) or 4)
    contact_link_limit = int(args.contact_link_limit or capture.get("contact_link_limit", 4) or 4)
    contact_link_hints = [str(item).strip() for item in list(capture.get("contact_link_hints", []) or ["contact", "about", "team", "trade"]) if str(item).strip()]
    priority_regions = _priority_regions(config)

    if not source_path.exists():
        payload = {"status": "waiting_for_google_maps_places", "email_candidate_count": 0, "validated_email_count": 0}
        _write_json(report_path, payload)
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return 0

    items = list(_read_json(source_path).get("items", []) or [])
    previous_output = {_record_key(item): item for item in list(_read_json(output_path).get("items", []) or [])}
    runtime_state = _read_json(runtime_state_path) if runtime_state_path.exists() else {}
    enriched = []
    validated_email_count = 0
    email_candidate_count = 0
    checked_sites = 0
    deferred_count = 0
    website_cache: dict[str, dict[str, Any]] = {}
    page_fetch_failures = 0

    def sort_key(item: dict[str, Any]) -> tuple[int, int, int, str]:
        state = str(item.get("geo", "")).split("/", 1)[0].strip().upper()
        source_url = _record_key(item)
        previous = dict(previous_output.get(source_url, {}) or {})
        previous_reason = str(previous.get("email_validation_reason", "") or "")
        website = str(item.get("website", "")).strip()
        priority_bucket = 0 if state in priority_regions else 1
        unresolved_bucket = 0 if website and (previous_reason in {"", "pending_batch", "no_website"} or previous_reason.startswith("fetch_failed")) else 1
        cursor_bucket = 0
        return (priority_bucket, unresolved_bucket, cursor_bucket, str(item.get("company_name", "")))

    ordered_items = sorted(items, key=sort_key)
    selected_batch_keys, next_lane_cursors, selection_meta = _select_enrichment_batch(
        ordered_items,
        previous_output,
        runtime_state,
        max_sites_per_run=max_sites_per_run,
    )

    for item in ordered_items:
        website = str(item.get("website", "")).strip()
        website_domain = str(item.get("website_root_domain", "")).strip()
        source_url = _record_key(item)
        previous = dict(previous_output.get(source_url, {}) or {})
        email = ""
        validation_reason = "no_website"
        crawled_pages = []
        if previous:
            email = str(previous.get("email", "") or "")
            validation_reason = str(previous.get("email_validation_reason", "") or validation_reason)
            crawled_pages = list(previous.get("crawled_pages", []) or [])
            email_source_page = str(previous.get("email_source_page", "") or "")
            website_fit_status = str(previous.get("website_fit_status", "unknown"))
            website_fit_reasons = list(previous.get("website_fit_reasons", []) or [])
            contact_form_detected = bool(previous.get("contact_form_detected", False))
            contact_form_url = str(previous.get("contact_form_url", ""))
            contact_form_signals = list(previous.get("contact_form_signals", []) or [])
        else:
            email_source_page = ""
            website_fit_status = "unknown"
            website_fit_reasons = []
            contact_form_detected = False
            contact_form_url = ""
            contact_form_signals = []
        if website:
            if validation_reason in {"domain_match", "domain_resolves"} or contact_form_detected:
                pass
            elif website in website_cache:
                cached = website_cache[website]
                email = str(cached.get("email", ""))
                validation_reason = str(cached.get("validation_reason", "unknown"))
                crawled_pages = list(cached.get("crawled_pages", []) or [])
                website_fit_status = str(cached.get("website_fit_status", "unknown"))
                website_fit_reasons = list(cached.get("website_fit_reasons", []) or [])
                contact_form_detected = bool(cached.get("contact_form_detected", False))
                contact_form_url = str(cached.get("contact_form_url", ""))
                contact_form_signals = list(cached.get("contact_form_signals", []) or [])
            elif source_url not in selected_batch_keys:
                validation_reason = "pending_batch"
                deferred_count += 1
                website_fit_status = "pending_batch"
                website_fit_reasons = []
                contact_form_detected = False
                contact_form_url = ""
                contact_form_signals = []
            else:
                try:
                    homepage_html = _fetch_html(website)
                    checked_sites += 1
                    pages = [
                        website,
                        *extract_candidate_links(
                            website,
                            homepage_html,
                            limit=contact_link_limit,
                            extra_hints=contact_link_hints,
                        ),
                    ][: max(1, max_pages_per_site)]
                    page_html_map = {website: homepage_html}
                    for page in pages[1:]:
                        try:
                            page_html_map[page] = _fetch_html(page)
                        except Exception:  # noqa: BLE001
                            page_fetch_failures += 1
                            continue
                    emails = []
                    email_source_page = ""
                    for page, html in page_html_map.items():
                        crawled_pages.append(page)
                        page_emails = [match.lower() for match in EMAIL_RE.findall(html)]
                        page_emails.extend(
                            match.lower()
                            for match in re.findall(r"mailto:([A-Z0-9._%+\-]+@[A-Z0-9.\-]+\.[A-Z]{2,})", html, re.I)
                        )
                        if page_emails and not email_source_page:
                            email_source_page = page
                        emails.extend(page_emails)
                    deduped = []
                    seen = set()
                    for candidate in emails:
                        if candidate in seen:
                            continue
                        seen.add(candidate)
                        deduped.append(candidate)
                    email_candidate_count += len(deduped)
                    for candidate in deduped:
                        ok, reason = _email_is_realish(candidate, website_domain)
                        if ok:
                            email = candidate
                            validation_reason = reason
                            validated_email_count += 1
                            break
                    if not email and deduped:
                        validation_reason = "no_valid_email_after_validation"
                    website_fit_status, website_fit_reasons = _website_fit_assessment(
                        page_html_map,
                        account_type=str(item.get("account_type") or ""),
                        query_family=str(item.get("query_family") or ""),
                    )
                    contact_form_detected, contact_form_url, contact_form_signals = _detect_contact_form(page_html_map)
                except Exception as exc:  # noqa: BLE001
                    validation_reason = f"fetch_failed:{exc}"
                    website_fit_status = "unknown"
                    website_fit_reasons = []
                    contact_form_detected = False
                    contact_form_url = ""
                    contact_form_signals = []
                website_cache[website] = {
                    "email": email,
                    "validation_reason": validation_reason,
                    "crawled_pages": list(crawled_pages),
                    "email_source_page": email_source_page,
                    "website_fit_status": website_fit_status,
                    "website_fit_reasons": list(website_fit_reasons),
                    "contact_form_detected": contact_form_detected,
                    "contact_form_url": contact_form_url,
                    "contact_form_signals": list(contact_form_signals),
                }
        else:
            website_fit_status = "unknown"
            website_fit_reasons = []
            contact_form_detected = False
            contact_form_url = ""
            contact_form_signals = []

        enriched.append(
            {
                **previous,
                **item,
                "source_url": source_url,
                "lead_source_key": _lane_key(item),
                "lead_source_label": _lane_label(item),
                "email": email,
                "email_validation_status": "valid" if email else "invalid_or_missing",
                "email_validation_reason": validation_reason,
                "email_source_page": str(website_cache.get(website, {}).get("email_source_page", "")) if website else "",
                "reachability_status": (
                    "form_and_email_available"
                    if email and contact_form_detected
                    else "email_verified"
                    if email
                    else "form_available"
                    if contact_form_detected
                    else item.get("reachability_status", "unknown")
                ),
                "signals": list(item.get("signals", [])) + ([f"email_validation:{validation_reason}"] if validation_reason else []),
                "crawled_pages": crawled_pages,
                "website_fit_status": website_fit_status,
                "website_fit_reasons": website_fit_reasons,
                "contact_form_detected": contact_form_detected,
                "contact_form_url": contact_form_url,
                "contact_form_signals": contact_form_signals,
                "pages_crawled_count": len(crawled_pages),
            }
        )

    _write_json(output_path, {"items": enriched})
    _write_json(
        runtime_state_path,
        {
            **runtime_state,
            "checked_site_count": checked_sites,
            "deferred_count": deferred_count,
            "priority_regions": priority_regions,
            "max_sites_per_run": max_sites_per_run,
            "max_pages_per_site": max_pages_per_site,
            "contact_link_limit": contact_link_limit,
            "page_fetch_failures": page_fetch_failures,
            "lane_cursors": next_lane_cursors,
            "selected_batch_size": int(selection_meta.get("selected_count") or 0),
            "selected_batch_lane_stats": dict(selection_meta.get("lane_stats") or {}),
        },
    )
    summary = enrichment_quality_summary(enriched, checked_sites, deferred_count)
    summary["lane_quality"] = _lane_quality_snapshot(enriched)
    report = {
        "status": "ok",
        "checked_site_count": checked_sites,
        "deferred_count": deferred_count,
        "email_candidate_count": email_candidate_count,
        "validated_email_count": validated_email_count,
        "newly_validated_email_count": validated_email_count,
        "total_validated_email_count": summary.get("validated_email_count", 0),
        "contact_form_detected_count": len([item for item in enriched if item.get("contact_form_detected")]),
        "page_fetch_failures": page_fetch_failures,
        "raw_import_path": str(output_path),
        "quality_summary": summary,
    }
    report["data_platform_sync"] = sync_marketing_suite(project_root=project_root)
    _write_json(report_path, report)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
