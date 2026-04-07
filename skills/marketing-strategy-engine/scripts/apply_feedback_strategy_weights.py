#!/usr/bin/env python3

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path


def _read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _infer_angle_family(primary_angle: str) -> str:
    text = (primary_angle or "").lower()
    if "partner" in text or "channel" in text or "assortment" in text:
        return "partner_growth"
    if "design" in text or "curated" in text:
        return "design_fit"
    if "project" in text or "quote" in text or "ordering" in text:
        return "execution_fit"
    return "general_fit"


def _adjust(weights: dict, bucket: str, key: str, delta: float) -> None:
    section = weights.setdefault(bucket, {})
    section[key] = round(section.get(key, 0.0) + delta, 3)


CLASS_POLICY = {
    "positive_interest": {"channel": 1.25, "path": 0.75, "angle": 0.75},
    "referral": {"channel": 0.55, "path": 0.35, "angle": 0.2},
    "neutral_question": {"channel": 0.35, "path": 0.25, "angle": 0.1},
    "not_now": {"channel": -0.15, "path": -0.1, "angle": -0.05},
    "not_fit": {"channel": -0.35, "path": -0.25, "angle": -0.6},
    "invalid_contact": {"channel": -1.4, "path": 0.0, "angle": -0.4},
    "hard_bounce": {"channel": -1.4, "path": 0.0, "angle": -0.4},
    "unsubscribe": {"channel": -1.4, "path": -0.1, "angle": -0.4},
    "spam_complaint_risk": {"channel": -3.0, "path": -1.2, "angle": -0.8},
    "auto_reply": {"channel": -0.05, "path": 0.0, "angle": 0.0},
}


def main() -> int:
    parser = argparse.ArgumentParser(description="Apply feedback patches into strategy weight biases.")
    parser.add_argument("--feedback-patches", required=True)
    parser.add_argument("--last-cycle")
    parser.add_argument("--output", required=True)
    args = parser.parse_args()

    patches = _read_json(Path(args.feedback_patches).expanduser()).get("items", [])
    output_path = Path(args.output).expanduser()
    existing = _read_json(output_path) if output_path.exists() else {}
    weights = {
        "channel_bias": existing.get("channel_bias", {}),
        "path_bias": existing.get("path_bias", {}),
        "angle_family_bias": existing.get("angle_family_bias", {}),
        "history": existing.get("history", []),
    }

    task_lookup = {}
    if args.last_cycle:
        last_cycle_path = Path(args.last_cycle).expanduser()
        if last_cycle_path.exists():
            cycle = _read_json(last_cycle_path)
            strategy_tasks_path = cycle.get("artifacts", {}).get("strategy_tasks_path")
            if strategy_tasks_path and Path(strategy_tasks_path).exists():
                task_items = _read_json(Path(strategy_tasks_path)).get("items", [])
                task_lookup = {item.get("outreach_task_id"): item for item in task_items}

    applied = []
    for patch in patches:
        classification = patch.get("classification")
        task = task_lookup.get(patch.get("task_id"), {})
        channel = task.get("channel")
        path_type = task.get("path_type")
        angle_family = task.get("primary_angle_family") or _infer_angle_family(task.get("primary_angle", ""))

        policy = CLASS_POLICY.get(classification, {})
        if channel and policy.get("channel"):
            _adjust(weights, "channel_bias", channel, float(policy["channel"]))
        if path_type and policy.get("path"):
            _adjust(weights, "path_bias", path_type, float(policy["path"]))
        if angle_family and policy.get("angle"):
            _adjust(weights, "angle_family_bias", angle_family, float(policy["angle"]))

        applied.append(
            {
                "feedback_id": patch.get("feedback_id"),
                "task_id": patch.get("task_id"),
                "classification": classification,
                "channel": channel,
                "path_type": path_type,
                "angle_family": angle_family,
            }
        )

    weights["last_updated_at"] = _utc_now()
    weights["history"] = (weights.get("history", []) + applied)[-100:]
    _write_json(output_path, weights)
    print(
        json.dumps(
            {
                "status": "ok",
                "applied_count": len(applied),
                "output": str(output_path),
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
