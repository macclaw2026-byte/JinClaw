#!/usr/bin/env python3

from __future__ import annotations

import json
from pathlib import Path
from typing import Dict, List

from paths import RESELECTIONS_ROOT


def _write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _intent_affinity(intent: Dict[str, object], plan_id: str) -> float:
    goal = str(intent.get("goal", "")).lower()
    if plan_id == "audited_external_extension":
        if all(token in goal for token in ["install", "approved", "official", "rollback"]):
            return 16.0
        if any(token in goal for token in ["install", "approved dependency", "package", "use the safest and most efficient way"]):
            return 6.0
    if plan_id == "in_house_capability_rebuild":
        if any(token in goal for token in ["learn its strengths", "build a local replacement", "rebuild", "local equivalent"]):
            return 5.0
    return 0.0


def reselect_plan(
    task_id: str,
    intent: Dict[str, object],
    candidate_plans: List[Dict[str, object]],
    proposal_judgment: Dict[str, object],
    tool_scores: Dict[str, object],
) -> Dict[str, object]:
    by_plan = {str(plan.get("plan_id", "")): plan for plan in candidate_plans}
    proposal_scores = {str(item.get("plan_id", "")): item for item in proposal_judgment.get("scores", [])}
    tool_score_map = {str(item.get("plan_id", "")): item for item in tool_scores.get("scores", [])}

    ranked = []
    for plan_id, plan in by_plan.items():
        proposal = proposal_scores.get(plan_id, {})
        tool = tool_score_map.get(plan_id, {})
        objective = float(proposal.get("score", 0.0))
        objective += float(tool.get("efficiency_gain", 0.0)) * 1.5
        objective -= float(tool.get("risk_score", 0.0)) * 1.2
        if tool.get("rollback_ready"):
            objective += 1.5
        if tool.get("audit_ready"):
            objective += 1.5
        objective += _intent_affinity(intent, plan_id)
        if not tool.get("safe_enough", False):
            objective -= 100.0
        ranked.append(
            {
                "plan_id": plan_id,
                "objective_score": round(objective, 2),
                "proposal_score": proposal.get("score", 0.0),
                "efficiency_gain": tool.get("efficiency_gain", 0.0),
                "risk_score": tool.get("risk_score", 0.0),
                "safe_enough": bool(tool.get("safe_enough", False)),
            }
        )

    ranked = sorted(ranked, key=lambda item: (-float(item["objective_score"]), item["plan_id"]))
    selected = ranked[0] if ranked else {"plan_id": proposal_judgment.get("selected_plan", {}).get("plan_id", "")}
    final_plan = by_plan.get(str(selected.get("plan_id", "")), proposal_judgment.get("selected_plan", {}))
    original_plan_id = str(proposal_judgment.get("selected_plan", {}).get("plan_id", ""))
    switched = bool(original_plan_id and original_plan_id != str(final_plan.get("plan_id", "")))
    payload = {
        "task_id": task_id,
        "original_plan_id": original_plan_id,
        "final_plan_id": final_plan.get("plan_id", ""),
        "switched": switched,
        "switch_reason": "higher-efficiency safe option identified" if switched else "original plan remained the best safe option",
        "ranked_candidates": ranked,
        "final_selected_plan": final_plan,
    }
    _write_json(RESELECTIONS_ROOT / f"{task_id}.json", payload)
    return payload


def main() -> int:
    import argparse

    parser = argparse.ArgumentParser(description="Reselect the final plan using safety-first efficiency scoring")
    parser.add_argument("--task-id", required=True)
    parser.add_argument("--plans-json", required=True)
    parser.add_argument("--judgment-json", required=True)
    parser.add_argument("--tool-scores-json", required=True)
    args = parser.parse_args()
    print(
        json.dumps(
            reselect_plan(
                args.task_id,
                {},
                json.loads(args.plans_json),
                json.loads(args.judgment_json),
                json.loads(args.tool_scores_json),
            ),
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
