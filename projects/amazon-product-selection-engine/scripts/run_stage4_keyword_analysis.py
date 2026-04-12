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
from datetime import datetime, timezone
from pathlib import Path

from amazon_selection_common import safe_float


ROOT = Path("/Users/mac_claw/.openclaw/workspace")
DEFAULT_INPUT = ROOT / "data/amazon-product-selection/processed/stage3-amazon-keyword-metrics.csv"
DEFAULT_PROCESSED = ROOT / "data/amazon-product-selection/processed"
DEFAULT_OUTPUT = ROOT / "output/amazon-product-selection"


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def parse_int(value: str | int | float | None) -> int | None:
    number = safe_float(str(value or ""))
    if number is None:
        return None
    return int(number)


def positive_log_score(value: int | None, low: int, high: int) -> float:
    if value is None:
        return 50.0
    if value <= low:
        return 0.0
    if value >= high:
        return 100.0
    low_log = math.log10(low)
    high_log = math.log10(high)
    value_log = math.log10(value)
    return round((value_log - low_log) / (high_log - low_log) * 100, 2)


def inverse_log_score(value: int | None, good: int, bad: int) -> float:
    if value is None:
        return 50.0
    if value <= good:
        return 100.0
    if value >= bad:
        return 0.0
    good_log = math.log10(good)
    bad_log = math.log10(bad)
    value_log = math.log10(value)
    return round((bad_log - value_log) / (bad_log - good_log) * 100, 2)


def score_demand(avg_sales: int | None, max_sales: int | None, min_sales: int | None) -> float:
    avg_score = positive_log_score(avg_sales, low=200, high=2000)
    max_score = positive_log_score(max_sales, low=500, high=10000)
    min_score = positive_log_score(min_sales, low=50, high=300)
    return round(avg_score * 0.65 + max_score * 0.25 + min_score * 0.10, 2)


def score_competition(result_count: int | None, review_avg: int | None) -> float:
    result_score = inverse_log_score(result_count, good=500, bad=40000)
    review_score = inverse_log_score(review_avg, good=300, bad=10000)
    return round(result_score * 0.45 + review_score * 0.55, 2)


def score_freshness(newest_listing_age_days: int | None) -> float:
    if newest_listing_age_days is None:
        return 50.0
    return round(inverse_log_score(newest_listing_age_days, good=14, bad=365), 2)


def build_reason_lines(
    *,
    result_count: int | None,
    review_avg: int | None,
    sales_avg: int | None,
    newest_listing_age_days: int | None,
    hard_fail_reasons: list[str],
    demand_score: float,
    competition_score: float,
    freshness_score: float,
) -> str:
    reasons: list[str] = []
    if hard_fail_reasons:
        reasons.extend(hard_fail_reasons)
    if sales_avg is not None and sales_avg >= 1000:
        reasons.append("需求强，首页30天销量均值较高")
    elif sales_avg is not None and sales_avg >= 400:
        reasons.append("需求中等，首页30天销量仍有空间")
    else:
        reasons.append("需求偏弱，首页30天销量均值不高")

    if competition_score >= 70:
        reasons.append("竞争相对可控，搜索结果量和review均值较友好")
    elif competition_score >= 50:
        reasons.append("竞争中等，需要进一步结合产品差异化判断")
    else:
        reasons.append("竞争偏强，首页竞争密度较高")

    if newest_listing_age_days is None:
        reasons.append("上架时间数据不完整，已按中性分处理")
    elif newest_listing_age_days <= 90:
        reasons.append("近期仍有新上架产品，存在切入信号")
    else:
        reasons.append("近期上新不明显，切入节奏要更谨慎")

    if result_count is not None and result_count <= 1000:
        reasons.append("关键词结果量不大，利于聚焦")
    if review_avg is not None and review_avg <= 800:
        reasons.append("首页review均值偏低，新品切入阻力较小")

    return "；".join(dict.fromkeys(reasons))


def analyze_row(row: dict[str, str]) -> dict[str, object]:
    result_count = parse_int(row.get("result_count"))
    review_avg = parse_int(row.get("review_avg"))
    sales_avg = parse_int(row.get("sales_30d_avg"))
    sales_min = parse_int(row.get("sales_30d_min"))
    sales_max = parse_int(row.get("sales_30d_max"))
    newest_age = parse_int(row.get("newest_listing_age_days"))

    demand_score = score_demand(sales_avg, sales_max, sales_min)
    competition_score = score_competition(result_count, review_avg)
    freshness_score = score_freshness(newest_age)
    opportunity_score = round(demand_score * 0.45 + competition_score * 0.40 + freshness_score * 0.15, 2)

    hard_fail_reasons: list[str] = []
    if result_count is not None and result_count > 40000:
        hard_fail_reasons.append("搜索结果量过大")
    if review_avg is not None and review_avg > 10000:
        hard_fail_reasons.append("首页review均值过高")
    if sales_avg is not None and sales_avg < 220:
        hard_fail_reasons.append("首页30天销量均值偏低")

    if hard_fail_reasons:
        decision = "reject"
    elif opportunity_score >= 65 and demand_score >= 35 and competition_score >= 40:
        decision = "qualified"
    elif opportunity_score >= 50 and demand_score >= 20:
        decision = "watchlist"
    else:
        decision = "reject"

    reason_summary = build_reason_lines(
        result_count=result_count,
        review_avg=review_avg,
        sales_avg=sales_avg,
        newest_listing_age_days=newest_age,
        hard_fail_reasons=hard_fail_reasons,
        demand_score=demand_score,
        competition_score=competition_score,
        freshness_score=freshness_score,
    )

    priority_rank = {
        "qualified": 1,
        "watchlist": 2,
        "reject": 3,
    }[decision]

    launch_data_status = "complete" if row.get("launch_date_earliest") else "missing"

    return {
        **row,
        "decision": decision,
        "priority_rank": priority_rank,
        "opportunity_score": opportunity_score,
        "demand_score": demand_score,
        "competition_score": competition_score,
        "freshness_score": freshness_score,
        "launch_data_status": launch_data_status,
        "hard_fail_reason": "；".join(hard_fail_reasons),
        "reason_summary": reason_summary,
    }


