#!/usr/bin/env python3

from __future__ import annotations

import argparse
import json
import re
from html import unescape
from pathlib import Path
from urllib.parse import unquote, urlparse
from urllib.request import Request, urlopen
from datetime import datetime, timezone


EMAIL_RE = re.compile(r"[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}", re.I)
TITLE_RE = re.compile(r"<title[^>]*>(.*?)</title>", re.I | re.S)
LINK_RE = re.compile(r'href="(?P<href>https?://[^"]+)"', re.I)


def _read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _fetch_html(url: str, timeout: int = 12) -> str:
    request = Request(
        url,
        headers={
            "User-Agent": "Mozilla/5.0 (compatible; MarketingAutomationSuite/1.0; +https://example.com/bot)"
        },
    )
    with urlopen(request, timeout=timeout) as response:
        charset = response.headers.get_content_charset() or "utf-8"
        return response.read().decode(charset, errors="replace")


def _extract_title(html: str) -> str:
    match = TITLE_RE.search(html)
    if not match:
        return ""
    title = unescape(match.group(1))
    return re.sub(r"\s+", " ", title).strip()


def _derive_company_name(title: str, domain: str) -> str:
    if title:
        return title.split("|")[0].split("-")[0].strip()
    return domain


def _infer_name_from_url(url: str) -> str:
    parsed = urlparse(url)
    path = unquote(parsed.path or "").strip("/")
    if not path:
        return parsed.netloc.lower().replace("www.", "")
    tail = path.split("/")[-1]
    tail = tail.replace("+", " ").replace("-", " ")
    return re.sub(r"\s+", " ", tail).strip().title()


def _reachability(emails: list[str], html: str) -> str:
    if emails:
        return "email_unverified"
    if "<form" in html.lower():
        return "form_available"
    return "unknown"


def _source_confidence(title: str, emails: list[str], html: str) -> float:
    score = 0.55
    if title:
        score += 0.12
    if emails:
        score += 0.15
    if "<form" in html.lower():
        score += 0.1
    return round(min(score, 0.92), 2)


def _extract_external_links(html: str, page_domain: str) -> list[str]:
    urls = []
    seen = set()
    for match in LINK_RE.finditer(html):
        href = match.group("href")
        parsed = urlparse(href)
        if not parsed.netloc:
            continue
        domain = parsed.netloc.lower().replace("www.", "")
        if domain == page_domain:
            continue
        if domain in {"facebook.com", "instagram.com", "x.com", "twitter.com", "youtube.com"}:
            continue
        normalized = f"{parsed.scheme}://{parsed.netloc}{parsed.path or ''}"
        if normalized in seen:
            continue
        seen.add(normalized)
        urls.append(normalized)
        if len(urls) >= 12:
            break
    return urls


def main() -> int:
    parser = argparse.ArgumentParser(description="Fetch public account pages and emit normalized raw-import leads.")
    parser.add_argument("--project-root", required=True)
    args = parser.parse_args()

    project_root = Path(args.project_root).expanduser().resolve()
    targets_path = project_root / "data" / "discovery-targets.json"
    generated_targets_path = project_root / "data" / "discovery-targets.generated.json"
    retry_targets_path = project_root / "runtime" / "prospect-data-engine" / "retry-targets.generated.json"
    output_dir = project_root / "output" / "prospect-data-engine"
    raw_import_path = project_root / "data" / "raw-imports" / "discovered-public-accounts.json"
    runtime_path = project_root / "runtime" / "prospect-data-engine" / "discovery-state.json"

    targets = _read_json(targets_path).get("items", []) if targets_path.exists() else []
    generated_targets = _read_json(generated_targets_path).get("items", []) if generated_targets_path.exists() else []
    retry_targets = _read_json(retry_targets_path).get("items", []) if retry_targets_path.exists() else []
    enabled_targets = []
    now = datetime.now(timezone.utc)
    for item in [*targets, *generated_targets, *retry_targets]:
        if not item.get("enabled"):
            continue
        retry_not_before = item.get("retry_not_before")
        if retry_not_before:
            try:
                retry_at = datetime.fromisoformat(retry_not_before.replace("Z", "+00:00"))
                if retry_at > now:
                    continue
            except ValueError:
                pass
        enabled_targets.append(item)

    discovered = []
    failures = []

    for item in enabled_targets:
        url = item.get("target_url", "").strip()
        if not url:
            continue
        try:
            html = _fetch_html(url)
            parsed = urlparse(url)
            domain = parsed.netloc.lower().replace("www.", "")
            title = _extract_title(html)
            emails = sorted(set(EMAIL_RE.findall(html)))
            company_name = _derive_company_name(title, domain)
            if item.get("source_family") == "linkedin_company_pages" and not title:
                company_name = _infer_name_from_url(url)
            elif item.get("source_family") == "google_business_profile" and not title:
                company_name = _infer_name_from_url(url)
            discovered.append(
                {
                    "source_url": url,
                    "company_name": company_name,
                    "website_root_domain": domain,
                    "account_type": item.get("account_type", ""),
                    "persona_type": item.get("persona_type", ""),
                    "geo": item.get("geo", ""),
                    "signals": list(item.get("signal_hints", [])) + (["contact_form_detected"] if "<form" in html.lower() else []),
                    "email": emails[0] if emails else "",
                    "full_name": "",
                    "reachability_status": _reachability(emails, html),
                    "source_confidence": _source_confidence(title, emails, html),
                    "query_id": item.get("query_id"),
                    "discovery_query": item.get("generated_from_query"),
                    "query_family": item.get("query_family"),
                    "source_family": item.get("source_family", "official_websites"),
                    "target_id": item.get("target_id"),
                    "generated_from_provider": item.get("generated_from_provider"),
                    "discovery_metadata": {
                        "page_title": title,
                        "email_count": len(emails),
                        "form_detected": "<form" in html.lower(),
                        "external_links": _extract_external_links(html, domain),
                    },
                }
            )
        except Exception as exc:  # noqa: BLE001
            failures.append({"target_url": url, "error": str(exc)})

    _write_json(raw_import_path, {"items": discovered})
    _write_json(
        output_dir / "discovery-report.json",
        {
            "target_count": len(targets),
            "enabled_target_count": len(enabled_targets),
            "discovered_count": len(discovered),
            "failure_count": len(failures),
            "failures": failures,
            "raw_import_path": str(raw_import_path),
        },
    )
    _write_json(
        runtime_path,
        {
            "status": "ok",
            "enabled_target_count": len(enabled_targets),
            "discovered_count": len(discovered),
            "failure_count": len(failures),
            "raw_import_path": str(raw_import_path),
        },
    )

    print(
        json.dumps(
            {
                "status": "ok",
                "enabled_target_count": len(enabled_targets),
                "discovered_count": len(discovered),
                "failure_count": len(failures),
                "raw_import_path": str(raw_import_path),
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
