#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
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
OUT_DIR = ROOT / "output/cross-market-arbitrage-engine/1688"
OUT_DIR.mkdir(parents=True, exist_ok=True)

GATE_MARKERS = [
    "login.taobao.com",
    "login.1688.com",
    "member/signin",
    "短信登录",
    "密码登录",
    "请按住滑块",
    "punish",
    "x5secdata",
    "nocaptcha",
]


def _signals(final_url: str, title: str, text: str, html: str) -> dict[str, object]:
    blob = "\n".join([final_url, title, text[:12000], html]).lower()
    gated = any(marker.lower() in blob for marker in GATE_MARKERS)
    offer_links = html.lower().count("/offer/")
    detail_links = html.lower().count("detail.1688.com")
    return {
        "gated": gated,
        "offer_link_hits": offer_links,
        "detail_link_hits": detail_links,
        "has_search_results": (offer_links + detail_links) > 0 and not gated,
        "usable_search_page": (offer_links + detail_links) > 0 and not gated and len(text.strip()) > 120,
    }


def fetch_page(*, cdp_url: str, url: str, wait_seconds: float) -> dict[str, object]:
    with sync_playwright() as p:
        browser = p.chromium.connect_over_cdp(cdp_url)
        context = browser.contexts[0] if browser.contexts else browser.new_context()
        page = context.new_page()
        Stealth().apply_stealth_sync(page)
        page.goto(url, wait_until="domcontentloaded", timeout=15000)
        page.wait_for_timeout(max(0, int(wait_seconds * 1000)))
        final_url = page.url
        title = page.title()
        try:
            visible_text = page.locator("body").inner_text(timeout=3000)
        except Exception:
            visible_text = ""
        try:
            html = page.content()
        except Exception:
            html = ""
        page.close()
    return {
        "url": final_url,
        "title": title,
        "visible_text": visible_text,
        "html": html,
        "signals": _signals(final_url, title, visible_text, html),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Fetch 1688 page through current logged-in Chrome session via CDP")
    parser.add_argument("--url", required=True)
    parser.add_argument("--cdp", default=DEFAULT_CDP)
    parser.add_argument("--wait-seconds", type=float, default=3.0)
    parser.add_argument("--save-prefix", default="latest")
    args = parser.parse_args()

    payload = fetch_page(cdp_url=args.cdp, url=args.url, wait_seconds=args.wait_seconds)
    prefix = OUT_DIR / args.save_prefix
    (prefix.with_suffix(".txt")).write_text(str(payload.get("visible_text") or ""), encoding="utf-8")
    (prefix.with_suffix(".html")).write_text(str(payload.get("html") or ""), encoding="utf-8")
    (prefix.with_suffix(".json")).write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    result = {
        "url": payload["url"],
        "title": payload["title"],
        "signals": payload["signals"],
        "text_path": str(prefix.with_suffix(".txt")),
        "html_path": str(prefix.with_suffix(".html")),
        "json_path": str(prefix.with_suffix(".json")),
    }
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
