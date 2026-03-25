#!/usr/bin/env python3

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Dict, List

AUTONOMY_DIR = Path("/Users/mac_claw/.openclaw/workspace/tools/openmoss/autonomy")
if str(AUTONOMY_DIR) not in sys.path:
    sys.path.insert(0, str(AUTONOMY_DIR))

from browser_task_signals import collect_browser_task_signals
from challenge_classifier import classify_challenge
from recovery_engine import classify_failure


def solve_problem(task_id: str, blockers: List[str], arbitration: Dict[str, object], approval: Dict[str, object]) -> Dict[str, object]:
    blocker_text = " | ".join(blockers).strip()
    browser_signals = collect_browser_task_signals(task_id)
    challenge = classify_challenge(task_id, blockers, {"status": "recovering" if blockers else "planning", "current_stage": "execute" if blockers else ""})
    if approval.get("pending"):
        root_cause = "approval_pending"
    elif browser_signals.get("requirements_evaluation", {}).get("ok") is True:
        root_cause = "business_requirements_satisfied"
    elif browser_signals.get("diagnosis") not in {"", "none"}:
        root_cause = str(browser_signals.get("diagnosis"))
    elif challenge.get("challenge_type") != "none":
        root_cause = challenge.get("challenge_type")
    elif not arbitration.get("necessity_proof", {}).get("required", True) and "stay_on_local_plan_until_necessity_is_proven" in arbitration.get("next_best_actions", []):
        root_cause = "necessity_not_proven"
    else:
        root_cause = classify_failure(blocker_text) if blocker_text else "planning_gap"
    options = []
    if approval.get("pending"):
        options.append("wait_for_or_request_approval")
    if root_cause == "necessity_not_proven":
        options.extend(["prove_necessity_before_switching", "continue_current_plan"])
    if root_cause in {"missing_dependency", "transient_error"}:
        options.append("repair_and_retry")
    if root_cause in {"browser_control_channel_lost", "stale_target_id"}:
        options.append("reacquire_browser_channel")
    if root_cause == "draft_listings_remaining":
        options.append("process_next_draft_listing")
    if root_cause in {"general_failure", "planning_gap"}:
        options.append("research_alternative_solution")
    if root_cause == "browser_channel_reacquired":
        options.append("continue_current_plan")
    if root_cause == "upload_control_path_invalid":
        options.extend(["needs_network_request_level_debugging", "investigate_frontend_binding_and_network_request_chain"])
    if root_cause == "frontend_binding_not_triggered":
        options.extend(["investigate_frontend_binding_and_network_request_chain", "needs_network_request_level_debugging"])
    if root_cause == "browser_form_validation_blocking_submit":
        options.extend(["normalize_invalid_numeric_fields_then_resubmit", "repair_form_validation_then_retry_submit"])
    if root_cause == "upload_saved_successfully":
        options.append("confirm_business_outcome_and_finalize")
    if root_cause == "business_requirements_satisfied":
        options.append("confirm_business_outcome_and_finalize")
    if root_cause == "needs_network_request_level_debugging":
        options.append("needs_network_request_level_debugging")
    if root_cause == "auth_or_config_error":
        options.append("request_authorized_configuration")
    if root_cause == "authorization_required":
        options.append("request_authorized_session")
    if root_cause == "human_verification_required":
        options.append("await_human_verification_checkpoint")
    if root_cause in {"rate_limit", "waf_or_access_block", "rendering_barrier"}:
        options.append(challenge.get("recommended_route", "switch_to_safer_route"))
    if root_cause == "permission_error":
        options.append("apply_permission_recovery")
    recommendation = options[0] if options else "continue_current_plan"
    return {
        "task_id": task_id,
        "root_cause": root_cause,
        "blockers": blockers,
        "browser_signals": browser_signals,
        "challenge": challenge,
        "options": options,
        "recommended_action": recommendation,
        "arbitration_hint": arbitration.get("next_best_actions", []),
    }


def main() -> int:
    import argparse

    parser = argparse.ArgumentParser(description="Generate problem-solving options for a blocked mission")
    parser.add_argument("--task-id", required=True)
    parser.add_argument("--blockers-json", required=True)
    parser.add_argument("--arbitration-json", required=True)
    parser.add_argument("--approval-json", required=True)
    args = parser.parse_args()
    print(
        json.dumps(
            solve_problem(args.task_id, json.loads(args.blockers_json), json.loads(args.arbitration_json), json.loads(args.approval_json)),
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
