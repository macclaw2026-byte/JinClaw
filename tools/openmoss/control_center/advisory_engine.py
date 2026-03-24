#!/usr/bin/env python3

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict

from paths import ADVISORIES_ROOT


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _write_json(path: Path, payload) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def build_advisory(task_id: str, mission: Dict[str, object], state: Dict[str, object]) -> Dict[str, object]:
    selected_plan = mission.get("selected_plan", {})
    intent = mission.get("intent", {})
    approval = mission.get("approval", {})
    judgment = mission.get("proposal_judgment", {})
    selected_score = judgment.get("final_selected_score", judgment.get("selected_score", {}))
    reselection = mission.get("reselection", {})
    adoption_flow = mission.get("adoption_flow", {})
    fetch_route = mission.get("fetch_route", {})
    challenge = mission.get("challenge", {})
    authorized_session = mission.get("authorized_session", {})
    capability_clone = mission.get("capability_clone", {})
    advisories = []
    if approval.get("pending"):
        advisories.append("High-risk external actions remain pending approval; continue public-read research first.")
    if selected_plan.get("plan_id") == "audited_external_extension":
        advisories.append("This external path is preferred only because it is currently the safest high-efficiency option after review.")
        advisories.append("Document rollback and replacement steps before adopting the third-party tool.")
    if selected_plan.get("plan_id") == "in_house_capability_rebuild":
        advisories.append("Learn from the external technique, but rebuild the useful capability locally instead of trusting the external artifact.")
    if intent.get("requires_external_information"):
        advisories.append("Use official docs and source repositories before weaker public commentary.")
    if reselection.get("switched"):
        advisories.append("The final plan was reselected because it offered a safer high-efficiency outcome than the original choice.")
    if adoption_flow.get("rollback_ready"):
        advisories.append("Keep rollback evidence current before broadening adoption of the chosen capability path.")
    if fetch_route.get("current_route"):
        advisories.append(f"Current acquisition route: {fetch_route.get('current_route')}. Prefer route escalation over brute-force retries.")
    if challenge.get("challenge_type") not in {None, "", "none"}:
        advisories.append(f"Detected challenge type: {challenge.get('challenge_type')}; follow the compliant route instead of bypassing it.")
    if authorized_session.get("needs_authorized_session"):
        advisories.append("Use an isolated reviewed authorized session only after approval.")
    if capability_clone.get("promotion", {}).get("promoted"):
        advisories.append("A local cloned capability has been promoted and can participate in future routing.")
    payload = {
        "task_id": task_id,
        "generated_at": _utc_now_iso(),
        "status": state.get("status", ""),
        "current_stage": state.get("current_stage", ""),
        "insights": [
            f"Selected plan: {selected_plan.get('label', '')}",
            f"Security risk posture: {mission.get('approval', {}).get('overall_risk', 'unknown')}",
            f"Efficiency score: {selected_score.get('efficiency_score', 'n/a')}",
            f"Risk score: {selected_score.get('risk_score', 'n/a')}",
            f"Adoption mode: {adoption_flow.get('adoption_mode', 'n/a')}",
            f"Fetch route: {fetch_route.get('current_route', 'n/a')}",
            f"Challenge type: {challenge.get('challenge_type', 'none')}",
            f"Capability clone: {capability_clone.get('promotion', {}).get('status', 'n/a')}",
        ],
        "recommendations": advisories,
    }
    _write_json(ADVISORIES_ROOT / f"{task_id}.json", payload)
    return payload


def main() -> int:
    import argparse

    parser = argparse.ArgumentParser(description="Generate task-level advisory output")
    parser.add_argument("--task-id", required=True)
    parser.add_argument("--mission-json", required=True)
    parser.add_argument("--state-json", required=True)
    args = parser.parse_args()
    print(json.dumps(build_advisory(args.task_id, json.loads(args.mission_json), json.loads(args.state_json)), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
