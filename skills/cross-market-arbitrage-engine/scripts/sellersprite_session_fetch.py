#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
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


def _extract_numeric(raw: str) -> float | None:
    cleaned = raw.replace(",", "").strip().lower()
    try:
        if cleaned.endswith("k"):
            return float(cleaned[:-1]) * 1000.0
        if cleaned.endswith("m"):
            return float(cleaned[:-1]) * 1_000_000.0
        return float(cleaned)
    except Exception:
        return None


def _extract_sellersprite_signals(text: str) -> dict[str, object]:
    signals: dict[str, object] = {}
    patterns = {
        "search_volume": [
            r"search volume[^0-9]{0,20}(\d[\d,]*(?:\.\d+)?[km]?)",
            r"monthly search volume[^0-9]{0,20}(\d[\d,]*(?:\.\d+)?[km]?)",
        ],
        "purchase_rate": [
            r"purchase rate[^0-9]{0,20}(\d+(?:\.\d+)?)\s*%",
        ],
        "opportunity_score": [
            r"opportunity score[^0-9]{0,20}(\d+(?:\.\d+)?)",
            r"opportunity[^0-9]{0,20}(\d+(?:\.\d+)?)",
        ],
        "monthly_sales": [
            r"monthly sales[^0-9]{0,20}(\d[\d,]*(?:\.\d+)?[km]?)",
            r"sales[^0-9]{0,20}(\d[\d,]*(?:\.\d+)?[km]?)",
        ],
        "monthly_revenue": [
            r"revenue[^0-9]{0,20}\$?\s*(\d[\d,]*(?:\.\d+)?[km]?)",
        ],
        "bsr": [
            r"\bbsr[^0-9#]{0,20}#?\s*(\d[\d,]*)",
            r"best sellers rank[^0-9#]{0,20}#?\s*(\d[\d,]*)",
        ],
        "trend_growth_percent": [
            r"trending[^0-9+-]{0,20}([+-]?\d+(?:\.\d+)?)\s*%",
            r"growth rate[^0-9+-]{0,20}([+-]?\d+(?:\.\d+)?)\s*%",
        ],
    }
    lowered = text.lower()
    for field, field_patterns in patterns.items():
        for pattern in field_patterns:
            found = re.search(pattern, lowered, flags=re.I)
            if not found:
                continue
            raw = found.group(1)
            value = _extract_numeric(raw)
            signals[field] = value if value is not None else raw
            break
    signals["has_keyword_research"] = "keyword research" in lowered
    signals["has_product_research"] = "product research" in lowered
    signals["has_category_insights"] = "category insights" in lowered
    signals["has_sellersprite_branding"] = "sellersprite" in lowered
    return signals


def fetch_page(*, cdp_url: str, url: str, wait_seconds: float) -> dict[str, object]:
    with sync_playwright() as p:
        browser = p.chromium.connect_over_cdp(cdp_url)
        context = browser.contexts[0] if browser.contexts else browser.new_context()
        page = context.new_page()
        Stealth().apply_stealth_sync(page)
        page.goto(url, wait_until="load", timeout=60000)
        page.wait_for_timeout(max(0, int(wait_seconds * 1000)))
        title = page.title()
        body_text = ""
        try:
            body_text = page.locator("body").inner_text(timeout=10000)
        except Exception:
            body_text = ""
        html = page.content()
        page.close()
    return {
        "url": url,
        "title": title,
        "visible_text": body_text,
        "html": html,
        "signals": _extract_sellersprite_signals(body_text),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Fetch SellerSprite pages through the current logged-in Chrome session via CDP")
    parser.add_argument("--url", required=True)
    parser.add_argument("--cdp", default=DEFAULT_CDP)
    parser.add_argument("--wait-seconds", type=float, default=6.0)
    parser.add_argument("--save-prefix", default="latest")
    args = parser.parse_args()

    payload = fetch_page(cdp_url=args.cdp, url=args.url, wait_seconds=args.wait_seconds)
    prefix = OUT_DIR / args.save_prefix
    (prefix.with_suffix(".txt")).write_text(str(payload.get("visible_text") or ""), encoding="utf-8")
    (prefix.with_suffix(".html")).write_text(str(payload.get("html") or ""), encoding="utf-8")
    result = {
        "url": payload["url"],
        "title": payload["title"],
        "signals": payload["signals"],
        "text_path": str(prefix.with_suffix(".txt")),
        "html_path": str(prefix.with_suffix(".html")),
    }
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
