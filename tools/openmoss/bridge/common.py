#!/usr/bin/env python3

from __future__ import annotations

import json
import os
import shutil
import tempfile
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict


WORKSPACE_ROOT = Path("/Users/mac_claw/.openclaw/workspace")
BRIDGE_ROOT = WORKSPACE_ROOT / "tools" / "openmoss" / "bridge"
BRIDGE_STATE_ROOT = WORKSPACE_ROOT / "tools" / "openmoss" / "runtime" / "bridge"


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def read_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    with path.open("r", encoding="utf-8") as fh:
        return json.load(fh)


def write_json_atomic(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(prefix=path.name + ".", dir=str(path.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(data, fh, ensure_ascii=False, indent=2)
        os.replace(tmp_name, path)
    finally:
        if os.path.exists(tmp_name):
            os.unlink(tmp_name)


def append_jsonl(path: Path, data: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(data, ensure_ascii=False) + "\n")


@dataclass
class BridgeConfig:
    enabled: bool
    dry_run: bool
    dispatch_to_openclaw: bool
    deliver_outbox: bool
    wait_for_completion: bool
    dispatch_timeout_ms: int
    provider: str
    hub_url: str
    token_env: str
    token_file: Path
    poll_interval_seconds: float
    wake_mode: str
    session_namespace: str
    state_root: Path

    @property
    def inbox_dir(self) -> Path:
        return self.state_root / "inbox"

    @property
    def dispatch_dir(self) -> Path:
        return self.state_root / "dispatch"

    @property
    def outbox_dir(self) -> Path:
        return self.state_root / "outbox"

    @property
    def dispatched_dir(self) -> Path:
        return self.state_root / "dispatched"

    @property
    def dispatch_results_dir(self) -> Path:
        return self.state_root / "dispatch_results"

    @property
    def processed_dir(self) -> Path:
        return self.state_root / "processed"

    @property
    def sessions_dir(self) -> Path:
        return self.state_root / "sessions"

    @property
    def status_file(self) -> Path:
        return self.state_root / "bridge_status.json"

    @property
    def config_file(self) -> Path:
        return BRIDGE_ROOT / "config.local.json"


DEFAULT_CONFIG = {
    "enabled": False,
    "dry_run": True,
    "dispatch_to_openclaw": False,
    "deliver_outbox": False,
    "wait_for_completion": True,
    "dispatch_timeout_ms": 30000,
    "provider": "imclaw",
    "hub_url": "https://imclaw-server.app.mosi.cn",
    "token_env": "IMCLAW_TOKEN",
    "token_file": str(BRIDGE_ROOT / ".env.local"),
    "poll_interval_seconds": 2.0,
    "wake_mode": "dispatch-only",
    "session_namespace": "imclaw",
    "state_root": str(BRIDGE_STATE_ROOT),
}


def load_bridge_config() -> BridgeConfig:
    raw = dict(DEFAULT_CONFIG)
    local_file = BRIDGE_ROOT / "config.local.json"
    if local_file.exists():
        raw.update(read_json(local_file, {}))
    return BridgeConfig(
        enabled=bool(raw["enabled"]),
        dry_run=bool(raw["dry_run"]),
        dispatch_to_openclaw=bool(raw["dispatch_to_openclaw"]),
        deliver_outbox=bool(raw["deliver_outbox"]),
        wait_for_completion=bool(raw["wait_for_completion"]),
        dispatch_timeout_ms=int(raw["dispatch_timeout_ms"]),
        provider=str(raw["provider"]),
        hub_url=str(raw["hub_url"]),
        token_env=str(raw["token_env"]),
        token_file=Path(str(raw["token_file"])).expanduser(),
        poll_interval_seconds=float(raw["poll_interval_seconds"]),
        wake_mode=str(raw["wake_mode"]),
        session_namespace=str(raw["session_namespace"]),
        state_root=Path(str(raw["state_root"])).expanduser(),
    )


def ensure_bridge_layout(cfg: BridgeConfig) -> None:
    for path in [
        cfg.inbox_dir,
        cfg.dispatch_dir,
        cfg.dispatched_dir,
        cfg.dispatch_results_dir,
        cfg.outbox_dir,
        cfg.processed_dir,
        cfg.sessions_dir,
    ]:
        path.mkdir(parents=True, exist_ok=True)
    if not cfg.status_file.exists():
        write_bridge_status(
            cfg,
            status="initialized",
            note="bridge layout created",
        )


def load_env_file(path: Path) -> Dict[str, str]:
    values: Dict[str, str] = {}
    if not path.exists():
        return values
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        values[key.strip()] = value.strip().strip("\"'")
    return values


def resolve_secret(cfg: BridgeConfig, key: str) -> str:
    direct = os.environ.get(key, "").strip()
    if direct:
        return direct
    file_values = load_env_file(cfg.token_file)
    return file_values.get(key, "").strip()


def write_bridge_status(cfg: BridgeConfig, status: str, **extra: Any) -> None:
    payload = {
        "status": status,
        "updated_at": utc_now_iso(),
        "provider": cfg.provider,
        "dry_run": cfg.dry_run,
        "enabled": cfg.enabled,
        "dispatch_to_openclaw": cfg.dispatch_to_openclaw,
        "deliver_outbox": cfg.deliver_outbox,
        "wait_for_completion": cfg.wait_for_completion,
        "wake_mode": cfg.wake_mode,
    }
    payload.update(extra)
    write_json_atomic(cfg.status_file, payload)


def queue_counts(cfg: BridgeConfig) -> Dict[str, int]:
    return {
        "inbox": len(list(cfg.inbox_dir.glob("*.json"))),
        "dispatch": len(list(cfg.dispatch_dir.glob("*.json"))),
        "dispatched": len(list(cfg.dispatched_dir.glob("*.json"))),
        "dispatch_results": len(list(cfg.dispatch_results_dir.glob("*.json"))),
        "outbox": len(list(cfg.outbox_dir.glob("*.json"))),
        "sessions": len(list(cfg.sessions_dir.glob("*.json"))),
    }


def conversation_session_key(
    cfg: BridgeConfig,
    provider: str,
    conversation_id: str,
    conversation_type: str = "group",
) -> str:
    provider_norm = provider.strip().lower().replace(":", "-")
    convo_norm = conversation_id.strip()
    convo_type = conversation_type.strip().lower() or "group"
    if provider_norm == "telegram":
        if convo_norm.startswith("-") or convo_type == "group":
            return f"agent:main:telegram:group:{convo_norm}"
        return f"agent:main:telegram:direct:{convo_norm}"
    return f"agent:main:{cfg.session_namespace}:{provider_norm}:{convo_norm}"


def reset_state_dir(cfg: BridgeConfig) -> None:
    if cfg.state_root.exists():
        shutil.rmtree(cfg.state_root)
    ensure_bridge_layout(cfg)
