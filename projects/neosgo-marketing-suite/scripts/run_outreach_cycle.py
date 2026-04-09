#!/usr/bin/env python3

from __future__ import annotations

import argparse
import csv
import json
import os
import re
import subprocess
import sys
import textwrap
from datetime import datetime, timezone
from pathlib import Path
from urllib import error as urllib_error
from urllib import request as urllib_request
from urllib.parse import urlparse
from typing import Any


WORKSPACE_ROOT = Path("/Users/mac_claw/.openclaw/workspace")
PROJECT_ROOT = WORKSPACE_ROOT / "projects" / "neosgo-marketing-suite"
OPENCLAW_BIN = "/opt/homebrew/bin/openclaw"
DEFAULT_CHAT = "8528973600"
DEFAULT_PATH = "/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin"
CONTACTS_PATH = PROJECT_ROOT / "data" / "raw-imports" / "discovered-google-maps-validated-contacts.json"
STATE_PATH = PROJECT_ROOT / "runtime" / "outreach" / "state.json"
EVENTS_PATH = PROJECT_ROOT / "runtime" / "outreach" / "events.jsonl"
LATEST_SUMMARY_PATH = PROJECT_ROOT / "runtime" / "outreach" / "latest-summary.json"
REVIEW_QUEUE_PATH = PROJECT_ROOT / "runtime" / "outreach" / "review-queue.json"
REVIEW_TEMPLATE_PATH = PROJECT_ROOT / "runtime" / "outreach" / "review-decisions.template.json"
CAPTCHA_QUEUE_PATH = PROJECT_ROOT / "runtime" / "outreach" / "captcha-queue.json"
CAPTCHA_TEMPLATE_PATH = PROJECT_ROOT / "runtime" / "outreach" / "captcha-decisions.template.json"
TELEGRAM_REPLY_STATE_PATH = PROJECT_ROOT / "runtime" / "outreach" / "telegram-reply-state.json"
CONTENT_PATH = PROJECT_ROOT / "config" / "outreach-campaign-content.yaml"
OUTREACH_ENV_PATH = PROJECT_ROOT / ".env.outreach"
FORM_ADAPTERS_PATH = PROJECT_ROOT / "config" / "outreach-form-adapters.json"
MAIL_BATCH_SCRIPT = WORKSPACE_ROOT / "skills" / "neosgo-lead-engine" / "scripts" / "send_outreach_mail_batch.py"
PLAYWRIGHT_PYTHON = WORKSPACE_ROOT / "tools" / "matrix-venv" / "bin" / "python"
TELEGRAM_INGRESS_PATH = WORKSPACE_ROOT / "tools" / "openmoss" / "runtime" / "autonomy" / "ingress" / "telegram.jsonl"
PLAYWRIGHT_PROFILE_DIR = PROJECT_ROOT / "runtime" / "outreach" / "playwright-profile"
STATE_PRIORITY = ["RI", "MA", "CT", "NH", "ME", "VT"]
SUCCESS_TEXT_RE = re.compile(
    r"(thank you|thanks for reaching out|message sent|we('|\u2019)?ll be in touch|we will be in touch|successfully submitted|request has been sent)",
    re.I,
)
ERROR_TEXT_RE = re.compile(
    r"(required|invalid|error sending your message|please try again later|submission failed|captcha|please complete|please fill|antispam token is invalid)",
    re.I,
)
PLACEHOLDER_HINT_RE = re.compile(r"Fill .* here if you want it to differ", re.I)


def _subprocess_env() -> dict[str, str]:
    env = os.environ.copy()
    env["PATH"] = f"{DEFAULT_PATH}:{env.get('PATH', '')}".strip(":")
    return env


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _read_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return default


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _append_event(event: dict[str, Any]) -> None:
    EVENTS_PATH.parent.mkdir(parents=True, exist_ok=True)
    with EVENTS_PATH.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(event, ensure_ascii=False) + "\n")


def _yaml_to_json(path: Path) -> dict[str, Any]:
    ruby = textwrap.dedent(
        """
        require 'yaml'
        require 'json'
        data = YAML.load_file(ARGV[0])
        puts JSON.generate(data)
        """
    )
    proc = subprocess.run(
        ["/usr/bin/ruby", "-e", ruby, str(path)],
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
        env=_subprocess_env(),
    )
    if proc.returncode != 0:
        raise RuntimeError(proc.stderr.strip() or proc.stdout.strip() or "yaml parse failed")
    return json.loads(proc.stdout)


def _load_content() -> dict[str, Any]:
    data = _yaml_to_json(CONTENT_PATH)
    sender_identity = dict(data.get("sender_identity") or {})
    message_assets = dict(data.get("message_assets") or {})
    email_defaults = dict(data.get("email_defaults") or {})
    contact_form_defaults = dict(data.get("contact_form_defaults") or {})

    main_body = str(message_assets.get("main_message_body") or "").strip()
    email_body = str(email_defaults.get("body_text") or "").strip()
    form_body = str(contact_form_defaults.get("message") or "").strip()
    if not email_body or PLACEHOLDER_HINT_RE.search(email_body):
        email_defaults["body_text"] = main_body
    if not form_body or PLACEHOLDER_HINT_RE.search(form_body):
        contact_form_defaults["message"] = main_body
    if not email_defaults.get("subject"):
        email_defaults["subject"] = message_assets.get("email_subject") or message_assets.get("primary_subject") or ""
    if not contact_form_defaults.get("subject"):
        contact_form_defaults["subject"] = message_assets.get("contact_form_subject") or message_assets.get("primary_subject") or ""
    return {
        **data,
        "sender_identity": sender_identity,
        "message_assets": message_assets,
        "email_defaults": email_defaults,
        "contact_form_defaults": contact_form_defaults,
    }


def _load_outreach_env() -> dict[str, str]:
    values: dict[str, str] = {}
    if not OUTREACH_ENV_PATH.exists():
        return values
    try:
        lines = OUTREACH_ENV_PATH.read_text(encoding="utf-8").splitlines()
    except OSError:
        return values
    for raw in lines:
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip().strip('"').strip("'")
    return values


def _load_form_adapters() -> dict[str, Any]:
    payload = _read_json(FORM_ADAPTERS_PATH, {"domains": {}})
    return dict(payload or {"domains": {}})


def _normalized_domain(value: str) -> str:
    raw = str(value or "").strip()
    if not raw:
        return ""
    if "://" not in raw:
        raw = f"https://{raw}"
    try:
        host = urlparse(raw).netloc.lower().strip()
    except Exception:
        return ""
    if host.startswith("www."):
        host = host[4:]
    return host


def _adapter_for(item: dict[str, Any], adapters: dict[str, Any]) -> dict[str, Any]:
    domains = dict(adapters.get("domains") or {})
    for candidate in (
        _normalized_domain(str(item.get("contact_form_url") or "")),
        _normalized_domain(str(item.get("website") or "")),
    ):
        if candidate and candidate in domains:
            return dict(domains[candidate] or {})
    return {}


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


def _load_state() -> dict[str, Any]:
    payload = _read_json(
        STATE_PATH,
        {
            "campaign_id": "neosgo-initial-outreach",
            "email_delivery_pending": False,
            "last_email_sent_at": "",
            "targets": {},
            "stats": {},
        },
    )
    payload.setdefault("targets", {})
    payload.setdefault("stats", {})
    payload.setdefault("email_delivery_pending", False)
    payload.setdefault("last_email_sent_at", "")
    return payload


