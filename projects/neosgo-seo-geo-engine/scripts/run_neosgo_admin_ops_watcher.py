#!/usr/bin/env python3
# RULES-FIRST NOTICE:
# Before modifying this file, first read:
# - `JINCLAW_CONSTITUTION.md`
# - `AI_OPTIMIZATION_FRAMEWORK.md`
# Follow the constitution and framework:
# brain-first, one-doctor, fail-closed, evidence-over-narration,
# validate locally, then use the required PR workflow.
from __future__ import annotations

import argparse
import base64
import json
import os
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any


ENV_PATH = Path("/Users/mac_claw/.config/openclaw/env/neosgo-admin-ops.env")
CURSOR_PATH = Path("/Users/mac_claw/.config/openclaw/state/neosgo-admin-ops-events.cursor")
OPENCLAW_BIN = "/opt/homebrew/bin/openclaw"
DEFAULT_BASE_URL = "https://mc.neosgo.com"
DEFAULT_CHAT = "8528973600"
DEFAULT_POLL_INTERVAL = 60
DEFAULT_PATH = "/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin"


class OpsWatcherError(RuntimeError):
    pass


class OpsWatcherHttpError(OpsWatcherError):
    def __init__(self, path: str, status_code: int, raw: str) -> None:
        super().__init__(f"GET {path} failed with {status_code}: {raw}")
        self.path = path
        self.status_code = status_code
        self.raw = raw


class OpsWatcherTransientNetworkError(OpsWatcherError):
    pass


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _read_env(path: Path) -> dict[str, str]:
    data: dict[str, str] = {}
    if not path.exists():
        return data
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        data[key.strip()] = value.strip()
    return data


def _subprocess_env() -> dict[str, str]:
    env = os.environ.copy()
    env["PATH"] = f"{DEFAULT_PATH}:{env.get('PATH', '')}".strip(":")
    return env


def _ensure_parent(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)


def _read_cursor(path: Path) -> str:
    if not path.exists():
        return ""
    return path.read_text(encoding="utf-8").strip()


def _write_cursor(path: Path, cursor: str) -> None:
    _ensure_parent(path)
    path.write_text(cursor.strip(), encoding="utf-8")


def _safe_request(base_url: str, bearer_token: str, path: str) -> dict[str, Any]:
    url = base_url.rstrip("/") + path
    req = urllib.request.Request(
        url,
        headers={
            "Authorization": f"Bearer {bearer_token}",
            "Accept": "application/json",
        },
        method="GET",
    )
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            raw = resp.read().decode("utf-8", errors="replace")
            return json.loads(raw) if raw.strip() else {}
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode("utf-8", errors="replace")
        raise OpsWatcherHttpError(path, exc.code, raw) from exc
    except urllib.error.URLError as exc:
        raise OpsWatcherError(f"GET {path} network error: {exc}") from exc


def _request_with_retries(
    base_url: str,
    bearer_token: str,
    path: str,
    *,
    retries: int = 2,
    retryable_status_codes: tuple[int, ...] = (500, 502, 503, 504),
) -> dict[str, Any]:
    attempt = 0
    while True:
        try:
            return _safe_request(base_url, bearer_token, path)
        except OpsWatcherHttpError as exc:
            if exc.status_code not in retryable_status_codes or attempt >= retries:
                raise
            time.sleep(min(2**attempt, 4))
            attempt += 1
        except OpsWatcherError as exc:
            message = str(exc).lower()
            transient_markers = (
                "network error",
                "handshake operation timed out",
                "timed out",
                "temporary failure in name resolution",
                "nodename nor servname provided",
                "connection reset",
                "connection refused",
                "connection aborted",
                "no route to host",
            )
            if not any(marker in message for marker in transient_markers) or attempt >= retries:
                raise
            time.sleep(min(2**attempt, 4))
            attempt += 1


