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
BLOCKED_EMAIL_PREFIXES = {"noreply", "no-reply", "donotreply", "do-not-reply", "example"}


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _fetch_html(url: str) -> str:
    request = Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urlopen(request, timeout=20) as response:
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
    return deduped[:4]


def _website_root_domain(url: str) -> str:
    return urlparse(url if "://" in url else f"https://{url}").netloc.lower().removeprefix("www.")


def _email_is_realish(email: str, website_domain: str) -> tuple[bool, str]:
    email = email.strip().lower()
    if not EMAIL_RE.fullmatch(email):
        return False, "syntax_invalid"
    local, _, domain = email.partition("@")
    if local in BLOCKED_EMAIL_PREFIXES:
        return False, "blocked_prefix"
    try:
        socket.getaddrinfo(domain, None)
    except OSError:
        return False, "domain_unresolvable"
    if website_domain and (domain == website_domain or domain.endswith(f".{website_domain}")):
        return True, "domain_match"
    return True, "domain_resolves"


def main() -> int:
    parser = argparse.ArgumentParser(description="Visit websites from Google Maps places and extract validated emails.")
    parser.add_argument("--project-root", required=True)
    args = parser.parse_args()

    project_root = Path(args.project_root).expanduser().resolve()
    source_path = project_root / "data" / "raw-imports" / "discovered-google-maps-places.json"
    report_path = project_root / "output" / "prospect-data-engine" / "google-maps-email-enrichment-report.json"
    output_path = project_root / "data" / "raw-imports" / "discovered-google-maps-validated-contacts.json"

    if not source_path.exists():
        payload = {"status": "waiting_for_google_maps_places", "email_candidate_count": 0, "validated_email_count": 0}
        _write_json(report_path, payload)
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return 0

    items = list(_read_json(source_path).get("items", []) or [])
    enriched = []
    validated_email_count = 0
    email_candidate_count = 0
    checked_sites = 0

    for item in items:
        website = str(item.get("website", "")).strip()
        website_domain = str(item.get("website_root_domain", "")).strip()
        email = ""
        validation_reason = "no_website"
        crawled_pages = []
        if website:
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
            except Exception as exc:  # noqa: BLE001
                validation_reason = f"fetch_failed:{exc}"

        enriched.append(
            {
                **item,
                "email": email,
                "email_validation_status": "valid" if email else "invalid_or_missing",
                "email_validation_reason": validation_reason,
                "reachability_status": "email_verified" if email else item.get("reachability_status", "unknown"),
                "signals": list(item.get("signals", [])) + ([f"email_validation:{validation_reason}"] if validation_reason else []),
                "crawled_pages": crawled_pages,
            }
        )

    _write_json(output_path, {"items": enriched})
    report = {
        "status": "ok",
        "checked_site_count": checked_sites,
        "email_candidate_count": email_candidate_count,
        "validated_email_count": validated_email_count,
        "raw_import_path": str(output_path),
    }
    _write_json(report_path, report)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