def _parse_iso(raw: str) -> datetime | None:
    value = str(raw or "").strip()
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def _email_send_allowed(state: dict[str, Any], *, min_minutes_between_emails: int) -> bool:
    if bool(state.get("email_delivery_pending")):
        return False
    last = _parse_iso(str(state.get("last_email_sent_at") or ""))
    if not last:
        return True
    elapsed = (datetime.now(timezone.utc) - last).total_seconds()
    return elapsed >= max(0, int(min_minutes_between_emails or 0)) * 60


def _release_pending_email_if_safe(state: dict[str, Any], *, hold_minutes: int) -> dict[str, Any] | None:
    if not bool(state.get("email_delivery_pending")):
        return None
    last = _parse_iso(str(state.get("last_email_sent_at") or ""))
    if not last:
        state["email_delivery_pending"] = False
        return {
            "type": "email_delivery_hold_released",
            "at": _now_iso(),
            "reason": "missing_last_email_sent_at",
        }
    elapsed = (datetime.now(timezone.utc) - last).total_seconds()
    if elapsed < max(0, int(hold_minutes or 0)) * 60:
        return None
    state["email_delivery_pending"] = False
    return {
        "type": "email_delivery_hold_released",
        "at": _now_iso(),
        "reason": "no_failure_detected_within_hold_window",
        "hold_minutes": int(hold_minutes or 0),
        "last_email_sent_at": state.get("last_email_sent_at"),
    }


def _target_key(item: dict[str, Any]) -> str:
    return str(item.get("source_url") or item.get("website") or item.get("company_name") or "").strip()


def _is_email_valid(item: dict[str, Any]) -> bool:
    return str(item.get("email_validation_reason") or "").strip() in {"domain_match", "domain_resolves"}


def _email_is_usable(item: dict[str, Any]) -> bool:
    if not _is_email_valid(item):
        return False
    email = str(item.get("email") or "").strip().lower()
    if not email:
        return False
    blocked = ("godaddy.com", "mysite.com", "example.com", "example.org")
    return not any(email.endswith(f"@{suffix}") for suffix in blocked)


def _is_form_candidate(item: dict[str, Any]) -> bool:
    if not item.get("contact_form_detected"):
        return False
    signals = [str(signal).lower() for signal in list(item.get("contact_form_signals") or [])]
    if "textarea_field" in signals or "contact_like_url" in signals:
        return True
    return False


def _load_candidates() -> list[dict[str, Any]]:
    payload = _read_json(CONTACTS_PATH, {"items": []})
    candidates: list[dict[str, Any]] = []
    for item in payload.get("items", []) or []:
        state = str(item.get("geo", "")).split("/", 1)[0].strip().upper()
        if state not in STATE_PRIORITY:
            continue
        if str(item.get("website_fit_status") or "").strip() != "approved":
            continue
        if not item.get("website"):
            continue
        if not (_is_form_candidate(item) or _email_is_usable(item)):
            continue
        candidates.append(item)

    def sort_key(item: dict[str, Any]) -> tuple[int, int, int, str]:
        state = str(item.get("geo", "")).split("/", 1)[0].strip().upper()
        state_rank = STATE_PRIORITY.index(state) if state in STATE_PRIORITY else 999
        form_rank = 0 if _is_form_candidate(item) else 1
        email_rank = 0 if _email_is_usable(item) else 1
        return (state_rank, form_rank, email_rank, str(item.get("company_name") or ""))

    return sorted(candidates, key=sort_key)


def _select_next_candidate(state: dict[str, Any]) -> dict[str, Any] | None:
    for item in _load_candidates():
        key = _target_key(item)
        target_state = dict((state.get("targets") or {}).get(key) or {})
        if target_state.get("status") in {
            "contact_form_submitted",
            "contact_form_needs_review",
            "contact_form_failed_email_deferred",
            "email_sent_pending_confirmation",
            "email_sent_local_only",
            "email_failed",
            "contact_form_failed",
            "captcha_pending_operator",
            "waiting_reply",
            "review_hold",
            "stopped",
        }:
            continue
        if target_state:
            merged = dict(item)
            for field in (
                "force_channel",
                "form_retry_attempted",
                "captcha_ticket_id",
                "operator_last_reply",
                "operator_resolved_at",
            ):
                if field in target_state:
                    merged[field] = target_state[field]
            return merged
        return item
    return None


def _channel_for(item: dict[str, Any], state: dict[str, Any]) -> str:
    target_state = dict((state.get("targets") or {}).get(_target_key(item)) or {})
    forced = str(target_state.get("force_channel") or "").strip()
    if forced == "contact_form" and _is_form_candidate(item):
        return "contact_form"
    if forced == "email" and _email_is_usable(item) and _email_send_allowed(state, min_minutes_between_emails=5):
        return "email"
    if _is_form_candidate(item):
        return "contact_form"
    if _email_is_usable(item) and _email_send_allowed(state, min_minutes_between_emails=5):
        return "email"
    return "none"


def _target_status_update(item: dict[str, Any], channel: str, status: str, extra: dict[str, Any] | None = None) -> dict[str, Any]:
    preserved = {}
    for field in (
        "force_channel",
        "form_retry_attempted",
        "captcha_ticket_id",
        "operator_last_reply",
        "operator_resolved_at",
    ):
        if field in item:
            preserved[field] = item[field]
    return {
        "company_name": item.get("company_name"),
        "state": str(item.get("geo", "")).split("/", 1)[0].strip().upper(),
        "website": item.get("website"),
        "source_url": item.get("source_url"),
        "channel": channel,
        "status": status,
        "updated_at": _now_iso(),
        **preserved,
        **(extra or {}),
    }


def _suggest_review_action(target: dict[str, Any]) -> str:
    result = dict(target.get("result") or target.get("contact_form_result") or {})
    reason = str(result.get("reason") or "").strip()
    if reason.startswith("submit_click_failed"):
        return "ready_for_form_retry"
    if reason in {"unknown_result", "submission_error"}:
        return "review_hold"
    if reason == "validation_error":
        return "ready_for_email"
    return "review_hold"


def _write_review_artifacts(state: dict[str, Any]) -> None:
    targets = list((state.get("targets") or {}).items())
    items = []
    template_items = []
    for key, target in targets:
        if str(target.get("status") or "") != "contact_form_needs_review":
            continue
        result = dict(target.get("result") or target.get("contact_form_result") or {})
        item = {
            "review_key": key,
            "company_name": target.get("company_name"),
            "state": target.get("state"),
            "website": target.get("website"),
            "contact_form_url": target.get("contact_form_url") or target.get("website"),
            "current_status": target.get("status"),
            "detected_reason": result.get("reason"),
            "detected_errors": result.get("errors") or [],
            "updated_at": target.get("updated_at"),
            "suggested_action": _suggest_review_action(target),
            "sample_text_excerpt": str(result.get("sample_text") or "")[:400],
        }
        items.append(item)
        template_items.append(
            {
                **item,
                "operator_decision": "",
                "operator_notes": "",
                "resolved_at": "",
            }
        )
    _write_json(REVIEW_QUEUE_PATH, {"generated_at": _now_iso(), "items": items})
    _write_json(REVIEW_TEMPLATE_PATH, {"generated_at": _now_iso(), "items": template_items})


def _captcha_ticket_id(target_key: str) -> str:
    key = re.sub(r"[^a-zA-Z0-9]+", "-", target_key).strip("-").lower()
    return f"captcha-{key[:48] or 'unknown'}"


