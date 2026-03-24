#!/usr/bin/env python3

from __future__ import annotations

import json
from pathlib import Path
from typing import Dict

from paths import AUTHORIZED_SESSIONS_ROOT


def _write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def build_authorized_session_plan(task_id: str, intent: Dict[str, object], challenge: Dict[str, object]) -> Dict[str, object]:
    needs_authorized_session = challenge.get("recommended_route") == "authorized_session" or challenge.get("challenge_type") in {
        "authorization_required",
        "waf_or_access_block",
    }
    payload = {
        "task_id": task_id,
        "needs_authorized_session": needs_authorized_session,
        "approval_required": needs_authorized_session,
        "session_mode": "isolated_reviewed_context" if needs_authorized_session else "not_required",
        "rules": [
            "Never reuse broad browser auth state without explicit approval.",
            "Use an isolated reviewed context for any authorized session.",
            "Do not persist credentials into general workspace outputs.",
        ],
        "triggers": {
            "challenge_type": challenge.get("challenge_type", "none"),
            "needs_browser": bool(intent.get("needs_browser")),
        },
    }
    _write_json(AUTHORIZED_SESSIONS_ROOT / f"{task_id}.json", payload)
    return payload


def main() -> int:
    import argparse

    parser = argparse.ArgumentParser(description="Build an authorized-session handling plan")
    parser.add_argument("--task-id", required=True)
    parser.add_argument("--intent-json", required=True)
    parser.add_argument("--challenge-json", required=True)
    args = parser.parse_args()
    print(
        json.dumps(
            build_authorized_session_plan(args.task_id, json.loads(args.intent_json), json.loads(args.challenge_json)),
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