def _items_from_payload(payload: dict[str, Any]) -> list[dict[str, Any]]:
    data = payload.get("data")
    if isinstance(data, dict):
        items = data.get("items")
        if isinstance(items, list):
            return [item for item in items if isinstance(item, dict)]
    return []


def _next_cursor_from_payload(payload: dict[str, Any]) -> str:
    data = payload.get("data")
    if isinstance(data, dict):
        value = data.get("nextCursor")
        if isinstance(value, str):
            return value.strip()
    return ""


def _decode_cursor(cursor: str) -> dict[str, Any]:
    text = str(cursor or "").strip()
    if not text:
        return {}
    padding = "=" * (-len(text) % 4)
    try:
        raw = base64.urlsafe_b64decode((text + padding).encode("utf-8")).decode("utf-8", errors="replace")
        payload = json.loads(raw)
        return payload if isinstance(payload, dict) else {}
    except Exception:
        return {}


def _parse_datetime(value: str) -> datetime | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None


def _filter_items_after_cursor(items: list[dict[str, Any]], saved_cursor: str) -> list[dict[str, Any]]:
    cursor_meta = _decode_cursor(saved_cursor)
    cursor_created_at = _parse_datetime(str(cursor_meta.get("createdAt") or ""))
    if not cursor_created_at:
        return items
    filtered: list[dict[str, Any]] = []
    for item in items:
        item_created_at = _parse_datetime(str(item.get("createdAt") or ""))
        if item_created_at and item_created_at > cursor_created_at:
            filtered.append(item)
    return filtered


def _events_request_path(saved_cursor: str) -> str:
    if saved_cursor:
        return f"/api/automation/admin/ops/events?after={urllib.parse.quote(saved_cursor, safe='')}&limit=100"
    return "/api/automation/admin/ops/events?limit=20"


def _poll_events(base_url: str, token: str, saved_cursor: str) -> tuple[str, dict[str, Any], bool]:
    path = _events_request_path(saved_cursor)
    try:
        payload = _request_with_retries(base_url, token, path)
        return path, payload, False
    except OpsWatcherHttpError as exc:
        if saved_cursor and exc.status_code in (400, 404, 410):
            fallback_path = "/api/automation/admin/ops/events?limit=20"
            payload = _request_with_retries(base_url, token, fallback_path)
            return fallback_path, payload, True
        raise


def _format_money(value: Any) -> str:
    try:
        amount = float(value)
    except Exception:
        return ""
    return f"${amount:,.2f}"


def _parse_created_at(value: str) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    try:
        dt = datetime.fromisoformat(text.replace("Z", "+00:00"))
        return dt.astimezone().strftime("%m-%d %H:%M")
    except ValueError:
        return text