def _write_captcha_artifacts(state: dict[str, Any]) -> None:
    items = []
    template_items = []
    for key, target in list((state.get("targets") or {}).items()):
        if str(target.get("status") or "") != "captcha_pending_operator":
            continue
        result = dict(target.get("result") or target.get("contact_form_result") or {})
        ticket_id = str(target.get("captcha_ticket_id") or _captcha_ticket_id(key))
        item = {
            "ticket_id": ticket_id,
            "review_key": key,
            "company_name": target.get("company_name"),
            "state": target.get("state"),
            "website": target.get("website"),
            "contact_form_url": target.get("contact_form_url") or target.get("website"),
            "current_status": target.get("status"),
            "detected_reason": result.get("reason"),
            "detected_errors": result.get("errors") or [],
            "updated_at": target.get("updated_at"),
            "sample_text_excerpt": str(result.get("sample_text") or "")[:400],
            "next_step": "等待人工处理验证码或人工确认后通过 Telegram 回复结果",
        }
        items.append(item)
        template_items.append(
            {
                **item,
                "operator_decision": "",
                "operator_notes": "",
                "resolved_at": "",
            }
        )
    _write_json(CAPTCHA_QUEUE_PATH, {"generated_at": _now_iso(), "items": items})
    _write_json(CAPTCHA_TEMPLATE_PATH, {"generated_at": _now_iso(), "items": template_items})


def _parse_telegram_reply(text: str) -> dict[str, str] | None:
    raw = str(text or "").strip()
    if not raw:
        return None
    patterns = [
        r"^outreach\s+captcha\s+(?P<ticket>[A-Za-z0-9\-]+)\s+(?P<action>submitted|retry|email|stop)$",
        r"^验证码\s+(?P<ticket>[A-Za-z0-9\-]+)\s+(?P<action>已提交|重试|改邮件|停止)$",
    ]
    for pattern in patterns:
        match = re.match(pattern, raw, re.I)
        if not match:
            continue
        action = str(match.group("action") or "").strip().lower()
        mapping = {
            "submitted": "submitted",
            "retry": "retry",
            "email": "email",
            "stop": "stop",
            "已提交": "submitted",
            "重试": "retry",
            "改邮件": "email",
            "停止": "stop",
        }
        normalized = mapping.get(action)
        if not normalized:
            return None
        return {"ticket_id": str(match.group("ticket") or "").strip(), "action": normalized, "raw_text": raw}
    return None


def _apply_telegram_captcha_reply(state: dict[str, Any], reply: dict[str, str], *, at: str) -> dict[str, Any] | None:
    ticket = str(reply.get("ticket_id") or "").strip()
    action = str(reply.get("action") or "").strip()
    if not ticket or not action:
        return None
    for key, target in list((state.get("targets") or {}).items()):
        if str(target.get("captcha_ticket_id") or "") != ticket:
            continue
        updated = dict(target)
        updated["updated_at"] = at
        updated["operator_last_reply"] = reply.get("raw_text")
        updated["operator_resolved_at"] = at
        if action == "submitted":
            updated["status"] = "contact_form_submitted"
        elif action == "retry":
            updated["status"] = "ready_for_form_retry"
            updated["force_channel"] = "contact_form"
        elif action == "email":
            updated["status"] = "ready_for_email"
            updated["force_channel"] = "email"
        elif action == "stop":
            updated["status"] = "stopped"
        else:
            return None
        state["targets"][key] = updated
        return {
            "type": "captcha_reply_applied",
            "at": at,
            "key": key,
            "company_name": updated.get("company_name"),
            "ticket_id": ticket,
            "action": action,
        }
    return None


def _process_telegram_replies(state: dict[str, Any]) -> list[dict[str, Any]]:
    replies = []
    ingress_path = TELEGRAM_INGRESS_PATH
    if not ingress_path.exists():
        return replies
    reply_state = _read_json(TELEGRAM_REPLY_STATE_PATH, {"last_line": 0})
    last_line = int(reply_state.get("last_line") or 0)
    try:
        lines = ingress_path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return replies
    new_last_line = last_line
    for idx, line in enumerate(lines[last_line:], start=last_line + 1):
        new_last_line = idx
        try:
            payload = json.loads(line)
        except json.JSONDecodeError:
            continue
        parsed = _parse_telegram_reply(str(payload.get("text") or ""))
        if not parsed:
            continue
        event = _apply_telegram_captcha_reply(state, parsed, at=str(payload.get("at") or _now_iso()))
        if event:
            replies.append(event)
    _write_json(TELEGRAM_REPLY_STATE_PATH, {"last_line": new_last_line, "updated_at": _now_iso()})
    return replies


def _refresh_target_routing_from_results(state: dict[str, Any], adapters: dict[str, Any]) -> list[dict[str, Any]]:
    events = []
    for key, target in list((state.get("targets") or {}).items()):
        status = str(target.get("status") or "")
        if status not in {"contact_form_failed_email_deferred", "contact_form_failed"}:
            continue
        result = dict(target.get("contact_form_result") or target.get("result") or {})
        sample_text = str(result.get("sample_text") or "").lower()
        errors = [str(error).lower() for error in list(result.get("errors") or [])]
        adapter = _adapter_for(target, adapters)
        if any("captcha" in error for error in errors) or "confirm you're human" in sample_text or "captcha validation failed" in sample_text:
            ticket_id = str(target.get("captcha_ticket_id") or _captcha_ticket_id(key))
            target["status"] = "captcha_pending_operator"
            target["captcha_ticket_id"] = ticket_id
            target["updated_at"] = _now_iso()
            target["reason"] = "captcha_required_manual_step"
            events.append(
                {
                    "type": "target_rerouted_for_captcha",
                    "at": _now_iso(),
                    "key": key,
                    "company_name": target.get("company_name"),
                    "ticket_id": ticket_id,
                }
            )
            continue
        if adapter and str(result.get("reason") or "") == "validation_error" and not bool(target.get("form_retry_attempted")):
            target["status"] = "ready_for_form_retry"
            target["force_channel"] = "contact_form"
            target["updated_at"] = _now_iso()
            target["reason"] = "adapter_available_for_retry"
            target["form_retry_attempted"] = True
            events.append(
                {
                    "type": "target_rerouted_for_form_retry",
                    "at": _now_iso(),
                    "key": key,
                    "company_name": target.get("company_name"),
                }
            )
    return events


