#!/usr/bin/env python3

from __future__ import annotations

import argparse
import concurrent.futures
import json
import re
from pathlib import Path
from urllib.parse import parse_qs, quote_plus, unquote, urlparse
from urllib.request import Request, urlopen


RESULT_RE = re.compile(r'href="(?P<href>https?://[^"]+)"', re.I)
BLOCKED_HOSTS = {"duckduckgo.com", "html.duckduckgo.com", "bing.com", "www.bing.com"}
ALLOWED_SEARCH_HOST_PATHS = {
    "google.com": ("/maps", "/localservices", "/search"),
    "www.google.com": ("/maps", "/localservices", "/search"),
    "linkedin.com": ("/company/",),
    "www.linkedin.com": ("/company/",),
}
BLOCKED_FILE_SUFFIXES = (".pdf", ".doc", ".docx", ".xls", ".xlsx", ".ppt", ".pptx", ".zip")
BLOCKED_RESULT_HOSTS = {
    "yelp.com",
    "www.yelp.com",
    "facebook.com",
    "www.facebook.com",
    "instagram.com",
    "www.instagram.com",
    "x.com",
    "twitter.com",
    "www.twitter.com",
    "dictionary.cambridge.org",
    "www.dictionary.cambridge.org",
    "merriam-webster.com",
    "www.merriam-webster.com",
    "dictionary.com",
    "www.dictionary.com",
    "realtor.com",
    "www.realtor.com",
    "zillow.com",
    "www.zillow.com",
    "movoto.com",
    "www.movoto.com",
    "coldwellbanker.com",
    "www.coldwellbanker.com",
    "edinburgh.in.us",
    "www.edinburgh.in.us",
    "talkofthevillages.com",
    "www.talkofthevillages.com",
}


def _read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _fetch(url: str, timeout: int = 12) -> str:
    request = Request(
        url,
        headers={"User-Agent": "Mozilla/5.0 (compatible; MarketingAutomationSuite/1.0; +https://example.com/bot)"},
    )
    with urlopen(request, timeout=timeout) as response:
        charset = response.headers.get_content_charset() or "utf-8"
        return response.read().decode(charset, errors="replace")


def _search_duckduckgo(query: str) -> str:
    url = f"https://html.duckduckgo.com/html/?q={quote_plus(query)}"
    return _fetch(url, timeout=4)


def _search_bing_rss(query: str) -> str:
    url = f"https://www.bing.com/search?format=rss&q={quote_plus(query)}"
    return _fetch(url, timeout=8)


def _normalize_result_url(href: str) -> str | None:
    if "duckduckgo.com/l/?" in href:
        parsed = urlparse(href)
        actual = parse_qs(parsed.query).get("uddg", [""])[0]
        href = unquote(actual or "")
    if not href.startswith("http"):
        return None
    parsed = urlparse(href)
    if not parsed.netloc:
        return None
    host = parsed.netloc.lower().replace("www.", "")
    path = parsed.path or "/"
    if host in BLOCKED_HOSTS:
        return None
    if host in BLOCKED_RESULT_HOSTS:
        return None
    if host in ALLOWED_SEARCH_HOST_PATHS:
        allowed_prefixes = ALLOWED_SEARCH_HOST_PATHS[host]
        if not any(path.startswith(prefix) for prefix in allowed_prefixes):
            return None
    if path.lower().endswith(BLOCKED_FILE_SUFFIXES):
        return None
    return f"{parsed.scheme}://{parsed.netloc}{parsed.path or ''}"


def _passes_family_filter(url: str, query_family: str, source_family: str) -> bool:
    parsed = urlparse(url)
    host = parsed.netloc.lower()
    path = parsed.path or "/"
    if query_family == "linkedin_company_page" or source_family == "linkedin_company_pages":
        return host in {"linkedin.com", "www.linkedin.com"} and path.startswith("/company/")
    if query_family == "google_business_profile" or source_family == "google_business_profile":
        return host in {"google.com", "www.google.com"} and path.startswith("/maps")
    if query_family == "industry_directory" or source_family in {"trade_directories", "association_lists", "exhibitor_lists"}:
        lowered = f"{host}{path}".lower()
        return any(token in lowered for token in ["directory", "dealer", "partner", "association", "members", "member", "exhibitor", "showroom"])
    lowered = f"{host}{path}".lower()
    if any(token in lowered for token in ["/search", "/category/", "/tag/", "/wp-content/", "/dictionary/", "/realestate", "/homes-search/", "/forums/"]):
        return False
    return True


