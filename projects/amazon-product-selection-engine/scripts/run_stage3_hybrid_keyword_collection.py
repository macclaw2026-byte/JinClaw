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
import html
import json
import random
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from statistics import mean


ROOT = Path("/Users/mac_claw/.openclaw/workspace")
DEFAULT_PROCESSED = ROOT / "data/amazon-product-selection/processed"
DEFAULT_OUTPUT = ROOT / "output/amazon-product-selection"
EXTENSION_ROOT = Path(
    "/Users/mac_claw/Library/Application Support/Google/Chrome/Default/Extensions/lnbmbgocenenhhhdojdielgnmeflbnfb/5.0.2_0"
)
EXTENSION_STORAGE_LOG = Path(
    "/Users/mac_claw/Library/Application Support/Google/Chrome/Default/Local Extension Settings/lnbmbgocenenhhhdojdielgnmeflbnfb/000003.log"
)
AMAZON_BASE = "https://www.amazon.com"
SELLERSPRITE_BASE = "https://www.sellersprite.com"
AMAZON_BLOCK_PATTERNS = (
    r"sorry, we just need to make sure you're not a robot",
    r"enter the characters you see below",
    r"sorry! something went wrong on our end",
    r"to discuss automated access to amazon data please contact",
    r"api-services-support@amazon\.com",
)


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def write_csv(path: Path, rows: list[dict], fieldnames: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def load_existing_rows(path: Path, *, primary_key: str) -> dict[str, dict]:
    if not path.exists():
        return {}
    payload = load_json(path)
    rows = payload.get("rows") or payload.get("metrics") or payload.get("details") or []
    if not isinstance(rows, list):
        return {}
    by_key: dict[str, dict] = {}
    for row in rows:
        if not isinstance(row, dict):
            continue
        key = str(row.get(primary_key, "") or "").strip()
        if key:
            by_key[key] = row
    return by_key


def load_existing_detail_groups(path: Path) -> dict[str, list[dict]]:
    if not path.exists():
        return {}
    payload = load_json(path)
    rows = payload.get("rows") or payload.get("details") or []
    if not isinstance(rows, list):
        return {}
    grouped: dict[str, list[dict]] = {}
    for row in rows:
        if not isinstance(row, dict):
            continue
        keyword = str(row.get("keyword", "") or "").strip()
        if not keyword:
            continue
        grouped.setdefault(keyword, []).append(row)
    return grouped


def is_completed_status(status: str) -> bool:
    return str(status or "").strip() in {"ok", "empty"}


def materialize_metric_rows(keyword_rows: list[dict], metric_by_keyword: dict[str, dict]) -> list[dict]:
    ordered: list[dict] = []
    for keyword_row in keyword_rows:
        keyword = str(keyword_row.get("keyword", "") or "").strip()
        if keyword and keyword in metric_by_keyword:
            ordered.append(metric_by_keyword[keyword])
    return ordered


def materialize_detail_rows(keyword_rows: list[dict], detail_by_keyword: dict[str, list[dict]]) -> list[dict]:
    ordered: list[dict] = []
    for keyword_row in keyword_rows:
        keyword = str(keyword_row.get("keyword", "") or "").strip()
        if keyword:
            ordered.extend(detail_by_keyword.get(keyword) or [])
    return ordered


def parse_int(value) -> int | None:
    if value in (None, "", "None"):
        return None
    try:
        return int(float(str(value).replace(",", "").strip()))
    except ValueError:
        return None


def safe_request(url: str, *, headers: dict[str, str], timeout: int = 30) -> tuple[int, str, str]:
    request = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            body = response.read().decode("utf-8", errors="ignore")
            return response.status, response.geturl(), body
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="ignore")
        return exc.code, url, body


def load_extension_auth() -> dict[str, str]:
    raw = EXTENSION_STORAGE_LOG.read_bytes().decode("latin1", errors="ignore")
    token_matches = re.findall(r'__SIGN_IN_USER.*?\{.*?"token":"([^"]+)".*?\}', raw)
    uuid_matches = re.findall(r'__UUID&"([0-9a-f\-]{36})"', raw)
    source_match = re.search(r'__SOURCE[^"]*"([^"]+)"', raw)
    fp_match = re.search(r'__FPH\{.*?"value":"([0-9a-f]+)"', raw)
    manifest = json.loads((EXTENSION_ROOT / "manifest.json").read_text(encoding="utf-8"))
    version = str(manifest.get("version", "5.0.2"))
    if not token_matches:
        raise RuntimeError("SellerSprite extension sign-in token was not found in local extension storage")
    if not uuid_matches:
        raise RuntimeError("SellerSprite extension random token UUID was not found in local extension storage")
    return {
        "auth_token": token_matches[-1],
        "random_token": uuid_matches[-1],
        "auth_fp": fp_match.group(1) if fp_match else "",
        "source": source_match.group(1) if source_match else "chrome",
        "extension": "lnbmbgocenenhhhdojdielgnmeflbnfb",
        "version": version,
        "language": "zh_CN",
        "ext_version_tkk": version.replace(".", "00", 1).replace(".", "0") + ".1364508470",
    }