def _form_submission_script() -> str:
    return textwrap.dedent(
        r"""
        from pathlib import Path
        from playwright.sync_api import sync_playwright
        import json, re, sys

        target_url = sys.argv[1]
        payload = json.loads(sys.argv[2])
        adapter = dict(payload.get("_adapter") or {})
        profile_dir = payload.get("_profile_dir") or ""

        def field_score(meta):
            text = " ".join([
                str(meta.get("name") or ""),
                str(meta.get("id") or ""),
                str(meta.get("placeholder") or ""),
                str(meta.get("aria") or ""),
                str(meta.get("label") or ""),
            ]).lower()
            score = 0
            if "message" in text or "comment" in text or "details" in text or "project" in text or "inquiry" in text:
                score += 5
            if "email" in text:
                score += 3
            if "name" in text:
                score += 2
            if "newsletter" in text or "sign up" in text or "signup" in text:
                score -= 6
            return score

        def choose_form(page):
            preferred_selector = str(adapter.get("form_selector") or "").strip()
            if preferred_selector:
                try:
                    preferred = page.locator(preferred_selector).first
                    if preferred.count() > 0:
                        try:
                            preferred.wait_for(timeout=2000)
                        except Exception:
                            pass
                        form_text = ""
                        try:
                            form_text = preferred.inner_text().lower()
                        except Exception:
                            form_text = ""
                        fields = []
                        for sel in ["input", "textarea", "select"]:
                            for el in preferred.locator(sel).all():
                                fields.append(
                                    {
                                        "tag": sel,
                                        "type": (el.get_attribute("type") or ""),
                                        "name": (el.get_attribute("name") or ""),
                                        "id": (el.get_attribute("id") or ""),
                                        "placeholder": (el.get_attribute("placeholder") or ""),
                                        "aria": (el.get_attribute("aria-label") or ""),
                                        "required": bool(el.get_attribute("required")),
                                    }
                                )
                        return (0, preferred, fields, form_text), 100
                except Exception:
                    pass
            best = None
            best_score = -999
            forms = page.locator("form").all()
            for idx, form in enumerate(forms):
                score = 0
                fields = []
                for sel in ["input", "textarea", "select"]:
                    locs = form.locator(sel).all()
                    for el in locs[:50]:
                        meta = {
                            "tag": sel,
                            "type": (el.get_attribute("type") or ""),
                            "name": (el.get_attribute("name") or ""),
                            "id": (el.get_attribute("id") or ""),
                            "placeholder": (el.get_attribute("placeholder") or ""),
                            "aria": (el.get_attribute("aria-label") or ""),
                            "required": bool(el.get_attribute("required")),
                        }
                        fields.append(meta)
                        score += field_score(meta)
                        if sel == "textarea":
                            score += 3
                if any((f.get("type") or "").lower() == "hidden" for f in fields):
                    pass
                form_text = ""
                try:
                    form_text = form.inner_text().lower()
                except Exception:
                    form_text = ""
                if re.search(r"(newsletter|sign up|subscribe)", form_text) and not re.search(r"(message|project|inquiry|contact)", form_text):
                    score -= 8
                if re.search(r"\d+\s*[\+\-]\s*\d+\s*=", form_text):
                    score += 1
                if score > best_score:
                    best = (idx, form, fields, form_text)
                    best_score = score
            return best, best_score

        def pick_value(meta):
            text = " ".join([
                str(meta.get("name") or ""),
                str(meta.get("id") or ""),
                str(meta.get("placeholder") or ""),
                str(meta.get("aria") or ""),
                str(meta.get("label") or ""),
            ]).lower()
            if "first" in text and "name" in text:
                return payload["first_name"]
            if "last" in text and "name" in text:
                return payload["last_name"]
            if "name" in text:
                return payload["full_name"]
            if "email" in text:
                return payload["email"]
            if "phone" in text or "tel" in text:
                return payload["phone"]
            if "company" in text or "business" in text or "organization" in text:
                return payload["company"]
            if "website" in text or "url" in text:
                return payload["website"]
            if "subject" in text or "topic" in text:
                return payload["subject"]
            if "address" in text:
                return payload["address_line_1"]
            if text.endswith("city") or " city" in text:
                return payload["city"]
            if "state" in text or "province" in text:
                return payload["state"]
            if "zip" in text or "postal" in text:
                return payload["postal_code"]
            if "country" in text:
                return payload["country"]
            if "message" in text or "comment" in text or "details" in text or "project" in text or "inquiry" in text:
                return payload["message"]
            return ""

        def visible_text(locator):
            try:
                return " ".join((locator.inner_text() or "").split())
            except Exception:
                return ""

        def closest_field_text(el):
            selectors = [
                "xpath=ancestor::*[self::li or self::fieldset or self::div][1]",
                "xpath=ancestor::form[1]",
            ]
            for selector in selectors:
                try:
                    node = el.locator(selector).first
                    text = visible_text(node)
                    if text:
                        return text
                except Exception:
                    continue
            return ""

        def match_rule(rule_text, haystack):
            return str(rule_text or "").strip().lower() in str(haystack or "").strip().lower()

        def apply_adapter_checkboxes(form):
            checkbox_rules = list(adapter.get("checkbox_rules") or [])
            applied = []
            if not checkbox_rules:
                return applied
            for rule in checkbox_rules:
                group_hint = str(rule.get("group_hint") or "")
                option_label = str(rule.get("option_label") or "")
                if not group_hint or not option_label:
                    continue
                for box in form.locator("input[type=checkbox]").all():
                    field_text = closest_field_text(box)
                    label_text = ""
                    try:
                        box_id = box.get_attribute("id") or ""
                        if box_id:
                            label_text = visible_text(form.locator(f"label[for='{box_id}']").first)
                    except Exception:
                        label_text = ""
                    if not match_rule(group_hint, field_text):
                        continue
                    if not match_rule(option_label, label_text + " " + field_text):
                        continue
                    try:
                        box.check(force=True)
                        applied.append({"group_hint": group_hint, "option_label": option_label})
                        break
                    except Exception:
                        continue
            return applied

        def apply_adapter_selects(form):
            select_rules = list(adapter.get("select_rules") or [])
            applied = []
            if not select_rules:
                return applied
            for rule in select_rules:
                label_hint = str(rule.get("label_hint") or "")
                option_label = str(rule.get("option_label") or "")
                if not label_hint or not option_label:
                    continue
                for el in form.locator("select").all():
                    field_text = closest_field_text(el)
                    if not match_rule(label_hint, field_text):
                        continue
                    try:
                        el.select_option(label=option_label)
                        applied.append({"label_hint": label_hint, "option_label": option_label})
                        break
                    except Exception:
                        try:
                            options = [o.strip() for o in el.locator("option").all_inner_texts()]
                            for option in options:
                                if match_rule(option_label, option):
                                    el.select_option(label=option)
                                    applied.append({"label_hint": label_hint, "option_label": option})
                                    raise StopIteration
                        except StopIteration:
                            break
                        except Exception:
                            continue
            return applied

        def fill_captcha(form, form_text):
            match = re.search(r"(\d+)\s*([+\-])\s*(\d+)\s*=", form_text or "")
            if not match:
                return False
            left = int(match.group(1))
            op = match.group(2)
            right = int(match.group(3))
            answer = str(left + right if op == "+" else left - right)
            for el in form.locator("input").all():
                name = (el.get_attribute("name") or "").lower()
                typ = (el.get_attribute("type") or "").lower()
                if typ == "hidden":
                    continue
                joined = " ".join([name, (el.get_attribute("id") or "").lower(), (el.get_attribute("placeholder") or "").lower()])
                if "captcha" in joined or "quiz" in joined:
                    try:
                        el.fill(answer)
                        return True
                    except Exception:
                        continue
            return False

        def human_pause(page, low=250, high=650):
            try:
                import random
                page.wait_for_timeout(random.randint(low, high))
            except Exception:
                try:
                    page.wait_for_timeout(low)
                except Exception:
                    pass

        def warm_page(page):
            try:
                page.mouse.move(240, 180)
                human_pause(page, 250, 450)
                page.mouse.move(520, 340)
                human_pause(page, 180, 320)
                page.mouse.wheel(0, 420)
                human_pause(page, 350, 700)
                page.mouse.wheel(0, -180)
                human_pause(page, 250, 450)
            except Exception:
                pass

        def human_fill(el, value):
            try:
                el.click()
            except Exception:
                pass
            try:
                el.fill("")
            except Exception:
                pass
            try:
                el.type(value, delay=35)
                return True
            except Exception:
                try:
                    el.fill(value)
                    return True
                except Exception:
                    return False

        def extract_frame_result(page, target_frame_name):
            if not target_frame_name:
                return None
            for _ in range(12):
                try:
                    page.wait_for_timeout(500)
                except Exception:
                    pass
                for frame in page.frames:
                    if frame.name != target_frame_name:
                        continue
                    try:
                        html = frame.content()
                        text = frame.locator("body").inner_text()
                    except Exception:
                        continue
                    success = bool(re.search(r"(thank you|message sent|we('|\u2019)?ll be in touch|gform_confirmation|request has been sent)", text + " " + html, re.I))
                    errors = re.findall(r"(required|invalid|error sending your message|please try again later|submission failed|captcha|please complete|please fill|antispam token is invalid)", text, re.I)
                    explicit_submission_error = bool(re.search(r"(error sending your message|please try again later|submission failed)", text, re.I))
                    return {
                        "success": success and not explicit_submission_error,
                        "text": text[:600],
                        "html_excerpt": html[:600],
                        "errors": errors[:6],
                        "explicit_submission_error": explicit_submission_error,
                    }
            return None

        with sync_playwright() as p:
            context = p.chromium.launch_persistent_context(
                str(Path(profile_dir or ".")),
                headless=True,
                viewport={"width": 1440, "height": 1200},
                user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/136.0.0.0 Safari/537.36",
                locale="en-US",
            )
            page = context.pages[0] if context.pages else context.new_page()
            response_log = []

            normalized_target_host = ""
            normalized_target_path = ""
            try:
                parsed_target = urlparse(target_url)
                normalized_target_host = (parsed_target.netloc or "").lower().replace("www.", "")
                normalized_target_path = (parsed_target.path or "/").rstrip("/") or "/"
            except Exception:
                pass

            def on_response(resp):
                try:
                    parsed_resp = urlparse(resp.url)
                    resp_host = (parsed_resp.netloc or "").lower().replace("www.", "")
                    resp_path = (parsed_resp.path or "/").rstrip("/") or "/"
                    if normalized_target_host and resp_host != normalized_target_host:
                        return
                    if normalized_target_path and resp_path != normalized_target_path:
                        return
                except Exception:
                    return
                try:
                    body = resp.text()[:4000]
                except Exception:
                    body = ""
                response_log.append({"url": resp.url, "status": resp.status, "body": body})

            page.on("response", on_response)
            page.goto(target_url, wait_until="domcontentloaded", timeout=45000)
            try:
                page.wait_for_load_state("networkidle", timeout=10000)
            except Exception:
                pass
            human_pause(page, 1200, 2200)
            warm_page(page)

            chosen, score = choose_form(page)
            if not chosen or score < 3:
                context.close()
                print(json.dumps({"ok": False, "reason": "no_contact_form_candidate", "score": score}))
                raise SystemExit(0)

            _, form, fields, form_text = chosen
            filled = []
            for sel in ["input", "textarea"]:
                for el in form.locator(sel).all():
                    typ = (el.get_attribute("type") or "").lower()
                    if typ in {"hidden", "submit", "button", "checkbox", "radio", "file"}:
                        continue
                    meta = {
                        "name": el.get_attribute("name") or "",
                        "id": el.get_attribute("id") or "",
                        "placeholder": el.get_attribute("placeholder") or "",
                        "aria": el.get_attribute("aria-label") or "",
                        "label": closest_field_text(el),
                    }
                    value = pick_value(meta)
                    if not value:
                        continue
                    try:
                        if human_fill(el, value):
                            filled.append(meta)
                            human_pause(page, 90, 220)
                    except Exception:
                        continue

            for el in form.locator("select").all():
                meta = {
                    "name": el.get_attribute("name") or "",
                    "id": el.get_attribute("id") or "",
                    "placeholder": el.get_attribute("placeholder") or "",
                    "aria": el.get_attribute("aria-label") or "",
                    "label": closest_field_text(el),
                }
                text = " ".join(meta.values()).lower()
                choice = None
                if "country" in text:
                    choice = "USA"
                elif "state" in text:
                    choice = payload["state"]
                elif "inquiry" in text or "project" in text or "service" in text:
                    options = [o.lower() for o in el.locator("option").all_inner_texts()]
                    for preferred in ["general", "trade", "sales", "project", "consult"]:
                        if any(preferred in option for option in options):
                            choice = preferred
                            break
                if choice:
                    try:
                        el.select_option(label=choice)
                    except Exception:
                        try:
                            el.select_option(choice)
                        except Exception:
                            pass
                human_pause(page, 80, 160)

            adapter_checkbox_applied = apply_adapter_checkboxes(form)
            adapter_select_applied = apply_adapter_selects(form)

            captcha_filled = fill_captcha(form, form_text)
            human_pause(page, 800, 1600)
            pre_text = page.locator("body").inner_text()
            frame_name = ""
            try:
                frame_name = form.get_attribute("target") or ""
            except Exception:
                frame_name = ""
            submitter = form.locator("button, input[type=submit]").first
            try:
                submitter.scroll_into_view_if_needed()
                try:
                    box = submitter.bounding_box()
                    if box:
                        page.mouse.move(box["x"] + min(box["width"] / 2, 20), box["y"] + min(box["height"] / 2, 12))
                        human_pause(page, 200, 420)
                except Exception:
                    pass
                human_pause(page, 250, 600)
                submitter.click()
            except Exception as exc:
                try:
                    human_pause(page, 250, 600)
                    submitter.evaluate("(el) => el.click()")
                except Exception as js_exc:
                    context.close()
                    print(json.dumps({"ok": False, "reason": f"submit_click_failed:{exc} | js_click_failed:{js_exc}", "score": score}))
                    raise SystemExit(0)

            try:
                page.wait_for_timeout(5000)
            except Exception:
                pass
            try:
                page.wait_for_load_state("networkidle", timeout=10000)
            except Exception:
                pass

            frame_result = extract_frame_result(page, frame_name)
            if frame_result and frame_result.get("success"):
                context.close()
                print(
                    json.dumps(
                        {
                            "ok": True,
                            "reason": "submitted",
                            "score": score,
                            "captcha_filled": captcha_filled,
                            "filled_count": len(filled),
                            "adapter_checkbox_applied": adapter_checkbox_applied,
                            "adapter_select_applied": adapter_select_applied,
                            "target_url": target_url,
                            "sample_text": str(frame_result.get("text") or "")[:600],
                            "errors": list(frame_result.get("errors") or [])[:6],
                            "detected_via": "frame_confirmation",
                        },
                        ensure_ascii=False,
                    )
                )
                raise SystemExit(0)

            response_confirmation = None
            response_captcha = None
            for entry in response_log:
                body = str(entry.get("body") or "")
                status = int(entry.get("status") or 0)
                if (
                    status == 429
                    or re.search(r"(please verify you are human|recaptcha|captcha)", body, re.I)
                ):
                    response_captcha = entry
                if "GF_AJAX_POSTBACK" in body and re.search(r"(thanks for contacting us|we('|\u2019)?ll be in touch|gform_confirmation_message)", body, re.I):
                    response_confirmation = entry
            if response_captcha:
                context.close()
                print(
                    json.dumps(
                        {
                            "ok": False,
                            "reason": "captcha_required",
                            "score": score,
                            "captcha_filled": captcha_filled,
                            "filled_count": len(filled),
                            "adapter_checkbox_applied": adapter_checkbox_applied,
                            "adapter_select_applied": adapter_select_applied,
                            "target_url": target_url,
                            "sample_text": str(response_captcha.get("body") or "")[:600],
                            "errors": ["captcha"],
                            "detected_via": "response_captcha",
                        },
                        ensure_ascii=False,
                    )
                )
                raise SystemExit(0)
            if response_confirmation:
                context.close()
                print(
                    json.dumps(
                        {
                            "ok": True,
                            "reason": "submitted",
                            "score": score,
                            "captcha_filled": captcha_filled,
                            "filled_count": len(filled),
                            "adapter_checkbox_applied": adapter_checkbox_applied,
                            "adapter_select_applied": adapter_select_applied,
                            "target_url": target_url,
                            "sample_text": str(response_confirmation.get("body") or "")[:600],
                            "errors": [],
                            "detected_via": "response_confirmation",
                        },
                        ensure_ascii=False,
                    )
                )
                raise SystemExit(0)

            body_text = page.locator("body").inner_text()
            success = bool(re.search(r"(thank you|thanks for contacting us|thanks for reaching out|message sent|we('|\u2019)?ll be in touch|we will be in touch|successfully submitted|request has been sent|gform_confirmation_message)", body_text, re.I))
            errors = re.findall(r"(required|invalid|error sending your message|please try again later|submission failed|captcha|please complete|please fill|antispam token is invalid)", body_text, re.I)
            antispam_invalid = "antispam token is invalid" in body_text.lower()
            explicit_submission_error = bool(re.search(r"(error sending your message|please try again later|submission failed)", body_text, re.I))
            frame_errors = list((frame_result or {}).get("errors") or [])
            if frame_result and not errors:
                errors = frame_errors[:6]
            if frame_result and not body_text.strip():
                body_text = str(frame_result.get("text") or "")
            if frame_result and frame_result.get("explicit_submission_error"):
                explicit_submission_error = True
            if success:
                errors = [err for err in errors if str(err).lower() in {"captcha", "required", "antispam token is invalid"}]
            has_captcha_error = any(str(err).lower() == "captcha" for err in errors)
            context.close()
            print(
                json.dumps(
                    {
                        "ok": bool(success and not explicit_submission_error and not any(str(err).lower() in {"captcha", "required", "antispam token is invalid"} for err in errors)),
                        "reason": (
                            "submitted"
                            if success and not explicit_submission_error and not any(str(err).lower() in {"captcha", "required", "antispam token is invalid"} for err in errors)
                            else "captcha_required"
                            if has_captcha_error
                            else "antispam_token_invalid"
                            if antispam_invalid
                            else "submission_error"
                            if explicit_submission_error
                            else "validation_error"
                            if errors
                            else "unknown_result"
                        ),
                        "score": score,
                        "captcha_filled": captcha_filled,
                        "filled_count": len(filled),
                        "adapter_checkbox_applied": adapter_checkbox_applied,
                        "adapter_select_applied": adapter_select_applied,
                        "target_url": target_url,
                        "sample_text": body_text[:600],
                        "errors": errors[:6],
                    },
                    ensure_ascii=False,
                )
            )
        """
    )