def _extract_urls(html: str, max_results: int) -> list[str]:
    urls = []
    seen = set()
    for match in RESULT_RE.finditer(html):
        normalized = _normalize_result_url(match.group("href"))
        if not normalized:
            continue
        if normalized in seen:
            continue
        seen.add(normalized)
        urls.append(normalized)
        if len(urls) >= max_results:
            break
    return urls


def _extract_rss_urls(xml_text: str, max_results: int) -> list[str]:
    links = re.findall(r"<link>(https?://[^<]+)</link>", xml_text, flags=re.I)
    urls = []
    seen = set()
    for href in links:
        normalized = _normalize_result_url(href)
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        urls.append(normalized)
        if len(urls) >= max_results:
            break
    return urls


def _read_json_safe(path: Path) -> dict:
    if not path.exists():
        return {}
    return _read_json(path)


def _load_query_weights(project_root: Path) -> dict[str, float]:
    runtime_path = project_root / "runtime" / "prospect-data-engine" / "query-weights.json"
    payload = _read_json_safe(runtime_path)
    return payload.get("query_bias", {})


def _provider_health(project_root: Path) -> dict[str, float]:
    health_path = project_root / "runtime" / "prospect-data-engine" / "provider-health.json"
    payload = _read_json_safe(health_path)
    return payload.get("provider_scores", {"duckduckgo": 1.0, "bing_rss": 0.9})


def _target_priority(item: dict, query_bias: dict[str, float]) -> tuple[float, float, int]:
    query_id = item.get("query_id") or item.get("query", "")
    bias = float(query_bias.get(query_id, query_bias.get(item.get("query", ""), 0.0)))
    rank = int(item.get("priority_rank", 9999) or 9999)
    region_rank = int(item.get("region_rank", 9999) or 9999)
    return (-bias, region_rank, rank)


