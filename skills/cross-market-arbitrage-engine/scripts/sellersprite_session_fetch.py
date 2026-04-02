#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path
from urllib.parse import urljoin

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


def _dedupe_keep_order(values: list[str]) -> list[str]:
    seen: set[str] = set()
    rows: list[str] = []
    for value in values:
        normalized = str(value or "").strip()
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        rows.append(normalized)
    return rows


def _extract_months(text: str) -> list[str]:
    return _dedupe_keep_order(re.findall(r"\b20\d{2}-(?:0[1-9]|1[0-2])\b", text))


def _extract_known_terms(text: str, known_terms: list[str]) -> list[str]:
    present = [term for term in known_terms if term in text]
    return _dedupe_keep_order(present)


def _parse_product_research(text: str) -> dict[str, object]:
    return {
        "page_kind": "product_research",
        "platforms": _extract_known_terms(text, ["亚马逊", "TikTok"]),
        "stations": _extract_known_terms(
            text,
            ["美国站", "日本站", "英国站", "德国站", "法国站", "意大利", "西班牙", "加拿大", "印度站", "墨西哥"],
        ),
        "months": _extract_months(text),
        "recommended_modes": _extract_known_terms(
            text,
            [
                "低价长尾选品",
                "研发新品榜",
                "潜力单变体",
                "销量飙升榜",
                "潜力市场",
                "未被满足的市场",
                "不压库存的市场",
                "投机市场",
                "高需求低要求市场",
                "全品类铺货",
                "精品铺货",
                "低价商品",
                "新手推荐",
                "BSR1000榜单",
            ],
        ),
        "filter_metrics": _extract_known_terms(
            text,
            [
                "月销量",
                "月销售额",
                "子体销量",
                "月销量增长率",
                "BSR",
                "小类BSR",
                "价格",
                "评分数",
                "月评新增",
                "毛利率",
                "上架时间",
                "包装重量",
                "包装尺寸",
                "低价商品",
            ],
        ),
    }


def _parse_keyword_research(text: str) -> dict[str, object]:
    return {
        "page_kind": "keyword_research",
        "stations": _extract_known_terms(
            text,
            ["美国", "日本", "英国", "德国", "法国", "意大利", "西班牙", "加拿大", "印度", "墨西哥", "巴西站", "澳洲站", "阿联酋", "沙特"],
        ),
        "months": _extract_months(text),
        "recommended_modes": _extract_known_terms(
            text,
            ["热门市场", "趋势市场", "类目飙升榜", "类目热搜榜"],
        ),
        "filter_metrics": _extract_known_terms(
            text,
            [
                "月搜索量",
                "月搜索量同比增长值",
                "月搜索量近3个月增长值",
                "新细分市场",
                "商品数",
                "购买量",
                "展示量",
                "SPR",
                "货流值",
                "价格",
                "评分数",
                "月搜索量增长率",
                "需供比",
                "购买率",
                "点击量",
                "标题密度",
                "点击总占比",
                "转化总占比",
                "PPC竞价",
            ],
        ),
        "categories": _extract_known_terms(
            text,
            [
                "Arts, Crafts & Sewing",
                "Automotive Parts & Accessories",
                "Baby",
                "Beauty & Personal Care",
                "Cell Phones & Accessories",
                "Clothing, Shoes & Jewelry",
                "Electronics",
                "Health, Household & Baby Care",
                "Home & Kitchen",
                "Office Products",
                "Patio, Lawn & Garden",
                "Pet Supplies",
                "Sports & Outdoors",
                "Tools & Home Improvement",
                "Toys & Games",
            ],
        ),
    }


def _parse_visible_text(url: str, title: str, text: str) -> dict[str, object]:
    title_text = f"{title}\n{text}"
    if "选产品" in title_text or "/product-research" in url:
        return _parse_product_research(text)
    if "关键词选品" in title_text or "/keyword-research" in url:
        return _parse_keyword_research(text)
    return {
        "page_kind": "generic",
        "months": _extract_months(text),
        "platforms": _extract_known_terms(text, ["亚马逊", "TikTok"]),
    }


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
        "parsed": _parse_visible_text(url, title, body_text),
    }


def fetch_api(*, cdp_url: str, base_url: str, api_path: str, wait_seconds: float) -> dict[str, object]:
    with sync_playwright() as p:
        browser = p.chromium.connect_over_cdp(cdp_url)
        context = browser.contexts[0] if browser.contexts else browser.new_context()
        page = context.new_page()
        Stealth().apply_stealth_sync(page)
        page.goto(base_url, wait_until="load", timeout=60000)
        page.wait_for_timeout(max(0, int(wait_seconds * 1000)))
        result = page.evaluate(
            """async (apiPath) => {
              const resp = await fetch(apiPath, {
                credentials: 'include',
                headers: {
                  'X-Requested-With': 'XMLHttpRequest',
                  'Accept': 'application/json, text/javascript, */*; q=0.01'
                }
              });
              const text = await resp.text();
              return {status: resp.status, ok: resp.ok, url: resp.url, text};
            }""",
            api_path,
        )
        page.close()
    text = str(result.get("text") or "")
    parsed_body: object
    try:
        parsed_body = json.loads(text)
    except Exception:
        parsed_body = text
    api_url = str(result.get("url") or urljoin(base_url, api_path))
    return {
        "url": api_url,
        "title": "",
        "visible_text": text,
        "html": "",
        "signals": {
            "api_status": result.get("status"),
            "api_ok": result.get("ok"),
        },
        "parsed": {
            "page_kind": "api",
            "api_path": api_path,
            "api_status": result.get("status"),
            "api_ok": result.get("ok"),
            "api_url": api_url,
            "body": parsed_body,
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Fetch SellerSprite pages through the current logged-in Chrome session via CDP")
    parser.add_argument("--url")
    parser.add_argument("--api-path")
    parser.add_argument("--base-url")
    parser.add_argument("--cdp", default=DEFAULT_CDP)
    parser.add_argument("--wait-seconds", type=float, default=6.0)
    parser.add_argument("--save-prefix", default="latest")
    args = parser.parse_args()

    if args.api_path:
        base_url = args.base_url or args.url or "https://www.sellersprite.com/v2/keyword-research"
        payload = fetch_api(cdp_url=args.cdp, base_url=base_url, api_path=args.api_path, wait_seconds=args.wait_seconds)
    else:
        if not args.url:
            raise SystemExit("--url is required unless --api-path is provided")
        payload = fetch_page(cdp_url=args.cdp, url=args.url, wait_seconds=args.wait_seconds)
    prefix = OUT_DIR / args.save_prefix
    (prefix.with_suffix(".txt")).write_text(str(payload.get("visible_text") or ""), encoding="utf-8")
    (prefix.with_suffix(".html")).write_text(str(payload.get("html") or ""), encoding="utf-8")
    (prefix.with_suffix(".json")).write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    result = {
        "url": payload["url"],
        "title": payload["title"],
        "signals": payload["signals"],
        "parsed": payload.get("parsed") or {},
        "text_path": str(prefix.with_suffix(".txt")),
        "html_path": str(prefix.with_suffix(".html")),
        "json_path": str(prefix.with_suffix(".json")),
    }
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
