#!/usr/bin/env python3

from __future__ import annotations

import json
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Optional

try:
    import requests
except Exception:  # pragma: no cover
    requests = None

try:
    import websocket
except Exception:  # pragma: no cover
    websocket = None


def require_transport_deps() -> None:
    missing = []
    if requests is None:
        missing.append("requests")
    if websocket is None:
        missing.append("websocket-client")
    if missing:
        raise RuntimeError(
            "missing bridge dependencies: "
            + ", ".join(missing)
            + " (run bootstrap_bridge_env.sh first)"
        )


@dataclass
class IMClawTransportConfig:
    hub_url: str
    token: str
    reconnect_seconds: float = 5.0
    log_file: Optional[Path] = None


class IMClawTransport:
    def __init__(self, cfg: IMClawTransportConfig):
        require_transport_deps()
        self.cfg = cfg
        self._ws = None
        self._thread = None
        self._stop = threading.Event()
        self._on_message: Optional[Callable[[dict], None]] = None
        self._on_status: Optional[Callable[[str, dict], None]] = None

    def on_message(self, fn: Callable[[dict], None]) -> None:
        self._on_message = fn

    def on_status(self, fn: Callable[[str, dict], None]) -> None:
        self._on_status = fn

    def _emit_status(self, status: str, **extra: object) -> None:
        if self._on_status:
            self._on_status(status, extra)

    def _ws_url(self) -> str:
        return self.cfg.hub_url.rstrip("/").replace("https://", "wss://").replace("http://", "ws://") + f"/ws?token={self.cfg.token}"

    def connect_once(self) -> None:
        ws_url = self._ws_url()
        self._emit_status("connecting", ws_url=ws_url)

        def on_open(ws_app):
            self._emit_status("connected", ws_url=ws_url)

        def on_message(ws_app, raw: str):
            try:
                payload = json.loads(raw)
            except json.JSONDecodeError:
                self._emit_status("invalid_json", raw=raw[:500])
                return
            if self._on_message:
                self._on_message(payload)

        def on_error(ws_app, error):
            self._emit_status("error", error=str(error))

        def on_close(ws_app, code, reason):
            self._emit_status("closed", code=code, reason=reason)

        self._ws = websocket.WebSocketApp(
            ws_url,
            on_open=on_open,
            on_message=on_message,
            on_error=on_error,
            on_close=on_close,
        )
        self._ws.run_forever()

    def run_forever(self) -> None:
        while not self._stop.is_set():
            try:
                self.connect_once()
            except Exception as exc:
                self._emit_status("connect_failed", error=str(exc))
            if self._stop.is_set():
                break
            time.sleep(self.cfg.reconnect_seconds)

    def start_background(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self.run_forever, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._ws:
            try:
                self._ws.close()
            except Exception:
                pass
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=3)

    def get_profile(self) -> dict:
        require_transport_deps()
        resp = requests.get(
            self.cfg.hub_url.rstrip("/") + "/api/v1/agents/me",
            headers={"Authorization": f"Bearer {self.cfg.token}"},
            timeout=20,
        )
        resp.raise_for_status()
        return resp.json()

    def send_group_message(
        self,
        group_id: str,
        content: str,
        reply_to_id: Optional[str] = None,
        attachments: Optional[list[dict]] = None,
    ) -> dict:
        require_transport_deps()
        payload = {"content": content}
        if reply_to_id:
            payload["reply_to_id"] = reply_to_id
        if attachments:
            payload["attachments"] = attachments
        resp = requests.post(
            self.cfg.hub_url.rstrip("/") + f"/api/v1/groups/{group_id}/messages",
            headers={"Authorization": f"Bearer {self.cfg.token}"},
            json=payload,
            timeout=20,
        )
        resp.raise_for_status()
        return resp.json()
