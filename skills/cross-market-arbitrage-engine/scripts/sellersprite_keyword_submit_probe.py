#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path("/Users/mac_claw/.openclaw/workspace")
VENV_PY = ROOT / "tools/matrix-venv/bin/python"

if sys.executable != str(VENV_PY) and VENV_PY.exists():
    try:
        import playwright  # type: ignore  # noqa: F401
    except Exception:
        raise SystemExit(subprocess.run([str(VENV_PY), __file__, *sys.argv[1:]]).returncode)

from playwright.sync_api import sync_playwright
from playwright_stealth import Stealth

DEFAULT_CDP = "http://127.0.0.1:18800"
OUT_DIR = ROOT / "output/cross-market-arbitrage-engine/sellersprite"
OUT_DIR.mkdir(parents=True, exist_ok=True)
KEYWORD_RESEARCH_URL = "https://www.sellersprite.com/v2/keyword-research"


def _safe_json(value):
    try:
        json.dumps(value, ensure_ascii=False)
        return value
    except Exception:
        return str(value)


def _clean_lines(text: str) -> list[str]:
    rows: list[str] = []
    for raw in str(text or "").splitlines():
        line = raw.replace("\u200b", "").strip()
        if line:
            rows.append(line)
    return rows


def _parse_keyword_results(text: str) -> dict[str, object]:
    lines = _clean_lines(text)
    result_count = 0
    for line in lines:
        if "搜索结果数" in line:
            digits = "".join(ch for ch in line if ch.isdigit())
            if digits:
                result_count = int(digits)
            break
    top_keywords: list[dict[str, object]] = []
    for idx in range(len(lines) - 2):
        rank_line = lines[idx]
        keyword_line = lines[idx + 1]
        cn_line = lines[idx + 2]
        if not rank_line.isdigit():
            continue
        if not any(ch.isalpha() for ch in keyword_line):
            continue
        row = {
            "rank": int(rank_line),
            "keyword": keyword_line,
            "keyword_cn": cn_line if any("\u4e00" <= ch <= "\u9fff" for ch in cn_line) else "",
        }
        numeric_window = lines[idx + 3 : idx + 14]
        monthly_searches = ""
        for candidate in numeric_window:
            normalized = candidate.replace(",", "").strip()
            if normalized.replace(".", "", 1).isdigit():
                monthly_searches = candidate
                break
        if not monthly_searches:
            continue
        row["monthly_searches"] = monthly_searches
        top_keywords.append(row)
        if len(top_keywords) >= 8:
            break
    return {
        "result_count": result_count,
        "top_keywords": top_keywords,
    }