def main() -> int:
    parser = argparse.ArgumentParser(description="Expand discovery queries into public discovery targets.")
    parser.add_argument("--project-root", required=True)
    args = parser.parse_args()

    project_root = Path(args.project_root).expanduser().resolve()
    queries_path = project_root / "data" / "discovery-queries.json"
    generated_queries_path = project_root / "data" / "discovery-queries.generated.json"
    generated_targets_path = project_root / "data" / "discovery-targets.generated.json"
    output_dir = project_root / "output" / "prospect-data-engine"
    runtime_path = project_root / "runtime" / "prospect-data-engine" / "search-discovery-state.json"
    query_weights = _load_query_weights(project_root)
    provider_scores = _provider_health(project_root)

    queries = _read_json(queries_path).get("items", []) if queries_path.exists() else []
    generated_queries = _read_json(generated_queries_path).get("items", []) if generated_queries_path.exists() else []
    queries = [*queries, *generated_queries]
    enabled_queries = sorted([item for item in queries if item.get("enabled")], key=lambda item: _target_priority(item, query_weights))

    generated_targets = []
    failures = []
    for idx, item in enumerate(enabled_queries, start=1):
        query = item.get("query", "").strip()
        max_results = int(item.get("max_results", 5) or 5)
        if not query:
            continue
        try:
            providers = []
            if provider_scores.get("duckduckgo", 0.0) > 0.15:
                providers.append(("duckduckgo", _search_duckduckgo, _extract_urls))
            if provider_scores.get("bing_rss", 0.0) > 0.15:
                providers.append(("bing_rss", _search_bing_rss, _extract_rss_urls))
            if not providers:
                providers = [("duckduckgo", _search_duckduckgo, _extract_urls), ("bing_rss", _search_bing_rss, _extract_rss_urls)]

            provider_results: dict[str, list[str]] = {}
            provider_errors: dict[str, str] = {}

            def _run_provider(provider_tuple: tuple[str, object, object]) -> tuple[str, list[str], str | None]:
                provider_name, search_fn, extract_fn = provider_tuple
                try:
                    html = search_fn(query)
                    urls = extract_fn(html, max_results=max_results)
                    return provider_name, urls, None
                except Exception as exc:  # noqa: BLE001
                    return provider_name, [], str(exc)

            with concurrent.futures.ThreadPoolExecutor(max_workers=len(providers)) as executor:
                future_map = [executor.submit(_run_provider, provider) for provider in providers]
                for future in concurrent.futures.as_completed(future_map):
                    provider_name, urls, error = future.result()
                    if error:
                        provider_errors[provider_name] = error
                    else:
                        provider_results[provider_name] = urls

            merged_urls = []
            seen_urls = set()
            for provider_name, urls in sorted(provider_results.items(), key=lambda pair: -provider_scores.get(pair[0], 0.0)):
                for url in urls:
                    if not _passes_family_filter(url, item.get("query_family", "official_search"), item.get("source_family", "official_websites")):
                        continue
                    if url in seen_urls:
                        continue
                    seen_urls.add(url)
                    merged_urls.append((provider_name, url))
                    if len(merged_urls) >= max_results:
                        break
                if len(merged_urls) >= max_results:
                    break

            if item.get("query_family") == "google_business_profile":
                maps_url = f"https://www.google.com/maps/search/{quote_plus(query)}"
                if maps_url not in seen_urls:
                    merged_urls.insert(0, ("maps_direct", maps_url))
                    seen_urls.add(maps_url)

            urls = [url for _, url in merged_urls]
            provider_hits = {}
            for provider_name, url in merged_urls:
                provider_hits[provider_name] = provider_hits.get(provider_name, 0) + 1

            for result_idx, url in enumerate(urls, start=1):
                generated_targets.append(
                    {
                        "target_url": url,
                        "target_id": f"generated-target-{idx}-{result_idx}",
                        "account_type": item.get("account_type", ""),
                        "persona_type": item.get("persona_type", ""),
                        "geo": item.get("geo", ""),
                        "query_id": item.get("query_id"),
                        "query_family": item.get("query_family", "official_search"),
                        "source_family": item.get("source_family", "official_websites"),
                        "signal_hints": list(item.get("signal_hints", [])) + ["query_discovery"],
                        "enabled": True,
                        "generated_from_query": query,
                        "generated_from_providers": sorted(provider_hits.keys()),
                        "generated_from_provider": merged_urls[result_idx - 1][0] if result_idx - 1 < len(merged_urls) else "",
                        "generated_rank": result_idx,
                        "query_bias": float(query_weights.get(item.get("query_id", ""), query_weights.get(query, 0.0))),
                        "provider_hits": provider_hits,
                    }
                )
            for provider_name, error in provider_errors.items():
                failures.append({"query": query, "provider": provider_name, "error": error})
        except Exception as exc:  # noqa: BLE001
            failures.append({"query": query, "error": str(exc)})

    _write_json(generated_targets_path, {"items": generated_targets})
    _write_json(
        output_dir / "search-discovery-report.json",
        {
            "query_count": len(queries),
            "enabled_query_count": len(enabled_queries),
            "generated_target_count": len(generated_targets),
            "failure_count": len(failures),
            "failures": failures,
            "provider_scores": provider_scores,
            "generated_targets_path": str(generated_targets_path),
        },
    )
    _write_json(
        runtime_path,
        {
            "status": "ok",
            "enabled_query_count": len(enabled_queries),
            "generated_target_count": len(generated_targets),
            "failure_count": len(failures),
            "provider_scores": provider_scores,
            "generated_targets_path": str(generated_targets_path),
        },
    )
    print(
        json.dumps(
            {
                "status": "ok",
                "enabled_query_count": len(enabled_queries),
                "generated_target_count": len(generated_targets),
                "failure_count": len(failures),
                "generated_targets_path": str(generated_targets_path),
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