def write_csv(path: Path, rows: list[dict], fieldnames: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def main() -> int:
    parser = argparse.ArgumentParser(description="Stage 4: score and filter Amazon keyword metrics into qualified/watchlist/reject buckets.")
    parser.add_argument("--input", default=str(DEFAULT_INPUT), help="Stage-3 keyword metrics csv path.")
    parser.add_argument("--analysis-json", default=str(DEFAULT_PROCESSED / "stage4-keyword-analysis.json"))
    parser.add_argument("--analysis-csv", default=str(DEFAULT_PROCESSED / "stage4-keyword-analysis.csv"))
    parser.add_argument("--qualified-csv", default=str(DEFAULT_PROCESSED / "stage4-qualified-keywords.csv"))
    parser.add_argument("--output-analysis-csv", default=str(DEFAULT_OUTPUT / "amazon-product-selection-stage4-analysis.csv"))
    parser.add_argument("--output-qualified-csv", default=str(DEFAULT_OUTPUT / "amazon-product-selection-qualified-keywords.csv"))
    args = parser.parse_args()

    input_path = Path(args.input).expanduser().resolve()
    rows = list(csv.DictReader(input_path.open(encoding="utf-8")))
    analyzed_rows = [analyze_row(row) for row in rows]
    analyzed_rows.sort(
        key=lambda row: (
            int(row["priority_rank"]),
            -float(row["opportunity_score"]),
            int(row["keyword_rank"]),
        )
    )
    qualified_rows = [row for row in analyzed_rows if row["decision"] == "qualified"]
    watchlist_rows = [row for row in analyzed_rows if row["decision"] == "watchlist"]
    rejected_rows = [row for row in analyzed_rows if row["decision"] == "reject"]

    analysis_payload = {
        "generated_at": utc_now(),
        "input_file": str(input_path),
        "keyword_count": len(analyzed_rows),
        "qualified_count": len(qualified_rows),
        "watchlist_count": len(watchlist_rows),
        "reject_count": len(rejected_rows),
        "thresholds": {
            "hard_fail": {
                "result_count_gt": 40000,
                "review_avg_gt": 10000,
                "sales_30d_avg_lt": 220,
            },
            "qualified": {
                "opportunity_score_gte": 65,
                "demand_score_gte": 35,
                "competition_score_gte": 40,
            },
            "watchlist": {
                "opportunity_score_gte": 50,
                "demand_score_gte": 20,
            },
        },
        "rows": analyzed_rows,
    }

    analysis_json = Path(args.analysis_json).expanduser().resolve()
    analysis_csv = Path(args.analysis_csv).expanduser().resolve()
    qualified_csv = Path(args.qualified_csv).expanduser().resolve()
    output_analysis_csv = Path(args.output_analysis_csv).expanduser().resolve()
    output_qualified_csv = Path(args.output_qualified_csv).expanduser().resolve()

    analysis_json.parent.mkdir(parents=True, exist_ok=True)
    output_analysis_csv.parent.mkdir(parents=True, exist_ok=True)
    analysis_json.write_text(json.dumps(analysis_payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    fieldnames = list(analyzed_rows[0].keys()) if analyzed_rows else []
    if analyzed_rows:
        write_csv(analysis_csv, analyzed_rows, fieldnames)
        write_csv(output_analysis_csv, analyzed_rows, fieldnames)
    if qualified_rows:
        write_csv(qualified_csv, qualified_rows, fieldnames)
        write_csv(output_qualified_csv, qualified_rows, fieldnames)
    else:
        write_csv(qualified_csv, [], fieldnames)
        write_csv(output_qualified_csv, [], fieldnames)

    print(
        json.dumps(
            {
                "status": "ok",
                "keyword_count": len(analyzed_rows),
                "qualified_count": len(qualified_rows),
                "watchlist_count": len(watchlist_rows),
                "reject_count": len(rejected_rows),
                "analysis_csv": str(analysis_csv),
                "qualified_csv": str(qualified_csv),
            },
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
