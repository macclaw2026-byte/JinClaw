#!/usr/bin/env python3

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path


SCRIPT_DIR = Path(__file__).resolve().parent
SUITE_ROOT = SCRIPT_DIR.parent
WORKSPACE_ROOT = Path("/Users/mac_claw/.openclaw/workspace")
PROSPECT_BOOTSTRAP = WORKSPACE_ROOT / "skills/prospect-data-engine/scripts/bootstrap_prospect_workspace.py"
PROSPECT_IMPORT = WORKSPACE_ROOT / "skills/prospect-data-engine/scripts/import_public_prospect_data.py"
PROSPECT_DISCOVERY = WORKSPACE_ROOT / "skills/prospect-data-engine/scripts/discover_public_accounts.py"
PROSPECT_SEARCH_DISCOVERY = WORKSPACE_ROOT / "skills/prospect-data-engine/scripts/expand_search_discovery.py"
GOOGLE_MAPS_DISCOVERY = WORKSPACE_ROOT / "skills/prospect-data-engine/scripts/discover_google_maps_places.py"
GOOGLE_MAPS_EMAIL_ENRICHMENT = WORKSPACE_ROOT / "skills/prospect-data-engine/scripts/enrich_google_maps_website_contacts.py"
GOOGLE_MAPS_CAPTURE_CYCLE = WORKSPACE_ROOT / "skills/prospect-data-engine/scripts/run_google_maps_capture_cycle.py"
DISCOVERY_RECIPES = WORKSPACE_ROOT / "skills/prospect-data-engine/scripts/build_discovery_recipe_library.py"
DISCOVERY_QUERY_WEIGHTS = WORKSPACE_ROOT / "skills/prospect-data-engine/scripts/apply_discovery_query_weights.py"
SOURCE_HEALTH_RETRY = WORKSPACE_ROOT / "skills/prospect-data-engine/scripts/update_source_health_retry.py"
DIRECTORY_DISCOVERY = WORKSPACE_ROOT / "skills/prospect-data-engine/scripts/discover_industry_directory_accounts.py"
GBP_DISCOVERY = WORKSPACE_ROOT / "skills/prospect-data-engine/scripts/discover_google_business_profiles.py"
LINKEDIN_DISCOVERY = WORKSPACE_ROOT / "skills/prospect-data-engine/scripts/discover_linkedin_company_pages.py"
STRATEGY_BRIEF = WORKSPACE_ROOT / "skills/marketing-strategy-engine/scripts/build_strategy_brief.py"
STRATEGY_WEIGHTS = WORKSPACE_ROOT / "skills/marketing-strategy-engine/scripts/apply_feedback_strategy_weights.py"
STRATEGY_TASKS = WORKSPACE_ROOT / "skills/marketing-strategy-engine/scripts/build_strategy_tasks.py"
STRATEGY_CARDS = WORKSPACE_ROOT / "skills/marketing-strategy-engine/scripts/build_strategy_cards.py"
EXECUTION_QUEUE = WORKSPACE_ROOT / "skills/outreach-feedback-engine/scripts/build_execution_queue.py"
FEEDBACK_PROCESSOR = WORKSPACE_ROOT / "skills/outreach-feedback-engine/scripts/process_feedback_events.py"
FIRST_OUTPUT_PACKET = WORKSPACE_ROOT / "skills/marketing-automation-suite/scripts/build_first_output_packet.py"


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _run_python(script: Path, *args: str) -> dict:
    completed = subprocess.run(
        [sys.executable, str(script), *args],
        capture_output=True,
        text=True,
        check=False,
    )
    stdout = completed.stdout.strip()
    payload = {}
    if stdout:
        try:
            payload = json.loads(stdout)
        except json.JSONDecodeError:
            payload = {"stdout": stdout}
    return {
        "ok": completed.returncode == 0,
        "returncode": completed.returncode,
        "stdout": stdout,
        "stderr": completed.stderr.strip(),
        "payload": payload,
        "script": str(script),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Run one unified marketing automation suite cycle.")
    parser.add_argument("--project-root", required=True)
    args = parser.parse_args()

    project_root = Path(args.project_root).expanduser().resolve()
    config_path = project_root / "config" / "project-config.json"
    runtime_state_path = project_root / "runtime" / "state.json"
    suite_runtime_root = project_root / "runtime" / "marketing-automation-suite"
    suite_output_root = project_root / "output" / "marketing-automation-suite"
    suite_reports_root = project_root / "reports" / "marketing-automation-suite"
    discovery_recipe_output = project_root / "output" / "prospect-data-engine" / "discovery-recipe-library.json"
    generated_queries_path = project_root / "data" / "discovery-queries.generated.json"

    config = _read_json(config_path)
    cycle_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")

    recipe_result = _run_python(
        DISCOVERY_RECIPES,
        "--config",
        str(config_path),
        "--manual-queries",
        str(project_root / "data" / "discovery-queries.json"),
        "--output",
        str(discovery_recipe_output),
        "--generated-queries",
        str(generated_queries_path),
    )

    strategy_ready_seed_path_existing = project_root / "output" / "prospect-data-engine" / "strategy-ready-seeds.json"
    prospect_records_path_existing = project_root / "output" / "prospect-data-engine" / "prospect-records.json"
    pre_query_weight_result = _run_python(
        DISCOVERY_QUERY_WEIGHTS,
        "--queries",
        str(generated_queries_path),
        "--strategy-ready-seeds",
        str(strategy_ready_seed_path_existing),
        "--feedback-events",
        str(project_root / "data" / "feedback-events.json"),
        "--prospects",
        str(prospect_records_path_existing),
        "--output",
        str(project_root / "runtime" / "prospect-data-engine" / "query-weights.json"),
    )

    search_discovery_result = _run_python(
        PROSPECT_SEARCH_DISCOVERY,
        "--project-root",
        str(project_root),
    )
    google_maps_capture_cycle_result = _run_python(
        GOOGLE_MAPS_CAPTURE_CYCLE,
        "--project-root",
        str(project_root),
    )
    google_maps_discovery_result = dict(
        (google_maps_capture_cycle_result.get("payload", {}) or {}).get("discovery") or {}
    ) or _run_python(
        GOOGLE_MAPS_DISCOVERY,
        "--project-root",
        str(project_root),
    )
    google_maps_email_enrichment_result = dict(
        (google_maps_capture_cycle_result.get("payload", {}) or {}).get("enrichment") or {}
    ) or _run_python(
        GOOGLE_MAPS_EMAIL_ENRICHMENT,
        "--project-root",
        str(project_root),
    )
    discovery_result = _run_python(
        PROSPECT_DISCOVERY,
        "--project-root",
        str(project_root),
    )
    directory_discovery_result = _run_python(
        DIRECTORY_DISCOVERY,
        "--project-root",
        str(project_root),
    )
    gbp_discovery_result = _run_python(
        GBP_DISCOVERY,
        "--project-root",
        str(project_root),
    )
    linkedin_discovery_result = _run_python(
        LINKEDIN_DISCOVERY,
        "--project-root",
        str(project_root),
    )

    import_result = _run_python(
        PROSPECT_IMPORT,
        "--project-root",
        str(project_root),
    )
    source_health_result = _run_python(
        SOURCE_HEALTH_RETRY,
        "--project-root",
        str(project_root),
    )

    merged_seed_path = Path(
        import_result.get("payload", {}).get("merged_seed_path", project_root / "data" / "prospect-seeds.json")
    )
    strategy_ready_seed_path = Path(
        import_result.get("payload", {}).get("strategy_ready_seed_path", merged_seed_path)
    )
    quality_gate_status = import_result.get("payload", {}).get("quality_gate_status", "unknown")
    allowed_for_strategy = import_result.get("payload", {}).get("allowed_for_strategy", True)
    review_queue_count = import_result.get("payload", {}).get("review_queue_count", 0)
    review_queue_path = import_result.get("payload", {}).get(
        "review_queue_path", str(project_root / "output" / "prospect-data-engine" / "review-queue.json")
    )

    bootstrap_result = _run_python(
        PROSPECT_BOOTSTRAP,
        "--project-root",
        str(project_root),
        "--config",
        str(config_path),
        "--seeds",
        str(strategy_ready_seed_path),
    )

    prospect_records_path = project_root / "output" / "prospect-data-engine" / "prospect-records.json"

    feedback_events_path = project_root / "data" / "feedback-events.json"
    feedback_output_dir = suite_output_root / cycle_id / "feedback"
    feedback_processing_result = _run_python(
        FEEDBACK_PROCESSOR,
        "--feedback-events",
        str(feedback_events_path),
        "--output-dir",
        str(feedback_output_dir),
    )
    suppression_registry_path = feedback_processing_result.get("payload", {}).get(
        "suppression_registry_path",
        str(feedback_output_dir / "suppression-registry.json"),
    )
    feedback_patches_path = feedback_processing_result.get("payload", {}).get(
        "feedback_patches_path",
        str(feedback_output_dir / "feedback-patches.json"),
    )
    approval_queue_path = feedback_processing_result.get("payload", {}).get(
        "approval_queue_path",
        str(feedback_output_dir / "approval-queue.json"),
    )
    strategy_weights_path = project_root / "runtime" / "marketing-strategy-engine" / "strategy-weights.json"
    last_cycle_path = suite_runtime_root / "last_cycle.json"
    strategy_weights_result = _run_python(
        STRATEGY_WEIGHTS,
        "--feedback-patches",
        str(feedback_patches_path),
        "--last-cycle",
        str(last_cycle_path),
        "--output",
        str(strategy_weights_path),
    )
    discovery_query_weight_result = _run_python(
        DISCOVERY_QUERY_WEIGHTS,
        "--queries",
        str(generated_queries_path),
        "--strategy-ready-seeds",
        str(strategy_ready_seed_path),
        "--feedback-events",
        str(feedback_events_path),
        "--prospects",
        str(prospect_records_path),
        "--output",
        str(project_root / "runtime" / "prospect-data-engine" / "query-weights.json"),
    )

    strategy_brief_path = suite_output_root / cycle_id / "strategy-brief.json"
    strategy_result = _run_python(
        STRATEGY_BRIEF,
        "--config",
        str(config_path),
        "--prospects",
        str(prospect_records_path),
        "--output",
        str(strategy_brief_path),
    )

    strategy_tasks_path = suite_output_root / cycle_id / "strategy-tasks.json"
    strategy_tasks_result = _run_python(
        STRATEGY_TASKS,
        "--config",
        str(config_path),
        "--prospects",
        str(prospect_records_path),
        "--brief",
        str(strategy_brief_path),
        "--strategy-weights",
        str(strategy_weights_path),
        "--output",
        str(strategy_tasks_path),
    )

    strategy_cards_path = suite_output_root / cycle_id / "strategy-cards.json"
    strategy_cards_result = _run_python(
        STRATEGY_CARDS,
        "--prospects",
        str(prospect_records_path),
        "--strategy-tasks",
        str(strategy_tasks_path),
        "--output",
        str(strategy_cards_path),
    )

    execution_queue_path = suite_output_root / cycle_id / "execution-queue.json"
    execution_result = _run_python(
        EXECUTION_QUEUE,
        "--strategy-tasks",
        str(strategy_tasks_path),
        "--feedback-events",
        str(feedback_events_path),
        "--suppression-registry",
        str(suppression_registry_path),
        "--output",
        str(execution_queue_path),
    )

    preliminary_report = {
        "cycle_id": cycle_id,
        "project_id": config.get("project", {}).get("id", ""),
        "ran_at": _utc_now_iso(),
        "inputs": {
            "project_root": str(project_root),
            "config_path": str(config_path),
        },
        "steps": {
            "discovery_recipe_library": recipe_result,
            "discovery_query_weight_update_pre": pre_query_weight_result,
            "prospect_search_discovery": search_discovery_result,
            "google_maps_capture_cycle": google_maps_capture_cycle_result,
            "google_maps_discovery": google_maps_discovery_result,
            "google_maps_email_enrichment": google_maps_email_enrichment_result,
            "prospect_discovery": discovery_result,
            "industry_directory_discovery": directory_discovery_result,
            "google_business_profile_discovery": gbp_discovery_result,
            "linkedin_company_page_discovery": linkedin_discovery_result,
            "prospect_import": import_result,
            "source_health_retry_update": source_health_result,
            "prospect_data_engine": bootstrap_result,
            "strategy_weight_update": strategy_weights_result,
            "discovery_query_weight_update_post": discovery_query_weight_result,
            "marketing_strategy_engine": strategy_result,
            "strategy_task_compilation": strategy_tasks_result,
            "strategy_card_generation": strategy_cards_result,
            "feedback_processing": feedback_processing_result,
            "outreach_feedback_engine": execution_result,
        },
        "artifacts": {
            "discovery_recipe_library_path": str(discovery_recipe_output),
            "generated_queries_path": str(generated_queries_path),
            "merged_seed_path": str(merged_seed_path),
            "strategy_ready_seed_path": str(strategy_ready_seed_path),
            "review_queue_path": str(review_queue_path),
            "prospect_records_path": str(prospect_records_path),
            "provider_health_path": str(project_root / "runtime" / "prospect-data-engine" / "provider-health.json"),
            "source_health_path": str(project_root / "runtime" / "prospect-data-engine" / "source-health.json"),
            "retry_targets_path": str(project_root / "runtime" / "prospect-data-engine" / "retry-targets.generated.json"),
            "discovery_query_weights_path": str(project_root / "runtime" / "prospect-data-engine" / "query-weights.json"),
            "strategy_weights_path": str(strategy_weights_path),
            "strategy_brief_path": str(strategy_brief_path),
            "strategy_tasks_path": str(strategy_tasks_path),
            "strategy_cards_path": str(strategy_cards_path),
            "feedback_output_dir": str(feedback_output_dir),
            "suppression_registry_path": str(suppression_registry_path),
            "feedback_patches_path": str(feedback_patches_path),
            "approval_queue_path": str(approval_queue_path),
            "execution_queue_path": str(execution_queue_path),
        },
        "quality_gate": {
            "status": quality_gate_status,
            "allowed_for_strategy": allowed_for_strategy,
            "review_queue_count": review_queue_count,
        },
        "status": "ok"
        if all(
            step.get("ok")
            for step in [
                recipe_result,
                pre_query_weight_result,
                search_discovery_result,
                google_maps_discovery_result,
                google_maps_email_enrichment_result,
                discovery_result,
                directory_discovery_result,
                gbp_discovery_result,
                linkedin_discovery_result,
                import_result,
                source_health_result,
                bootstrap_result,
                feedback_processing_result,
                strategy_weights_result,
                discovery_query_weight_result,
                strategy_result,
                strategy_tasks_result,
                strategy_cards_result,
                execution_result,
            ]
        )
        else "degraded",
    }

    preliminary_report_path = suite_runtime_root / "preliminary_cycle.json"
    _write_json(preliminary_report_path, preliminary_report)

    first_output_packet_json = suite_output_root / cycle_id / "first-output-packet.json"
    first_output_packet_md = suite_output_root / cycle_id / "first-output-packet.md"
    first_output_packet_result = _run_python(
        FIRST_OUTPUT_PACKET,
        "--cycle-report",
        str(preliminary_report_path),
        "--output-json",
        str(first_output_packet_json),
        "--output-md",
        str(first_output_packet_md),
    )

    cycle_report = {
        "cycle_id": cycle_id,
        "project_id": config.get("project", {}).get("id", ""),
        "ran_at": _utc_now_iso(),
        "inputs": {
            "project_root": str(project_root),
            "config_path": str(config_path),
        },
        "steps": {
            "discovery_recipe_library": recipe_result,
            "discovery_query_weight_update_pre": pre_query_weight_result,
            "prospect_search_discovery": search_discovery_result,
            "google_maps_discovery": google_maps_discovery_result,
            "google_maps_email_enrichment": google_maps_email_enrichment_result,
            "prospect_discovery": discovery_result,
            "industry_directory_discovery": directory_discovery_result,
            "google_business_profile_discovery": gbp_discovery_result,
            "linkedin_company_page_discovery": linkedin_discovery_result,
            "prospect_import": import_result,
            "source_health_retry_update": source_health_result,
            "prospect_data_engine": bootstrap_result,
            "strategy_weight_update": strategy_weights_result,
            "discovery_query_weight_update_post": discovery_query_weight_result,
            "marketing_strategy_engine": strategy_result,
            "strategy_task_compilation": strategy_tasks_result,
            "strategy_card_generation": strategy_cards_result,
            "feedback_processing": feedback_processing_result,
            "outreach_feedback_engine": execution_result,
            "first_output_packet": first_output_packet_result,
        },
        "artifacts": {
            "discovery_recipe_library_path": str(discovery_recipe_output),
            "generated_queries_path": str(generated_queries_path),
            "merged_seed_path": str(merged_seed_path),
            "strategy_ready_seed_path": str(strategy_ready_seed_path),
            "review_queue_path": str(review_queue_path),
            "prospect_records_path": str(prospect_records_path),
            "provider_health_path": str(project_root / "runtime" / "prospect-data-engine" / "provider-health.json"),
            "source_health_path": str(project_root / "runtime" / "prospect-data-engine" / "source-health.json"),
            "retry_targets_path": str(project_root / "runtime" / "prospect-data-engine" / "retry-targets.generated.json"),
            "discovery_query_weights_path": str(project_root / "runtime" / "prospect-data-engine" / "query-weights.json"),
            "strategy_weights_path": str(strategy_weights_path),
            "strategy_brief_path": str(strategy_brief_path),
            "strategy_tasks_path": str(strategy_tasks_path),
            "strategy_cards_path": str(strategy_cards_path),
            "feedback_output_dir": str(feedback_output_dir),
            "suppression_registry_path": str(suppression_registry_path),
            "feedback_patches_path": str(feedback_patches_path),
            "approval_queue_path": str(approval_queue_path),
            "execution_queue_path": str(execution_queue_path),
            "first_output_packet_json": str(first_output_packet_json),
            "first_output_packet_md": str(first_output_packet_md),
        },
        "quality_gate": {
            "status": quality_gate_status,
            "allowed_for_strategy": allowed_for_strategy,
            "review_queue_count": review_queue_count,
        },
        "status": "ok"
        if all(
            step.get("ok")
            for step in [
                recipe_result,
                pre_query_weight_result,
                search_discovery_result,
                google_maps_discovery_result,
                google_maps_email_enrichment_result,
                discovery_result,
                directory_discovery_result,
                gbp_discovery_result,
                linkedin_discovery_result,
                import_result,
                source_health_result,
                bootstrap_result,
                feedback_processing_result,
                strategy_weights_result,
                discovery_query_weight_result,
                strategy_result,
                strategy_tasks_result,
                strategy_cards_result,
                execution_result,
                first_output_packet_result,
            ]
        )
        else "degraded",
    }

    _write_json(suite_runtime_root / "last_cycle.json", cycle_report)
    _write_json(suite_reports_root / f"{cycle_id}.json", cycle_report)

    runtime_state = _read_json(runtime_state_path)
    runtime_state["status"] = "suite_cycle_completed" if cycle_report["status"] == "ok" else "suite_cycle_degraded"
    runtime_state["last_completed_cycle"] = cycle_id
    runtime_state["last_feedback_sync_at"] = _utc_now_iso()
    runtime_state.setdefault("notes", [])
    runtime_state["notes"].append(f"{cycle_id}: unified marketing suite cycle -> {cycle_report['status']}")
    _write_json(runtime_state_path, runtime_state)

    print(json.dumps(cycle_report, ensure_ascii=False, indent=2))
    return 0 if cycle_report["status"] == "ok" else 1


if __name__ == "__main__":
    raise SystemExit(main())
