#!/usr/bin/env python3

from __future__ import annotations

import argparse
import json
import os
import subprocess
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo


PROJECT_ROOT = Path("/Users/mac_claw/.openclaw/workspace/projects/neosgo-marketing-suite")
OPENCLAW_BIN = "/opt/homebrew/bin/openclaw"
DEFAULT_CHAT = "8528973600"
DEFAULT_PATH = "/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin"
REPORTS_DIR = PROJECT_ROOT / "reports" / "marketing-automation-suite"
RAW_IMPORT_PATH = PROJECT_ROOT / "data" / "raw-imports" / "discovered-google-maps-places.json"
STRATEGY_READY_PATH = PROJECT_ROOT / "output" / "prospect-data-engine" / "strategy-ready-seeds.json"
CRAWL_STATE_PATH = PROJECT_ROOT / "runtime" / "prospect-data-engine" / "google-maps-crawl-state.json"
STATE_PATH = PROJECT_ROOT / "runtime" / "prospect-data-engine" / "daily-telegram-state.json"
OUTREACH_EVENTS_PATH = PROJECT_ROOT / "runtime" / "outreach" / "events.jsonl"
OUTREACH_STATE_PATH = PROJECT_ROOT / "runtime" / "outreach" / "state.json"
TZ_NY = ZoneInfo("America/New_York")
NEW_ENGLAND_STATES = ["RI", "MA", "CT", "NH", "ME", "VT"]


def _subprocess_env() -> dict[str, str]:
    env = os.environ.copy()
    env["PATH"] = f"{DEFAULT_PATH}:{env.get('PATH', '')}".strip(":")
    return env


def _read_json(path: Path, default):
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default


def _write_json(path: Path, payload) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _send(chat_id: str, text: str) -> dict:
    proc = subprocess.run(
        [OPENCLAW_BIN, "message", "send", "--channel", "telegram", "--target", chat_id, "--message", text, "--json"],
        capture_output=True,
        text=True,
        timeout=120,
        env=_subprocess_env(),
        check=False,
    )
    return {"returncode": proc.returncode, "stdout": proc.stdout.strip(), "stderr": proc.stderr.strip()}


def _load_reports() -> list[dict]:
    reports = []
    for path in sorted(REPORTS_DIR.glob("*.json")):
        payload = _read_json(path, {})
        if not payload:
            continue
        ran_at = str(payload.get("ran_at") or "").strip()
        if not ran_at:
            continue
        try:
            ran_dt = datetime.fromisoformat(ran_at.replace("Z", "+00:00")).astimezone(TZ_NY)
        except ValueError:
            continue
        reports.append({"path": path, "payload": payload, "ran_at_ny": ran_dt})
    reports.sort(key=lambda item: item["ran_at_ny"])
    return reports


def _report_discovered_count(report_payload: dict) -> int:
    steps = dict(report_payload.get("steps") or {})
    payload = dict((steps.get("google_maps_discovery") or {}).get("payload") or {})
    return int(payload.get("discovered_count") or 0)


def _state_counts_from_raw() -> dict[str, int]:
    payload = _read_json(RAW_IMPORT_PATH, {"items": []})
    counts = {state: 0 for state in NEW_ENGLAND_STATES}
    for item in payload.get("items", []) or []:
        state = str(item.get("geo", "")).split("/", 1)[0].strip().upper()
        if state in counts:
            counts[state] += 1
    return counts


def _approved_counts() -> dict[str, int]:
    payload = _read_json(STRATEGY_READY_PATH, {"items": []})
    counts = {state: 0 for state in NEW_ENGLAND_STATES}
    for item in payload.get("items", []) or []:
        if str(item.get("source_family") or "") != "google_maps_places":
            continue
        if str(item.get("fit_precheck_status") or "") != "approved":
            continue
        state = str(item.get("geo", "")).split("/", 1)[0].strip().upper()
        if state in counts:
            counts[state] += 1
    return counts


def _phase_lines() -> tuple[str, list[str]]:
    crawl_state = _read_json(CRAWL_STATE_PATH, {})
    active_phase = str(crawl_state.get("active_phase") or "unknown")
    complete = bool(crawl_state.get("new_england_complete"))
    stats = dict(crawl_state.get("state_stats") or {})
    raw_counts = _state_counts_from_raw()
    approved_counts = _approved_counts()
    lines = []
    for state in NEW_ENGLAND_STATES:
        detail = dict(stats.get(state) or {})
        successful_queries = int(detail.get("successful_queries") or 0)
        total_queries = int(detail.get("total_queries") or 0)
        stabilization = int(detail.get("stable_no_growth_runs") or 0)
        stabilization_needed = int(detail.get("stabilization_runs_required") or 2)
        lines.append(
            f"- {state}：已抓到 {raw_counts[state]} 家，符合当前标准 {approved_counts[state]} 家；"
            f"查询进度 {successful_queries}/{total_queries}；稳定观察 {stabilization}/{stabilization_needed}"
        )
    phase_text = "新英格兰阶段已完成，后续会自动开始剩余州。" if complete else f"当前还在 {active_phase} 阶段，新英格兰 6 州还没有全部跑完。"
    return phase_text, lines


