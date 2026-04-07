#!/usr/bin/env python3

from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path


def _read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _buying_context(item: dict) -> str:
    signals = item.get("top_signals", [])
    if any("partner" in signal or "dealer" in signal or "distribution" in signal for signal in signals):
        return "partnership_fit"
    if any("quote" in signal or "project" in signal or "install" in signal for signal in signals):
        return "active_project"
    if item.get("intent_score", 0) >= 20:
        return "exploratory"
    return "weak_signal_observation"


def main() -> int:
    parser = argparse.ArgumentParser(description="Build a strategy brief scaffold from a project config.")
    parser.add_argument("--config", required=True)
    parser.add_argument("--prospects", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()

    config = _read_json(Path(args.config).expanduser())
    prospect_records = _read_json(Path(args.prospects).expanduser()).get("items", [])
    tier_counts = Counter(item.get("score_tier", "unknown") for item in prospect_records)
    channel_ready_counts = Counter(item.get("reachability_status", "unknown") for item in prospect_records)
    account_type_counts = Counter(item.get("account_type", "unknown") for item in prospect_records)
    buying_context_counts = Counter(_buying_context(item) for item in prospect_records)
    top_accounts = sorted(prospect_records, key=lambda item: item.get("total_score", 0.0), reverse=True)[:5]
    brief = {
        "project_id": config.get("project", {}).get("id", ""),
        "business_goal": config.get("project", {}).get("business_goal", ""),
        "conversion_target": config.get("project", {}).get("conversion_target", ""),
        "segmentation_axes": config.get("marketing_strategy_engine", {}).get("segmentation_axes", []),
        "priority_channels": config.get("channels", {}).get("priority", []),
        "human_review_required_for": config.get("marketing_strategy_engine", {}).get("require_human_review_for", []),
        "prospect_summary": {
            "total": len(prospect_records),
            "score_tiers": dict(tier_counts),
            "channel_readiness": dict(channel_ready_counts),
            "account_types": dict(account_type_counts),
            "buying_contexts": dict(buying_context_counts),
        },
        "segment_hypotheses": [
            {
                "segment_key": "design-led_accounts",
                "when_to_use": "designer-heavy or specification-led accounts dominate",
                "primary_value_frame": "curated selection, project support, easier specification flow",
            },
            {
                "segment_key": "execution-led_accounts",
                "when_to_use": "contractor / builder / ops accounts dominate",
                "primary_value_frame": "quote efficiency, repeat ordering, install workflow support",
            },
            {
                "segment_key": "channel_accounts",
                "when_to_use": "distributor / dealer / showroom fit is strong",
                "primary_value_frame": "partner upside, assortment fit, regional channel growth",
            },
        ],
        "top_accounts": [
            {
                "account_id": item.get("account_id"),
                "company_name": item.get("company_name"),
                "score_tier": item.get("score_tier"),
                "total_score": item.get("total_score"),
                "recommended_channel_hint": item.get("reachability_status"),
                "buying_context_hint": _buying_context(item),
            }
            for item in top_accounts
        ],
        "status": "draft",
    }
    out = Path(args.output).expanduser()
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(brief, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"output": str(out), "status": "written"}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
