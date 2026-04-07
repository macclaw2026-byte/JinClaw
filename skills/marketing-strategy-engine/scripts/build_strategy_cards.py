#!/usr/bin/env python3

from __future__ import annotations

import argparse
import json
from pathlib import Path


def _read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Build account strategy cards from strategy tasks and prospect records.")
    parser.add_argument("--prospects", required=True)
    parser.add_argument("--strategy-tasks", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()

    prospects = _read_json(Path(args.prospects).expanduser()).get("items", [])
    tasks = _read_json(Path(args.strategy_tasks).expanduser()).get("items", [])
    prospect_by_account = {item.get("account_id"): item for item in prospects}

    cards = []
    for task in tasks:
        prospect = prospect_by_account.get(task.get("account_id"), {})
        cards.append(
            {
                "strategy_id": task.get("strategy_id"),
                "account_id": task.get("account_id"),
                "company_name": prospect.get("company_name"),
                "score_tier": prospect.get("score_tier"),
                "total_score": prospect.get("total_score"),
                "account_type": task.get("account_type"),
                "persona_type": task.get("persona_type"),
                "buying_context": task.get("buying_context"),
                "channel_readiness": task.get("channel_readiness"),
                "path_type": task.get("path_type"),
                "channel_recommendation": task.get("channel"),
                "primary_angle_family": task.get("primary_angle_family"),
                "primary_angle": task.get("primary_angle"),
                "support_angle": task.get("support_angle"),
                "anti_angle": task.get("anti_angle"),
                "value_map": task.get("value_map", []),
                "proof_map": task.get("proof_map", []),
                "cta_pair": {
                    "primary": task.get("CTA"),
                    "fallback": task.get("fallback_CTA"),
                },
                "followup_plan": task.get("followup_plan", []),
                "approval_required": task.get("approval_required", False),
                "strategy_hypothesis": task.get("strategy_hypothesis", {}),
                "strategy_weight_context": task.get("strategy_weight_context", {}),
            }
        )

    out = Path(args.output).expanduser()
    _write_json(out, {"items": cards})
    print(json.dumps({"output": str(out), "count": len(cards)}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