def sellersprite_tk(value: str, *, tkk: str) -> str:
    if not value:
        return ""

    def op(acc: int, seed: str) -> int:
        for index in range(0, len(seed) - 2, 3):
            char = seed[index + 2]
            shift = ord(char) - 87 if char >= "a" else int(char)
            shifted = (acc >> shift) if seed[index + 1] == "+" else ((acc << shift) & 0xFFFFFFFF)
            acc = ((acc + shifted) & 0xFFFFFFFF) if seed[index] == "+" else (acc ^ shifted)
        return acc

    left, right = tkk.split(".")
    base = int(left or 0)
    payload: list[int] = []
    for ch in value:
        code = ord(ch)
        if code < 128:
            payload.append(code)
        elif code < 2048:
            payload.extend([code >> 6 | 192, code & 63 | 128])
        else:
            payload.extend([code >> 12 | 224, code >> 6 & 63 | 128, code & 63 | 128])
    acc = base
    for item in payload:
        acc = op(acc + item, "+-a^+6")
    acc = op(acc, "+-3^+b+-f")
    acc ^= int(right or 0)
    if acc < 0:
        acc = 2147483648 + (acc & 2147483647)
    out = acc % 1_000_000
    return f"{out}.{out ^ base}"


def sellersprite_headers(auth: dict[str, str]) -> dict[str, str]:
    headers = {
        "User-Agent": "Mozilla/5.0",
        "Accept": "application/json",
        "Content-Type": "application/json",
        "Auth-Token": auth["auth_token"],
        "Random-Token": auth["random_token"],
    }
    if auth.get("auth_fp"):
        headers["Auth-FP"] = auth["auth_fp"]
    return headers


def fetch_sellersprite_quick_view(asins: list[str], auth: dict[str, str]) -> dict[str, object]:
    asin_csv = ",".join(dict.fromkeys(str(asin or "").strip() for asin in asins if str(asin or "").strip()))
    if not asin_csv:
        return {"items": []}
    params = {
        "asins": asin_csv,
        "tk": sellersprite_tk(asin_csv, tkk=auth["ext_version_tkk"]),
        "version": auth["version"],
        "language": auth["language"],
        "extension": auth["extension"],
        "source": auth["source"],
    }
    url = f"{SELLERSPRITE_BASE}/v2/extension/competitor-lookup/quick-view/US?{urllib.parse.urlencode(params)}"
    status, _, body = safe_request(url, headers=sellersprite_headers(auth))
    if status != 200:
        raise RuntimeError(f"SellerSprite quick-view returned HTTP {status} for asins={asin_csv}")
    payload = json.loads(body)
    if payload.get("code") not in (0, "OK", None):
        raise RuntimeError(f"SellerSprite quick-view failed for asins={asin_csv}: {payload.get('message')}")
    return payload.get("data") or {}


def fetch_amazon_search_html(keyword: str) -> tuple[int, str]:
    params = urllib.parse.urlencode({"k": keyword})
    url = f"{AMAZON_BASE}/s?{params}"
    headers = {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/135.0.0.0 Safari/537.36",
        "Accept-Language": "en-US,en;q=0.9",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
        "Cache-Control": "no-cache",
        "Pragma": "no-cache",
    }
    status, _, body = safe_request(url, headers=headers)
    return status, body


def detect_amazon_block(html_text: str) -> str:
    lowered = str(html_text or "").lower()
    for pattern in AMAZON_BLOCK_PATTERNS:
        if re.search(pattern, lowered, flags=re.I):
            return "amazon_http_block_detected"
    return ""


def extract_result_count(html_text: str) -> int | None:
    patterns = [
        r'"totalResultCount"\s*:\s*(\d+)',
        r'1-\d+ of over ([\d,]+) results',
        r'1-\d+ of ([\d,]+) results',
    ]
    for pattern in patterns:
        found = re.search(pattern, html_text, flags=re.I)
        if found:
            return int(found.group(1).replace(",", ""))
    return None


