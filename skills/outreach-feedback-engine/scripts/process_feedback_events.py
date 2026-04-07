#!/usr/bin/env python3

from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path


def _read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _classify(item: dict) -> str:
    explicit = (item.get("classification") or "").strip()
    if explicit:
        return explicit
    outcome = (item.get("outcome_type") or "").strip().lower()
    mapping = {
        "reply": "positive_interest",
        "positive_reply": "positive_interest",
        "referral": "referral",
        "question": "neutral_question",
        "not_now": "not_now",
        "not_fit": "not_fit",
        "unsubscribe": "unsubscribe",
        "invalid": "invalid_contact",
        "hard_bounce": "hard_bounce",
        "bounce": "hard_bounce",
        "auto_reply": "auto_reply",
        "complaint": "spam_complaint_risk",
        "complaint_risk": "spam_complaint_risk",
    }
    return mapping.get(outcome, "unclassified")


def _next_action(classification: str) -> tuple[str, bool]:
    table = {
        "positive_interest": ("human_follow_up", True),
        "referral": ("create_referral_candidate", True),
        "neutral_question": ("answer_question", True),
        "not_now": ("recycle_later", False),
        "not_fit": ("downscore_or_close", False),
        "unsubscribe": ("suppress_forever", False),
        "invalid_contact": ("mark_invalid_and_suppress", False),
        "hard_bounce": ("mark_invalid_and_suppress", False),
        "auto_reply": ("wait_and_retry_later", False),
        "spam_complaint_risk": ("escalate_and_stop", True),
    }
    return table.get(classification, ("manual_triage", True))


def _suppression_action(classification: str) -> str | None:
    mapping = {
        "unsubscribe": "suppress",
        "invalid_contact": "suppress",
        "hard_bounce": "suppress",
        "spam_complaint_risk": "suppress_and_escalate",
    }
    return mapping.get(classification)


def main() -> int:
    parser = argparse.ArgumentParser(description="Process outreach feedback events into suppression, reports, and patches.")
    parser.add_argument("--feedback-events", required=True)
    parser.add_argument("--output-dir", required=True)
    args = parser.parse_args()

    events = _read_json(Path(args.feedback_events).expanduser()).get("items", [])
    output_dir = Path(args.output_dir).expanduser()

    classified = []
    suppression_items = []
    feedback_patches = []
    counts = Counter()

    for index, item in enumerate(events, start=1):
        classification = _classify(item)
        next_action, human_review_required = _next_action(classification)
        counts[classification] += 1
        classified_item = {
            "feedback_id": item.get("feedback_id") or f"feedback-{index}",
            "task_id": item.get("task_id", ""),
            "account_id": item.get("account_id", ""),
            "contact_id": item.get("contact_id"),
            "channel": item.get("channel", ""),
            "classification": classification,
            "confidence": item.get("confidence", 0.75 if classification != "unclassified" else 0.4),
            "evidence_excerpt": item.get("evidence_excerpt") or item.get("evidence") or "",
            "next_action": next_action,
            "human_review_required": human_review_required,
            "outcome_type": item.get("outcome_type", ""),
        }
        classified.append(classified_item)

        suppression_action = _suppression_action(classification)
        if suppression_action:
            suppression_items.append(
                {
                    "suppression_id": f"suppression-{index}",
                    "task_id": classified_item["task_id"],
                    "account_id": classified_item["account_id"],
                    "contact_id": classified_item["contact_id"],
                    "channel": classified_item["channel"],
                    "reason": classification,
                    "action": suppression_action,
                }
            )

        data_patch = None
        strategy_patch = None
        if classification in {"invalid_contact", "hard_bounce"}:
            data_patch = {"mark_reachability": "invalid", "decrease_source_confidence": True}
            strategy_patch = {"channel_penalty": classified_item["channel"], "avoid_same_endpoint": True}
        elif classification == "unsubscribe":
            data_patch = {"lifecycle_status": "suppressed"}
            strategy_patch = {"stop_future_outreach": True}
        elif classification == "not_fit":
            strategy_patch = {"downrank_angle_family": True}
        elif classification == "positive_interest":
            strategy_patch = {"promote_angle_family": True, "promote_channel": classified_item["channel"]}

        feedback_patches.append(
            {
                "feedback_id": classified_item["feedback_id"],
                "account_id": classified_item["account_id"],
                "task_id": classified_item["task_id"],
                "classification": classification,
                "data_patch": data_patch,
                "strategy_patch": strategy_patch,
            }
        )

    daily_report = {
        "total_events": len(events),
        "classification_counts": dict(counts),
        "suppression_count": len(suppression_items),
        "human_review_count": len([item for item in classified if item["human_review_required"]]),
        "top_positive_segments": [],
    }
    weekly_report = {
        "total_events": len(events),
        "segment_conversion": {},
        "channel_win_rate": {},
        "strategy_win_rate": {},
        "data_quality_drift": {
            "invalid_contact_count": counts.get("invalid_contact", 0) + counts.get("hard_bounce", 0),
            "unsubscribe_count": counts.get("unsubscribe", 0),
        },
    }
    anomaly_report = {
        "has_anomaly": any(
            counts[key] > 0 for key in ["spam_complaint_risk", "hard_bounce", "invalid_contact", "unsubscribe"]
        ),
        "signals": {
            "spam_complaint_risk": counts.get("spam_complaint_risk", 0),
            "hard_bounce": counts.get("hard_bounce", 0),
            "invalid_contact": counts.get("invalid_contact", 0),
            "unsubscribe": counts.get("unsubscribe", 0),
        },
    }
    approval_queue = {
        "items": [
            {
                "feedback_id": item["feedback_id"],
                "task_id": item["task_id"],
                "account_id": item["account_id"],
                "classification": item["classification"],
                "next_action": item["next_action"],
            }
            for item in classified
            if item["human_review_required"]
        ]
    }

    _write_json(output_dir / "classified-feedback.json", {"items": classified})
    _write_json(output_dir / "suppression-registry.json", {"items": suppression_items})
    _write_json(output_dir / "feedback-patches.json", {"items": feedback_patches})
    _write_json(output_dir / "daily-report.json", daily_report)
    _write_json(output_dir / "weekly-report.json", weekly_report)
    _write_json(output_dir / "anomaly-report.json", anomaly_report)
    _write_json(output_dir / "approval-queue.json", approval_queue)

    print(
        json.dumps(
            {
                "status": "ok",
                "event_count": len(events),
                "suppression_count": len(suppression_items),
                "human_review_count": len([item for item in classified if item["human_review_required"]]),
                "classified_feedback_path": str(output_dir / "classified-feedback.json"),
                "suppression_registry_path": str(output_dir / "suppression-registry.json"),
                "feedback_patches_path": str(output_dir / "feedback-patches.json"),
                "daily_report_path": str(output_dir / "daily-report.json"),
                "weekly_report_path": str(output_dir / "weekly-report.json"),
                "anomaly_report_path": str(output_dir / "anomaly-report.json"),
                "approval_queue_path": str(output_dir / "approval-queue.json"),
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