def _line_for_event(event: dict[str, Any]) -> str:
    event_key = str(event.get("eventKey") or "").strip()
    title = str(event.get("title") or "").strip()
    message = str(event.get("message") or "").strip()
    payload = dict(event.get("payload") or {})
    created_at = _parse_created_at(str(event.get("createdAt") or ""))
    link_url = str(event.get("linkUrl") or "").strip()

    detail = ""
    if event_key == "order.created":
        order_number = str(payload.get("orderNumber") or "").strip()
        buyer_name = str(payload.get("buyerName") or "").strip()
        amount = _format_money(payload.get("totalAmount"))
        parts = ["有新订单"]
        if order_number:
            parts.append(f"订单号 {order_number}")
        if amount:
            parts.append(f"金额 {amount}")
        if buyer_name:
            parts.append(f"买家 {buyer_name}")
        detail = "，".join(parts)
    elif event_key == "inquiry.created":
        subject = str(payload.get("subject") or "").strip()
        sender_name = str(payload.get("senderName") or "").strip()
        sender_email = str(payload.get("senderEmail") or "").strip()
        parts = ["有新的客户咨询"]
        if subject:
            parts.append(f"主题“{subject}”")
        if sender_name:
            parts.append(f"来自 {sender_name}")
        if sender_email:
            parts.append(sender_email)
        detail = "，".join(parts)
    elif event_key == "seller.application_submitted":
        business_name = str(payload.get("businessName") or payload.get("sellerBusinessName") or "").strip()
        contact_email = str(payload.get("contactEmail") or payload.get("email") or "").strip()
        parts = ["有新的卖家入驻申请"]
        if business_name:
            parts.append(business_name)
        if contact_email:
            parts.append(contact_email)
        detail = "，".join(parts)
    elif event_key == "product.submitted":
        product_name = str(payload.get("productName") or payload.get("name") or "").strip()
        sku = str(payload.get("sku") or "").strip()
        seller_business_name = str(payload.get("sellerBusinessName") or payload.get("businessName") or "").strip()
        parts = ["有新的产品提交审核"]
        if product_name:
            parts.append(product_name)
        if sku:
            parts.append(f"SKU {sku}")
        if seller_business_name:
            parts.append(seller_business_name)
        detail = "，".join(parts)
    elif event_key == "payout.requested":
        seller_business_name = str(payload.get("sellerBusinessName") or payload.get("businessName") or "").strip()
        amount = _format_money(payload.get("amount"))
        parts = ["有新的卖家提现申请"]
        if seller_business_name:
            parts.append(seller_business_name)
        if amount:
            parts.append(f"金额 {amount}")
        detail = "，".join(parts)
    elif event_key == "order.tracking_exception":
        order_number = str(payload.get("orderNumber") or "").strip()
        issue = str(payload.get("issueSummary") or payload.get("summary") or title or message).strip()
        parts = ["有订单物流异常"]
        if order_number:
            parts.append(f"订单号 {order_number}")
        if issue:
            parts.append(issue)
        detail = "，".join(parts)
    else:
        detail = f"有新的后台事件，{title or message or event_key or '请查看后台'}"

    suffix_parts = []
    if created_at:
        suffix_parts.append(created_at)
    if link_url:
        suffix_parts.append(link_url)
    if suffix_parts:
        detail = f"{detail}。{' | '.join(suffix_parts)}"
    return detail


def _build_event_message(items: list[dict[str, Any]]) -> str:
    ordered = sorted(items, key=lambda item: str(item.get("createdAt") or ""))
    lines = ["新提醒："]
    for idx, item in enumerate(ordered[:8], start=1):
        lines.append(f"{idx}. {_line_for_event(item)}")
    extra = len(ordered) - 8
    if extra > 0:
        lines.append(f"另有 {extra} 条新事件，请到后台查看。")
    return "\n".join(lines)


def _send_telegram(chat_id: str, text: str) -> dict[str, Any]:
    proc = subprocess.run(
        [OPENCLAW_BIN, "message", "send", "--channel", "telegram", "--target", chat_id, "--message", text, "--json"],
        capture_output=True,
        text=True,
        timeout=120,
        env=_subprocess_env(),
        check=False,
    )
    return {
        "returncode": proc.returncode,
        "stdout": proc.stdout.strip(),
        "stderr": proc.stderr.strip(),
    }


def _host_from_base_url(base_url: str) -> str:
    parsed = urllib.parse.urlparse(base_url)
    return parsed.hostname or ""


def _network_diagnostics(base_url: str) -> dict[str, Any]:
    host = _host_from_base_url(base_url)
    diag: dict[str, Any] = {"host": host}
    if not host:
        return diag
    try:
        infos = socket.getaddrinfo(host, 443, proto=socket.IPPROTO_TCP)
        addresses = sorted({info[4][0] for info in infos if info[4]})
        diag["dns_ok"] = True
        diag["resolved_addresses"] = addresses[:4]
    except Exception as exc:
        diag["dns_ok"] = False
        diag["dns_error"] = str(exc)
    return diag