def _parse_event_time(raw: str) -> datetime | None:
    value = str(raw or "").strip()
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(TZ_NY)
    except ValueError:
        return None


def _today_failure_lines(now_ny: datetime) -> list[str]:
    if not OUTREACH_EVENTS_PATH.exists():
        return []
    outreach_state = _read_json(OUTREACH_STATE_PATH, {"targets": {}})
    targets = dict(outreach_state.get("targets") or {})
    lines: list[str] = []
    seen: set[tuple[str, str]] = set()
    for raw in OUTREACH_EVENTS_PATH.read_text(encoding="utf-8").splitlines():
        if not raw.strip():
            continue
        try:
            event = json.loads(raw)
        except json.JSONDecodeError:
            continue
        if str(event.get("type") or "") not in {"email_failed", "contact_form_failed", "contact_form_failed_email_deferred"}:
            continue
        event_time = _parse_event_time(str(event.get("at") or ""))
        if not event_time or event_time.date() != now_ny.date():
            continue
        key = str(event.get("key") or "")
        event_type = str(event.get("type") or "")
        dedupe_key = (key, event_type)
        if dedupe_key in seen:
            continue
        seen.add(dedupe_key)
        target = dict(targets.get(key) or {})
        website = str(target.get("website") or "").strip()
        result = dict(event.get("result") or {})
        reason = str(result.get("reason") or target.get("reason") or "未知原因").strip()
        form_reason = str(result.get("form_reason") or "").strip()
        errors = [str(error).strip() for error in list(result.get("errors") or []) if str(error).strip()]
        detail_parts = [reason] if reason else []
        if form_reason:
            detail_parts.append(f"表单原因：{form_reason}")
        if errors:
            detail_parts.append(f"错误：{'; '.join(errors[:3])}")
        detail = "；".join(part for part in detail_parts if part) or "未知原因"
        lines.append(f"- {event.get('company_name') or '未知公司'} | {website or '无网站'} | {detail}")
    return lines


def _build_text() -> tuple[str, dict]:
    now_ny = datetime.now(TZ_NY)
    reports = _load_reports()
    latest = reports[-1] if reports else None
    latest_count = _report_discovered_count(latest["payload"]) if latest else 0

    yesterday_date = now_ny.date().fromordinal(now_ny.date().toordinal() - 1)
    yesterday_reports = [item for item in reports if item["ran_at_ny"].date() == yesterday_date]
    yesterday_latest = yesterday_reports[-1] if yesterday_reports else None
    yesterday_count = _report_discovered_count(yesterday_latest["payload"]) if yesterday_latest else 0
    delta = latest_count - yesterday_count if yesterday_latest else 0

    phase_text, state_lines = _phase_lines()
    failure_lines = _today_failure_lines(now_ny)
    text = (
        "NEOSGO 潜在客户采集日报\n"
        f"生成时间（纽约）：{now_ny.strftime('%Y-%m-%d %H:%M:%S')}\n"
        f"Google Maps 累计抓到的潜在客户：{latest_count} 家\n"
        f"比昨天新增：{delta} 家\n"
        f"{phase_text}\n"
        "新英格兰 6 州当前进度：\n"
        + "\n".join(state_lines)
    )
    if failure_lines:
        text += "\n\n今日触达失败公司清单：\n" + "\n".join(failure_lines)
    else:
        text += "\n\n今日触达失败公司清单：今天暂无失败记录。"
    metadata = {
        "generated_at_ny": now_ny.isoformat(),
        "latest_count": latest_count,
        "yesterday_count": yesterday_count,
        "delta_vs_yesterday": delta,
        "latest_report": str(latest["path"]) if latest else "",
        "yesterday_report": str(yesterday_latest["path"]) if yesterday_latest else "",
        "today_failure_count": len(failure_lines),
    }
    return text, metadata


def main() -> int:
    parser = argparse.ArgumentParser(description="Send NEOSGO daily lead collection summary to Telegram.")
    parser.add_argument("--chat-id", default=os.environ.get("NEOSGO_OUTREACH_CHAT", DEFAULT_CHAT))
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()

    text, metadata = _build_text()
    state = _read_json(STATE_PATH, {})
    today_key = str(metadata.get("generated_at_ny", ""))[:10]
    if not args.force and str(state.get("last_date_ny") or "") == today_key:
        print(json.dumps({"ok": True, "skipped": True, "reason": "already_sent_today"}, ensure_ascii=False))
        return 0

    delivery = _send(args.chat_id, text)
    _write_json(
        STATE_PATH,
        {
            "last_date_ny": today_key,
            "last_generated_at_ny": metadata.get("generated_at_ny"),
            "metadata": metadata,
            "delivery": delivery,
        },
    )
    print(json.dumps({"ok": True, "metadata": metadata, "delivery": delivery}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
