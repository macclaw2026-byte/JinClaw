#!/usr/bin/env python3

from __future__ import annotations

import argparse
import concurrent.futures
import json
import math
import re
import subprocess
import sys
import textwrap
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, quote_plus, unquote, urlparse
from urllib.request import Request, urlopen

from google_maps_capture_core import read_json, root_domain, write_json


WORKSPACE_ROOT = Path("/Users/mac_claw/.openclaw/workspace")
if str(WORKSPACE_ROOT) not in sys.path:
    sys.path.insert(0, str(WORKSPACE_ROOT))

from tools.openmoss.ops.local_data_platform_bridge import sync_marketing_suite


PHONE_RE = re.compile(r"(?:\+1[-.\s]?)?\(?\d{3}\)?[-.\s]\d{3}[-.\s]\d{4}")
RESULT_RE = re.compile(r'href="(?P<href>https?://[^"]+)"', re.I)
RSS_LINK_RE = re.compile(r"<link>(https?://[^<]+)</link>", re.I)
BING_BLOCK_RE = re.compile(r'<li class="b_algo".*?</li>', re.I | re.S)
CITE_RE = re.compile(r"<cite>(.*?)</cite>", re.I | re.S)
TAG_RE = re.compile(r"<[^>]+>")
WHITESPACE_RE = re.compile(r"\s+")
TOKEN_RE = re.compile(r"[a-z0-9]+")
NON_BUSINESS_HOSTS = (
    "google.com",
    "googleusercontent.com",
    "gstatic.com",
    "accounts.google.com",
    "support.google.com",
    "maps.google.com",
)
SEARCH_BLOCKED_HOSTS = {
    "duckduckgo.com",
    "html.duckduckgo.com",
    "bing.com",
    "www.bing.com",
    "yelp.com",
    "www.yelp.com",
    "facebook.com",
    "www.facebook.com",
    "instagram.com",
    "www.instagram.com",
    "x.com",
    "twitter.com",
    "www.twitter.com",
    "linkedin.com",
    "www.linkedin.com",
    "mapquest.com",
    "www.mapquest.com",
    "angi.com",
    "www.angi.com",
    "houzz.com",
    "www.houzz.com",
    "nextdoor.com",
    "www.nextdoor.com",
    "bbb.org",
    "www.bbb.org",
    "yellowpages.com",
    "www.yellowpages.com",
    "genealogy.com",
    "www.genealogy.com",
    "youtube.com",
    "www.youtube.com",
    "wikipedia.org",
    "www.wikipedia.org",
    "zhihu.com",
    "www.zhihu.com",
}
GENERIC_COMPANY_TOKENS = {
    "and",
    "by",
    "co",
    "company",
    "contracting",
    "contractor",
    "contractors",
    "construction",
    "design",
    "designer",
    "designers",
    "home",
    "inc",
    "interior",
    "interiors",
    "llc",
    "ltd",
    "of",
    "studio",
    "the",
}
PLACE_DETAIL_BATCH_SIZE = 12
SEARCH_RESULT_LIMIT = 4
SEARCH_FETCH_BYTES = 200 * 1024


def _record_key(item: dict[str, Any]) -> str:
    return str(item.get("source_url") or item.get("place_url") or item.get("website") or item.get("company_name") or "").strip()


def _missing_fields(item: dict[str, Any]) -> list[str]:
    missing: list[str] = []
    if not str(item.get("website") or "").strip():
        missing.append("website")
    if not str(item.get("phone") or "").strip():
        missing.append("phone")
    if not str(item.get("email") or "").strip():
        missing.append("email")
    return missing


