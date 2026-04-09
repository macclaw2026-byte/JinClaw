#!/usr/bin/env python3

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path("/Users/mac_claw/.openclaw/workspace/projects/neosgo-marketing-suite")
STATE_PATH = PROJECT_ROOT / "runtime" / "outreach" / "state.json"
EVENTS_PATH = PROJECT_ROOT / "runtime" / "outreach" / "events.jsonl"
REVIEW_TEMPLATE_PATH = PROJECT_ROOT / "runtime" / "outreach" / "review-decisions.template.json"
REPORT_PATH = PROJECT_ROOT / "runtime" / "outreach" / "review-decisions.last-run.json"


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _read_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _append_event(event: dict[str, Any]) -> None:
    EVENTS_PATH.parent.mkdir(parents=True, exist_ok=True)
    with EVENTS_PATH.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(event, ensure_ascii=False) + "\n")


def _apply_decision(target: dict[str, Any], decision: str, notes: str) -> dict[str, Any]:
    updated = dict(target)
    updated["review_resolution"] = decision
    updated["review_notes"] = notes
    updated["reviewed_at"] = _now_iso()
    if decision == "form_submitted_confirmed":
        updated["status"] = "contact_form_submitted"
        updated["force_channel"] = ""
    elif decision == "ready_for_form_retry":
        updated["status"] = "ready_for_form_retry"
        updated["force_channel"] = "contact_form"
    elif decision == "ready_for_email":
        updated["status"] = "ready_for_email"
        updated["force_channel"] = "email"
    elif decision == "review_hold":
        updated["status"] = "review_hold"
        updated["force_channel"] = ""
    elif decision == "stopped":
        updated["status"] = "stopped"
        updated["force_channel"] = ""
    else:
        raise ValueError(f"unsupported_decision:{decision}")
    updated["updated_at"] = _now_iso()
    return updated


def main() -> int:
    parser = argparse.ArgumentParser(description="Apply manual outreach review decisions back into runtime state.")
    parser.add_argument("--template", default=str(REVIEW_TEMPLATE_PATH))
    args = parser.parse_args()

    state = _read_json(STATE_PATH, {"targets": {}})
    targets = dict(state.get("targets") or {})
    template = _read_json(Path(args.template), {"items": []})

    supported = {"form_submitted_confirmed", "ready_for_form_retry", "ready_for_email", "review_hold", "stopped"}
    applied = []
    skipped = []
    for item in list(template.get("items") or []):
        decision = str(item.get("operator_decision") or "").strip()
        if not decision:
            continue
        review_key = str(item.get("review_key") or "").strip()
        if review_key not in targets:
            skipped.append({"review_key": review_key, "reason": "missing_target"})
            continue
        if decision not in supported:
            skipped.append({"review_key": review_key, "reason": f"unsupported_decision:{decision}"})
            continue
        notes = str(item.get("operator_notes") or "").strip()
        targets[review_key] = _apply_decision(targets[review_key], decision, notes)
        event = {
            "type": "review_decision_applied",
            "at": _now_iso(),
            "key": review_key,
            "company_name": targets[review_key].get("company_name"),
            "decision": decision,
            "notes": notes,
        }
        _append_event(event)
        applied.append(event)

    state["targets"] = targets
    _write_json(STATE_PATH, state)
    report = {
        "generated_at": _now_iso(),
        "applied_count": len(applied),
        "skipped_count": len(skipped),
        "applied": applied,
        "skipped": skipped,
    }
    _write_json(REPORT_PATH, report)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