def normalize_product_href(href: str) -> str:
    value = html.unescape(str(href or "").strip())
    if not value:
        return ""
    if value.startswith("/sspa/click"):
        parsed = urllib.parse.urlparse(value)
        query = urllib.parse.parse_qs(parsed.query)
        nested = query.get("url", [""])[0]
        if nested:
            value = urllib.parse.unquote(nested)
    if value.startswith("/"):
        value = f"{AMAZON_BASE}{value}"
    asin_match = re.search(r"/(?:dp|gp/product|gp/aw/d)/([A-Z0-9]{10})", value, flags=re.I)
    if asin_match:
        return f"{AMAZON_BASE}/dp/{asin_match.group(1).upper()}"
    return value.split("&", 1)[0]


def extract_card_title(chunk: str) -> str:
    heading = re.search(r"<h2\b[^>]*>(.*?)</h2>", chunk, flags=re.I | re.S)
    if heading:
        span_matches = re.findall(r"<span\b[^>]*>(.*?)</span>", heading.group(1), flags=re.I | re.S)
        for candidate in span_matches:
            text = html.unescape(re.sub(r"<[^>]+>", " ", candidate)).strip()
            if text and not re.fullmatch(r"[\d,().Kk+ ]+", text):
                return text
        heading_text = html.unescape(re.sub(r"<[^>]+>", " ", heading.group(1))).strip()
        if heading_text:
            return heading_text
    patterns = [
        r'<h2[^>]*>\s*<a[^>]*>\s*<span[^>]*>(.*?)</span>',
        r'<a[^>]*class="[^"]*a-link-normal[^"]*"[^>]*>\s*<span[^>]*>(.*?)</span>',
    ]
    for pattern in patterns:
        found = re.search(pattern, chunk, flags=re.I | re.S)
        if found:
            return html.unescape(re.sub(r"<[^>]+>", " ", found.group(1))).strip()
    return ""


def extract_card_rating(chunk: str) -> float | None:
    found = re.search(r'<span class="a-icon-alt">([0-9.]+) out of 5 stars</span>', chunk, flags=re.I)
    if not found:
        return None
    try:
        return float(found.group(1))
    except ValueError:
        return None


def extract_card_review_count(chunk: str) -> int | None:
    patterns = [
        r'aria-label="([\d,]+) ratings"',
        r'aria-label="([\d,]+) rating"',
        r'>([\d,]+)</span></a>',
    ]
    for pattern in patterns:
        found = re.search(pattern, chunk, flags=re.I)
        if found:
            return parse_int(found.group(1))
    return None


def extract_first_page_cards(html_text: str) -> list[dict[str, object]]:
    cards: list[dict[str, object]] = []
    seen_asins: set[str] = set()
    pattern = re.compile(r'<div[^>]+data-asin="([A-Z0-9]{10})"[^>]+data-index="(\d+)"[^>]*>', flags=re.I)
    matches = list(pattern.finditer(html_text))
    for idx, match in enumerate(matches):
        asin = match.group(1)
        if asin in seen_asins:
            continue
        seen_asins.add(asin)
        start = match.start()
        end = matches[idx + 1].start() if idx + 1 < len(matches) else min(len(html_text), start + 12000)
        chunk = html_text[start:end]
        href_match = re.search(r'href="([^"]+)"', chunk)
        href = normalize_product_href(href_match.group(1) if href_match else "")
        cards.append(
            {
                "card_index": len(cards) + 1,
                "amazon_data_index": int(match.group(2)),
                "asin": asin,
                "product_url": href or f"{AMAZON_BASE}/dp/{asin}",
                "sponsored": "/sspa/click" in (href_match.group(1) if href_match else ""),
                "title": extract_card_title(chunk),
                "rating": extract_card_rating(chunk),
                "review_count": extract_card_review_count(chunk),
            }
        )
    return cards


def launch_date_from_item(item: dict[str, object]) -> tuple[str, int | None]:
    available_days = parse_int(item.get("available_days"))
    available_raw = item.get("available")
    if available_raw in (None, "", 0):
        return "", available_days
    try:
        launch_dt = datetime.fromtimestamp(int(available_raw) / 1000, tz=timezone.utc)
        return launch_dt.date().isoformat(), available_days
    except Exception:
        return "", available_days