def _build_missing_backlog(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    backlog: list[dict[str, Any]] = []
    for item in items:
        missing = _missing_fields(item)
        if not missing:
            continue
        backlog.append(
            {
                "record_key": _record_key(item),
                "query_family": str(item.get("query_family") or ""),
                "account_type": str(item.get("account_type") or ""),
                "company_name": str(item.get("company_name") or ""),
                "geo": str(item.get("geo") or ""),
                "website": str(item.get("website") or ""),
                "phone": str(item.get("phone") or ""),
                "email": str(item.get("email") or ""),
                "place_url": str(item.get("place_url") or item.get("source_url") or ""),
                "website_fit_status": str(item.get("website_fit_status") or ""),
                "email_validation_reason": str(item.get("email_validation_reason") or ""),
                "missing_fields": missing,
            }
        )
    return backlog


def _is_business_link(url: str) -> bool:
    lowered = url.lower().strip()
    if not lowered.startswith(("http://", "https://")):
        return False
    host = root_domain(lowered)
    return bool(host) and not any(host == blocked or host.endswith(f".{blocked}") for blocked in NON_BUSINESS_HOSTS)


def _normalize_phone(raw: str) -> str:
    match = PHONE_RE.search(raw or "")
    if not match:
        return ""
    digits = re.sub(r"\D", "", match.group(0))
    if len(digits) == 11 and digits.startswith("1"):
        digits = digits[1:]
    if len(digits) == 10:
        return f"({digits[:3]}) {digits[3:6]}-{digits[6:]}"
    return match.group(0).strip()


def _digits_only(text: str) -> str:
    return re.sub(r"\D", "", str(text or ""))


def _normalize_text(text: str) -> str:
    return WHITESPACE_RE.sub(" ", str(text or "").lower()).strip()


def _tokenize(text: str) -> list[str]:
    return [token for token in TOKEN_RE.findall(_normalize_text(text)) if token]


def _state_name(state_code: str) -> str:
    mapping = {
        "CT": "Connecticut",
        "FL": "Florida",
        "MA": "Massachusetts",
        "ME": "Maine",
        "NH": "New Hampshire",
        "NY": "New York",
        "RI": "Rhode Island",
        "TX": "Texas",
        "VT": "Vermont",
    }
    return mapping.get(state_code.strip().upper(), state_code.strip().upper())


def _company_tokens(company_name: str) -> list[str]:
    tokens: list[str] = []
    for token in _tokenize(company_name):
        if len(token) <= 2 or token in GENERIC_COMPANY_TOKENS:
            continue
        if token not in tokens:
            tokens.append(token)
    return tokens


def _build_search_queries(item: dict[str, Any]) -> list[str]:
    company_name = str(item.get("company_name") or "").strip()
    geo = str(item.get("geo") or "")
    state_code = geo.split("/", 1)[0].strip().upper()
    state_name = _state_name(state_code)
    account_type = str(item.get("account_type") or "").strip()
    phone_digits = _digits_only(item.get("phone") or "")
    queries: list[str] = []
    for query in (
        f"\"{company_name}\" {state_code} official website".strip(),
        f"\"{company_name}\" {state_name} {account_type}".strip(),
        f"\"{company_name}\" {account_type}".strip(),
        f"\"{company_name}\" {state_code}".strip(),
    ):
        if query and query not in queries:
            queries.append(query)
    if phone_digits:
        for query in (
            f"\"{company_name}\" \"{phone_digits}\"".strip(),
            f"\"{company_name}\" \"{str(item.get('phone') or '').strip()}\"".strip(),
        ):
            if query and query not in queries:
                queries.insert(0, query)
    return queries


def _fetch_text(url: str, timeout: int = 8, max_bytes: int = SEARCH_FETCH_BYTES) -> str:
    request = Request(url, headers={"User-Agent": "Mozilla/5.0 (compatible; OpenClawDataPlatform/1.0)"})
    with urlopen(request, timeout=timeout) as response:
        charset = response.headers.get_content_charset() or "utf-8"
        chunks: list[bytes] = []
        remaining = max_bytes
        while remaining > 0:
            chunk = response.read(min(64 * 1024, remaining))
            if not chunk:
                break
            chunks.append(chunk)
            remaining -= len(chunk)
        return b"".join(chunks).decode(charset, errors="replace")


def _search_duckduckgo(query: str) -> str:
    return _fetch_text(f"https://html.duckduckgo.com/html/?q={quote_plus(query)}", timeout=5)


def _search_bing_rss(query: str) -> str:
    return _fetch_text(f"https://www.bing.com/search?format=rss&q={quote_plus(query)}", timeout=8, max_bytes=96 * 1024)


def _search_bing_html(query: str) -> str:
    return _fetch_text(f"https://www.bing.com/search?q={quote_plus(query)}", timeout=8, max_bytes=320 * 1024)


def _normalize_result_url(href: str) -> str | None:
    if "duckduckgo.com/l/?" in href:
        parsed = urlparse(href)
        actual = parse_qs(parsed.query).get("uddg", [""])[0]
        href = unquote(actual or "")
    if not href.startswith(("http://", "https://")):
        return None
    parsed = urlparse(href)
    if not parsed.netloc:
        return None
    host = parsed.netloc.lower()
    host_without_port = host.split(":", 1)[0]
    normalized_host = host_without_port.removeprefix("www.")
    if normalized_host in SEARCH_BLOCKED_HOSTS:
        return None
    lowered_path = (parsed.path or "/").lower()
    if lowered_path.endswith((".pdf", ".doc", ".docx", ".xls", ".xlsx", ".zip")):
        return None
    return f"{parsed.scheme}://{host_without_port}{parsed.path or '/'}"


def _extract_search_urls(payload: str, *, is_rss: bool, max_results: int) -> list[str]:
    matcher = RSS_LINK_RE.finditer(payload) if is_rss else RESULT_RE.finditer(payload)
    urls: list[str] = []
    seen: set[str] = set()
    for match in matcher:
        href = match.group(1 if is_rss else "href")
        normalized = _normalize_result_url(href)
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        urls.append(normalized)
        if len(urls) >= max_results:
            break
    return urls


def _extract_bing_html_urls(payload: str, *, max_results: int) -> list[str]:
    urls: list[str] = []
    seen: set[str] = set()
    for block in BING_BLOCK_RE.findall(payload):
        cite_match = CITE_RE.search(block)
        if not cite_match:
            continue
        cite_text = _normalize_text(TAG_RE.sub(" ", cite_match.group(1))).replace(" › ", "/")
        cite_text = cite_text.replace("…", "").strip().rstrip("›").strip()
        if not cite_text:
            continue
        candidate = cite_text
        if not candidate.startswith(("http://", "https://")):
            candidate = f"https://{candidate}"
        normalized = _normalize_result_url(candidate)
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        urls.append(normalized)
        if len(urls) >= max_results:
            break
    return urls


def _fetch_candidate_page(url: str) -> dict[str, Any]:
    html = _fetch_text(url, timeout=8)
    title_match = re.search(r"<title[^>]*>(.*?)</title>", html, flags=re.I | re.S)
    title = _normalize_text(TAG_RE.sub(" ", title_match.group(1) if title_match else ""))
    body = _normalize_text(TAG_RE.sub(" ", html))[:8000]
    return {"title": title, "body": body}


def _score_search_candidate(item: dict[str, Any], url: str, page: dict[str, Any]) -> tuple[float, list[str]]:
    evidence: list[str] = []
    score = 0.0
    host = root_domain(url)
    company_name = str(item.get("company_name") or "").strip()
    company_text = _normalize_text(company_name)
    phone_digits = _digits_only(item.get("phone") or "")
    account_type = _normalize_text(item.get("account_type") or "")
    company_tokens = _company_tokens(company_name)
    title = _normalize_text(page.get("title") or "")
    body = _normalize_text(page.get("body") or "")
    combined = f"{title} {body}".strip()

    if company_text and company_text in combined:
        score += 4.0
        evidence.append("full_name_match")

    token_hits = [token for token in company_tokens if token in combined or token in host]
    if token_hits:
        hit_count = len(set(token_hits))
        score += min(3.0, hit_count * 1.2)
        evidence.append(f"token_hits:{','.join(sorted(set(token_hits))[:4])}")

    host_tokens = set(_tokenize(host.replace(".", " ")))
    overlap = [token for token in company_tokens if token in host_tokens]
    if overlap:
        score += min(2.0, len(overlap) * 1.0)
        evidence.append(f"host_overlap:{','.join(sorted(set(overlap))[:3])}")

    if phone_digits and phone_digits in _digits_only(combined):
        score += 4.5
        evidence.append("phone_match")

    if account_type and account_type in combined:
        score += 0.8
        evidence.append("account_type_match")

    if title and any(token in title for token in company_tokens[:2]):
        score += 0.7
        evidence.append("title_token_match")

    if "contact" in combined or "about" in combined:
        score += 0.2
        evidence.append("contactish_page")

    return round(score, 3), evidence


def _is_search_match_confident(score: float, evidence: list[str]) -> bool:
    strong = {"full_name_match", "phone_match"}
    evidence_prefixes = {entry.split(":", 1)[0] for entry in evidence}
    if score >= 5.5 and evidence_prefixes & strong:
        return True
    if score >= 6.0 and "host_overlap" in evidence_prefixes and "token_hits" in evidence_prefixes:
        return True
    return False


def _search_candidate_urls(item: dict[str, Any]) -> list[dict[str, str]]:
    providers = [
        ("bing_html", _search_bing_html, "bing_html"),
        ("bing_rss", _search_bing_rss, True),
        ("duckduckgo", _search_duckduckgo, False),
    ]
    queries = _build_search_queries(item)
    candidates: list[dict[str, str]] = []
    seen: set[str] = set()
    for query in queries:
        with concurrent.futures.ThreadPoolExecutor(max_workers=len(providers)) as executor:
            future_map = {
                executor.submit(search_fn, query): (provider_name, is_rss)
                for provider_name, search_fn, is_rss in providers
            }
            for future in concurrent.futures.as_completed(future_map):
                provider_name, is_rss = future_map[future]
                try:
                    payload = future.result()
                except Exception:
                    continue
                if provider_name == "duckduckgo" and "anomaly-modal" in payload:
                    continue
                if is_rss == "bing_html":
                    extracted = _extract_bing_html_urls(payload, max_results=SEARCH_RESULT_LIMIT)
                else:
                    extracted = _extract_search_urls(payload, is_rss=bool(is_rss), max_results=SEARCH_RESULT_LIMIT)
                for url in extracted:
                    if url in seen:
                        continue
                    seen.add(url)
                    candidates.append({"provider": provider_name, "query": query, "url": url})
        if len(candidates) >= SEARCH_RESULT_LIMIT:
            break
    return candidates[:SEARCH_RESULT_LIMIT]


def _resolve_search_website(item: dict[str, Any]) -> dict[str, Any]:
    candidates = _search_candidate_urls(item)
    best: dict[str, Any] = {}
    best_score = -math.inf
    for candidate in candidates:
        try:
            page = _fetch_candidate_page(candidate["url"])
        except Exception as exc:
            candidate["error"] = str(exc)
            continue
        score, evidence = _score_search_candidate(item, candidate["url"], page)
        candidate["score"] = score
        candidate["evidence"] = evidence
        if score > best_score:
            best_score = score
            best = dict(candidate)
    if not best:
        return {"ok": False, "candidates": candidates, "reason": "no_candidate_page_fetch_succeeded"}
    if not _is_search_match_confident(float(best.get("score") or 0.0), list(best.get("evidence") or [])):
        return {"ok": False, "candidates": candidates, "best": best, "reason": "no_confident_match"}
    return {
        "ok": True,
        "website": str(best.get("url") or ""),
        "provider": str(best.get("provider") or ""),
        "query": str(best.get("query") or ""),
        "score": float(best.get("score") or 0.0),
        "evidence": list(best.get("evidence") or []),
        "candidates": candidates,
    }


def _extract_place_detail(raw: dict[str, Any]) -> dict[str, Any]:
    links = list(raw.get("links") or [])
    buttons = list(raw.get("buttons") or [])
    body = str(raw.get("body") or "")

    website = ""
    for link in links:
        href = str(link.get("href") or "").strip()
        if not _is_business_link(href):
            continue
        text_blob = " ".join(
            [
                str(link.get("text") or ""),
                str(link.get("aria") or ""),
                str(link.get("dataItemId") or ""),
            ]
        ).lower()
        if "website" in text_blob or "authority" in text_blob:
            website = href
            break
    if not website:
        business_links = [str(link.get("href") or "").strip() for link in links if _is_business_link(str(link.get("href") or "").strip())]
        if len(business_links) == 1:
            website = business_links[0]

    phone = ""
    for link in links:
        href = str(link.get("href") or "").strip()
        if href.startswith("tel:"):
            phone = _normalize_phone(href.removeprefix("tel:"))
            if phone:
                break
    if not phone:
        for entry in [*buttons, *links]:
            phone = _normalize_phone(
                " ".join(
                    [
                        str(entry.get("text") or ""),
                        str(entry.get("aria") or ""),
                        str(entry.get("dataItemId") or ""),
                    ]
                )
            )
            if phone:
                break
    if not phone:
        phone = _normalize_phone(body)

    has_add_website_prompt = "add website" in body.lower()
    return {
        "website": website,
        "phone": phone,
        "maps_missing_website_prompt": has_add_website_prompt,
    }


def _fetch_place_detail_batch(place_urls: list[str]) -> dict[str, dict[str, Any]]:
    venv_python = WORKSPACE_ROOT / "tools" / "matrix-venv" / "bin" / "python"
    if not venv_python.exists():
        raise RuntimeError(f"playwright runtime missing at {venv_python}")
    script = textwrap.dedent(
        """
        from playwright.sync_api import sync_playwright
        import json
        import sys

        urls = json.loads(sys.argv[1])

        def normalize(text: str) -> str:
            return " ".join(str(text or "").split())

        results = []
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page(viewport={"width": 1440, "height": 1400})
            for url in urls:
                try:
                    page.goto(url, wait_until="domcontentloaded", timeout=25000)
                    try:
                        page.wait_for_load_state("networkidle", timeout=6000)
                    except Exception:
                        pass
                    page.wait_for_timeout(1200)
                    payload = page.evaluate(
                        '''() => {
                          const normalize = (text) => (text || '').replace(/\\s+/g, ' ').trim();
                          const links = [...document.querySelectorAll('a[href]')].map((el) => ({
                            href: el.href || '',
                            text: normalize(el.innerText || ''),
                            aria: normalize(el.getAttribute('aria-label') || ''),
                            dataItemId: el.getAttribute('data-item-id') || ''
                          }));
                          const buttons = [...document.querySelectorAll('button,[role="button"]')].map((el) => ({
                            text: normalize(el.innerText || ''),
                            aria: normalize(el.getAttribute('aria-label') || ''),
                            dataItemId: el.getAttribute('data-item-id') || ''
                          }));
                          return {
                            body: normalize((document.body && document.body.innerText) || '').slice(0, 6000),
                            links,
                            buttons
                          };
                        }'''
                    )
                    results.append({"place_url": url, "ok": True, "payload": payload})
                except Exception as exc:
                    results.append({"place_url": url, "ok": False, "error": str(exc)})
            browser.close()
        print(json.dumps({"items": results}, ensure_ascii=False))
        """
    )
    completed = subprocess.run(
        [str(venv_python), "-c", script, json.dumps(place_urls, ensure_ascii=False)],
        capture_output=True,
        text=True,
        timeout=max(90, len(place_urls) * 12),
        check=False,
    )
    if completed.returncode != 0:
        raise RuntimeError((completed.stderr or completed.stdout or "playwright place-detail fetch failed").strip())
    payload = json.loads(completed.stdout or "{}")
    results: dict[str, dict[str, Any]] = {}
    for item in list(payload.get("items") or []):
        place_url = str(item.get("place_url") or "").strip()
        if not place_url:
            continue
        if not item.get("ok"):
            results[place_url] = {"error": str(item.get("error") or "unknown_error")}
            continue
        results[place_url] = _extract_place_detail(dict(item.get("payload") or {}))
    return results


def _fetch_place_details(place_urls: list[str]) -> dict[str, dict[str, Any]]:
    if not place_urls:
        return {}
    results: dict[str, dict[str, Any]] = {}
    urls = list(place_urls)
    for start in range(0, len(urls), PLACE_DETAIL_BATCH_SIZE):
        chunk = urls[start : start + PLACE_DETAIL_BATCH_SIZE]
        try:
            results.update(_fetch_place_detail_batch(chunk))
        except Exception as exc:
            if len(chunk) == 1:
                results[chunk[0]] = {"error": str(exc)}
                continue
            for place_url in chunk:
                try:
                    results.update(_fetch_place_detail_batch([place_url]))
                except Exception as single_exc:
                    results[place_url] = {"error": str(single_exc)}
    return results


def _merge_place_detail(item: dict[str, Any], detail: dict[str, Any]) -> tuple[dict[str, Any], list[str]]:
    updated = dict(item)
    changed: list[str] = []
    website = str(updated.get("website") or "").strip()
    phone = str(updated.get("phone") or "").strip()

    detail_website = str(detail.get("website") or "").strip()
    detail_phone = str(detail.get("phone") or "").strip()

    if not website and detail_website:
        updated["website"] = detail_website
        updated["website_root_domain"] = root_domain(detail_website)
        changed.append("website")
    elif website and not str(updated.get("website_root_domain") or "").strip():
        updated["website_root_domain"] = root_domain(website)

    if not phone and detail_phone:
        updated["phone"] = detail_phone
        changed.append("phone")

    if detail.get("maps_missing_website_prompt"):
        signals = list(updated.get("signals") or [])
        signal = "google_maps_prompt_add_website"
        if signal not in signals:
            signals.append(signal)
            updated["signals"] = signals
    if changed:
        signals = list(updated.get("signals") or [])
        marker = "google_maps_targeted_place_backfill"
        if marker not in signals:
            signals.append(marker)
            updated["signals"] = signals
    return updated, changed


def _merge_search_website(item: dict[str, Any], detail: dict[str, Any]) -> tuple[dict[str, Any], list[str]]:
    updated = dict(item)
    changed: list[str] = []
    website = str(updated.get("website") or "").strip()
    detail_website = str(detail.get("website") or "").strip()
    if not website and detail_website:
        updated["website"] = detail_website
        updated["website_root_domain"] = root_domain(detail_website)
        updated["website_source"] = "external_search_fallback"
        updated["website_source_provider"] = str(detail.get("provider") or "")
        updated["website_search_confidence"] = float(detail.get("score") or 0.0)
        updated["website_search_evidence"] = list(detail.get("evidence") or [])
        updated["website_search_query"] = str(detail.get("query") or "")
        changed.append("website")
    if changed:
        signals = list(updated.get("signals") or [])
        marker = "external_search_website_backfill"
        if marker not in signals:
            signals.append(marker)
        provider = str(detail.get("provider") or "").strip()
        if provider:
            provider_signal = f"external_search_provider_{provider}"
            if provider_signal not in signals:
                signals.append(provider_signal)
        updated["signals"] = signals
    return updated, changed


def main() -> int:
    parser = argparse.ArgumentParser(description="Backfill missing website/phone fields for Google Maps records and export a missing backlog.")
    parser.add_argument("--project-root", required=True)
    parser.add_argument("--max-place-targets", type=int, default=60)
    parser.add_argument("--max-search-targets", type=int, default=24)
    args = parser.parse_args()

    project_root = Path(args.project_root).expanduser().resolve()
    raw_root = project_root / "data" / "raw-imports"
    output_root = project_root / "output" / "prospect-data-engine"
    source_path = raw_root / "discovered-google-maps-places.json"
    validated_path = raw_root / "discovered-google-maps-validated-contacts.json"
    report_path = output_root / "google-maps-missing-field-backfill-report.json"
    backlog_path = output_root / "google-maps-missing-field-backlog.json"

    places_payload = read_json(source_path, {})
    validated_payload = read_json(validated_path, {})
    places = list(places_payload.get("items") or [])
    validated = list(validated_payload.get("items") or [])

    before_backlog = _build_missing_backlog(validated)
    place_targets = [
        item
        for item in validated
        if str(item.get("place_url") or item.get("source_url") or "").strip()
        and ("website" in _missing_fields(item) or "phone" in _missing_fields(item))
    ]
    place_targets.sort(
        key=lambda item: (
            0 if not str(item.get("website") or "").strip() else 1,
            0 if not str(item.get("phone") or "").strip() else 1,
            str(item.get("query_family") or ""),
            str(item.get("company_name") or ""),
        )
    )
    selected_targets = place_targets[: max(0, int(args.max_place_targets or 0))]
    detail_map = _fetch_place_details(
        [str(item.get("place_url") or item.get("source_url") or "").strip() for item in selected_targets]
    ) if selected_targets else {}

    detail_by_place_url: dict[str, dict[str, Any]] = {}
    detail_updates = {
        "website_fills": 0,
        "phone_fills": 0,
        "target_count": len(selected_targets),
        "success_count": 0,
        "error_count": 0,
    }
    for item in selected_targets:
        place_url = str(item.get("place_url") or item.get("source_url") or "").strip()
        detail = dict(detail_map.get(place_url) or {})
        if detail.get("error"):
            detail_updates["error_count"] += 1
            continue
        _, changed = _merge_place_detail(item, detail)
        detail_by_place_url[place_url] = detail
        if changed:
            detail_updates["success_count"] += 1
        if "website" in changed:
            detail_updates["website_fills"] += 1
        if "phone" in changed:
            detail_updates["phone_fills"] += 1

    def apply_updates(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
        merged_items: list[dict[str, Any]] = []
        for item in items:
            place_url = str(item.get("place_url") or item.get("source_url") or "").strip()
            detail = detail_by_place_url.get(place_url)
            if not detail:
                merged_items.append(item)
                continue
            merged, _ = _merge_place_detail(item, detail)
            merged_items.append(merged)
        return merged_items

    if detail_by_place_url:
        places = apply_updates(places)
        validated = apply_updates(validated)
        write_json(source_path, {"items": places})
        write_json(validated_path, {"items": validated})

    search_targets = [
        item
        for item in validated
        if not str(item.get("website") or "").strip()
        and str(item.get("company_name") or "").strip()
        and "google_maps_prompt_add_website" in list(item.get("signals") or [])
    ]
    search_targets.sort(
        key=lambda item: (
            0 if str(item.get("phone") or "").strip() else 1,
            str(item.get("query_family") or ""),
            str(item.get("company_name") or ""),
        )
    )
    selected_search_targets = search_targets[: max(0, int(args.max_search_targets or 0))]
    search_detail_by_key: dict[str, dict[str, Any]] = {}
    search_updates = {
        "website_fills": 0,
        "target_count": len(selected_search_targets),
        "success_count": 0,
        "error_count": 0,
        "no_confident_match_count": 0,
    }
    for item in selected_search_targets:
        try:
            detail = _resolve_search_website(item)
        except Exception as exc:
            search_updates["error_count"] += 1
            search_detail_by_key[_record_key(item)] = {"ok": False, "reason": str(exc)}
            continue
        search_detail_by_key[_record_key(item)] = detail
        if not detail.get("ok"):
            search_updates["no_confident_match_count"] += 1
            continue
        _, changed = _merge_search_website(item, detail)
        if changed:
            search_updates["success_count"] += 1
            if "website" in changed:
                search_updates["website_fills"] += 1

    def apply_search_updates(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
        merged_items: list[dict[str, Any]] = []
        for item in items:
            detail = search_detail_by_key.get(_record_key(item))
            if not detail or not detail.get("ok"):
                merged_items.append(item)
                continue
            merged, _ = _merge_search_website(item, detail)
            merged_items.append(merged)
        return merged_items

    if any(detail.get("ok") for detail in search_detail_by_key.values()):
        places = apply_search_updates(places)
        validated = apply_search_updates(validated)
        write_json(source_path, {"items": places})
        write_json(validated_path, {"items": validated})

    after_backlog = _build_missing_backlog(validated)
    write_json(backlog_path, {"items": after_backlog})

    summary_before = {
        "missing_website": sum(1 for item in before_backlog if "website" in list(item.get("missing_fields") or [])),
        "missing_phone": sum(1 for item in before_backlog if "phone" in list(item.get("missing_fields") or [])),
        "missing_email": sum(1 for item in before_backlog if "email" in list(item.get("missing_fields") or [])),
    }
    summary_after = {
        "missing_website": sum(1 for item in after_backlog if "website" in list(item.get("missing_fields") or [])),
        "missing_phone": sum(1 for item in after_backlog if "phone" in list(item.get("missing_fields") or [])),
        "missing_email": sum(1 for item in after_backlog if "email" in list(item.get("missing_fields") or [])),
    }

    report = {
        "status": "ok",
        "selected_target_count": len(selected_targets),
        "selected_search_target_count": len(selected_search_targets),
        "before": summary_before,
        "after": summary_after,
        "detail_updates": detail_updates,
        "search_updates": search_updates,
        "backlog_path": str(backlog_path),
        "source_path": str(source_path),
        "validated_path": str(validated_path),
    }
    report["data_platform_sync"] = sync_marketing_suite(project_root=project_root)
    write_json(report_path, report)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
