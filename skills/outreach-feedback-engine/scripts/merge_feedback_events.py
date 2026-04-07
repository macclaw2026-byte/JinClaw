#!/usr/bin/env python3

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path


def _read_json(path: Path) -> dict:
    if not path.exists():
        return {"items": []}
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _utc_marker() -> str:
    return datetime.now(timezone.utc).isoformat()


def _is_completed(item: dict) -> bool:
    if (item.get("template_status") or "").strip() == "awaiting_operator_input":
        return False
    required = [
        (item.get("feedback_id") or "").strip(),
        (item.get("task_id") or "").strip(),
        (item.get("account_id") or "").strip(),
        (item.get("outcome_type") or "").strip(),
        (item.get("channel") or "").strip(),
        (item.get("classification") or "").strip(),
    ]
    return all(required)


def _normalize_item(item: dict) -> dict:
    return {
        "feedback_id": (item.get("feedback_id") or "").strip(),
        "task_id": (item.get("task_id") or "").strip(),
        "account_id": (item.get("account_id") or "").strip(),
        "contact_id": item.get("contact_id"),
        "outcome_type": (item.get("outcome_type") or "").strip(),
        "channel": (item.get("channel") or "").strip(),
        "classification": (item.get("classification") or "").strip(),
        "evidence": item.get("evidence") or "",
        "evidence_excerpt": item.get("evidence_excerpt") or "",
        "operator_notes": item.get("operator_notes") or "",
        "captured_at": (item.get("captured_at") or _utc_marker()).strip(),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Merge completed operator feedback template rows into feedback-events.json.")
    parser.add_argument("--source", required=True)
    parser.add_argument("--target", required=True)
    parser.add_argument("--archive")
    args = parser.parse_args()

    source_path = Path(args.source).expanduser()
    target_path = Path(args.target).expanduser()
    archive_path = Path(args.archive).expanduser() if args.archive else None

    source_items = _read_json(source_path).get("items", [])
    target_items = _read_json(target_path).get("items", [])

    completed = [_normalize_item(item) for item in source_items if _is_completed(item)]
    existing_by_id = {str(item.get("feedback_id")): item for item in target_items}
    merged_count = 0
    for item in completed:
        existing_by_id[item["feedback_id"]] = item
        merged_count += 1

    merged_items = list(existing_by_id.values())
    _write_json(
        target_path,
        {
            "items": merged_items,
            "meta": {
                "updated_at": _utc_marker(),
                "source_path": str(source_path),
                "merged_count": merged_count,
            },
        },
    )

    if archive_path is not None:
        _write_json(
            archive_path,
            {
                "items": source_items,
                "meta": {
                    "archived_at": _utc_marker(),
                    "source_path": str(source_path),
                },
            },
        )

    print(
        json.dumps(
            {
                "status": "ok",
                "source_count": len(source_items),
                "completed_count": len(completed),
                "target_total": len(merged_items),
                "output": str(target_path),
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
