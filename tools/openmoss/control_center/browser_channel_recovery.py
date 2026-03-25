#!/usr/bin/env python3

from __future__ import annotations

import json
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Dict, Iterable, List

from paths import BROWSER_CHANNELS_ROOT, OPENCLAW_ROOT


def _write_json(path: Path, payload: Dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def load_gateway_token() -> str:
    config_path = OPENCLAW_ROOT / "openclaw.json"
    try:
        payload = json.loads(config_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return ""
    return str(payload.get("gateway", {}).get("auth", {}).get("token", "")).strip()


def browser_control_get(token: str, path: str, timeout: int = 10) -> Dict[str, object]:
    req = urllib.request.Request(
        f"http://127.0.0.1:18791{path}",
        headers={"Authorization": f"Bearer {token}"},
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode(errors="ignore"))


def browser_control_post(token: str, path: str, body: Dict[str, object], timeout: int = 20) -> Dict[str, object]:
    req = urllib.request.Request(
        f"http://127.0.0.1:18791{path}",
        data=json.dumps(body).encode(),
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode(errors="ignore"))


def _normalize_expected_domains(expected_domains: Iterable[str] | None, last_known_url: str) -> List[str]:
    domains = [str(item).strip().lower() for item in (expected_domains or []) if str(item).strip()]
    if last_known_url:
        parsed = urllib.parse.urlparse(last_known_url)
        hostname = (parsed.hostname or "").strip().lower()
        if hostname:
            domains.append(hostname)
    deduped: List[str] = []
    seen = set()
    for item in domains:
        if item in seen:
            continue
        seen.add(item)
        deduped.append(item)
    return deduped


def get_current_relay_context(expected_domains: Iterable[str] | None = None, last_known_url: str = "") -> Dict[str, object]:
    token = load_gateway_token()
    expected = _normalize_expected_domains(expected_domains, last_known_url)
    if not token:
        return {
            "ok": False,
            "status": "missing_gateway_token",
            "expected_domains": expected,
            "last_known_url": last_known_url,
        }

    body = {
        "profile": "chrome-relay",
        "kind": "evaluate",
        "fn": """() => ({
  href: location.href,
  title: document.title || '',
  readyState: document.readyState || '',
})""",
    }
    try:
        response = browser_control_post(token, "/act", body, timeout=15)
    except (urllib.error.URLError, urllib.error.HTTPError, json.JSONDecodeError) as exc:
        return {
            "ok": False,
            "status": "relay_context_probe_failed",
            "error": str(exc),
            "expected_domains": expected,
            "last_known_url": last_known_url,
        }

    result = response.get("result", {}) if isinstance(response, dict) else {}
    page_url = ""
    if isinstance(result, dict):
        page_url = str(result.get("href", "") or result.get("url", "")).strip()
    if not page_url:
        page_url = str(response.get("url", "")).strip() if isinstance(response, dict) else ""
    target_id = str(response.get("targetId", "")).strip() if isinstance(response, dict) else ""
    matched_domain = ""
    lowered_url = page_url.lower()
    for domain in expected:
        if domain and domain in lowered_url:
            matched_domain = domain
            break
    matched = bool(matched_domain or not expected)
    return {
        "ok": bool(target_id and page_url and matched),
        "status": "browser_channel_recovered" if target_id and page_url and matched else "relay_context_mismatch",
        "target_id": target_id,
        "page_url": page_url,
        "title": str(result.get("title", "")).strip() if isinstance(result, dict) else "",
        "ready_state": str(result.get("readyState", "")).strip() if isinstance(result, dict) else "",
        "expected_domains": expected,
        "matched_domain": matched_domain,
        "last_known_url": last_known_url,
    }


def recover_browser_channel(task_id: str, expected_domains: Iterable[str] | None = None, last_known_url: str = "") -> Dict[str, object]:
    result = {
        "task_id": task_id,
        **get_current_relay_context(expected_domains=expected_domains, last_known_url=last_known_url),
    }
    _write_json(BROWSER_CHANNELS_ROOT / f"{task_id}.json", result)
    return result
