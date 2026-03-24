#!/usr/bin/env python3

from __future__ import annotations

import json
from pathlib import Path
from typing import Dict, List

from paths import CHALLENGES_ROOT


def _write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def classify_challenge(task_id: str, blockers: List[str], state: Dict[str, object]) -> Dict[str, object]:
    text = " | ".join([str(item) for item in blockers]).lower()
    challenge_type = "none"
    recommended_route = "continue"
    if any(token in text for token in ["captcha", "turnstile", "challenge page", "verify you are human"]):
        challenge_type = "human_verification_required"
        recommended_route = "human_checkpoint"
    elif any(token in text for token in ["403", "forbidden", "access denied"]):
        challenge_type = "waf_or_access_block"
        recommended_route = "official_source_or_authorized_session"
    elif any(token in text for token in ["429", "rate limit", "too many requests"]):
        challenge_type = "rate_limit"
        recommended_route = "slow_down_and_switch_to_structured_source"
    elif any(token in text for token in ["login", "sign in", "authentication", "authorized session"]):
        challenge_type = "authorization_required"
        recommended_route = "authorized_session"
    elif any(token in text for token in ["loading", "client rendered", "javascript", "render", "dynamic content"]):
        challenge_type = "rendering_barrier"
        recommended_route = "browser_render"
    payload = {
        "task_id": task_id,
        "challenge_type": challenge_type,
        "recommended_route": recommended_route,
        "blockers": blockers,
        "status": state.get("status", ""),
        "current_stage": state.get("current_stage", ""),
    }
    _write_json(CHALLENGES_ROOT / f"{task_id}.json", payload)
    return payload


def main() -> int:
    import argparse

    parser = argparse.ArgumentParser(description="Classify web-access challenges and recommend a compliant route")
    parser.add_argument("--task-id", required=True)
    parser.add_argument("--blockers-json", required=True)
    parser.add_argument("--state-json", required=True)
    args = parser.parse_args()
    print(json.dumps(classify_challenge(args.task_id, json.loads(args.blockers_json), json.loads(args.state_json)), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
