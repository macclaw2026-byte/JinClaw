#!/usr/bin/env python3

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import uuid
from pathlib import Path
from typing import Any, Dict

from common import (
    ensure_bridge_layout,
    load_bridge_config,
    queue_counts,
    read_json,
    utc_now_iso,
    write_bridge_status,
    write_json_atomic,
)


def _result_path(cfg, dispatch_file: Path) -> Path:
    return cfg.dispatch_results_dir / f"{dispatch_file.stem}.result.json"


def _archive_path(cfg, dispatch_file: Path) -> Path:
    return cfg.dispatched_dir / dispatch_file.name


def _run_openclaw(args: list[str]) -> Dict[str, Any]:
    proc = subprocess.run(args, capture_output=True, text=True, check=False)
    if proc.returncode != 0:
        raise RuntimeError(proc.stderr.strip() or proc.stdout.strip() or f"command failed: {' '.join(args)}")
    stdout = proc.stdout.strip()
    return json.loads(stdout) if stdout else {}


def _build_message(dispatch: Dict[str, Any]) -> str:
    message = dispatch.get("message", {})
    parts = [
        "[OpenMOSS bridge dispatch]",
        f"provider: {dispatch.get('provider', 'unknown')}",
        f"conversation_id: {dispatch.get('conversation_id', 'unknown')}",
        f"conversation_type: {message.get('conversation_type', 'unknown')}",
        f"sender_name: {message.get('sender_name', 'unknown')}",
        f"sender_id: {message.get('sender_id', 'unknown')}",
        f"message_id: {message.get('id', 'unknown')}",
        "content:",
        str(message.get("content", "")),
    ]
    return "\n".join(parts)


def process_dispatch(dispatch_file: Path) -> Dict[str, Any]:
    cfg = load_bridge_config()
    dispatch = read_json(dispatch_file, {})
    dispatch_id = str(dispatch.get("dispatch_id") or uuid.uuid4().hex)
    result = {
        "dispatch_id": dispatch_id,
        "dispatch_file": str(dispatch_file),
        "session_key": dispatch.get("session_key", ""),
        "conversation_id": dispatch.get("conversation_id", ""),
        "provider": dispatch.get("provider", cfg.provider),
        "processed_at": utc_now_iso(),
        "dry_run": cfg.dry_run,
        "dispatch_to_openclaw": cfg.dispatch_to_openclaw,
    }

    if cfg.dry_run or not cfg.dispatch_to_openclaw:
        result["status"] = "skipped"
        result["reason"] = "dry_run" if cfg.dry_run else "dispatch_disabled"
        result["preview"] = _build_message(dispatch)
        write_json_atomic(_result_path(cfg, dispatch_file), result)
        shutil.move(str(dispatch_file), _archive_path(cfg, dispatch_file))
        return result

    idempotency_key = uuid.uuid4().hex
    send_params = {
        "idempotencyKey": idempotency_key,
        "sessionKey": dispatch["session_key"],
        "message": _build_message(dispatch),
        "timeoutMs": cfg.dispatch_timeout_ms,
    }
    send_response = _run_openclaw(
        [
            "openclaw",
            "gateway",
            "call",
            "chat.send",
            "--params",
            json.dumps(send_params, ensure_ascii=False),
            "--json",
        ]
    )

    result["status"] = "sent"
    result["send"] = {
        "params": send_params,
        "response": send_response,
    }

    run_id = send_response.get("runId")
    if cfg.wait_for_completion and run_id:
        wait_params = {
            "runId": run_id,
            "timeoutMs": cfg.dispatch_timeout_ms,
        }
        wait_response = _run_openclaw(
            [
                "openclaw",
                "gateway",
                "call",
                "agent.wait",
                "--params",
                json.dumps(wait_params, ensure_ascii=False),
                "--json",
            ]
        )
        result["wait"] = {
            "params": wait_params,
            "response": wait_response,
        }
        result["status"] = "completed"

    write_json_atomic(_result_path(cfg, dispatch_file), result)
    shutil.move(str(dispatch_file), _archive_path(cfg, dispatch_file))
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description="Dispatch bridge payloads into isolated OpenClaw sessions")
    parser.add_argument("--limit", type=int, default=20)
    args = parser.parse_args()

    cfg = load_bridge_config()
    ensure_bridge_layout(cfg)
    dispatch_files = sorted(cfg.dispatch_dir.glob("*.json"))[: args.limit]
    results = [process_dispatch(path) for path in dispatch_files]
    write_bridge_status(
        cfg,
        status="dispatch_processed",
        processed_count=len(results),
        queue_counts=queue_counts(cfg),
        last_dispatch_result=results[-1] if results else None,
    )
    print(json.dumps({"processed": results, "count": len(results)}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