def enrich_first_page_cards(cards: list[dict[str, object]], seller_sprite_items: list[dict[str, object]]) -> list[dict[str, object]]:
    item_by_asin = {str(item.get("asin", "") or "").strip(): item for item in seller_sprite_items if item.get("asin")}
    enriched: list[dict[str, object]] = []
    for card in cards:
        item = item_by_asin.get(str(card["asin"]))
        launch_date, launch_age_days = launch_date_from_item(item or {})
        enriched.append(
            {
                **card,
                "sales_30d": parse_int((item or {}).get("month_units")),
                "launch_date": launch_date,
                "launch_age_days": launch_age_days,
                "seller_type": str((item or {}).get("seller_type", "") or ""),
                "seller_sprite_url": normalize_product_href(str((item or {}).get("url", "") or "")),
                "matched_from_sellersprite": bool(item),
            }
        )
    return enriched


def aggregate_keyword_row(keyword_row: dict[str, object], result_count: int | None, first_page_cards: list[dict[str, object]]) -> dict[str, object]:
    review_values = [int(card["review_count"]) for card in first_page_cards if card.get("review_count") is not None]
    sales_values = [int(card["sales_30d"]) for card in first_page_cards if card.get("sales_30d") is not None]
    launch_rows = [card for card in first_page_cards if card.get("launch_date")]
    representative = None
    if first_page_cards:
        representative = max(
            first_page_cards,
            key=lambda card: (
                int(card.get("sales_30d") or 0),
                int(card.get("review_count") or 0),
                -int(card.get("card_index") or 0),
            ),
        )
    earliest_launch = min((card["launch_date"] for card in launch_rows), default="")
    latest_launch = max((card["launch_date"] for card in launch_rows), default="")
    oldest_age_days = max((int(card["launch_age_days"]) for card in launch_rows if card.get("launch_age_days") is not None), default=None)
    newest_age_days = min((int(card["launch_age_days"]) for card in launch_rows if card.get("launch_age_days") is not None), default=None)
    matched_card_count = sum(1 for card in first_page_cards if card.get("matched_from_sellersprite"))
    representative_url = ""
    if representative:
        representative_url = representative.get("product_url") or representative.get("seller_sprite_url") or ""
    return {
        "keyword_rank": keyword_row["keyword_rank"],
        "keyword": keyword_row["keyword"],
        "seed_asin": keyword_row["seed_asin"],
        "seed_product_title": keyword_row["seed_product_title"],
        "seed_product_url": keyword_row["seed_product_url"],
        "search_url": f"{AMAZON_BASE}/s?k={urllib.parse.quote_plus(str(keyword_row['keyword']))}",
        "result_count": result_count,
        "first_page_product_link_total": len(first_page_cards),
        "first_page_matched_metric_count": matched_card_count,
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
        "representative_asin": str((representative or {}).get("asin", "") or ""),
        "representative_product_url": representative_url,
        "representative_title": str((representative or {}).get("title", "") or ""),
        "collection_status": "ok" if first_page_cards else "empty",
        "collection_error": "",
    }


