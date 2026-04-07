#!/usr/bin/env python3

from __future__ import annotations

import argparse
import json
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path


POSITIVE_CLASSES = {"positive_interest", "referral", "neutral_question"}
NEGATIVE_CLASSES = {"invalid_contact", "hard_bounce", "unsubscribe", "spam_complaint_risk", "not_fit"}


def _read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _read_json_safe(path: Path) -> dict:
    if not path.exists():
        return {"items": []}
    return _read_json(path)


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def main() -> int:
    parser = argparse.ArgumentParser(description="Apply discovery-query weights from strategy-ready records and feedback.")
    parser.add_argument("--queries", required=True)
    parser.add_argument("--strategy-ready-seeds", required=True)
    parser.add_argument("--feedback-events", required=True)
    parser.add_argument("--prospects")
    parser.add_argument("--output", required=True)
    args = parser.parse_args()

    queries = _read_json_safe(Path(args.queries).expanduser()).get("items", [])
    seeds = _read_json_safe(Path(args.strategy_ready_seeds).expanduser()).get("items", [])
    feedback_events = _read_json_safe(Path(args.feedback_events).expanduser()).get("items", [])
    prospects = _read_json_safe(Path(args.prospects).expanduser()).get("items", []) if args.prospects else []

    query_lookup = {}
    for item in queries:
        query_key = item.get("query_id") or item.get("query")
        if query_key:
            query_lookup[query_key] = item
        if item.get("query"):
            query_lookup[item["query"]] = item

    seed_stats: dict[str, dict] = defaultdict(lambda: {"count": 0, "avg_confidence_total": 0.0, "high_fit_count": 0})
    for seed in seeds:
        query_key = seed.get("query_id") or seed.get("discovery_query")
        if not query_key:
            continue
        stat = seed_stats[query_key]
        stat["count"] += 1
        stat["avg_confidence_total"] += float(seed.get("source_confidence", 0.0) or 0.0)
        if any(signal in {"active_project_pipeline", "design_led_projects", "trade_program_fit"} for signal in seed.get("signals", [])):
            stat["high_fit_count"] += 1

    account_to_query = {}
    for prospect in prospects:
        query_key = prospect.get("query_id") or prospect.get("discovery_query")
        if query_key:
            account_to_query[prospect.get("account_id")] = query_key

    feedback_counts: dict[str, Counter] = defaultdict(Counter)
    for item in feedback_events:
        account_id = item.get("account_id")
        query_key = account_to_query.get(account_id)
        if not query_key:
            continue
        classification = (item.get("classification") or item.get("outcome_type") or "").strip().lower()
        feedback_counts[query_key][classification] += 1

    query_bias = {}
    performance = []
    for key, item in query_lookup.items():
        if key != item.get("query_id") and key != item.get("query"):
            continue
        stat = seed_stats.get(key, {"count": 0, "avg_confidence_total": 0.0, "high_fit_count": 0})
        count = stat["count"]
        avg_confidence = (stat["avg_confidence_total"] / count) if count else 0.0
        positive = sum(feedback_counts.get(key, Counter()).get(k, 0) for k in POSITIVE_CLASSES)
        negative = sum(feedback_counts.get(key, Counter()).get(k, 0) for k in NEGATIVE_CLASSES)
        bias = 0.0
        if count:
            bias += min(2.4, count * 0.12)
            bias += min(1.2, stat["high_fit_count"] * 0.08)
            bias += max(-0.8, (avg_confidence - 0.7) * 3.0)
        bias += positive * 0.8
        bias -= negative * 1.1
        query_bias[item.get("query_id") or item.get("query")] = round(bias, 3)
        performance.append(
            {
                "query_id": item.get("query_id"),
                "query": item.get("query"),
                "query_family": item.get("query_family"),
                "source_family": item.get("source_family"),
                "strategy_ready_count": count,
                "high_fit_count": stat["high_fit_count"],
                "average_source_confidence": round(avg_confidence, 4),
                "positive_feedback_count": positive,
                "negative_feedback_count": negative,
                "bias": round(bias, 3),
            }
        )

    for key, stat in seed_stats.items():
        if key in query_bias:
            continue
        avg_confidence = (stat["avg_confidence_total"] / stat["count"]) if stat["count"] else 0.0
        positive = sum(feedback_counts.get(key, Counter()).get(k, 0) for k in POSITIVE_CLASSES)
        negative = sum(feedback_counts.get(key, Counter()).get(k, 0) for k in NEGATIVE_CLASSES)
        bias = 0.0
        if stat["count"]:
            bias += min(2.4, stat["count"] * 0.12)
            bias += min(1.2, stat["high_fit_count"] * 0.08)
            bias += max(-0.8, (avg_confidence - 0.7) * 3.0)
        bias += positive * 0.8
        bias -= negative * 1.1
        query_bias[key] = round(bias, 3)
        performance.append(
            {
                "query_id": key,
                "query": key,
                "query_family": "manual_or_legacy",
                "source_family": "unclassified_public_source",
                "strategy_ready_count": stat["count"],
                "high_fit_count": stat["high_fit_count"],
                "average_source_confidence": round(avg_confidence, 4),
                "positive_feedback_count": positive,
                "negative_feedback_count": negative,
                "bias": round(bias, 3),
            }
        )

    performance.sort(key=lambda row: (-row["bias"], -row["strategy_ready_count"], row["query"] or ""))
    payload = {
        "updated_at": _utc_now(),
        "query_bias": query_bias,
        "performance": performance,
    }
    output_path = Path(args.output).expanduser()
    _write_json(output_path, payload)
    print(
        json.dumps(
            {
                "status": "ok",
                "query_count": len(query_bias),
                "top_bias_query": performance[0]["query"] if performance else "",
                "output": str(output_path),
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
