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
import math
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path("/Users/mac_claw/.openclaw/workspace")
PROJECT_ROOT = ROOT / "projects/amazon-product-selection-engine"
VENV_PY = ROOT / "tools/matrix-venv/bin/python"
WORKER_SCRIPT = PROJECT_ROOT / "scripts/run_stage3_amazon_keyword_collection.py"
DEFAULT_INPUT = ROOT / "data/amazon-product-selection/processed/stage2-unique-alternate-keywords.json"
DEFAULT_ALTERNATE_ENTRIES = ROOT / "data/amazon-product-selection/processed/stage2-alternate-keyword-entries.json"
DEFAULT_WORKER_DIR = ROOT / "data/amazon-product-selection/processed/stage3-workers"
DEFAULT_PROCESSED = ROOT / "data/amazon-product-selection/processed"
DEFAULT_OUTPUT = ROOT / "output/amazon-product-selection"
DEFAULT_CDP = "http://127.0.0.1:9222"


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def write_csv(path: Path, rows: list[dict], fieldnames: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def load_unique_keyword_rows(path: Path) -> list[dict]:
    payload = json.loads(path.read_text(encoding="utf-8"))
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
                "seed_subcategory": str(raw.get("seed_subcategory", "") or raw.get("subcategory", "") or "").strip(),
                "seed_primary_keyword": str(raw.get("seed_primary_keyword", "") or raw.get("primary_keyword", "") or "").strip(),
                "alternate_keyword_position": raw.get("alternate_keyword_position", ""),
                "alternate_keyword_occurrence_count": int(raw.get("alternate_keyword_occurrence_count") or 0),
                "alternate_keyword_source_asin_count": int(raw.get("alternate_keyword_source_asin_count") or 0),
            }
        )
    rows.sort(key=lambda item: int(item.get("keyword_rank", 0) or 0))
    return rows


def load_alternate_entries(path: Path) -> list[dict]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    rows = payload.get("alternate_keyword_entries") or []
    normalized: list[dict] = []
    for index, raw in enumerate(rows, start=1):
        keyword = str(raw.get("alternate_keyword", "") or "").strip()
        if not keyword:
            continue
        normalized.append(
            {
                "alternate_keyword_entry_rank": int(raw.get("alternate_keyword_entry_rank") or index),
                "source_rank": raw.get("source_rank", ""),
                "asin": str(raw.get("asin", "") or "").strip(),
                "product_url": str(raw.get("product_url", "") or "").strip(),
                "product_title": str(raw.get("product_title", "") or "").strip(),
                "brand": str(raw.get("brand", "") or "").strip(),
                "category_path": str(raw.get("category_path", "") or "").strip(),
                "subcategory": str(raw.get("subcategory", "") or "").strip(),
                "seller_type": str(raw.get("seller_type", "") or "").strip(),
                "sales_30d": raw.get("sales_30d", ""),
                "ratings_count": raw.get("ratings_count", ""),
                "primary_keyword": str(raw.get("primary_keyword", "") or "").strip(),
                "alternate_keyword_position": raw.get("alternate_keyword_position", ""),
                "alternate_keyword": keyword,
            }
        )
    normalized.sort(key=lambda item: int(item.get("alternate_keyword_entry_rank", 0) or 0))
    return normalized


def chunk_keyword_rows(rows: list[dict], worker_count: int, chunk_size: int) -> list[list[dict]]:
    if not rows:
        return []
    effective_chunk_size = chunk_size if chunk_size > 0 else math.ceil(len(rows) / max(1, min(worker_count, len(rows))))
    return [rows[index : index + effective_chunk_size] for index in range(0, len(rows), effective_chunk_size)]


def _worker_python() -> str:
    return str(VENV_PY if VENV_PY.exists() else Path(sys.executable))


