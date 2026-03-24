#!/usr/bin/env python3

from __future__ import annotations

import argparse
import os
import signal
import time
import uuid

from common import ensure_bridge_layout, load_bridge_config, queue_counts, resolve_secret, utc_now_iso, write_bridge_status, write_json_atomic
from deliver_outbox import deliver_one
from dispatch_to_openclaw import process_dispatch
from imclaw_transport import IMClawTransport, IMClawTransportConfig
from process_queue import process_one


def normalize_inbound(payload: dict, default_provider: str) -> dict | None:
    if payload.get("type") not in {"message", "mentioned", "system_message"}:
        return None
    body = payload.get("payload") or {}
    group_id = body.get("group_id") or body.get("conversation_id")
    if not group_id:
        return None
    sender_id = body.get("sender_id") or body.get("user_id") or body.get("agent_id") or "unknown"
    sender_name = body.get("sender_name") or body.get("display_name") or "unknown"
    content = body.get("content") or body.get("content_preview") or ""
    return {
        "id": body.get("id") or uuid.uuid4().hex,
        "provider": default_provider,
        "conversation_id": group_id,
        "conversation_type": body.get("group_type") or "group",
        "sender_id": sender_id,
        "sender_name": sender_name,
        "content": content,
        "attachments": body.get("attachments", []),
        "received_at": utc_now_iso(),
        "source": "bridge-service",
        "raw_event_type": payload.get("type"),
        "raw_payload": body,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Supervise the local OpenMOSS bridge sidecar")
    parser.add_argument("--once", action="store_true")
    parser.add_argument("--no-live-transport", action="store_true")
    args = parser.parse_args()

    cfg = load_bridge_config()
    ensure_bridge_layout(cfg)
    stopped = False
    transport = None

    def handle_signal(signum, frame):
        nonlocal stopped
        stopped = True
        write_bridge_status(cfg, status="stopping", signal=signum)
        if transport:
            transport.stop()

    signal.signal(signal.SIGINT, handle_signal)
    signal.signal(signal.SIGTERM, handle_signal)

    if cfg.enabled and not args.no_live_transport:
        token = resolve_secret(cfg, cfg.token_env)
        if not token:
            raise SystemExit(f"missing required secret: {cfg.token_env} (env or {cfg.token_file})")
        transport = IMClawTransport(
            IMClawTransportConfig(
                hub_url=cfg.hub_url,
                token=token,
            )
        )

        def on_status(status: str, extra: dict) -> None:
            write_bridge_status(cfg, status=status, transport="imclaw", **extra)

        def on_message(payload: dict) -> None:
            normalized = normalize_inbound(payload, cfg.provider)
            if normalized is None:
                return
            filename = cfg.inbox_dir / f"live-{normalized['id']}.json"
            write_json_atomic(filename, normalized)
            write_bridge_status(
                cfg,
                status="live_message_ingested",
                last_inbound_file=str(filename),
                last_message_id=normalized["id"],
                last_conversation_id=normalized["conversation_id"],
            )

        transport.on_status(on_status)
        transport.on_message(on_message)
        transport.start_background()
        write_bridge_status(cfg, status="service_started", mode="live")
    else:
        write_bridge_status(cfg, status="service_started", mode="queue-only")

    while not stopped:
        for inbox_file in sorted(cfg.inbox_dir.glob("*.json")):
            process_one(inbox_file)
        for dispatch_file in sorted(cfg.dispatch_dir.glob("*.json")):
            process_dispatch(dispatch_file)
        for outbox_file in sorted(cfg.outbox_dir.glob("*.json")):
            deliver_one(outbox_file)
        write_bridge_status(
            cfg,
            status="service_healthy",
            mode="live" if transport else "queue-only",
            queue_counts=queue_counts(cfg),
        )
        if args.once:
            break
        time.sleep(cfg.poll_interval_seconds)

    if transport:
        transport.stop()
    write_bridge_status(cfg, status="stopped", queue_counts=queue_counts(cfg))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
