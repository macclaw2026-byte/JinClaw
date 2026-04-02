#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
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
PRODUCT_RESEARCH_URL = "https://www.sellersprite.com/v3/product-research"


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


def _is_badge_line(value: str) -> bool:
    token = str(value or "").strip()
    if not token:
        return True
    return token in {"AC", "A+", "BS", "V", "AMZ", "FBA", "FBM"}


def _find_price(lines: list[str]) -> str:
    for line in lines:
        if re.fullmatch(r"\$\d+(?:\.\d+)?", line.strip()):
            return line.strip()
    return ""


def _find_sales_amount(lines: list[str]) -> str:
    for line in lines:
        if re.fullmatch(r"\$\d[\d,]*(?:\.\d+)?[KMB]?\+?", line.strip()):
            normalized = line.strip().lower()
            if normalized in {"$0", "$0.0", "$0.00"}:
                continue
            return line.strip()
    return ""


def _find_monthly_sales(lines: list[str]) -> str:
    preferred: list[str] = []
    for line in lines:
        value = line.strip()
        if re.fullmatch(r"\d[\d,]*(?:\.\d+)?[KMB]\+?", value):
            preferred.append(value)
    if preferred:
        return preferred[0]
    for line in lines:
        value = line.strip()
        if re.fullmatch(r"\d[\d,]{3,}(?:\.\d+)?\+?", value):
            return value
    for line in lines:
        value = line.strip()
        if re.fullmatch(r"\d[\d,]*(?:\.\d+)?", value):
            if value in {"1", "2", "3", "4", "5"}:
                continue
            return value
    return ""


def _find_review_count(lines: list[str]) -> str:
    for line in lines:
        value = line.strip().replace(",", "")
        if value.isdigit() and len(value) >= 4:
            return line.strip()
    return ""


def _find_rating(lines: list[str]) -> str:
    for line in lines:
        value = line.strip()
        if re.fullmatch(r"[1-5]\.\d", value):
            return value
    for line in lines:
        value = line.strip()
        if re.fullmatch(r"[1-5](?:\.0)?", value):
            return value
    return ""


def _find_listing_date(lines: list[str]) -> str:
    for line in lines:
        value = line.strip()
        if re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
            return value
    return ""


def _parse_product_results(text: str) -> dict[str, object]:
    lines = _clean_lines(text)
    products: list[dict[str, object]] = []
    for idx, line in enumerate(lines):
        if "ASIN:" not in line:
            continue
        title_idx = idx - 1
        while title_idx >= 0 and (_is_badge_line(lines[title_idx]) or len(lines[title_idx].strip()) < 8):
            title_idx -= 1
        if title_idx < 0:
            continue
        title = lines[title_idx].strip()
        if any(flag in title for flag in ["月销量", "评分数", "卖家精灵", "开始筛选", "搜索结果数", "LQS:", "卖家:"]):
            continue
        rank = None
        for back_idx in range(title_idx - 1, max(-1, title_idx - 4), -1):
            probe = lines[back_idx].strip()
            if probe.isdigit():
                rank = int(probe)
                break
        window = lines[idx : idx + 40]
        asin_match = re.search(r"ASIN:\s*([A-Z0-9]{10})", line)
        products.append(
            {
                "rank": rank,
                "product_name": title,
                "asin": asin_match.group(1) if asin_match else "",
                "monthly_sales_hint": _find_monthly_sales(window),
                "sales_amount_hint": _find_sales_amount(window),
                "price_hint": _find_price(window),
                "review_count_hint": _find_review_count(window),
                "rating_hint": _find_rating(window),
                "listing_date_hint": _find_listing_date(window),
            }
        )
        if len(products) >= 8:
            break
    return {
        "product_rows_detected": len(products),
        "top_products": products,
    }


def run_probe(*, cdp_url: str, wait_seconds: float) -> dict[str, object]:
    requests: list[dict[str, object]] = []
    responses: list[dict[str, object]] = []
    with sync_playwright() as p:
        browser = p.chromium.connect_over_cdp(cdp_url)
        context = browser.contexts[0] if browser.contexts else browser.new_context()
        page = context.new_page()
        Stealth().apply_stealth_sync(page)

        def on_request(req):
            if "sellersprite.com" not in req.url:
                return
            requests.append(
                {
                    "url": req.url,
                    "method": req.method,
                    "post_data": req.post_data or "",
                }
            )

        def on_response(resp):
            if "sellersprite.com" not in resp.url:
                return
            try:
                body = resp.text()[:1000]
            except Exception:
                body = ""
            responses.append(
                {
                    "url": resp.url,
                    "status": resp.status,
                    "method": resp.request.method,
                    "body_preview": body,
                }
            )

        page.on("request", on_request)
        page.on("response", on_response)
        page.goto(PRODUCT_RESEARCH_URL, wait_until="domcontentloaded", timeout=60000)
        page.wait_for_timeout(4000)
        page.get_by_text("开始筛选", exact=False).first.click(timeout=15000)
        deadline = time.time() + max(wait_seconds, 4.0)
        last_url = page.url
        while time.time() < deadline:
            page.wait_for_timeout(500)
            if page.url != last_url:
                last_url = page.url
        title = page.title()
        body_text = ""
        try:
            body_text = page.locator("body").inner_text(timeout=6000)
        except Exception:
            body_text = ""
        html = page.content()
        page.close()
    return {
        "title": title,
        "final_url": last_url,
        "visible_text": body_text,
        "html": html,
        "parsed": _parse_product_results(body_text),
        "requests": [_safe_json(item) for item in requests],
        "responses": [_safe_json(item) for item in responses],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Submit SellerSprite product research through current logged-in Chrome")
    parser.add_argument("--cdp", default=DEFAULT_CDP)
    parser.add_argument("--save-prefix", default="sellersprite-product-submit")
    parser.add_argument("--wait-seconds", type=float, default=8.0)
    args = parser.parse_args()

    payload = run_probe(cdp_url=args.cdp, wait_seconds=args.wait_seconds)
    prefix = OUT_DIR / args.save_prefix
    (prefix.with_suffix(".txt")).write_text(str(payload.get("visible_text") or ""), encoding="utf-8")
    (prefix.with_suffix(".html")).write_text(str(payload.get("html") or ""), encoding="utf-8")
    (prefix.with_suffix(".json")).write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    result = {
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
