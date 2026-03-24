#!/usr/bin/env python3

from __future__ import annotations

import argparse
import json
import uuid
from datetime import datetime
from pathlib import Path

from common import (
    BRIDGE_ROOT,
    ensure_bridge_layout,
    load_bridge_config,
    queue_counts,
    read_json,
    reset_state_dir,
    utc_now_iso,
    write_bridge_status,
    write_json_atomic,
)


def _message_file_name() -> str:
    return f"{datetime.utcnow().strftime('%Y%m%dT%H%M%S')}-{uuid.uuid4().hex[:8]}.json"


def cmd_init(args: argparse.Namespace) -> int:
    cfg = load_bridge_config()
    ensure_bridge_layout(cfg)
    print(f"bridge root: {BRIDGE_ROOT}")
    print(f"state root:  {cfg.state_root}")
    print(f"config file: {cfg.config_file}")
    print("status: initialized")
    return 0


def cmd_status(args: argparse.Namespace) -> int:
    cfg = load_bridge_config()
    ensure_bridge_layout(cfg)
    status = read_json(cfg.status_file, {})
    payload = {
        "config": {
            "enabled": cfg.enabled,
            "dry_run": cfg.dry_run,
            "dispatch_to_openclaw": cfg.dispatch_to_openclaw,
            "deliver_outbox": cfg.deliver_outbox,
            "wait_for_completion": cfg.wait_for_completion,
            "dispatch_timeout_ms": cfg.dispatch_timeout_ms,
            "provider": cfg.provider,
            "hub_url": cfg.hub_url,
            "token_env": cfg.token_env,
            "token_file": str(cfg.token_file),
            "wake_mode": cfg.wake_mode,
            "session_namespace": cfg.session_namespace,
            "state_root": str(cfg.state_root),
        },
        "queue_counts": queue_counts(cfg),
        "status": status,
    }
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


def cmd_ingest_sample(args: argparse.Namespace) -> int:
    cfg = load_bridge_config()
    ensure_bridge_layout(cfg)
    message = {
        "id": args.message_id or uuid.uuid4().hex,
        "provider": args.provider or cfg.provider,
        "conversation_id": args.conversation_id,
        "conversation_type": args.conversation_type,
        "sender_id": args.sender_id,
        "sender_name": args.sender_name,
        "content": args.content,
        "attachments": [],
        "received_at": utc_now_iso(),
        "source": "sample-cli",
    }
    out_path = cfg.inbox_dir / _message_file_name()
    write_json_atomic(out_path, message)
    write_bridge_status(
        cfg,
        status="message_ingested",
        last_inbound_file=str(out_path),
        last_message_id=message["id"],
    )
    print(f"queued sample message: {out_path}")
    return 0


def cmd_enable(args: argparse.Namespace) -> int:
    cfg = load_bridge_config()
    payload = {
        "enabled": args.enabled,
        "dry_run": args.dry_run,
        "dispatch_to_openclaw": args.dispatch_to_openclaw,
        "deliver_outbox": args.deliver_outbox,
        "wait_for_completion": args.wait_for_completion,
        "dispatch_timeout_ms": args.dispatch_timeout_ms,
        "provider": cfg.provider,
        "hub_url": cfg.hub_url,
        "token_env": cfg.token_env,
        "token_file": str(cfg.token_file),
        "poll_interval_seconds": cfg.poll_interval_seconds,
        "wake_mode": cfg.wake_mode,
        "session_namespace": cfg.session_namespace,
        "state_root": str(cfg.state_root),
    }
    write_json_atomic(cfg.config_file, payload)
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


def cmd_reset_state(args: argparse.Namespace) -> int:
    cfg = load_bridge_config()
    reset_state_dir(cfg)
    write_bridge_status(cfg, status="state_reset", note="bridge runtime state cleared")
    print(f"reset state: {cfg.state_root}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Local OpenMOSS bridge runtime")
    sub = parser.add_subparsers(dest="cmd", required=True)

    sub.add_parser("init")
    sub.add_parser("status")

    ingest = sub.add_parser("ingest-sample")
    ingest.add_argument("--conversation-id", required=True)
    ingest.add_argument("--conversation-type", default="group")
    ingest.add_argument("--sender-id", required=True)
    ingest.add_argument("--sender-name", default="unknown")
    ingest.add_argument("--content", required=True)
    ingest.add_argument("--provider", default="")
    ingest.add_argument("--message-id", default="")

    enable = sub.add_parser("enable")
    enable.add_argument("--enabled", action="store_true", default=True)
    enable.add_argument("--dry-run", action="store_true", default=False)
    enable.add_argument("--dispatch-to-openclaw", action="store_true", default=False)
    enable.add_argument("--deliver-outbox", action="store_true", default=False)
    enable.add_argument("--wait-for-completion", action="store_true", default=False)
    enable.add_argument("--dispatch-timeout-ms", type=int, default=30000)

    sub.add_parser("reset-state")
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    if args.cmd == "init":
        return cmd_init(args)
    if args.cmd == "status":
        return cmd_status(args)
    if args.cmd == "ingest-sample":
        return cmd_ingest_sample(args)
    if args.cmd == "enable":
        return cmd_enable(args)
    if args.cmd == "reset-state":
        return cmd_reset_state(args)
    parser.error(f"unknown command: {args.cmd}")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