def _submit_contact_form(item: dict[str, Any], content: dict[str, Any], adapters: dict[str, Any]) -> dict[str, Any]:
    if not PLAYWRIGHT_PYTHON.exists():
        return {"ok": False, "reason": f"playwright_runtime_missing:{PLAYWRIGHT_PYTHON}"}
    sender = dict(content.get("sender_identity") or {})
    form_defaults = dict(content.get("contact_form_defaults") or {})
    payload = {
        "full_name": form_defaults.get("full_name") or sender.get("full_name") or "",
        "first_name": form_defaults.get("first_name") or sender.get("first_name") or "",
        "last_name": form_defaults.get("last_name") or sender.get("last_name") or "",
        "email": form_defaults.get("sender_email") or sender.get("sender_email") or "",
        "phone": form_defaults.get("phone") or sender.get("phone") or "",
        "company": form_defaults.get("company_name") or sender.get("company_name") or "",
        "website": form_defaults.get("company_website") or sender.get("company_website") or "",
        "subject": form_defaults.get("subject") or "",
        "message": form_defaults.get("message") or "",
        "address_line_1": form_defaults.get("address_line_1") or sender.get("address_line_1") or "",
        "city": form_defaults.get("city") or sender.get("city") or "",
        "state": form_defaults.get("state") or sender.get("state") or "",
        "postal_code": form_defaults.get("postal_code") or sender.get("postal_code") or "",
        "country": form_defaults.get("country") or sender.get("country") or "",
        "_adapter": _adapter_for(item, adapters),
        "_profile_dir": str(PLAYWRIGHT_PROFILE_DIR),
    }
    target_url = str(item.get("contact_form_url") or item.get("website") or "").strip()
    proc = subprocess.run(
        [str(PLAYWRIGHT_PYTHON), "-c", _form_submission_script(), target_url, json.dumps(payload, ensure_ascii=False)],
        capture_output=True,
        text=True,
        timeout=180,
        env=_subprocess_env(),
        check=False,
    )
    raw = proc.stdout.strip() or proc.stderr.strip()
    try:
        result = json.loads(raw) if raw else {}
    except json.JSONDecodeError:
        result = {"ok": False, "reason": raw or f"non_json_exit:{proc.returncode}"}
    result["returncode"] = proc.returncode
    return result


