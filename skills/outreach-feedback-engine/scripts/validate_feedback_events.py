#!/usr/bin/env python3

from __future__ import annotations

import argparse
import json
from pathlib import Path


ALLOWED_CLASSIFICATIONS = {
    "positive_interest",
    "referral",
    "neutral_question",
    "not_now",
    "not_fit",
    "unsubscribe",
    "invalid_contact",
    "hard_bounce",
    "auto_reply",
    "spam_complaint_risk",
}


def _read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _is_completed(item: dict) -> bool:
    return (item.get("template_status") or "").strip() != "awaiting_operator_input"


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate completed feedback template rows before merge.")
    parser.add_argument("--source", required=True)
    parser.add_argument("--output")
    args = parser.parse_args()

    source_path = Path(args.source).expanduser()
    payload = _read_json(source_path)
    items = payload.get("items", [])
    completed_items = [item for item in items if _is_completed(item)]

    errors: list[dict] = []
    warnings: list[dict] = []
    completed_count = 0

    for index, item in enumerate(items, start=1):
        if not _is_completed(item):
            continue
        completed_count += 1
        feedback_id = (item.get("feedback_id") or f"row-{index}").strip()
        classification = (item.get("classification") or "").strip()
        outcome_type = (item.get("outcome_type") or "").strip()
        channel = (item.get("channel") or "").strip()
        task_id = (item.get("task_id") or "").strip()
        account_id = (item.get("account_id") or "").strip()
        captured_at = (item.get("captured_at") or "").strip()
        evidence = (item.get("evidence") or item.get("evidence_excerpt") or "").strip()

        missing = []
        if not task_id:
            missing.append("task_id")
        if not account_id:
            missing.append("account_id")
        if not channel:
            missing.append("channel")
        if not outcome_type:
            missing.append("outcome_type")
        if not classification:
            missing.append("classification")
        if not captured_at:
            missing.append("captured_at")
        if missing:
            errors.append({"feedback_id": feedback_id, "type": "missing_required_fields", "fields": missing})
            continue

        if classification not in ALLOWED_CLASSIFICATIONS:
            errors.append(
                {
                    "feedback_id": feedback_id,
                    "type": "invalid_classification",
                    "classification": classification,
                }
            )

        if classification in {"positive_interest", "referral", "neutral_question", "spam_complaint_risk"} and not evidence:
            errors.append(
                {
                    "feedback_id": feedback_id,
                    "type": "missing_evidence",
                    "classification": classification,
                }
            )

        if classification in {"invalid_contact", "hard_bounce", "unsubscribe"} and not evidence:
            warnings.append(
                {
                    "feedback_id": feedback_id,
                    "type": "suppression_without_evidence_excerpt",
                    "classification": classification,
                }
            )

    result = {
        "status": "ok" if not errors else "blocked",
        "source": str(source_path),
        "item_count": len(items),
        "completed_count": completed_count,
        "pending_count": len(items) - completed_count,
        "error_count": len(errors),
        "warning_count": len(warnings),
        "errors": errors,
        "warnings": warnings,
    }

    if args.output:
        _write_json(Path(args.output).expanduser(), result)

    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if not errors else 1


if __name__ == "__main__":
    raise SystemExit(main())