def _poll_once(env: dict[str, str]) -> dict[str, Any]:
    base_url = env.get("NEOSGO_ADMIN_BASE_URL") or DEFAULT_BASE_URL
    token = env.get("NEOSGO_ADMIN_AUTOMATION_KEY", "").strip()
    chat_id = env.get("TELEGRAM_CHAT_ID") or DEFAULT_CHAT
    if not token:
        raise OpsWatcherError("missing env key: NEOSGO_ADMIN_AUTOMATION_KEY")

    _ensure_parent(CURSOR_PATH)
    if not CURSOR_PATH.exists():
        CURSOR_PATH.write_text("", encoding="utf-8")
    saved_cursor = _read_cursor(CURSOR_PATH)
    try:
        path, payload, cursor_recovered = _poll_events(base_url, token, saved_cursor)
    except OpsWatcherError as exc:
        message = str(exc).lower()
        transient_markers = (
            "network error",
            "handshake operation timed out",
            "timed out",
            "temporary failure in name resolution",
            "nodename nor servname provided",
            "connection reset",
            "connection refused",
            "connection aborted",
            "no route to host",
        )
        if any(marker in message for marker in transient_markers):
            return {
                "ok": True,
                "degraded": True,
                "error": str(exc),
                "saved_cursor_present": bool(saved_cursor),
                "cursor_updated": False,
                "cursor_recovered": False,
                "telegram_sent": False,
                "network_diagnostics": _network_diagnostics(base_url),
            }
        raise
    items = _items_from_payload(payload)
    next_cursor = _next_cursor_from_payload(payload)
    if cursor_recovered:
        items = _filter_items_after_cursor(items, saved_cursor)
    result: dict[str, Any] = {
        "ok": True,
        "path": path,
        "saved_cursor_present": bool(saved_cursor),
        "items_count": len(items),
        "next_cursor_present": bool(next_cursor),
        "cursor_updated": False,
        "cursor_recovered": cursor_recovered,
        "telegram_sent": False,
    }

    if items:
        text = _build_event_message(items)
        delivery = _send_telegram(chat_id, text)
        result["delivery"] = delivery
        if delivery["returncode"] != 0:
            result["ok"] = False
            result["error"] = "telegram_send_failed"
            return result
        result["telegram_sent"] = True

    if next_cursor:
        _write_cursor(CURSOR_PATH, next_cursor)
        result["cursor_updated"] = True
    return result


def _format_top_list(items: Any, key_name: str, value_name: str, fallback_name: str) -> str:
    rows = [item for item in list(items or []) if isinstance(item, dict)]
    parts: list[str] = []
    for row in rows[:5]:
        label = str(row.get(key_name) or row.get("label") or fallback_name).strip()
        value = row.get(value_name)
        if value in (None, ""):
            parts.append(label)
        else:
            parts.append(f"{label} {value}")
    return "、".join(parts) or "暂无"


def _daily_report(env: dict[str, str], from_date: str, to_date: str) -> dict[str, Any]:
    base_url = env.get("NEOSGO_ADMIN_BASE_URL") or DEFAULT_BASE_URL
    token = env.get("NEOSGO_ADMIN_AUTOMATION_KEY", "").strip()
    chat_id = env.get("TELEGRAM_CHAT_ID") or DEFAULT_CHAT
    if not token:
        raise OpsWatcherError("missing env key: NEOSGO_ADMIN_AUTOMATION_KEY")

    summary = _request_with_retries(base_url, token, f"/api/automation/admin/ops/summary?from={from_date}&to={to_date}")
    analytics = _request_with_retries(base_url, token, f"/api/automation/admin/ops/analytics?from={from_date}&to={to_date}")
    queue = _request_with_retries(base_url, token, "/api/automation/admin/ops/queue")

    summary_data = dict(summary.get("data") or {})
    analytics_data = dict(analytics.get("data") or {})
    queue_data = dict(queue.get("data") or {})

    lines = [
        f"Neosgo 后台日报（{from_date} 到 {to_date}）",
        f"订单总量：{summary_data.get('orderCount') or summary_data.get('orders') or 0}",
        f"队列状态：待处理 {queue_data.get('pending') or 0}，处理中 {queue_data.get('processing') or 0}，失败 {queue_data.get('failed') or 0}",
        f"页面访问量：{analytics_data.get('pageViews') or 0}",
        f"独立访客：{analytics_data.get('uniqueVisitors') or 0}",
        f"平均活跃时长：{analytics_data.get('avgActiveTime') or analytics_data.get('averageActiveTime') or '暂无'}",
        f"热门页面：{_format_top_list(analytics_data.get('topPages'), 'path', 'views', '页面')}",
        f"热门地区：{_format_top_list(analytics_data.get('topRegions'), 'region', 'visitors', '地区')}",
    ]
    text = "\n".join(lines)
    delivery = _send_telegram(chat_id, text)
    return {
        "ok": delivery["returncode"] == 0,
        "delivery": delivery,
        "from": from_date,
        "to": to_date,
    }


