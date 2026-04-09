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
CONTENT_PATH = PROJECT_ROOT / "config" / "outreach-campaign-content.yaml"
MAIL_BATCH_SCRIPT = WORKSPACE_ROOT / "skills" / "neosgo-lead-engine" / "scripts" / "send_outreach_mail_batch.py"
PLAYWRIGHT_PYTHON = WORKSPACE_ROOT / "tools" / "matrix-venv" / "bin" / "python"
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
            "waiting_reply",
            "review_hold",
            "stopped",
        }:
            continue
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
    return {
        "company_name": item.get("company_name"),
        "state": str(item.get("geo", "")).split("/", 1)[0].strip().upper(),
        "website": item.get("website"),
        "source_url": item.get("source_url"),
        "channel": channel,
        "status": status,
        "updated_at": _now_iso(),
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


def _form_submission_script() -> str:
    return textwrap.dedent(
        r"""
        from playwright.sync_api import sync_playwright
        import json, re, sys

        target_url = sys.argv[1]
        payload = json.loads(sys.argv[2])

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

        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page(viewport={"width": 1440, "height": 1200})
            page.goto(target_url, wait_until="domcontentloaded", timeout=45000)
            try:
                page.wait_for_load_state("networkidle", timeout=10000)
            except Exception:
                pass

            chosen, score = choose_form(page)
            if not chosen or score < 3:
                browser.close()
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
                    }
                    value = pick_value(meta)
                    if not value:
                        continue
                    try:
                        el.fill(value)
                        filled.append(meta)
                    except Exception:
                        continue

            for el in form.locator("select").all():
                meta = {
                    "name": el.get_attribute("name") or "",
                    "id": el.get_attribute("id") or "",
                    "placeholder": el.get_attribute("placeholder") or "",
                    "aria": el.get_attribute("aria-label") or "",
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

            captcha_filled = fill_captcha(form, form_text)
            pre_text = page.locator("body").inner_text()
            submitter = form.locator("button, input[type=submit]").first
            try:
                submitter.click()
            except Exception as exc:
                browser.close()
                print(json.dumps({"ok": False, "reason": f"submit_click_failed:{exc}", "score": score}))
                raise SystemExit(0)

            try:
                page.wait_for_timeout(5000)
            except Exception:
                pass
            try:
                page.wait_for_load_state("networkidle", timeout=10000)
            except Exception:
                pass

            body_text = page.locator("body").inner_text()
            success = bool(re.search(r"(thank you|thanks for reaching out|message sent|we('|\u2019)?ll be in touch|we will be in touch|successfully submitted|request has been sent)", body_text, re.I))
            errors = re.findall(r"(required|invalid|error sending your message|please try again later|submission failed|captcha|please complete|please fill|antispam token is invalid)", body_text, re.I)
            antispam_invalid = "antispam token is invalid" in body_text.lower()
            explicit_submission_error = bool(re.search(r"(error sending your message|please try again later|submission failed)", body_text, re.I))
            browser.close()
            print(
                json.dumps(
                    {
                        "ok": bool(success and not errors and not explicit_submission_error),
                        "reason": (
                            "submitted"
                            if success and not errors and not explicit_submission_error
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
                        "target_url": target_url,
                        "sample_text": body_text[:600],
                        "errors": errors[:6],
                    },
                    ensure_ascii=False,
                )
            )
        """
    )


def _submit_contact_form(item: dict[str, Any], content: dict[str, Any]) -> dict[str, Any]:
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


def _should_email_fallback_after_form(result: dict[str, Any]) -> bool:
    reason = str(result.get("reason") or "").strip()
    return reason in {"no_contact_form_candidate", "validation_error", "antispam_token_invalid"}


def _email_fallback_after_form_failure(
    *,
    item: dict[str, Any],
    state: dict[str, Any],
    content: dict[str, Any],
    chat_id: str,
    no_telegram: bool,
    form_result: dict[str, Any],
) -> tuple[dict[str, Any], dict[str, Any] | None, dict[str, Any] | None]:
    min_gap = int((content.get("delivery_rules") or {}).get("min_minutes_between_emails", 5) or 5)
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
    state = _load_state()
    delivery_rules = dict(content.get("delivery_rules") or {})
    hold_minutes = int(delivery_rules.get("assume_delivered_after_no_failure_minutes", 10) or 10)
    attempts = []
    failure = None

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
            result = _submit_contact_form(item, content)
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
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0 if failure is None else 1


if __name__ == "__main__":
    raise SystemExit(main())
