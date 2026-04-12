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
from datetime import datetime, timezone
from pathlib import Path

from amazon_selection_common import (
    build_alternate_keywords,
    extract_primary_keyword,
    load_xlsx_records,
    parse_human_count,
    safe_float,
)


ROOT = Path("/Users/mac_claw/.openclaw/workspace")
DEFAULT_INPUT = ROOT / "data/amazon-product-selection/seller-sprite/latest-export.xlsx"
DEFAULT_PROCESSED = ROOT / "data/amazon-product-selection/processed"


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def write_csv(path: Path, rows: list[dict], fieldnames: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def split_alternate_keywords(value: str | list[str] | None) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        raw_values = value
    else:
        raw_values = str(value).split("|")
    keywords: list[str] = []
    seen: set[str] = set()
    for raw in raw_values:
        keyword = str(raw or "").strip()
        if not keyword or keyword in seen:
            continue
        seen.add(keyword)
        keywords.append(keyword)
    return keywords


def build_alternate_keyword_entries(product_rows: list[dict]) -> list[dict]:
    entries: list[dict] = []
    for row in product_rows:
        alternate_keywords = split_alternate_keywords(row.get("alternate_keywords"))
        for position, keyword in enumerate(alternate_keywords, start=1):
            entries.append(
                {
                    "alternate_keyword_entry_rank": len(entries) + 1,
                    "source_rank": row["source_rank"],
                    "asin": row["asin"],
                    "product_url": row["product_url"],
                    "product_title": row["product_title"],
                    "brand": row["brand"],
                    "category_path": row["category_path"],
                    "subcategory": row["subcategory"],
                    "seller_type": row["seller_type"],
                    "sales_30d": row["sales_30d"],
                    "ratings_count": row["ratings_count"],
                    "primary_keyword": row["primary_keyword"],
                    "alternate_keyword_position": position,
                    "alternate_keyword": keyword,
                }
            )
    return entries


def build_unique_alternate_keywords(alternate_entries: list[dict]) -> list[dict]:
    unique_rows: list[dict] = []
    seen_keywords: set[str] = set()
    source_asins_by_keyword: dict[str, set[str]] = {}
    occurrence_counts: dict[str, int] = {}

    for entry in alternate_entries:
        keyword = str(entry.get("alternate_keyword", "") or "").strip()
        if not keyword:
            continue
        occurrence_counts[keyword] = occurrence_counts.get(keyword, 0) + 1
        source_asins_by_keyword.setdefault(keyword, set()).add(str(entry.get("asin", "") or "").strip())
        if keyword in seen_keywords:
            continue
        seen_keywords.add(keyword)
        unique_rows.append(
            {
                "keyword_rank": len(unique_rows) + 1,
                "keyword": keyword,
                "seed_asin": entry["asin"],
                "seed_product_title": entry["product_title"],
                "seed_product_url": entry["product_url"],
                "seed_sales_30d": entry["sales_30d"],
                "seed_ratings_count": entry["ratings_count"],
                "seed_category_path": entry["category_path"],
                "seed_subcategory": entry["subcategory"],
                "seed_primary_keyword": entry["primary_keyword"],
                "alternate_keyword_position": entry["alternate_keyword_position"],
                "alternate_keyword_occurrence_count": 0,
                "alternate_keyword_source_asin_count": 0,
            }
        )

    for row in unique_rows:
        keyword = row["keyword"]
        row["alternate_keyword_occurrence_count"] = occurrence_counts.get(keyword, 0)
        row["alternate_keyword_source_asin_count"] = len(source_asins_by_keyword.get(keyword, set()))

    return unique_rows


def main() -> int:
    parser = argparse.ArgumentParser(description="Stage 2: extract product primary keywords and expand every alternate keyword from the validated SellerSprite export.")
    parser.add_argument("--input", default=str(DEFAULT_INPUT), help="SellerSprite stage-1 xlsx path.")
    parser.add_argument("--all-keywords-json", default=str(DEFAULT_PROCESSED / "stage2-product-keywords.json"))
    parser.add_argument("--all-keywords-csv", default=str(DEFAULT_PROCESSED / "stage2-product-keywords.csv"))
    parser.add_argument("--alternate-entries-json", default=str(DEFAULT_PROCESSED / "stage2-alternate-keyword-entries.json"))
    parser.add_argument("--alternate-entries-csv", default=str(DEFAULT_PROCESSED / "stage2-alternate-keyword-entries.csv"))
    parser.add_argument("--unique-alternate-keywords-json", default=str(DEFAULT_PROCESSED / "stage2-unique-alternate-keywords.json"))
    parser.add_argument("--unique-alternate-keywords-csv", default=str(DEFAULT_PROCESSED / "stage2-unique-alternate-keywords.csv"))
    parser.add_argument("--selected-keywords-json", default=str(DEFAULT_PROCESSED / "stage2-selected-keywords.json"))
    parser.add_argument("--selected-keywords-csv", default=str(DEFAULT_PROCESSED / "stage2-selected-keywords.csv"))
    parser.add_argument("--top-keywords-limit", type=int, default=20, help="Debug-only primary keyword sample size. Official stage 3 should use the unique alternate keyword handoff.")
    args = parser.parse_args()

    input_path = Path(args.input).expanduser().resolve()
    records = load_xlsx_records(input_path)

    product_rows: list[dict] = []
    for index, row in enumerate(records, start=1):
        title = str(row.get("Product Title", "") or "").strip()
        asin = str(row.get("ASIN", "") or "").strip()
        if not title or not asin:
            continue
        brand = str(row.get("Brand", "") or "").strip()
        category_path = str(row.get("Category Path", "") or "").strip()
        subcategory = str(row.get("Sub-Category", "") or "").strip()
        primary_keyword = extract_primary_keyword(title, brand=brand, subcategory=subcategory, category_path=category_path)
        alternate_keywords = build_alternate_keywords(title, subcategory=subcategory, category_path=category_path)
        sales_30d = safe_float(str(row.get("Sales", "") or ""))
        ratings_count = parse_human_count(str(row.get("Ratings", "") or ""))
        product_rows.append(
            {
                "source_rank": index,
                "asin": asin,
                "brand": brand,
                "product_title": title,
                "product_url": str(row.get("URL", "") or f"https://www.amazon.com/dp/{asin}"),
                "category_path": category_path,
                "subcategory": subcategory,
                "seller_type": str(row.get("Seller Type", "") or "").strip(),
                "sales_30d": int(sales_30d or 0),
                "ratings_count": ratings_count or 0,
                "rating": str(row.get("Rating", "") or "").strip(),
                "date_available": str(row.get("Date Available", "") or "").strip(),
                "available_days": str(row.get("Available days", "") or "").strip(),
                "size_tier": str(row.get("Product size tiers", "") or "").strip(),
                "primary_keyword": primary_keyword,
                "alternate_keywords": "|".join(alternate_keywords),
            }
        )

    product_rows.sort(key=lambda item: (-int(item.get("sales_30d", 0) or 0), int(item.get("source_rank", 0) or 0)))
    alternate_keyword_entries = build_alternate_keyword_entries(product_rows)
    unique_alternate_keywords = build_unique_alternate_keywords(alternate_keyword_entries)

    selected_keywords: list[dict] = []
    seen_keywords: set[str] = set()
    for row in product_rows:
        keyword = str(row.get("primary_keyword", "") or "").strip()
        if not keyword or keyword in seen_keywords:
            continue
        seen_keywords.add(keyword)
        selected_keywords.append(
            {
                "keyword_rank": len(selected_keywords) + 1,
                "keyword": keyword,
                "seed_asin": row["asin"],
                "seed_product_title": row["product_title"],
                "seed_product_url": row["product_url"],
                "seed_sales_30d": row["sales_30d"],
                "seed_ratings_count": row["ratings_count"],
                "seed_category_path": row["category_path"],
                "alternate_keywords": row["alternate_keywords"],
            }
        )
        if len(selected_keywords) >= args.top_keywords_limit:
            break

    all_keywords_json = Path(args.all_keywords_json).expanduser().resolve()
    all_keywords_csv = Path(args.all_keywords_csv).expanduser().resolve()
    alternate_entries_json = Path(args.alternate_entries_json).expanduser().resolve()
    alternate_entries_csv = Path(args.alternate_entries_csv).expanduser().resolve()
    unique_alternate_keywords_json = Path(args.unique_alternate_keywords_json).expanduser().resolve()
    unique_alternate_keywords_csv = Path(args.unique_alternate_keywords_csv).expanduser().resolve()
    selected_keywords_json = Path(args.selected_keywords_json).expanduser().resolve()
    selected_keywords_csv = Path(args.selected_keywords_csv).expanduser().resolve()
    all_keywords_json.parent.mkdir(parents=True, exist_ok=True)

    payload = {
        "generated_at": utc_now(),
        "input_file": str(input_path),
        "source_product_count": len(records),
        "keyword_row_count": len(product_rows),
        "alternate_keyword_entry_count": len(alternate_keyword_entries),
        "unique_alternate_keyword_count": len(unique_alternate_keywords),
        "selected_keyword_count": len(selected_keywords),
        "selection_strategy": f"debug_top_sales_unique_primary_keywords_limit_{args.top_keywords_limit}",
        "official_stage3_input_kind": "unique_alternate_keywords",
        "rows": product_rows,
        "alternate_keyword_entries": alternate_keyword_entries,
        "unique_alternate_keywords": unique_alternate_keywords,
        "selected_keywords": selected_keywords,
    }
    all_keywords_json.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    alternate_entries_json.write_text(
        json.dumps(
            {
                "generated_at": payload["generated_at"],
                "alternate_keyword_entry_count": len(alternate_keyword_entries),
                "alternate_keyword_entries": alternate_keyword_entries,
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    unique_alternate_keywords_json.write_text(
        json.dumps(
            {
                "generated_at": payload["generated_at"],
                "keyword_count": len(unique_alternate_keywords),
                "alternate_keyword_entry_count": len(alternate_keyword_entries),
                "keywords": unique_alternate_keywords,
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    selected_keywords_json.write_text(json.dumps({"generated_at": payload["generated_at"], "selected_keywords": selected_keywords}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    write_csv(all_keywords_csv, product_rows, list(product_rows[0].keys()) if product_rows else [])
    write_csv(alternate_entries_csv, alternate_keyword_entries, list(alternate_keyword_entries[0].keys()) if alternate_keyword_entries else [])
    write_csv(unique_alternate_keywords_csv, unique_alternate_keywords, list(unique_alternate_keywords[0].keys()) if unique_alternate_keywords else [])
    write_csv(selected_keywords_csv, selected_keywords, list(selected_keywords[0].keys()) if selected_keywords else [])
    print(
        json.dumps(
            {
                "status": "ok",
                "keyword_row_count": len(product_rows),
                "alternate_keyword_entry_count": len(alternate_keyword_entries),
                "unique_alternate_keyword_count": len(unique_alternate_keywords),
                "selected_keyword_count": len(selected_keywords),
                "unique_alternate_keywords_json": str(unique_alternate_keywords_json),
                "unique_alternate_keywords_csv": str(unique_alternate_keywords_csv),
            },
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