def checkpoint_outputs(
    *,
    details_json: Path,
    metrics_json: Path,
    metrics_csv: Path,
    final_csv: Path,
    expanded_json: Path,
    expanded_csv: Path,
    detail_rows: list[dict],
    metric_rows: list[dict],
    alternate_entries: list[dict],
) -> None:
    details_json.parent.mkdir(parents=True, exist_ok=True)
    details_json.write_text(
        json.dumps({"generated_at": utc_now(), "detail_row_count": len(detail_rows), "rows": detail_rows}, ensure_ascii=False, indent=2)
        + "\n",
        encoding="utf-8",
    )
    metrics_json.write_text(
        json.dumps({"generated_at": utc_now(), "keyword_count": len(metric_rows), "rows": metric_rows}, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    metric_fieldnames = list(metric_rows[0].keys()) if metric_rows else []
    write_csv(metrics_csv, metric_rows, metric_fieldnames)
    write_csv(final_csv, metric_rows, metric_fieldnames)

    metric_by_keyword = {str(row.get("keyword", "") or "").strip(): row for row in metric_rows}
    expanded_rows: list[dict] = []
    for entry in alternate_entries:
        keyword = str(entry.get("alternate_keyword", "") or "").strip()
        expanded_rows.append({**entry, **(metric_by_keyword.get(keyword) or {})})
    expanded_json.write_text(
        json.dumps({"generated_at": utc_now(), "row_count": len(expanded_rows), "rows": expanded_rows}, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    expanded_fieldnames = list(expanded_rows[0].keys()) if expanded_rows else []
    write_csv(expanded_csv, expanded_rows, expanded_fieldnames)


def main() -> int:
    parser = argparse.ArgumentParser(description="Stage 3 hybrid collector: exact Amazon first-page HTML + SellerSprite authenticated API enrichment.")
    parser.add_argument("--unique-keywords-json", default=str(DEFAULT_PROCESSED / "stage2-unique-alternate-keywords.json"))
    parser.add_argument("--alternate-entries-json", default=str(DEFAULT_PROCESSED / "stage2-alternate-keyword-entries.json"))
    parser.add_argument("--details-json", default=str(DEFAULT_PROCESSED / "stage3-amazon-keyword-details.json"))
    parser.add_argument("--metrics-json", default=str(DEFAULT_PROCESSED / "stage3-amazon-keyword-metrics.json"))
    parser.add_argument("--metrics-csv", default=str(DEFAULT_PROCESSED / "stage3-amazon-keyword-metrics.csv"))
    parser.add_argument("--expanded-json", default=str(DEFAULT_PROCESSED / "stage3-amazon-expanded-alternate-metrics.json"))
    parser.add_argument("--expanded-csv", default=str(DEFAULT_PROCESSED / "stage3-amazon-expanded-alternate-metrics.csv"))
    parser.add_argument("--final-csv", default=str(DEFAULT_OUTPUT / "amazon-product-selection-keyword-results.csv"))
    parser.add_argument("--limit", type=int, default=0, help="Optional keyword limit for validation runs.")
    parser.add_argument("--sleep-min-seconds", type=float, default=1.5)
    parser.add_argument("--sleep-max-seconds", type=float, default=4.0)
    parser.add_argument("--save-every", type=int, default=25)
    parser.add_argument("--max-new-keywords", type=int, default=0, help="Optional cap for how many pending keywords to process in this invocation.")
    args = parser.parse_args()

    if args.sleep_min_seconds < 0 or args.sleep_max_seconds < args.sleep_min_seconds:
        raise SystemExit("invalid sleep range")

    unique_payload = load_json(Path(args.unique_keywords_json).expanduser().resolve())
    alternate_payload = load_json(Path(args.alternate_entries_json).expanduser().resolve())
    keyword_rows = list(unique_payload.get("keywords") or [])
    alternate_entries = list(alternate_payload.get("alternate_keyword_entries") or [])
    if args.limit > 0:
        keyword_rows = keyword_rows[: args.limit]

    auth = load_extension_auth()
    details_json = Path(args.details_json).expanduser().resolve()
    metrics_json = Path(args.metrics_json).expanduser().resolve()
    metrics_csv = Path(args.metrics_csv).expanduser().resolve()
    expanded_json = Path(args.expanded_json).expanduser().resolve()
    expanded_csv = Path(args.expanded_csv).expanduser().resolve()
    final_csv = Path(args.final_csv).expanduser().resolve()

    metric_by_keyword = load_existing_rows(metrics_json, primary_key="keyword")
    detail_by_keyword = load_existing_detail_groups(details_json)
    consecutive_amazon_blocks = 0
    total_keywords = len(keyword_rows)
    pending_keyword_rows = [
        row for row in keyword_rows if not is_completed_status(str((metric_by_keyword.get(str(row.get("keyword", "") or "").strip()) or {}).get("collection_status", "") or ""))
    ]
    if args.limit > 0:
        pending_keyword_rows = pending_keyword_rows[: args.limit]
    if args.max_new_keywords > 0:
        pending_keyword_rows = pending_keyword_rows[: args.max_new_keywords]

    processed_this_run = 0
    for pending_index, keyword_row in enumerate(pending_keyword_rows, start=1):
        keyword = str(keyword_row.get("keyword", "") or "").strip()
        if not keyword:
            continue
        if processed_this_run > 0:
            time.sleep(random.uniform(args.sleep_min_seconds, args.sleep_max_seconds))

        queue_index = int(keyword_row.get("keyword_rank") or pending_index)
        print(f"[pending {pending_index}/{len(pending_keyword_rows)} | queue {queue_index}/{total_keywords}] hybrid collecting keyword: {keyword}", flush=True)
        status_code, html_text = fetch_amazon_search_html(keyword)
        block_reason = detect_amazon_block(html_text)
        if status_code != 200 or block_reason:
            consecutive_amazon_blocks += 1
            detail_by_keyword[keyword] = []
            metric_by_keyword[keyword] = {
                "keyword_rank": keyword_row["keyword_rank"],
                "keyword": keyword,
                "seed_asin": keyword_row["seed_asin"],
                "seed_product_title": keyword_row["seed_product_title"],
                "seed_product_url": keyword_row["seed_product_url"],
                "search_url": f"{AMAZON_BASE}/s?k={urllib.parse.quote_plus(keyword)}",
                "result_count": None,
                "first_page_product_link_total": 0,
                "first_page_matched_metric_count": 0,
                "review_min": None,
                "review_max": None,
                "review_avg": None,
                "sales_30d_min": None,
                "sales_30d_max": None,
                "sales_30d_avg": None,
                "launch_date_earliest": "",
                "launch_date_latest": "",
                "oldest_listing_age_days": None,
                "newest_listing_age_days": None,
                "representative_asin": "",
                "representative_product_url": "",
                "representative_title": "",
                "collection_status": "blocked",
                "collection_error": block_reason or f"amazon_http_status_{status_code}",
            }
            processed_this_run += 1
            if processed_this_run % args.save_every == 0:
                checkpoint_outputs(
                    details_json=details_json,
                    metrics_json=metrics_json,
                    metrics_csv=metrics_csv,
                    final_csv=final_csv,
                    expanded_json=expanded_json,
                    expanded_csv=expanded_csv,
                    detail_rows=materialize_detail_rows(keyword_rows, detail_by_keyword),
                    metric_rows=materialize_metric_rows(keyword_rows, metric_by_keyword),
                    alternate_entries=alternate_entries,
                )
            if consecutive_amazon_blocks >= 3:
                checkpoint_outputs(
                    details_json=details_json,
                    metrics_json=metrics_json,
                    metrics_csv=metrics_csv,
                    final_csv=final_csv,
                    expanded_json=expanded_json,
                    expanded_csv=expanded_csv,
                    detail_rows=materialize_detail_rows(keyword_rows, detail_by_keyword),
                    metric_rows=materialize_metric_rows(keyword_rows, metric_by_keyword),
                    alternate_entries=alternate_entries,
                )
                raise RuntimeError("amazon HTTP collection hit the circuit breaker after 3 consecutive block/error pages")
            continue

        consecutive_amazon_blocks = 0
        result_count = extract_result_count(html_text)
        amazon_cards = extract_first_page_cards(html_text)
        seller_sprite_data = fetch_sellersprite_quick_view([str(card["asin"]) for card in amazon_cards], auth)
        seller_sprite_items = list(seller_sprite_data.get("items") or [])
        first_page_cards = enrich_first_page_cards(amazon_cards, seller_sprite_items)
        detail_by_keyword[keyword] = [
            {
                "keyword": keyword,
                "search_url": f"{AMAZON_BASE}/s?k={urllib.parse.quote_plus(keyword)}",
                **card,
            }
            for card in first_page_cards
        ]
        metric_by_keyword[keyword] = aggregate_keyword_row(keyword_row, result_count, first_page_cards)
        processed_this_run += 1
        if processed_this_run % args.save_every == 0 or pending_index == len(pending_keyword_rows):
            checkpoint_outputs(
                details_json=details_json,
                metrics_json=metrics_json,
                metrics_csv=metrics_csv,
                final_csv=final_csv,
                expanded_json=expanded_json,
                expanded_csv=expanded_csv,
                detail_rows=materialize_detail_rows(keyword_rows, detail_by_keyword),
                metric_rows=materialize_metric_rows(keyword_rows, metric_by_keyword),
                alternate_entries=alternate_entries,
            )

    detail_rows = materialize_detail_rows(keyword_rows, detail_by_keyword)
    metric_rows = materialize_metric_rows(keyword_rows, metric_by_keyword)
    checkpoint_outputs(
        details_json=details_json,
        metrics_json=metrics_json,
        metrics_csv=metrics_csv,
        final_csv=final_csv,
        expanded_json=expanded_json,
        expanded_csv=expanded_csv,
        detail_rows=detail_rows,
        metric_rows=metric_rows,
        alternate_entries=alternate_entries,
    )
    completed_count = sum(1 for row in metric_rows if is_completed_status(str(row.get("collection_status", "") or "")))
    print(
        json.dumps(
            {
                "status": "ok",
                "keyword_count": len(metric_rows),
                "completed_keyword_count": completed_count,
                "processed_this_run": processed_this_run,
                "remaining_keyword_count": max(0, total_keywords - completed_count),
                "detail_row_count": len(detail_rows),
                "metrics_csv": str(metrics_csv),
                "expanded_csv": str(expanded_csv),
            },
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