def run_worker_chunk(
    *,
    worker_index: int,
    keyword_rows: list[dict],
    worker_dir: Path,
    cdp_url: str,
    wait_ms: int,
    min_inter_keyword_wait_ms: int,
    max_inter_keyword_wait_ms: int,
    resume_existing: bool,
) -> dict:
    chunk_dir = worker_dir / f"worker_{worker_index:02d}"
    chunk_dir.mkdir(parents=True, exist_ok=True)
    input_json = chunk_dir / "input.json"
    details_json = chunk_dir / "details.json"
    metrics_json = chunk_dir / "metrics.json"
    metrics_csv = chunk_dir / "metrics.csv"
    final_csv = chunk_dir / "final.csv"
    stdout_log = chunk_dir / "stdout.log"
    stderr_log = chunk_dir / "stderr.log"

    if resume_existing and details_json.exists() and metrics_json.exists():
        return {
            "worker_index": worker_index,
            "details_json": str(details_json),
            "metrics_json": str(metrics_json),
            "metrics_csv": str(metrics_csv),
            "final_csv": str(final_csv),
            "keyword_count": len(keyword_rows),
            "resumed": True,
        }

    input_payload = {
        "generated_at": utc_now(),
        "selected_keywords": keyword_rows,
    }
    input_json.write_text(json.dumps(input_payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    command = [
        _worker_python(),
        str(WORKER_SCRIPT),
        "--input",
        str(input_json),
        "--cdp-url",
        cdp_url,
        "--details-json",
        str(details_json),
        "--metrics-json",
        str(metrics_json),
        "--metrics-csv",
        str(metrics_csv),
        "--final-csv",
        str(final_csv),
        "--wait-ms",
        str(wait_ms),
        "--min-inter-keyword-wait-ms",
        str(min_inter_keyword_wait_ms),
        "--max-inter-keyword-wait-ms",
        str(max_inter_keyword_wait_ms),
    ]
    completed = subprocess.run(command, capture_output=True, text=True, check=False)
    stdout_log.write_text(completed.stdout or "", encoding="utf-8")
    stderr_log.write_text(completed.stderr or "", encoding="utf-8")
    if completed.returncode != 0:
        raise RuntimeError(
            f"worker {worker_index} failed with exit code {completed.returncode}: "
            f"{(completed.stderr or completed.stdout or '').strip()[:500]}"
        )
    return {
        "worker_index": worker_index,
        "details_json": str(details_json),
        "metrics_json": str(metrics_json),
        "metrics_csv": str(metrics_csv),
        "final_csv": str(final_csv),
        "keyword_count": len(keyword_rows),
        "resumed": False,
    }


def read_json_rows(path: Path, field_name: str) -> list[dict]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    rows = payload.get(field_name) or []
    if not isinstance(rows, list):
        return []
    return rows


def build_expanded_rows(alternate_entries: list[dict], metric_rows: list[dict]) -> list[dict]:
    metrics_by_keyword = {str(row.get("keyword", "") or "").strip(): row for row in metric_rows}
    expanded_rows: list[dict] = []
    for entry in alternate_entries:
        keyword = str(entry.get("alternate_keyword", "") or "").strip()
        metric = metrics_by_keyword.get(keyword, {})
        expanded_rows.append(
            {
                **entry,
                "keyword_rank": metric.get("keyword_rank", ""),
                "search_url": metric.get("search_url", ""),
                "result_count": metric.get("result_count", ""),
                "first_page_product_link_total": metric.get("first_page_product_link_total", ""),
                "review_min": metric.get("review_min", ""),
                "review_max": metric.get("review_max", ""),
                "review_avg": metric.get("review_avg", ""),
                "sales_30d_min": metric.get("sales_30d_min", ""),
                "sales_30d_max": metric.get("sales_30d_max", ""),
                "sales_30d_avg": metric.get("sales_30d_avg", ""),
                "launch_date_earliest": metric.get("launch_date_earliest", ""),
                "launch_date_latest": metric.get("launch_date_latest", ""),
                "oldest_listing_age_days": metric.get("oldest_listing_age_days", ""),
                "newest_listing_age_days": metric.get("newest_listing_age_days", ""),
                "representative_asin": metric.get("representative_asin", ""),
                "representative_product_url": metric.get("representative_product_url", ""),
                "representative_title": metric.get("representative_title", ""),
                "collection_status": metric.get("collection_status", ""),
                "collection_error": metric.get("collection_error", ""),
            }
        )
    return expanded_rows


def main() -> int:
    parser = argparse.ArgumentParser(description="Stage 3 official runner: query Amazon for every alternate keyword, merge worker results, and expand metrics back onto every alternate-keyword entry.")
    parser.add_argument("--input", default=str(DEFAULT_INPUT), help="Stage-2 unique alternate keyword json path.")
    parser.add_argument("--alternate-entries-json", default=str(DEFAULT_ALTERNATE_ENTRIES), help="Stage-2 alternate keyword entry json path.")
    parser.add_argument("--worker-count", type=int, default=1, help="Browser execution concurrency. Keep this within the global browser budget of 3 tabs.")
    parser.add_argument("--chunk-size", type=int, default=100, help="Number of unique keywords per worker chunk.")
    parser.add_argument("--max-keywords", type=int, default=0, help="Optional debug cap on unique keywords.")
    parser.add_argument("--cdp-url", default=DEFAULT_CDP, help="Chrome CDP endpoint.")
    parser.add_argument("--wait-ms", type=int, default=3500, help="Per-keyword wait budget inside each worker.")
    parser.add_argument("--min-inter-keyword-wait-ms", type=int, default=9000, help="Minimum randomized cooldown between keywords inside a worker.")
    parser.add_argument("--max-inter-keyword-wait-ms", type=int, default=18000, help="Maximum randomized cooldown between keywords inside a worker.")
    parser.add_argument("--worker-dir", default=str(DEFAULT_WORKER_DIR))
    parser.add_argument("--details-json", default=str(DEFAULT_PROCESSED / "stage3-amazon-keyword-details.json"))
    parser.add_argument("--metrics-json", default=str(DEFAULT_PROCESSED / "stage3-amazon-keyword-metrics.json"))
    parser.add_argument("--metrics-csv", default=str(DEFAULT_PROCESSED / "stage3-amazon-keyword-metrics.csv"))
    parser.add_argument("--expanded-json", default=str(DEFAULT_PROCESSED / "stage3-amazon-alternate-keyword-expanded.json"))
    parser.add_argument("--expanded-csv", default=str(DEFAULT_PROCESSED / "stage3-amazon-alternate-keyword-expanded.csv"))
    parser.add_argument("--final-csv", default=str(DEFAULT_OUTPUT / "amazon-product-selection-keyword-results.csv"))
    parser.add_argument("--output-expanded-csv", default=str(DEFAULT_OUTPUT / "amazon-product-selection-alternate-keyword-results.csv"))
    parser.add_argument("--resume-existing-workers", action="store_true", help="Reuse completed worker chunk outputs when present.")
    args = parser.parse_args()

    input_path = Path(args.input).expanduser().resolve()
    alternate_entries_path = Path(args.alternate_entries_json).expanduser().resolve()
    worker_dir = Path(args.worker_dir).expanduser().resolve()
    worker_dir.mkdir(parents=True, exist_ok=True)

    unique_keyword_rows = load_unique_keyword_rows(input_path)
    if args.max_keywords and args.max_keywords > 0:
        unique_keyword_rows = unique_keyword_rows[: args.max_keywords]
    alternate_entries = load_alternate_entries(alternate_entries_path)
    if args.worker_count < 1 or args.worker_count > 3:
        raise SystemExit("browser_execution_policy_violation: worker-count must stay within the global max-open-tabs budget of 3")
    if args.min_inter_keyword_wait_ms < 0 or args.max_inter_keyword_wait_ms < args.min_inter_keyword_wait_ms:
        raise SystemExit("invalid inter-keyword wait range")

    chunks = chunk_keyword_rows(unique_keyword_rows, args.worker_count, args.chunk_size)
    worker_results: list[dict] = []
    max_workers = max(1, min(args.worker_count, len(chunks))) if chunks else 1
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = [
            executor.submit(
                run_worker_chunk,
                worker_index=index,
                keyword_rows=chunk,
                worker_dir=worker_dir,
                cdp_url=args.cdp_url,
                wait_ms=args.wait_ms,
                min_inter_keyword_wait_ms=args.min_inter_keyword_wait_ms,
                max_inter_keyword_wait_ms=args.max_inter_keyword_wait_ms,
                resume_existing=args.resume_existing_workers,
            )
            for index, chunk in enumerate(chunks, start=1)
        ]
        for future in as_completed(futures):
            worker_results.append(future.result())

    worker_results.sort(key=lambda item: int(item["worker_index"]))
    detail_rows: list[dict] = []
    metric_rows: list[dict] = []
    for worker_result in worker_results:
        detail_rows.extend(read_json_rows(Path(worker_result["details_json"]), "details"))
        metric_rows.extend(read_json_rows(Path(worker_result["metrics_json"]), "metrics"))

    metric_rows.sort(key=lambda row: (int(row.get("keyword_rank", 0) or 0), str(row.get("keyword", "") or "")))
    detail_rows.sort(key=lambda row: (str(row.get("keyword", "") or ""), int(row.get("card_index", 0) or 0)))
    expanded_rows = build_expanded_rows(alternate_entries, metric_rows)

    details_json = Path(args.details_json).expanduser().resolve()
    metrics_json = Path(args.metrics_json).expanduser().resolve()
    metrics_csv = Path(args.metrics_csv).expanduser().resolve()
    expanded_json = Path(args.expanded_json).expanduser().resolve()
    expanded_csv = Path(args.expanded_csv).expanduser().resolve()
    final_csv = Path(args.final_csv).expanduser().resolve()
    output_expanded_csv = Path(args.output_expanded_csv).expanduser().resolve()

    details_json.parent.mkdir(parents=True, exist_ok=True)
    final_csv.parent.mkdir(parents=True, exist_ok=True)

    details_payload = {
        "generated_at": utc_now(),
        "keyword_count": len(metric_rows),
        "detail_row_count": len(detail_rows),
        "details": detail_rows,
        "worker_results": worker_results,
    }
    metrics_payload = {
        "generated_at": details_payload["generated_at"],
        "keyword_count": len(metric_rows),
        "alternate_keyword_entry_count": len(expanded_rows),
        "metrics": metric_rows,
        "worker_results": worker_results,
    }
    expanded_payload = {
        "generated_at": details_payload["generated_at"],
        "alternate_keyword_entry_count": len(expanded_rows),
        "rows": expanded_rows,
    }

    details_json.write_text(json.dumps(details_payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    metrics_json.write_text(json.dumps(metrics_payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    expanded_json.write_text(json.dumps(expanded_payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    if metric_rows:
        metric_fieldnames = list(metric_rows[0].keys())
        write_csv(metrics_csv, metric_rows, metric_fieldnames)
        write_csv(final_csv, metric_rows, metric_fieldnames)
    if expanded_rows:
        expanded_fieldnames = list(expanded_rows[0].keys())
        write_csv(expanded_csv, expanded_rows, expanded_fieldnames)
        write_csv(output_expanded_csv, expanded_rows, expanded_fieldnames)

    print(
        json.dumps(
            {
                "status": "ok",
                "keyword_count": len(metric_rows),
                "alternate_keyword_entry_count": len(expanded_rows),
                "worker_count": args.worker_count,
                "chunk_count": len(worker_results),
                "chunk_size": args.chunk_size,
                "metrics_csv": str(metrics_csv),
                "expanded_csv": str(expanded_csv),
            },
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
