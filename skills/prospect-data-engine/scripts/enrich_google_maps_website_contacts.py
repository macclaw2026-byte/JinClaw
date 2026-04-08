#!/usr/bin/env python3

from __future__ import annotations

import argparse
import json
import re
import socket
from pathlib import Path
from typing import Any
from urllib.parse import urljoin, urlparse
from urllib.request import Request, urlopen


EMAIL_RE = re.compile(r"([A-Z0-9._%+\-]+@[A-Z0-9.\-]+\.[A-Z]{2,})", re.I)
CONTACT_HINT_RE = re.compile(r"(contact|about|team|studio|trade|connect)", re.I)
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


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


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


def _extract_candidate_links(base_url: str, html: str) -> list[str]:
    links = []
    for href in re.findall(r'href=["\']([^"\']+)["\']', html, re.I):
        absolute = urljoin(base_url, href.strip())
        parsed = urlparse(absolute)
        if not parsed.scheme.startswith("http"):
            continue
        if urlparse(base_url).netloc != parsed.netloc:
            continue
        if CONTACT_HINT_RE.search(absolute):
            links.append(absolute)
    deduped = []
    seen = set()
    for link in links:
        if link in seen:
            continue
        seen.add(link)
        deduped.append(link)
    return deduped[:2]


def _website_root_domain(url: str) -> str:
    return urlparse(url if "://" in url else f"https://{url}").netloc.lower().removeprefix("www.")


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


def _website_fit_assessment(page_html_map: dict[str, str]) -> tuple[str, list[str]]:
    corpus = "\n".join(page_html_map.values()).lower()
    approved_hits = [term for term in APPROVED_WEBSITE_TERMS if term in corpus]
    reject_hits = [term for term in REJECT_WEBSITE_TERMS if term in corpus]
    review_hits = [term for term in REVIEW_WEBSITE_TERMS if term in corpus]
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
        if "<form" not in lowered and "hubspot-form" not in lowered and "wpforms" not in lowered and "formspree" not in lowered:
            continue
        if "newsletter" in lowered and "<textarea" not in lowered and not FORM_HINT_RE.search(page):
            continue
        if "<form" in lowered:
            signals.append("html_form_tag")
        if "type=\"email\"" in lowered or "type='email'" in lowered:
            signals.append("email_field")
        if "<textarea" in lowered:
            signals.append("textarea_field")
        if "name=\"message\"" in lowered or "name='message'" in lowered or "placeholder=\"message" in lowered or "placeholder='message" in lowered:
            signals.append("message_field")
        if "name=\"subject\"" in lowered or "name='subject'" in lowered:
            signals.append("subject_field")
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
        if "textarea_field" in signals or "message_field" in signals or "subject_field" in signals or "inquiry_language" in signals or ("contact_like_url" in signals and "email_field" in signals):
            return True, page, signals[:6]
    return False, "", []


def main() -> int:
    parser = argparse.ArgumentParser(description="Visit websites from Google Maps places and extract validated emails.")
    parser.add_argument("--project-root", required=True)
    parser.add_argument("--max-sites-per-run", type=int, default=0)
    args = parser.parse_args()

    project_root = Path(args.project_root).expanduser().resolve()
    config = _read_json(project_root / "config" / "project-config.json")
    capture = ((config.get("prospect_data_engine", {}) or {}).get("google_maps_capture", {}) or {})
    source_path = project_root / "data" / "raw-imports" / "discovered-google-maps-places.json"
    report_path = project_root / "output" / "prospect-data-engine" / "google-maps-email-enrichment-report.json"
    output_path = project_root / "data" / "raw-imports" / "discovered-google-maps-validated-contacts.json"
    runtime_state_path = project_root / "runtime" / "prospect-data-engine" / "google-maps-email-enrichment-state.json"
    max_sites_per_run = int(args.max_sites_per_run or capture.get("email_enrichment_max_sites_per_run", 40) or 40)
    priority_regions = _priority_regions(config)

    if not source_path.exists():
        payload = {"status": "waiting_for_google_maps_places", "email_candidate_count": 0, "validated_email_count": 0}
        _write_json(report_path, payload)
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return 0

    items = list(_read_json(source_path).get("items", []) or [])
    previous_output = {str(item.get("source_url", "")).strip(): item for item in list(_read_json(output_path).get("items", []) or [])}
    runtime_state = _read_json(runtime_state_path) if runtime_state_path.exists() else {}
    enriched = []
    validated_email_count = 0
    email_candidate_count = 0
    checked_sites = 0
    deferred_count = 0
    website_cache: dict[str, dict[str, Any]] = {}

    def sort_key(item: dict[str, Any]) -> tuple[int, int, int, str]:
        state = str(item.get("geo", "")).split("/", 1)[0].strip().upper()
        source_url = str(item.get("source_url", "")).strip()
        previous = dict(previous_output.get(source_url, {}) or {})
        previous_reason = str(previous.get("email_validation_reason", "") or "")
        website = str(item.get("website", "")).strip()
        priority_bucket = 0 if state in priority_regions else 1
        unresolved_bucket = 0 if website and previous_reason in {"", "pending_batch", "no_website", "fetch_failed"} else 1
        cursor_bucket = 0
        return (priority_bucket, unresolved_bucket, cursor_bucket, str(item.get("company_name", "")))

    ordered_items = sorted(items, key=sort_key)

    for item in ordered_items:
        website = str(item.get("website", "")).strip()
        website_domain = str(item.get("website_root_domain", "")).strip()
        source_url = str(item.get("source_url", "")).strip()
        previous = dict(previous_output.get(source_url, {}) or {})
        email = ""
        validation_reason = "no_website"
        crawled_pages = []
        if previous:
            email = str(previous.get("email", "") or "")
            validation_reason = str(previous.get("email_validation_reason", "") or validation_reason)
            crawled_pages = list(previous.get("crawled_pages", []) or [])
            website_fit_status = str(previous.get("website_fit_status", "unknown"))
            website_fit_reasons = list(previous.get("website_fit_reasons", []) or [])
            contact_form_detected = bool(previous.get("contact_form_detected", False))
            contact_form_url = str(previous.get("contact_form_url", ""))
            contact_form_signals = list(previous.get("contact_form_signals", []) or [])
        else:
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
            elif checked_sites >= max_sites_per_run:
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
                    pages = [website, *_extract_candidate_links(website, homepage_html)]
                    page_html_map = {website: homepage_html}
                    for page in pages[1:]:
                        try:
                            page_html_map[page] = _fetch_html(page)
                        except Exception:  # noqa: BLE001
                            continue
                    emails = []
                    for page, html in page_html_map.items():
                        crawled_pages.append(page)
                        emails.extend(match.lower() for match in EMAIL_RE.findall(html))
                        emails.extend(
                            match.lower()
                            for match in re.findall(r"mailto:([A-Z0-9._%+\-]+@[A-Z0-9.\-]+\.[A-Z]{2,})", html, re.I)
                        )
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
                    website_fit_status, website_fit_reasons = _website_fit_assessment(page_html_map)
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
                "email": email,
                "email_validation_status": "valid" if email else "invalid_or_missing",
                "email_validation_reason": validation_reason,
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
        },
    )
    report = {
        "status": "ok",
        "checked_site_count": checked_sites,
        "deferred_count": deferred_count,
        "email_candidate_count": email_candidate_count,
        "validated_email_count": validated_email_count,
        "contact_form_detected_count": len([item for item in enriched if item.get("contact_form_detected")]),
        "raw_import_path": str(output_path),
    }
    _write_json(report_path, report)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
