#!/usr/bin/env python3

from __future__ import annotations

import json
from pathlib import Path
from typing import Dict, List

from paths import FETCH_ROUTES_ROOT


def _write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _route_ladder(intent: Dict[str, object], selected_plan: Dict[str, object], domain_profile: Dict[str, object], challenge: Dict[str, object]) -> List[str]:
    ladder = list(domain_profile.get("default_fetch_ladder", [])) or [
        "official_api",
        "structured_public_endpoint",
        "static_fetch",
        "crawl4ai",
        "browser_render",
        "authorized_session",
        "human_checkpoint",
    ]
    if challenge.get("recommended_route") == "browser_render":
        return ["browser_render", "authorized_session", "human_checkpoint"]
    if challenge.get("recommended_route") == "official_source_or_authorized_session":
        return ["official_api", "structured_public_endpoint", "authorized_session", "human_checkpoint"]
    if challenge.get("recommended_route") == "slow_down_and_switch_to_structured_source":
        return ["official_api", "structured_public_endpoint", "static_fetch", "browser_render"]
    if challenge.get("recommended_route") == "authorized_session":
        return ["authorized_session", "human_checkpoint"]
    if challenge.get("recommended_route") == "human_checkpoint":
        return ["human_checkpoint"]
    if selected_plan.get("plan_id") == "audited_external_extension":
        return ["official_api", "structured_public_endpoint", "static_fetch", "crawl4ai", "browser_render", "authorized_session", "human_checkpoint"]
    return ladder


def build_fetch_route(task_id: str, intent: Dict[str, object], selected_plan: Dict[str, object], domain_profile: Dict[str, object], challenge: Dict[str, object]) -> Dict[str, object]:
    ladder = _route_ladder(intent, selected_plan, domain_profile, challenge)
    current = ladder[0] if ladder else "monitor"
    payload = {
        "task_id": task_id,
        "current_route": current,
        "route_ladder": ladder,
        "official_first": True,
        "browser_last_before_authorized": True,
        "challenge_awareness": challenge,
        "strategy": {
            "api_first": True,
            "static_fetch_before_browser": True,
            "browser_only_when_needed": True,
            "authorized_session_requires_review": True,
            "never_bypass_verification": True,
        },
    }
    _write_json(FETCH_ROUTES_ROOT / f"{task_id}.json", payload)
    return payload


def main() -> int:
    import argparse

    parser = argparse.ArgumentParser(description="Build an adaptive fetch route for a task")
    parser.add_argument("--task-id", required=True)
    parser.add_argument("--intent-json", required=True)
    parser.add_argument("--plan-json", required=True)
    parser.add_argument("--domain-profile-json", required=True)
    parser.add_argument("--challenge-json", required=True)
    args = parser.parse_args()
    print(
        json.dumps(
            build_fetch_route(
                args.task_id,
                json.loads(args.intent_json),
                json.loads(args.plan_json),
                json.loads(args.domain_profile_json),
                json.loads(args.challenge_json),
            ),
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
