#!/usr/bin/env python3
# RULES-FIRST NOTICE:
# Before modifying this file, first read:
# - `JINCLAW_CONSTITUTION.md`
# - `AI_OPTIMIZATION_FRAMEWORK.md`
# Follow the constitution and framework:
# brain-first, one-doctor, fail-closed, evidence-over-narration,
# validate locally, then use the required PR workflow.
from __future__ import annotations

import argparse
import csv
import json
import random
import re
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from statistics import mean
from urllib.parse import quote_plus

from amazon_selection_common import (
    normalize_text,
    parse_amazon_result_count,
    parse_card_rating,
    parse_card_review_count,
    parse_card_sales_30d,
    parse_launch_date,
)


ROOT = Path("/Users/mac_claw/.openclaw/workspace")
VENV_PY = ROOT / "tools/matrix-venv/bin/python"
DEFAULT_INPUT = ROOT / "data/amazon-product-selection/processed/stage2-selected-keywords.json"
DEFAULT_PROCESSED = ROOT / "data/amazon-product-selection/processed"
DEFAULT_OUTPUT = ROOT / "output/amazon-product-selection"
DEFAULT_CDP = "http://127.0.0.1:9222"
DEFAULT_MIN_INTER_KEYWORD_WAIT_MS = 9000
DEFAULT_MAX_INTER_KEYWORD_WAIT_MS = 18000

AMAZON_BLOCK_PATTERNS = (
    r"enter the characters you see below",
    r"sorry, we just need to make sure you're not a robot",
    r"sorry!? something went wrong!?",
    r"to discuss automated access to amazon data please contact",
    r"api-services-support@amazon\.com",
)


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _load_sync_playwright():
    try:
        from playwright.sync_api import sync_playwright  # type: ignore
    except Exception:
        if __name__ == "__main__" and sys.executable != str(VENV_PY) and VENV_PY.exists():
            raise SystemExit(subprocess.run([str(VENV_PY), __file__, *sys.argv[1:]], check=False).returncode)
        raise
    return sync_playwright


