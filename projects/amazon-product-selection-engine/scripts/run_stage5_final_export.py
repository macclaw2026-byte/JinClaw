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

from amazon_selection_common import safe_float


ROOT = Path("/Users/mac_claw/.openclaw/workspace")
DEFAULT_INPUT = ROOT / "data/amazon-product-selection/processed/stage4-keyword-analysis.csv"
DEFAULT_PROCESSED = ROOT / "data/amazon-product-selection/processed"
DEFAULT_OUTPUT = ROOT / "output/amazon-product-selection"


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def to_float(value: str | None) -> float:
    return float(safe_float(str(value or "")) or 0.0)


def sort_key(row: dict[str, str]) -> tuple[float, float, float]:
    return (
        -to_float(row.get("opportunity_score")),
        -to_float(row.get("competition_score")),
        -to_float(row.get("demand_score")),
    )


def write_csv(path: Path, rows: list[dict], fieldnames: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def build_export_row(source_row: dict[str, str], final_rank: int) -> dict[str, object]:
    return {
        "final_rank": final_rank,
        "keyword": source_row.get("keyword", ""),
        "decision": source_row.get("decision", ""),
        "opportunity_score": source_row.get("opportunity_score", ""),
        "demand_score": source_row.get("demand_score", ""),
        "competition_score": source_row.get("competition_score", ""),
        "freshness_score": source_row.get("freshness_score", ""),
        "result_count": source_row.get("result_count", ""),
        "first_page_product_link_total": source_row.get("first_page_product_link_total", ""),
        "review_min": source_row.get("review_min", ""),
        "review_max": source_row.get("review_max", ""),
        "review_avg": source_row.get("review_avg", ""),
        "sales_30d_min": source_row.get("sales_30d_min", ""),
        "sales_30d_max": source_row.get("sales_30d_max", ""),
        "sales_30d_avg": source_row.get("sales_30d_avg", ""),
        "launch_date_earliest": source_row.get("launch_date_earliest", ""),
        "launch_date_latest": source_row.get("launch_date_latest", ""),
        "newest_listing_age_days": source_row.get("newest_listing_age_days", ""),
        "launch_data_status": source_row.get("launch_data_status", ""),
        "representative_asin": source_row.get("representative_asin", ""),
        "representative_title": source_row.get("representative_title", ""),
        "representative_product_url": source_row.get("representative_product_url", ""),
        "reason_summary": source_row.get("reason_summary", ""),
    }


def build_summary_markdown(payload: dict) -> str:
    lines = [
        "# Amazon Product Selection Final Summary",
        "",
        f"- Generated at: {payload['generated_at']}",
        f"- Qualified keywords: {payload['qualified_count']}",
        f"- Watchlist keywords: {payload['watchlist_count']}",
        f"- Rejected keywords: {payload['reject_count']}",
        "",
        "## Final Qualified Keywords",
        "",
    ]
    for row in payload["final_rows"]:
        lines.append(
            f"{row['final_rank']}. {row['keyword']} | score={row['opportunity_score']} | url={row['representative_product_url']}"
        )
        lines.append(f"   {row['reason_summary']}")
    lines.append("")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="Stage 5: export the final qualified keyword shortlist and summary.")
    parser.add_argument("--input", default=str(DEFAULT_INPUT), help="Stage-4 analysis csv path.")
    parser.add_argument("--final-json", default=str(DEFAULT_PROCESSED / "stage5-final-shortlist.json"))
    parser.add_argument("--final-csv", default=str(DEFAULT_PROCESSED / "stage5-final-shortlist.csv"))
    parser.add_argument("--summary-md", default=str(DEFAULT_PROCESSED / "stage5-final-summary.md"))
    parser.add_argument("--output-final-csv", default=str(DEFAULT_OUTPUT / "amazon-product-selection-final-shortlist.csv"))
    parser.add_argument("--output-summary-md", default=str(DEFAULT_OUTPUT / "amazon-product-selection-final-summary.md"))
    args = parser.parse_args()

    input_path = Path(args.input).expanduser().resolve()
    rows = list(csv.DictReader(input_path.open(encoding="utf-8")))
    qualified_rows = sorted([row for row in rows if row.get("decision") == "qualified"], key=sort_key)
    watchlist_count = len([row for row in rows if row.get("decision") == "watchlist"])
    reject_count = len([row for row in rows if row.get("decision") == "reject"])
    final_rows = [build_export_row(row, index + 1) for index, row in enumerate(qualified_rows)]

    payload = {
        "generated_at": utc_now(),
        "input_file": str(input_path),
        "qualified_count": len(final_rows),
        "watchlist_count": watchlist_count,
        "reject_count": reject_count,
        "final_rows": final_rows,
    }

    final_json = Path(args.final_json).expanduser().resolve()
    final_csv = Path(args.final_csv).expanduser().resolve()
    summary_md = Path(args.summary_md).expanduser().resolve()
    output_final_csv = Path(args.output_final_csv).expanduser().resolve()
    output_summary_md = Path(args.output_summary_md).expanduser().resolve()

    final_json.parent.mkdir(parents=True, exist_ok=True)
    output_final_csv.parent.mkdir(parents=True, exist_ok=True)

    final_json.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    fieldnames = list(final_rows[0].keys()) if final_rows else [
        "final_rank",
        "keyword",
        "decision",
        "opportunity_score",
        "demand_score",
        "competition_score",
        "freshness_score",
        "result_count",
        "first_page_product_link_total",
        "review_min",
        "review_max",
        "review_avg",
        "sales_30d_min",
        "sales_30d_max",
        "sales_30d_avg",
        "launch_date_earliest",
        "launch_date_latest",
        "newest_listing_age_days",
        "launch_data_status",
        "representative_asin",
        "representative_title",
        "representative_product_url",
        "reason_summary",
    ]
    write_csv(final_csv, final_rows, fieldnames)
    write_csv(output_final_csv, final_rows, fieldnames)

    summary_text = build_summary_markdown(payload)
    summary_md.write_text(summary_text, encoding="utf-8")
    output_summary_md.write_text(summary_text, encoding="utf-8")

    print(
        json.dumps(
            {
                "status": "ok",
                "qualified_count": len(final_rows),
                "watchlist_count": watchlist_count,
                "reject_count": reject_count,
                "final_csv": str(final_csv),
                "summary_md": str(summary_md),
            },
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