def _send_one_email(item: dict[str, Any], content: dict[str, Any]) -> dict[str, Any]:
    sender = dict(content.get("sender_identity") or {})
    email_defaults = dict(content.get("email_defaults") or {})
    env = _load_outreach_env()
    resend_api_key = str(env.get("RESEND_API_KEY") or "").strip()
    resend_from_email = str(env.get("RESEND_FROM_EMAIL") or email_defaults.get("from_email") or sender.get("sender_email") or "").strip()
    resend_from_name = str(env.get("RESEND_FROM_NAME") or email_defaults.get("from_name") or sender.get("display_name") or "Neosgo Lighting").strip()
    resend_reply_to = str(env.get("RESEND_REPLY_TO") or email_defaults.get("reply_to") or sender.get("reply_to_email") or sender.get("sender_email") or "").strip()
    if resend_api_key and resend_from_email:
        payload = {
            "from": f"{resend_from_name} <{resend_from_email}>",
            "to": [str(item.get("email") or "").strip()],
            "subject": str(email_defaults.get("subject") or "").strip(),
            "text": str(email_defaults.get("body_text") or "").strip(),
        }
        if resend_reply_to:
            payload["reply_to"] = resend_reply_to
        req = urllib_request.Request(
            "https://api.resend.com/emails",
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Authorization": f"Bearer {resend_api_key}",
                "Content-Type": "application/json",
                "User-Agent": "neosgo-outreach/1.0",
            },
            method="POST",
        )
        try:
            with urllib_request.urlopen(req, timeout=60) as resp:
                body = resp.read().decode("utf-8", errors="replace")
                parsed = json.loads(body or "{}")
                return {
                    "provider": "resend",
                    "attempted": 1,
                    "sent": 1,
                    "failed": 0,
                    "failures": [],
                    "message_id": parsed.get("id", ""),
                    "status_code": getattr(resp, "status", 200),
                    "returncode": 0,
                }
        except urllib_error.HTTPError as exc:
            try:
                body = exc.read().decode("utf-8", errors="replace")
            except Exception:
                body = ""
            return {
                "provider": "resend",
                "attempted": 1,
                "sent": 0,
                "failed": 1,
                "failures": [
                    {
                        "recipient_email": str(item.get("email") or "").strip(),
                        "subject": str(email_defaults.get("subject") or "").strip(),
                        "status_code": exc.code,
                        "stderr": body or str(exc),
                    }
                ],
                "returncode": 1,
            }
        except Exception as exc:
            return {
                "provider": "resend",
                "attempted": 1,
                "sent": 0,
                "failed": 1,
                "failures": [
                    {
                        "recipient_email": str(item.get("email") or "").strip(),
                        "subject": str(email_defaults.get("subject") or "").strip(),
                        "stderr": str(exc),
                    }
                ],
                "returncode": 1,
            }
    queue_csv = PROJECT_ROOT / "runtime" / "outreach" / "mail-batch.csv"
    events_csv = PROJECT_ROOT / "runtime" / "outreach" / "mail-events.csv"
    queue_csv.parent.mkdir(parents=True, exist_ok=True)
    with queue_csv.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(
            fh,
            fieldnames=["queue_id", "file_id", "recipient_email", "subject", "body", "segment_primary", "template_version", "sender_display", "sender_email"],
        )
        writer.writeheader()
        writer.writerow(
            {
                "queue_id": _target_key(item),
                "file_id": _target_key(item),
                "recipient_email": item.get("email") or "",
                "subject": email_defaults.get("subject") or "",
                "body": email_defaults.get("body_text") or "",
                "segment_primary": "interior_designer",
                "template_version": "neosgo_initial_v1",
                "sender_display": f"{email_defaults.get('from_name') or sender.get('display_name') or 'Neosgo Lighting'} <{email_defaults.get('from_email') or sender.get('sender_email') or ''}>",
                "sender_email": email_defaults.get("from_email") or sender.get("sender_email") or "",
            }
        )
    proc = subprocess.run(
        ["python3", str(MAIL_BATCH_SCRIPT), "--csv", str(queue_csv), "--events-csv", str(events_csv), "--sleep-seconds", "0"],
        capture_output=True,
        text=True,
        timeout=180,
        env=_subprocess_env(),
        check=False,
    )
    try:
        payload = json.loads(proc.stdout.strip() or "{}")
    except json.JSONDecodeError:
        payload = {"attempted": 1, "sent": 0, "failed": 1, "failures": [{"stderr": proc.stderr.strip() or proc.stdout.strip()}]}
    payload["returncode"] = proc.returncode
    return payload