def run_probe(
    *,
    cdp_url: str,
    keyword: str,
    month: str,
    station: str,
    min_searches: int,
    min_growth_rate: float,
    department_value: str,
    wait_seconds: float,
) -> dict[str, object]:
    responses: list[dict[str, object]] = []
    requests: list[dict[str, object]] = []
    with sync_playwright() as p:
        browser = p.chromium.connect_over_cdp(cdp_url)
        context = browser.contexts[0] if browser.contexts else browser.new_context()
        page = context.new_page()
        Stealth().apply_stealth_sync(page)

        def on_response(resp):
            url = resp.url
            if "sellersprite.com" not in url:
                return
            if "/v2/keyword-research" not in url and "/v2/keyword-stat/" not in url and "/v2/live-search" not in url:
                return
            try:
                body = resp.text()
            except Exception:
                body = ""
            responses.append(
                {
                    "url": url,
                    "status": resp.status,
                    "method": resp.request.method,
                    "body_preview": body[:1200],
                }
            )

        def on_request(req):
            url = req.url
            if "sellersprite.com" not in url:
                return
            if "/v2/keyword-research" not in url and "/v2/keyword-stat/" not in url and "/v2/live-search" not in url:
                return
            requests.append(
                {
                    "url": url,
                    "method": req.method,
                    "post_data": req.post_data or "",
                }
            )

        page.on("response", on_response)
        page.on("request", on_request)
        page.goto(KEYWORD_RESEARCH_URL, wait_until="domcontentloaded", timeout=60000)
        page.wait_for_timeout(2000)
        page.evaluate(
            """(params) => {
              const form = document.querySelector('#form-condition-search');
              if (!form) return false;
              const ensure = (name, value) => {
                let el = form.querySelector(`[name="${name}"]`);
                if (!el) {
                  el = document.createElement('input');
                  el.type = 'hidden';
                  el.name = name;
                  form.appendChild(el);
                }
                el.value = value;
              };
              ensure('station', params.station);
              ensure('month', params.month);
              ensure('presetMode', 'potential');
              ensure('minSearches', String(params.minSearches));
              ensure('minGrowthRateTrendMin', String(params.minGrowthRate));
              ensure('includeKeywords', params.keyword);
              const dept = `departments[14]`;
              let deptEl = form.querySelector(`[name="${dept}"]`);
              if (!deptEl) {
                deptEl = document.createElement('input');
                deptEl.type = 'hidden';
                deptEl.name = dept;
                form.appendChild(deptEl);
              }
              deptEl.value = params.departmentValue;
              return true;
            }""",
            {
                "station": station,
                "month": month,
                "minSearches": min_searches,
                "minGrowthRate": min_growth_rate,
                "keyword": keyword,
                "departmentValue": department_value,
            },
        )
        page.locator('button[type="submit"]').click(timeout=15000)
        deadline = time.time() + max(wait_seconds, 3.0)
        last_url = page.url
        while time.time() < deadline:
            page.wait_for_timeout(500)
            if page.url != last_url:
                last_url = page.url
        title = page.title()
        body_text = ""
        try:
            body_text = page.locator("body").inner_text(timeout=5000)
        except Exception:
            body_text = ""
        html = page.content()
        page.close()
    return {
        "keyword": keyword,
        "title": title,
        "final_url": last_url,
        "visible_text": body_text,
        "html": html,
        "parsed": _parse_keyword_results(body_text),
        "requests": [_safe_json(item) for item in requests],
        "responses": [_safe_json(item) for item in responses],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Submit SellerSprite keyword research filters through current logged-in Chrome")
    parser.add_argument("--cdp", default=DEFAULT_CDP)
    parser.add_argument("--keyword", default="organizer")
    parser.add_argument("--month", default="202602")
    parser.add_argument("--station", default="US")
    parser.add_argument("--min-searches", type=int, default=10000)
    parser.add_argument("--min-growth-rate", type=float, default=10.0)
    parser.add_argument("--department-value", default="kitchen")
    parser.add_argument("--save-prefix", default="sellersprite-keyword-submit")
    parser.add_argument("--wait-seconds", type=float, default=8.0)
    args = parser.parse_args()

    payload = run_probe(
        cdp_url=args.cdp,
        keyword=args.keyword,
        month=args.month,
        station=args.station,
        min_searches=args.min_searches,
        min_growth_rate=args.min_growth_rate,
        department_value=args.department_value,
        wait_seconds=args.wait_seconds,
    )
    prefix = OUT_DIR / args.save_prefix
    (prefix.with_suffix(".txt")).write_text(str(payload.get("visible_text") or ""), encoding="utf-8")
    (prefix.with_suffix(".html")).write_text(str(payload.get("html") or ""), encoding="utf-8")
    (prefix.with_suffix(".json")).write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    result = {
        "keyword": payload.get("keyword"),
        "title": payload.get("title"),
        "final_url": payload.get("final_url"),
        "parsed": payload.get("parsed") or {},
        "request_count": len(payload.get("requests") or []),
        "response_count": len(payload.get("responses") or []),
        "text_path": str(prefix.with_suffix(".txt")),
        "html_path": str(prefix.with_suffix(".html")),
        "json_path": str(prefix.with_suffix(".json")),
    }
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
