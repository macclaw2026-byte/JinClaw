#!/usr/bin/env python3

from __future__ import annotations

import argparse
import json
import re
import sys
from html import unescape
from pathlib import Path
from urllib.parse import quote_plus, unquote, urlparse
from urllib.request import Request, urlopen


LINK_RE = re.compile(r'href="(?P<href>https?://[^"]+)"', re.I)
TITLE_RE = re.compile(r"<title[^>]*>(.*?)</title>", re.I | re.S)
DIRECTORY_FAMILIES = {"trade_directories", "association_lists", "exhibitor_lists"}


WORKSPACE_ROOT = Path("/Users/mac_claw/.openclaw/workspace")
if str(WORKSPACE_ROOT) not in sys.path:
    sys.path.insert(0, str(WORKSPACE_ROOT))

from tools.openmoss.ops.local_data_platform_bridge import sync_marketing_suite


def _read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _fetch_html(url: str, timeout: int = 12) -> str:
    request = Request(
        url,
        headers={"User-Agent": "Mozilla/5.0 (compatible; MarketingAutomationSuite/1.0; +https://example.com/bot)"},
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


def _infer_name_from_url(url: str) -> str:
    parsed = urlparse(url)
    tail = unquote((parsed.path or "/").strip("/").split("/")[-1])
    if not tail:
        return parsed.netloc.lower().replace("www.", "")
    tail = tail.replace("-", " ").replace("+", " ")
    return re.sub(r"\s+", " ", tail).strip().title()


def _infer_company_name_from_query(query: str) -> str:
    cleaned = query.replace('"', " ")
    cleaned = re.sub(r"\bdirectory\b", " ", cleaned, flags=re.I)
    cleaned = re.sub(r"\b(RI|MA|CT|NH|ME|VT|NY|CA|TX|FL)\b", " ", cleaned)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    return cleaned.title()


def _extract_external_candidates(directory_url: str, html: str) -> list[dict]:
    directory_domain = urlparse(directory_url).netloc.lower().replace("www.", "")
    items = []
    seen = set()
    for match in LINK_RE.finditer(html):
        href = match.group("href")
        parsed = urlparse(href)
        if not parsed.netloc:
            continue
        domain = parsed.netloc.lower().replace("www.", "")
        if domain == directory_domain:
            continue
        if domain in {"linkedin.com", "www.linkedin.com", "google.com", "www.google.com", "bing.com", "duckduckgo.com"}:
            continue
        normalized = f"{parsed.scheme}://{parsed.netloc}{parsed.path or ''}"
        if normalized in seen:
            continue
        seen.add(normalized)
        items.append(
            {
                "source_url": normalized,
                "company_name": _infer_name_from_url(normalized),
                "website_root_domain": domain,
            }
        )
        if len(items) >= 15:
            break
    return items


def main() -> int:
    parser = argparse.ArgumentParser(description="Discover candidate accounts from industry directory pages.")
    parser.add_argument("--project-root", required=True)
    args = parser.parse_args()

    project_root = Path(args.project_root).expanduser().resolve()
    manual_targets = _read_json(project_root / "data" / "discovery-targets.json").get("items", []) if (project_root / "data" / "discovery-targets.json").exists() else []
    generated_targets = _read_json(project_root / "data" / "discovery-targets.generated.json").get("items", []) if (project_root / "data" / "discovery-targets.generated.json").exists() else []
    generated_queries = _read_json(project_root / "data" / "discovery-queries.generated.json").get("items", []) if (project_root / "data" / "discovery-queries.generated.json").exists() else []
    targets = [item for item in [*manual_targets, *generated_targets] if item.get("enabled") and item.get("source_family") in DIRECTORY_FAMILIES]

    if not targets:
        for item in generated_queries:
            if not item.get("enabled"):
                continue
            if item.get("source_family") not in DIRECTORY_FAMILIES:
                continue
            query = item.get("query", "").strip()
            if not query:
                continue
            targets.append(
                {
                    "target_url": f"https://www.google.com/search?q={quote_plus(query)}",
                    "target_id": f"directory-synth-{item.get('query_id', '')}",
                    "account_type": item.get("account_type", ""),
                    "persona_type": item.get("persona_type", ""),
                    "geo": item.get("geo", ""),
                    "query_id": item.get("query_id"),
                    "generated_from_query": query,
                    "query_family": item.get("query_family"),
                    "source_family": item.get("source_family"),
                    "signal_hints": list(item.get("signal_hints", [])) + ["directory_search_candidate"],
                    "enabled": True,
                    "synthetic_search_candidate": True,
                }
            )

    discovered = []
    failures = []
    for target in targets:
        url = target.get("target_url", "").strip()
        if not url:
            continue
        try:
            synthetic = bool(target.get("synthetic_search_candidate"))
            if synthetic:
                discovered.append(
                    {
                        "source_url": url,
                        "company_name": _infer_company_name_from_query(target.get("generated_from_query", "")),
                        "website_root_domain": "",
                        "account_type": target.get("account_type", ""),
                        "persona_type": target.get("persona_type", ""),
                        "geo": target.get("geo", ""),
                        "signals": list(target.get("signal_hints", [])) + ["industry_directory_search_candidate"],
                        "email": "",
                        "full_name": "",
                        "reachability_status": "unknown",
                        "source_confidence": 0.66,
                        "query_id": target.get("query_id"),
                        "discovery_query": target.get("generated_from_query"),
                        "query_family": target.get("query_family"),
                        "source_family": target.get("source_family"),
                        "target_id": target.get("target_id"),
                        "discovery_metadata": {
                            "directory_url": url,
                            "directory_title": "synthetic directory search candidate",
                        },
                    }
                )
                continue
            html = _fetch_html(url)
            page_title = _extract_title(html)
            for candidate in _extract_external_candidates(url, html):
                discovered.append(
                    {
                        **candidate,
                        "account_type": target.get("account_type", ""),
                        "persona_type": target.get("persona_type", ""),
                        "geo": target.get("geo", ""),
                        "signals": list(target.get("signal_hints", [])) + ["industry_directory_discovery"],
                        "email": "",
                        "full_name": "",
                        "reachability_status": "unknown",
                        "source_confidence": 0.68,
                        "query_id": target.get("query_id"),
                        "discovery_query": target.get("generated_from_query"),
                        "query_family": target.get("query_family"),
                        "source_family": target.get("source_family"),
                        "target_id": target.get("target_id"),
                        "discovery_metadata": {
                            "directory_url": url,
                            "directory_title": page_title,
                        },
                    }
                )
        except Exception as exc:  # noqa: BLE001
            failures.append({"target_url": url, "error": str(exc)})

    output_path = project_root / "data" / "raw-imports" / "discovered-industry-directory-accounts.json"
    _write_json(output_path, {"items": discovered})
    report = {
        "enabled_target_count": len(targets),
        "discovered_count": len(discovered),
        "failure_count": len(failures),
        "failures": failures,
        "raw_import_path": str(output_path),
    }
    report_path = project_root / "output" / "prospect-data-engine" / "directory-discovery-report.json"
    _write_json(report_path, report)
    sync_result = sync_marketing_suite(project_root=project_root)
    report["data_platform_sync"] = sync_result
    _write_json(report_path, report)
    result = {
        "status": "ok",
        "enabled_target_count": len(targets),
        "discovered_count": len(discovered),
        "failure_count": len(failures),
        "raw_import_path": str(output_path),
        "data_platform_sync": sync_result,
    }
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