def _build_summary(state: dict[str, Any]) -> dict[str, Any]:
    targets = list((state.get("targets") or {}).values())
    counts: dict[str, int] = {}
    for item in targets:
        status = str(item.get("status") or "unknown")
        counts[status] = counts.get(status, 0) + 1
    return {
        "generated_at": _now_iso(),
        "campaign_id": state.get("campaign_id"),
        "email_delivery_pending": bool(state.get("email_delivery_pending")),
        "counts": counts,
        "total_touched": len(targets),
        "last_email_sent_at": state.get("last_email_sent_at", ""),
    }


def _notify_failure(chat_id: str, item: dict[str, Any], channel: str, result: dict[str, Any]) -> dict[str, Any]:
    text = (
        "NEOSGO 触达任务已暂停。\n"
        f"公司：{item.get('company_name')}\n"
        f"方式：{'网站表单' if channel == 'contact_form' else '邮件'}\n"
        f"结果：失败\n"
        f"原因：{result.get('reason', 'unknown')}\n"
        f"网址：{item.get('website') or ''}"
    )
    return _send_telegram(chat_id, text)


def _notify_success(chat_id: str, item: dict[str, Any], channel: str, result: dict[str, Any]) -> dict[str, Any]:
    text = (
        "NEOSGO 触达进展。\n"
        f"公司：{item.get('company_name')}\n"
        f"州：{str(item.get('geo', '')).split('/',1)[0].strip().upper()}\n"
        f"方式：{'网站表单' if channel == 'contact_form' else '邮件'}\n"
        f"结果：{result.get('reason', 'submitted')}"
    )
    return _send_telegram(chat_id, text)


def _notify_captcha_required(chat_id: str, item: dict[str, Any], ticket_id: str, result: dict[str, Any]) -> dict[str, Any]:
    text = (
        "NEOSGO 触达需要人工一步确认。\n"
        f"公司：{item.get('company_name')}\n"
        f"方式：网站表单\n"
        f"原因：检测到验证码或人工验证\n"
        f"表单地址：{result.get('target_url') or item.get('contact_form_url') or item.get('website')}\n"
        f"票据：{ticket_id}\n"
        "处理完成后，请直接回复以下任一指令：\n"
        f"- outreach captcha {ticket_id} submitted\n"
        f"- outreach captcha {ticket_id} retry\n"
        f"- outreach captcha {ticket_id} email\n"
        f"- outreach captcha {ticket_id} stop"
    )
    return _send_telegram(chat_id, text)


def _should_email_fallback_after_form(result: dict[str, Any]) -> bool:
    reason = str(result.get("reason") or "").strip()
    if bool(result.get("captcha_required")):
        return False
    if any("captcha" in str(error).lower() for error in list(result.get("errors") or [])):
        return False
    sample_text = str(result.get("sample_text") or "").lower()
    if "confirm you're human" in sample_text or "captcha validation failed" in sample_text:
        return False
    return reason in {"no_contact_form_candidate", "validation_error", "antispam_token_invalid"}