def _new_york_yesterday_window() -> tuple[str, str]:
    from zoneinfo import ZoneInfo

    ny_today = datetime.now(ZoneInfo("America/New_York")).date()
    return str(ny_today - timedelta(days=1)), str(ny_today)


def _startup_check(env: dict[str, str]) -> dict[str, Any]:
    base_url = env.get("NEOSGO_ADMIN_BASE_URL") or DEFAULT_BASE_URL
    token = env.get("NEOSGO_ADMIN_AUTOMATION_KEY", "").strip()
    if not token:
        raise OpsWatcherError("missing env key: NEOSGO_ADMIN_AUTOMATION_KEY")

    _ensure_parent(ENV_PATH)
    _ensure_parent(CURSOR_PATH)
    if not CURSOR_PATH.exists():
        CURSOR_PATH.write_text("", encoding="utf-8")
    cursor_before = _read_cursor(CURSOR_PATH)
    _write_cursor(CURSOR_PATH, cursor_before)
    cursor_after = _read_cursor(CURSOR_PATH)

    subscriptions = _request_with_retries(base_url, token, "/api/automation/admin/ops/subscriptions")
    events = _request_with_retries(base_url, token, "/api/automation/admin/ops/events?limit=20")

    return {
        "envFile": str(ENV_PATH),
        "cursorFile": str(CURSOR_PATH),
        "envFileExists": ENV_PATH.exists(),
        "cursorFileExists": CURSOR_PATH.exists(),
        "pollIntervalSeconds": int(env.get("NEOSGO_OPS_POLL_INTERVAL_SECONDS") or DEFAULT_POLL_INTERVAL),
        "apiConnectivity": "ok" if subscriptions.get("success") and events.get("success") else "failed",
        "telegramMode": "send only when there are new events",
        "subscriptionsSuccess": bool(subscriptions.get("success")),
        "eventsSuccess": bool(events.get("success")),
        "cursorReadWriteOk": cursor_before == cursor_after,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Watch Neosgo admin ops events and alert via Telegram.")
    parser.add_argument("--mode", choices=("poll-once", "startup-check", "daily-report"), default="poll-once")
    parser.add_argument("--from-date")
    parser.add_argument("--to-date")
    args = parser.parse_args()

    env = _read_env(ENV_PATH)
    try:
        if args.mode == "startup-check":
            print(json.dumps(_startup_check(env), ensure_ascii=False, indent=2))
            return 0
        if args.mode == "daily-report":
            default_from, default_to = _new_york_yesterday_window()
            from_date = args.from_date or default_from
            to_date = args.to_date or default_to
            result = _daily_report(env, from_date, to_date)
            print(json.dumps(result, ensure_ascii=False, indent=2))
            return 0 if result.get("ok") else 1
        result = _poll_once(env)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0 if result.get("ok") else 1
    except OpsWatcherError as exc:
        print(json.dumps({"ok": False, "error": str(exc), "at": _now_iso()}, ensure_ascii=False, indent=2), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
