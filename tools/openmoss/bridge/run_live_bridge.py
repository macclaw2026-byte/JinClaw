#!/usr/bin/env python3

from __future__ import annotations

import argparse
import json
import os
import signal
import sys
import uuid
from pathlib import Path

from common import ensure_bridge_layout, load_bridge_config, resolve_secret, utc_now_iso, write_bridge_status, write_json_atomic
from imclaw_transport import IMClawTransport, IMClawTransportConfig


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
        "source": "live-transport",
        "raw_event_type": payload.get("type"),
        "raw_payload": body,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Live IMClaw transport -> local bridge inbox")
    parser.add_argument("--foreground", action="store_true")
    args = parser.parse_args()

    cfg = load_bridge_config()
    ensure_bridge_layout(cfg)
    token = resolve_secret(cfg, cfg.token_env)
    if not token:
        raise SystemExit(f"missing required secret: {cfg.token_env} (env or {cfg.token_file})")
    if not cfg.enabled:
        raise SystemExit("bridge config enabled=false; refusing to connect live transport")
    if cfg.dry_run:
        print("warning: live transport running while bridge is still dry_run=true")

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

    def stop_handler(signum, frame):
        transport.stop()
        write_bridge_status(cfg, status="stopped", signal=signum)
        raise SystemExit(0)

    signal.signal(signal.SIGINT, stop_handler)
    signal.signal(signal.SIGTERM, stop_handler)

    profile = transport.get_profile()
    print(json.dumps({"ok": True, "profile": profile}, ensure_ascii=False, indent=2))
    transport.run_forever()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
