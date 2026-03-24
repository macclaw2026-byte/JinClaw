#!/usr/bin/env python3

from __future__ import annotations

import argparse
import json
import os
import shutil
import uuid
from pathlib import Path
from typing import Any, Dict

from common import ensure_bridge_layout, load_bridge_config, queue_counts, read_json, resolve_secret, utc_now_iso, write_bridge_status, write_json_atomic
from imclaw_transport import IMClawTransport, IMClawTransportConfig


def _sent_dir(cfg) -> Path:
    return cfg.state_root / "sent"


def _delivery_results_dir(cfg) -> Path:
    return cfg.state_root / "delivery_results"


def _ensure_dirs(cfg) -> None:
    _sent_dir(cfg).mkdir(parents=True, exist_ok=True)
    _delivery_results_dir(cfg).mkdir(parents=True, exist_ok=True)


def _result_path(cfg, outbox_file: Path) -> Path:
    return _delivery_results_dir(cfg) / f"{outbox_file.stem}.result.json"


def _archive_path(cfg, outbox_file: Path) -> Path:
    return _sent_dir(cfg) / outbox_file.name


def deliver_one(outbox_file: Path) -> Dict[str, Any]:
    cfg = load_bridge_config()
    _ensure_dirs(cfg)
    payload = read_json(outbox_file, {})
    result = {
        "delivery_id": uuid.uuid4().hex,
        "outbox_file": str(outbox_file),
        "conversation_id": payload.get("conversation_id", ""),
        "session_key": payload.get("session_key", ""),
        "provider": payload.get("provider", cfg.provider),
        "processed_at": utc_now_iso(),
        "dry_run": cfg.dry_run,
        "deliver_outbox": cfg.deliver_outbox,
    }

    if cfg.dry_run or not cfg.deliver_outbox:
        result["status"] = "skipped"
        result["reason"] = "dry_run" if cfg.dry_run else "delivery_disabled"
        result["preview"] = {
            "text": payload.get("text", ""),
            "attachments": payload.get("attachments", []),
        }
        write_json_atomic(_result_path(cfg, outbox_file), result)
        shutil.move(str(outbox_file), _archive_path(cfg, outbox_file))
        return result

    token = resolve_secret(cfg, cfg.token_env)
    if not token:
        raise RuntimeError(f"missing required secret: {cfg.token_env} (env or {cfg.token_file})")

    client = IMClawTransport(
        IMClawTransportConfig(
            hub_url=cfg.hub_url,
            token=token,
        )
    )
    response = client.send_group_message(
        group_id=str(payload["conversation_id"]),
        content=str(payload.get("text", "")),
        reply_to_id=payload.get("reply_to_id"),
        attachments=payload.get("attachments") or [],
    )
    result["status"] = "delivered"
    result["response"] = response
    write_json_atomic(_result_path(cfg, outbox_file), result)
    shutil.move(str(outbox_file), _archive_path(cfg, outbox_file))
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description="Deliver bridge outbox messages back to IMClaw")
    parser.add_argument("--limit", type=int, default=20)
    args = parser.parse_args()

    cfg = load_bridge_config()
    ensure_bridge_layout(cfg)
    _ensure_dirs(cfg)
    outbox_files = sorted(cfg.outbox_dir.glob("*.json"))[: args.limit]
    results = [deliver_one(path) for path in outbox_files]
    write_bridge_status(
        cfg,
        status="outbox_processed",
        processed_count=len(results),
        queue_counts=queue_counts(cfg),
        last_delivery_result=results[-1] if results else None,
    )
    print(json.dumps({"processed": results, "count": len(results)}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
