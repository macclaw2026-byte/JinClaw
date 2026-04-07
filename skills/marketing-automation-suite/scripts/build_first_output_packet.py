#!/usr/bin/env python3

from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path


def _read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Build a consolidated first-output packet for a marketing suite cycle.")
    parser.add_argument("--cycle-report", required=True)
    parser.add_argument("--output-json", required=True)
    parser.add_argument("--output-md", required=True)
    args = parser.parse_args()

    cycle = _read_json(Path(args.cycle_report).expanduser())
    artifacts = cycle.get("artifacts", {})
    quality_gate = cycle.get("quality_gate", {})
    search_payload = cycle.get("steps", {}).get("prospect_search_discovery", {}).get("payload", {})
    discovery_payload = cycle.get("steps", {}).get("prospect_discovery", {}).get("payload", {})
    import_payload = cycle.get("steps", {}).get("prospect_import", {}).get("payload", {})

    prospects = _read_json(Path(artifacts["prospect_records_path"]).expanduser()).get("items", [])
    strategy_tasks = _read_json(Path(artifacts["strategy_tasks_path"]).expanduser()).get("items", [])
    execution_queue = _read_json(Path(artifacts["execution_queue_path"]).expanduser())
    review_queue = _read_json(Path(artifacts["review_queue_path"]).expanduser()).get("items", [])
    source_registry = _read_json(Path(import_payload["source_registry_path"]).expanduser()).get("items", [])

    channels = Counter(item.get("channel", "unknown") for item in strategy_tasks)
    account_types = Counter(item.get("account_type", "unknown") for item in strategy_tasks)
    path_types = Counter(item.get("path_type", "unknown") for item in strategy_tasks)
    score_tiers = Counter(item.get("score_tier", "unknown") for item in strategy_tasks)

    readiness_checks = {
        "quality_gate_passed": quality_gate.get("allowed_for_strategy", False),
        "prospect_volume_ready": len(prospects) >= 50,
        "strategy_volume_ready": len(strategy_tasks) >= 25,
        "queue_volume_ready": execution_queue.get("summary", {}).get("queued", 0) >= 10,
        "channel_available": len(channels) >= 1,
        "review_queue_manageable": len(review_queue) <= max(25, len(prospects) // 5),
        "search_layer_active": search_payload.get("enabled_query_count", 0) > 0,
        "discovery_layer_active": discovery_payload.get("enabled_target_count", 0) > 0,
    }
    ready_for_operator_use = all(readiness_checks.values())

    packet = {
        "project_id": cycle.get("project_id", ""),
        "cycle_id": cycle.get("cycle_id", ""),
        "status": cycle.get("status", ""),
        "ready_for_operator_use": ready_for_operator_use,
        "readiness_checks": readiness_checks,
        "discovery": {
            "enabled_query_count": search_payload.get("enabled_query_count", 0),
            "generated_target_count": search_payload.get("generated_target_count", 0),
            "enabled_target_count": discovery_payload.get("enabled_target_count", 0),
            "discovered_count": discovery_payload.get("discovered_count", 0),
            "failure_count": discovery_payload.get("failure_count", 0),
        },
        "data_quality": {
            "source_count": import_payload.get("source_count", 0),
            "raw_record_count": import_payload.get("raw_record_count", 0),
            "deduped_record_count": import_payload.get("deduped_record_count", 0),
            "review_queue_count": len(review_queue),
            "quality_gate_status": quality_gate.get("status", "unknown"),
            "review_sources": [item.get("source_label") for item in source_registry if item.get("quality_rating") == "review"],
        },
        "strategy": {
            "task_count": len(strategy_tasks),
            "channels": dict(channels),
            "account_types": dict(account_types),
            "path_types": dict(path_types),
            "score_tiers": dict(score_tiers),
        },
        "execution": execution_queue.get("summary", {}),
        "operator_focus": {
            "top_review_items": review_queue[:10],
            "top_strategy_tasks": strategy_tasks[:10],
        },
        "artifacts": artifacts,
    }

    md = [
        f"# First Output Packet: {packet['project_id']}",
        "",
        f"- cycle_id: `{packet['cycle_id']}`",
        f"- status: `{packet['status']}`",
        f"- ready_for_operator_use: `{packet['ready_for_operator_use']}`",
        "",
        "## Discovery",
        f"- enabled queries: {packet['discovery']['enabled_query_count']}",
        f"- generated targets: {packet['discovery']['generated_target_count']}",
        f"- enabled targets: {packet['discovery']['enabled_target_count']}",
        f"- discovered accounts: {packet['discovery']['discovered_count']}",
        "",
        "## Data Quality",
        f"- source count: {packet['data_quality']['source_count']}",
        f"- raw records: {packet['data_quality']['raw_record_count']}",
        f"- deduped records: {packet['data_quality']['deduped_record_count']}",
        f"- review queue: {packet['data_quality']['review_queue_count']}",
        f"- quality gate: {packet['data_quality']['quality_gate_status']}",
        "",
        "## Strategy",
        f"- strategy tasks: {packet['strategy']['task_count']}",
        f"- channels: {packet['strategy']['channels']}",
        f"- path types: {packet['strategy']['path_types']}",
        f"- score tiers: {packet['strategy']['score_tiers']}",
        "",
        "## Execution",
        f"- queue summary: {packet['execution']}",
        "",
        "## Readiness Checks",
    ]
    for key, value in readiness_checks.items():
        md.append(f"- {key}: `{value}`")

    _write_json(Path(args.output_json).expanduser(), packet)
    _write_text(Path(args.output_md).expanduser(), "\n".join(md) + "\n")
    print(
        json.dumps(
            {
                "status": "ok",
                "ready_for_operator_use": ready_for_operator_use,
                "output_json": str(Path(args.output_json).expanduser()),
                "output_md": str(Path(args.output_md).expanduser()),
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