def _email_fallback_after_form_failure(
    *,
    item: dict[str, Any],
    state: dict[str, Any],
    content: dict[str, Any],
    adapters: dict[str, Any],
    chat_id: str,
    no_telegram: bool,
    form_result: dict[str, Any],
) -> tuple[dict[str, Any], dict[str, Any] | None, dict[str, Any] | None]:
    min_gap = int((content.get("delivery_rules") or {}).get("min_minutes_between_emails", 5) or 5)
    sample_text = str(form_result.get("sample_text") or "").lower()
    adapter = _adapter_for(item, adapters)
    captcha_required = bool(form_result.get("captcha_required")) or any("captcha" in str(error).lower() for error in list(form_result.get("errors") or [])) or "confirm you're human" in sample_text
    if captcha_required or bool(adapter.get("manual_captcha_handoff")) and str(form_result.get("reason") or "") == "captcha_required":
        ticket_id = _captcha_ticket_id(_target_key(item))
        target = _target_status_update(
            item,
            "contact_form",
            "captcha_pending_operator",
            {
                "result": form_result,
                "reason": "captcha_required_manual_step",
                "captcha_ticket_id": ticket_id,
            },
        )
        event = {
            "type": "captcha_pending_operator",
            "at": _now_iso(),
            "key": _target_key(item),
            "company_name": item.get("company_name"),
            "ticket_id": ticket_id,
            "result": form_result,
        }
        telegram = None if no_telegram else _notify_captcha_required(chat_id, item, ticket_id, form_result)
        return target, event, telegram
    if bool(adapter.get("disable_email_fallback")):
        return (
            _target_status_update(
                item,
                "contact_form",
                "review_hold",
                {"result": form_result, "reason": "domain_policy_disables_email_fallback"},
            ),
            {"type": "review_hold", "at": _now_iso(), "key": _target_key(item), "company_name": item.get("company_name"), "result": form_result},
            None,
        )
    if not _should_email_fallback_after_form(form_result):
        return (
            _target_status_update(
                item,
                "contact_form",
                "contact_form_needs_review",
                {"result": form_result, "reason": "form_result_not_safe_for_email_fallback"},
            ),
            {"type": "contact_form_needs_review", "at": _now_iso(), "key": _target_key(item), "company_name": item.get("company_name"), "result": form_result},
            None,
        )
    if not _email_is_usable(item):
        return (
            _target_status_update(
                item,
                "contact_form",
                "contact_form_failed",
                {"result": {"reason": "form_failed_no_email_fallback", "form_reason": form_result.get("reason")}},
            ),
            {"type": "contact_form_failed", "at": _now_iso(), "key": _target_key(item), "company_name": item.get("company_name"), "result": {"reason": "form_failed_no_email_fallback", "form_reason": form_result.get("reason")}},
            None,
        )
    if not _email_send_allowed(state, min_minutes_between_emails=min_gap):
        return (
            _target_status_update(
                item,
                "contact_form",
                "contact_form_failed_email_deferred",
                {"result": form_result, "reason": "email_guard_active"},
            ),
            {"type": "contact_form_failed_email_deferred", "at": _now_iso(), "key": _target_key(item), "company_name": item.get("company_name"), "result": form_result},
            None,
        )

    email_result = _send_one_email(item, content)
    sent_ok = int(email_result.get("sent", 0)) == 1 and int(email_result.get("failed", 0)) == 0
    if sent_ok:
        state["email_delivery_pending"] = True
        state["last_email_sent_at"] = _now_iso()
        target = _target_status_update(
            item,
            "email",
            "email_sent_local_only",
            {"result": email_result, "fallback_from": "contact_form"},
        )
        event = {
            "type": "email_sent_local_only",
            "at": _now_iso(),
            "key": _target_key(item),
            "company_name": item.get("company_name"),
            "result": email_result,
            "fallback_from": "contact_form",
        }
        telegram = None if no_telegram else _notify_success(chat_id, item, "email", {"reason": "email_sent_local_only_after_form_failure"})
        return target, event, telegram

    target = _target_status_update(
        item,
        "email",
        "email_failed",
        {"result": email_result, "fallback_from": "contact_form"},
    )
    event = {
        "type": "email_failed",
        "at": _now_iso(),
        "key": _target_key(item),
        "company_name": item.get("company_name"),
        "result": email_result,
        "fallback_from": "contact_form",
    }
    telegram = None if no_telegram else _notify_failure(chat_id, item, "email", {"reason": "email_send_failed_after_form_failure"})
    return target, event, telegram


def main() -> int:
    parser = argparse.ArgumentParser(description="Run one safe NEOSGO outreach step.")
    parser.add_argument("--chat-id", default=os.environ.get("NEOSGO_OUTREACH_CHAT", DEFAULT_CHAT))
    parser.add_argument("--max-attempts", type=int, default=1)
    parser.add_argument("--no-telegram", action="store_true")
    args = parser.parse_args()

    content = _load_content()
    adapters = _load_form_adapters()
    state = _load_state()
    delivery_rules = dict(content.get("delivery_rules") or {})
    hold_minutes = int(delivery_rules.get("assume_delivered_after_no_failure_minutes", 10) or 10)
    attempts = []
    failure = None

    reply_events = _process_telegram_replies(state)
    for event in reply_events:
        _append_event(event)
        attempts.append(event)

    reroute_events = _refresh_target_routing_from_results(state, adapters)
    for event in reroute_events:
        _append_event(event)
        attempts.append(event)
        if event.get("type") == "target_rerouted_for_captcha" and not args.no_telegram:
            key = str(event.get("key") or "")
            target = dict((state.get("targets") or {}).get(key) or {})
            ticket_id = str(event.get("ticket_id") or target.get("captcha_ticket_id") or "")
            if target and ticket_id:
                target["telegram_last"] = _notify_captcha_required(
                    args.chat_id,
                    target,
                    ticket_id,
                    dict(target.get("contact_form_result") or target.get("result") or {}),
                )
                state["targets"][key] = target

    release_event = _release_pending_email_if_safe(state, hold_minutes=hold_minutes)
    if release_event:
        _append_event(release_event)
        attempts.append(release_event)

    for _ in range(max(1, int(args.max_attempts or 1))):
        item = _select_next_candidate(state)
        if not item:
            break
        channel = _channel_for(item, state)
        if channel == "none":
            break

        key = _target_key(item)
        if channel == "contact_form":
            result = _submit_contact_form(item, content, adapters)
            if result.get("ok"):
                state["targets"][key] = _target_status_update(
                    item,
                    channel,
                    "contact_form_submitted",
                    {
                        "contact_form_url": item.get("contact_form_url") or item.get("website"),
                        "result": result,
                    },
                )
                event = {"type": "contact_form_submitted", "at": _now_iso(), "key": key, "company_name": item.get("company_name"), "result": result}
                _append_event(event)
                attempts.append(event)
                if not args.no_telegram:
                    state["targets"][key]["telegram_last"] = _notify_success(args.chat_id, item, channel, result)
            else:
                fallback_target, event, telegram = _email_fallback_after_form_failure(
                    item=item,
                    state=state,
                    content=content,
                    adapters=adapters,
                    chat_id=args.chat_id,
                    no_telegram=args.no_telegram,
                    form_result=result,
                )
                fallback_target["contact_form_url"] = item.get("contact_form_url") or item.get("website")
                fallback_target["contact_form_result"] = result
                state["targets"][key] = fallback_target
                _append_event(event)
                attempts.append(event)
                if telegram is not None:
                    state["targets"][key]["telegram_last"] = telegram
                if fallback_target["status"] == "email_failed":
                    failure = event
                    break
        else:
            email_result = _send_one_email(item, content)
            sent_ok = int(email_result.get("sent", 0)) == 1 and int(email_result.get("failed", 0)) == 0
            if sent_ok:
                state["targets"][key] = _target_status_update(
                    item,
                    channel,
                    "email_sent_local_only",
                    {"result": email_result},
                )
                state["email_delivery_pending"] = True
                state["last_email_sent_at"] = _now_iso()
                event = {"type": "email_sent_local_only", "at": _now_iso(), "key": key, "company_name": item.get("company_name"), "result": email_result}
                _append_event(event)
                attempts.append(event)
                if not args.no_telegram:
                    state["targets"][key]["telegram_last"] = _notify_success(args.chat_id, item, channel, {"reason": "email_sent_local_only"})
            else:
                state["targets"][key] = _target_status_update(
                    item,
                    channel,
                    "email_failed",
                    {"result": email_result},
                )
                event = {"type": "email_failed", "at": _now_iso(), "key": key, "company_name": item.get("company_name"), "result": email_result}
                _append_event(event)
                attempts.append(event)
                failure = event
                if not args.no_telegram:
                    state["targets"][key]["telegram_last"] = _notify_failure(args.chat_id, item, channel, {"reason": "email_send_failed"})
                break

    summary = _build_summary(state)
    summary["attempts"] = attempts
    summary["failure"] = failure
    _write_json(STATE_PATH, state)
    _write_json(LATEST_SUMMARY_PATH, summary)
    _write_review_artifacts(state)
    _write_captcha_artifacts(state)
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0 if failure is None else 1


if __name__ == "__main__":
    raise SystemExit(main())