def write_csv(path: Path, rows: list[dict], fieldnames: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def _clean_href(href: str | None, asin: str) -> str:
    if href and href.startswith("/"):
        return f"https://www.amazon.com{href.split('?', 1)[0]}"
    if href and href.startswith("http"):
        return href.split("?", 1)[0]
    return f"https://www.amazon.com/dp/{asin}"


def _extract_title_from_card(card_text: str) -> str:
    lines = [line.strip() for line in str(card_text or "").splitlines() if line.strip()]
    skip_tokens = {
        "Sponsored",
        "Results",
        "Overall Pick",
        "Amazon's Choice",
        "Top Brand",
        "Notable Arrival",
        "Featured from Amazon brands",
    }
    for line in lines:
        if line in skip_tokens:
            continue
        if re.fullmatch(r"[\d.]+", line):
            continue
        if "out of 5 stars" in line:
            continue
        if line.startswith("ASIN:") or line.startswith("Brand:") or line.startswith("Seller:"):
            continue
        if len(line) >= 20:
            return normalize_text(line)
    return lines[0] if lines else ""


def _parse_card(raw_card: dict) -> dict | None:
    asin = normalize_text(str(raw_card.get("asin", "") or "")).strip()
    if not re.fullmatch(r"[A-Z0-9]{10}", asin):
        return None
    card_text = str(raw_card.get("text", "") or "")
    title = normalize_text(str(raw_card.get("title", "") or "")) or _extract_title_from_card(card_text)
    href = _clean_href(str(raw_card.get("href", "") or ""), asin)

    rating = parse_card_rating(card_text)
    review_count = parse_card_review_count(card_text)
    sales_30d = parse_card_sales_30d(card_text)
    launch_date, launch_age_days = parse_launch_date(card_text)
    sponsored = "sponsored" in card_text.lower().splitlines()[0].lower() if card_text.splitlines() else False
    organic_position = None
    position_match = re.search(r"(SP|Organic) Position:\s*Page\s*\d+,\s*Position\s*(\d+)", card_text, flags=re.I)
    if position_match:
        organic_position = int(position_match.group(2))

    return {
        "card_index": int(raw_card.get("card_index", 0) or 0),
        "asin": asin,
        "product_url": href,
        "title": title,
        "rating": rating,
        "review_count": review_count,
        "sales_30d": sales_30d,
        "launch_date": launch_date,
        "launch_age_days": launch_age_days,
        "sponsored": sponsored,
        "position": organic_position,
        "raw_excerpt": normalize_text(card_text[:1200]),
    }


def _aggregate_keyword(keyword_row: dict, page_text: str, cards: list[dict]) -> dict:
    result_count = parse_amazon_result_count(page_text)
    review_values = [int(item["review_count"]) for item in cards if item.get("review_count") is not None]
    sales_values = [int(item["sales_30d"]) for item in cards if item.get("sales_30d") is not None]
    launch_rows = [item for item in cards if item.get("launch_date")]

    representative = None
    if cards:
        representative = max(
            cards,
            key=lambda item: (
                int(item.get("sales_30d") or 0),
                int(item.get("review_count") or 0),
                -int(item.get("card_index") or 0),
            ),
        )

    earliest_launch = min((item["launch_date"] for item in launch_rows), default="")
    latest_launch = max((item["launch_date"] for item in launch_rows), default="")
    oldest_age_days = max((int(item["launch_age_days"]) for item in launch_rows if item.get("launch_age_days") is not None), default=None)
    newest_age_days = min((int(item["launch_age_days"]) for item in launch_rows if item.get("launch_age_days") is not None), default=None)

    return {
        "keyword_rank": keyword_row["keyword_rank"],
        "keyword": keyword_row["keyword"],
        "seed_asin": keyword_row["seed_asin"],
        "seed_product_title": keyword_row["seed_product_title"],
        "seed_product_url": keyword_row["seed_product_url"],
        "search_url": f"https://www.amazon.com/s?k={quote_plus(keyword_row['keyword'])}",
        "result_count": result_count,
        "first_page_product_link_total": len(cards),
        "review_min": min(review_values) if review_values else None,
        "review_max": max(review_values) if review_values else None,
        "review_avg": round(mean(review_values), 2) if review_values else None,
        "sales_30d_min": min(sales_values) if sales_values else None,
        "sales_30d_max": max(sales_values) if sales_values else None,
        "sales_30d_avg": round(mean(sales_values), 2) if sales_values else None,
        "launch_date_earliest": earliest_launch,
        "launch_date_latest": latest_launch,
        "oldest_listing_age_days": oldest_age_days,
        "newest_listing_age_days": newest_age_days,
        "representative_asin": representative["asin"] if representative else "",
        "representative_product_url": representative["product_url"] if representative else "",
        "representative_title": representative["title"] if representative else "",
    }


def load_keyword_rows(input_path: Path) -> list[dict]:
    payload = json.loads(input_path.read_text(encoding="utf-8"))
    raw_rows = payload.get("keywords") or payload.get("selected_keywords") or []
    rows: list[dict] = []
    for index, raw in enumerate(raw_rows, start=1):
        keyword = str(raw.get("keyword", "") or "").strip()
        if not keyword:
            continue
        rows.append(
            {
                "keyword_rank": int(raw.get("keyword_rank") or index),
                "keyword": keyword,
                "seed_asin": str(raw.get("seed_asin", "") or raw.get("asin", "") or "").strip(),
                "seed_product_title": str(raw.get("seed_product_title", "") or raw.get("product_title", "") or "").strip(),
                "seed_product_url": str(raw.get("seed_product_url", "") or raw.get("product_url", "") or "").strip(),
                "seed_sales_30d": raw.get("seed_sales_30d", raw.get("sales_30d", "")),
                "seed_ratings_count": raw.get("seed_ratings_count", raw.get("ratings_count", "")),
                "seed_category_path": str(raw.get("seed_category_path", "") or raw.get("category_path", "") or "").strip(),
                "alternate_keywords": raw.get("alternate_keywords", ""),
            }
        )
    rows.sort(key=lambda item: int(item.get("keyword_rank", 0) or 0))
    return rows


def wait_for_keyword_page_text(page, wait_ms: int) -> str:
    deadline = time.monotonic() + max(1.0, wait_ms / 1000.0)
    markers = ("Variation Sold(30 days)", "Launch Date:", "Organic Position:", "SP Position:", "bought in past month")
    last_body_text = ""
    while time.monotonic() < deadline:
        page.wait_for_timeout(350)
        try:
            last_body_text = page.locator("body").inner_text(timeout=2000)
        except Exception:
            continue
        if any(marker in last_body_text for marker in markers):
            break
    return last_body_text


def detect_amazon_block(page_text: str, page_title: str = "") -> str:
    normalized = f"{normalize_text(page_title)}\n{normalize_text(page_text)}".lower()
    for pattern in AMAZON_BLOCK_PATTERNS:
        if re.search(pattern, normalized, flags=re.I):
            return "amazon_page_block_detected"
    return ""


def main() -> int:
    parser = argparse.ArgumentParser(description="Stage 3: collect Amazon front-end keyword metrics through the current Chrome session with SellerSprite extension signals.")
    parser.add_argument("--input", default=str(DEFAULT_INPUT), help="Stage-2 selected keyword JSON path.")
    parser.add_argument("--cdp-url", default=DEFAULT_CDP, help="Chrome CDP endpoint.")
    parser.add_argument("--details-json", default=str(DEFAULT_PROCESSED / "stage3-amazon-keyword-details.json"))
    parser.add_argument("--metrics-json", default=str(DEFAULT_PROCESSED / "stage3-amazon-keyword-metrics.json"))
    parser.add_argument("--metrics-csv", default=str(DEFAULT_PROCESSED / "stage3-amazon-keyword-metrics.csv"))
    parser.add_argument("--final-csv", default=str(DEFAULT_OUTPUT / "amazon-product-selection-keyword-results.csv"))
    parser.add_argument("--wait-ms", type=int, default=5000, help="Post-navigation wait time for SellerSprite overlay data to render.")
    parser.add_argument("--min-inter-keyword-wait-ms", type=int, default=DEFAULT_MIN_INTER_KEYWORD_WAIT_MS, help="Minimum randomized cooldown between keywords.")
    parser.add_argument("--max-inter-keyword-wait-ms", type=int, default=DEFAULT_MAX_INTER_KEYWORD_WAIT_MS, help="Maximum randomized cooldown between keywords.")
    args = parser.parse_args()
    if args.min_inter_keyword_wait_ms < 0 or args.max_inter_keyword_wait_ms < args.min_inter_keyword_wait_ms:
        raise SystemExit("invalid inter-keyword wait range")

    input_path = Path(args.input).expanduser().resolve()
    selected_keywords = load_keyword_rows(input_path)
    sync_playwright = _load_sync_playwright()

    detail_rows: list[dict] = []
    metric_rows: list[dict] = []

    with sync_playwright() as playwright:
        browser = playwright.chromium.connect_over_cdp(args.cdp_url)
        if not browser.contexts:
            raise RuntimeError("no browser context available on the connected Chrome session")
        context = browser.contexts[0]
        total_keywords = len(selected_keywords)
        for index, keyword_row in enumerate(selected_keywords, start=1):
            keyword = str(keyword_row.get("keyword", "") or "").strip()
            if not keyword:
                continue
            if index > 1:
                cooldown_ms = random.randint(args.min_inter_keyword_wait_ms, args.max_inter_keyword_wait_ms)
                print(
                    f"[{index}/{total_keywords}] stability cooldown before next keyword: {cooldown_ms}ms",
                    flush=True,
                )
                time.sleep(cooldown_ms / 1000.0)
            print(f"[{index}/{total_keywords}] collecting keyword: {keyword}", flush=True)
            cards: list[dict] = []
            collection_error = ""
            search_url = f"https://www.amazon.com/s?k={quote_plus(keyword)}"
            page = context.new_page()
            try:
                try:
                    page.goto(search_url, wait_until="domcontentloaded", timeout=45000)
                except Exception as exc:
                    collection_error = normalize_text(str(exc))
                body_text = wait_for_keyword_page_text(page, args.wait_ms)
                block_reason = detect_amazon_block(body_text, page.title())
                if block_reason:
                    raise RuntimeError(block_reason)
                raw_cards = page.locator('[data-component-type="s-search-result"][data-asin]').evaluate_all(
                    """(elements) => elements.map((el, index) => {
                        const link = el.querySelector('h2 a');
                        const titleNode = el.querySelector('h2');
                        return {
                            card_index: index + 1,
                            asin: el.getAttribute('data-asin') || '',
                            href: link ? link.getAttribute('href') || link.href || '' : '',
                            title: titleNode ? titleNode.textContent || '' : '',
                            text: el.innerText || el.textContent || ''
                        };
                    })"""
                )
                for raw_card in raw_cards:
                    card = _parse_card(raw_card)
                    if card is None:
                        continue
                    cards.append(card)
                    detail_rows.append(
                        {
                            "keyword": keyword,
                            "search_url": search_url,
                            **card,
                        }
                    )
                if collection_error and not cards:
                    raise RuntimeError(collection_error)
                aggregated = _aggregate_keyword(keyword_row, body_text, cards)
                aggregated["collection_status"] = "ok" if cards else "empty"
                aggregated["collection_error"] = collection_error
                metric_rows.append(aggregated)
            finally:
                page.close()

    details_json = Path(args.details_json).expanduser().resolve()
    metrics_json = Path(args.metrics_json).expanduser().resolve()
    metrics_csv = Path(args.metrics_csv).expanduser().resolve()
    final_csv = Path(args.final_csv).expanduser().resolve()
    details_json.parent.mkdir(parents=True, exist_ok=True)
    final_csv.parent.mkdir(parents=True, exist_ok=True)

    details_payload = {
        "generated_at": utc_now(),
        "keyword_count": len(metric_rows),
        "details": detail_rows,
    }
    metrics_payload = {
        "generated_at": details_payload["generated_at"],
        "keyword_count": len(metric_rows),
        "metrics": metric_rows,
    }
    details_json.write_text(json.dumps(details_payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    metrics_json.write_text(json.dumps(metrics_payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    if metric_rows:
        fieldnames = list(metric_rows[0].keys())
        write_csv(metrics_csv, metric_rows, fieldnames)
        write_csv(final_csv, metric_rows, fieldnames)
    print(json.dumps({"status": "ok", "keyword_count": len(metric_rows), "metrics_csv": str(metrics_csv), "final_csv": str(final_csv)}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
