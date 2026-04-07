#!/usr/bin/env python3
import argparse
import json
import os
import re
import subprocess
from pathlib import Path

import duckdb


OPENCLAW_BIN = "/opt/homebrew/bin/openclaw"
DEFAULT_TELEGRAM_TARGET = "8528973600"
DEFAULT_PATH = "/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin"
DEFAULT_SUPPRESSION_PATH = "/Users/mac_claw/.openclaw/workspace/output/neosgo/suppressed-emails.json"


def _subprocess_env() -> dict[str, str]:
    env = os.environ.copy()
    env["PATH"] = f"{DEFAULT_PATH}:{env.get('PATH', '')}".strip(":")
    return env


def _run_osascript(lines: list[str]) -> subprocess.CompletedProcess[str]:
    cmd = ["osascript"]
    for line in lines:
        cmd.extend(["-e", line])
    return subprocess.run(cmd, capture_output=True, text=True)


def _apple_escape(value: str) -> str:
    return value.replace("\\", "\\\\").replace('"', '\\"')


def _fetch_messages(account_name: str, mailbox_name: str, limit: int, unread_only: bool) -> list[dict]:
    script = [
        'tell application "Mail"',
        f'set theMailbox to mailbox "{_apple_escape(mailbox_name)}" of account "{_apple_escape(account_name)}"',
        'set msgList to messages of theMailbox',
    ]
    if unread_only:
        script.append('set msgList to (every message of theMailbox whose read status is false)')
    script.extend(
        [
            f'set maxCount to {limit}',
            'set outList to {}',
            'set currentIndex to 0',
            'repeat with m in msgList',
            'set currentIndex to currentIndex + 1',
            'if currentIndex > maxCount then exit repeat',
            'set end of outList to (id of m as text) & "||" & (sender of m as text) & "||" & (subject of m as text) & "||" & (date received of m as text) & "||" & (content of m as text)',
            'end repeat',
            'set AppleScript\'s text item delimiters to linefeed',
            'return outList as text',
            'end tell',
        ]
    )
    proc = _run_osascript(script)
    if proc.returncode != 0:
        raise RuntimeError(proc.stderr.strip() or proc.stdout.strip() or "Mail AppleScript failed")
    lines = [line for line in proc.stdout.splitlines() if line.strip()]
    messages = []
    for line in lines:
        parts = line.split("||", 4)
        if len(parts) != 5:
            continue
        messages.append(
            {
                "mail_message_id": parts[0].strip(),
                "sender": parts[1].strip(),
                "subject": parts[2].strip(),
                "date_received": parts[3].strip(),
                "content": parts[4].strip(),
            }
        )
    return messages


def _send_to_telegram(chat_id: str, text: str) -> dict:
    proc = subprocess.run(
        [OPENCLAW_BIN, "message", "send", "--channel", "telegram", "--target", chat_id, "--message", text, "--json"],
        capture_output=True,
        text=True,
        timeout=120,
        env=_subprocess_env(),
    )
    payload = {}
    try:
        payload = json.loads(proc.stdout or "{}")
    except Exception:
        payload = {"raw_stdout": proc.stdout.strip()}
    return {"returncode": proc.returncode, "payload": payload, "stderr": proc.stderr.strip()}


def _classify_message(msg: dict) -> str:
    text = f"{msg.get('subject','')} {msg.get('content','')}".lower()
    sender = str(msg.get("sender") or "").lower()
    bounce_tokens = [
        "mailer-daemon",
        "mail delivery subsystem",
        "mail delivery system",
        "postmaster",
        "undelivered mail returned to sender",
        "returned mail",
        "delivery status notification",
        "delivery failure",
        "delivery has failed",
        "message could not be delivered",
    ]
    if any(token in sender for token in bounce_tokens) or any(token in text for token in bounce_tokens):
        hard_bounce_tokens = [
            "user unknown",
            "unknown user",
            "recipient address rejected",
            "no such user",
            "mailbox unavailable",
            "invalid recipient",
            "address not found",
            "5.1.1",
            "550 5.1.1",
            "554 5.1.1",
        ]
        if any(token in text for token in hard_bounce_tokens):
            return "hard_bounce"
        return "bounced"
    unsubscribe_tokens = [
        "unsubscribe",
        "stop sending",
        "remove me",
        "do not contact",
        "don't contact",
        "请勿再发",
        "不要再发",
        "取消订阅",
        "退订",
    ]
    quote_tokens = ["quote", "pricing", "catalog", "sample", "project", "报价", "目录", "样品"]
    if any(token in text for token in unsubscribe_tokens):
        return "unsubscribe"
    if any(token in text for token in quote_tokens):
        return "reply"
    return "reply"


def _extract_bounced_recipient(msg: dict) -> str:
    text = f"{msg.get('subject','')}\n{msg.get('content','')}"
    patterns = [
        r"Final-Recipient:\s*rfc822;\s*([A-Z0-9._%+\-]+@[A-Z0-9.\-]+\.[A-Z]{2,})",
        r"Original-Recipient:\s*rfc822;\s*([A-Z0-9._%+\-]+@[A-Z0-9.\-]+\.[A-Z]{2,})",
        r"for <([A-Z0-9._%+\-]+@[A-Z0-9.\-]+\.[A-Z]{2,})>",
        r"to <([A-Z0-9._%+\-]+@[A-Z0-9.\-]+\.[A-Z]{2,})>",
    ]
    for pattern in patterns:
        match = re.search(pattern, text, flags=re.IGNORECASE)
        if match:
            return match.group(1).strip().lower()
    emails = re.findall(r"[A-Z0-9._%+\-]+@[A-Z0-9.\-]+\.[A-Z]{2,}", text, flags=re.IGNORECASE)
    ignore = {"cs@neosgo.com"}
    for email in emails:
        candidate = email.strip().lower()
        if candidate not in ignore and "mailer-daemon" not in candidate and "postmaster" not in candidate:
            return candidate
    return ""


def _build_event_rows(messages: list[dict]) -> list[dict]:
    rows = []
    for msg in messages:
        event_type = _classify_message(msg)
        queue_id = msg.get("queue_id") or ""
        file_id = msg.get("file_id") or ""
        payload = {
            "sender": msg.get("sender"),
            "subject": msg.get("subject"),
            "mail_message_id": msg.get("mail_message_id"),
            "content": msg.get("content"),
        }
        rows.append(
            {
                "queue_id": queue_id,
                "file_id": file_id,
                "event_type": "bounced" if event_type in {"bounced", "hard_bounce"} else event_type,
                "event_time": msg.get("date_received") or "",
                "payload_json": json.dumps(payload, ensure_ascii=False),
            }
        )
        if event_type == "hard_bounce" and queue_id and file_id:
            rows.append(
                {
                    "queue_id": queue_id,
                    "file_id": file_id,
                    "event_type": "do_not_contact",
                    "event_time": msg.get("date_received") or "",
                    "payload_json": json.dumps(
                        {
                            "reason": "hard_bounce",
                            "sender": msg.get("sender"),
                            "subject": msg.get("subject"),
                            "mail_message_id": msg.get("mail_message_id"),
                            "bounced_recipient": msg.get("bounced_recipient"),
                        },
                        ensure_ascii=False,
                    ),
                }
            )
    return rows


def _enrich_messages_with_queue(db_path: str, messages: list[dict]) -> list[dict]:
    if not db_path or not messages:
        return messages
    con = duckdb.connect(db_path, read_only=True)
    try:
        for msg in messages:
            classification = _classify_message(msg)
            sender = (msg.get("sender") or "").strip()
            email = sender
            if "<" in sender and ">" in sender:
                email = sender.split("<", 1)[1].split(">", 1)[0].strip()
            email = email.lower()
            row = None
            if classification in {"bounced", "hard_bounce"}:
                bounced_recipient = _extract_bounced_recipient(msg)
                msg["bounced_recipient"] = bounced_recipient
                if bounced_recipient:
                    row = con.execute(
                        """
                        select queue_id, file_id
                        from outreach_events
                        where event_type = 'sent'
                          and lower(trim(json_extract_string(payload_json, '$.recipient_email'))) = ?
                        order by event_time desc
                        limit 1
                        """,
                        [bounced_recipient],
                    ).fetchone()
            if row is None:
                row = con.execute(
                    """
                    select q.queue_id, q.file_id
                    from outreach_queue q
                    join outreach_ready_leads l
                      on q.queue_id = md5(l.queue_lead_id || '|' || l.segment_primary || '|email')
                    where lower(trim(coalesce(l.email,''))) = ?
                    order by q.created_at desc nulls last
                    limit 1
                    """,
                    [email],
                ).fetchone()
            if row:
                msg["queue_id"] = row[0]
                msg["file_id"] = row[1]
    finally:
        con.close()
    return messages


def _write_event_csv(path: Path, rows: list[dict]) -> None:
    import csv

    with path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=["queue_id", "file_id", "event_type", "event_time", "payload_json"])
        writer.writeheader()
        writer.writerows(rows)


def _update_suppression_file(path: str, messages: list[dict]) -> dict:
    file_path = Path(path)
    file_path.parent.mkdir(parents=True, exist_ok=True)
    payload = {"emails": [], "updated_at": ""}
    if file_path.exists():
        try:
            loaded = json.loads(file_path.read_text(encoding="utf-8"))
            if isinstance(loaded, dict):
                payload.update(loaded)
            elif isinstance(loaded, list):
                payload["emails"] = loaded
        except Exception:
            pass
    emails = {str(item).strip().lower() for item in (payload.get("emails") or []) if str(item).strip()}
    added = []
    for msg in messages:
        if _classify_message(msg) not in {"bounced", "hard_bounce"}:
            continue
        bounced_recipient = str(msg.get("bounced_recipient") or "").strip().lower()
        if bounced_recipient and bounced_recipient not in emails:
            emails.add(bounced_recipient)
            added.append(bounced_recipient)
    payload["emails"] = sorted(emails)
    payload["updated_at"] = subprocess.run(["date", "-u", "+%Y-%m-%dT%H:%M:%SZ"], capture_output=True, text=True).stdout.strip()
    file_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return {"path": str(file_path), "total": len(emails), "added": added}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--account-name", required=True)
    ap.add_argument("--mailbox", default="INBOX")
    ap.add_argument("--limit", type=int, default=10)
    ap.add_argument("--unread-only", action="store_true")
    ap.add_argument("--db")
    ap.add_argument("--json-out")
    ap.add_argument("--event-csv-out")
    ap.add_argument("--import-events", action="store_true")
    ap.add_argument("--suppression-file", default=DEFAULT_SUPPRESSION_PATH)
    ap.add_argument("--send-telegram", action="store_true")
    ap.add_argument("--telegram-chat", default=DEFAULT_TELEGRAM_TARGET)
    args = ap.parse_args()

    messages = _fetch_messages(args.account_name, args.mailbox, args.limit, args.unread_only)
    messages = _enrich_messages_with_queue(args.db or "", messages)
    event_rows = _build_event_rows(messages)
    suppression = _update_suppression_file(args.suppression_file, messages)
    telegram = []
    if args.send_telegram:
        for msg in messages:
            label = _classify_message(msg)
            if label in {"bounced", "hard_bounce"}:
                continue
            text = (
                f"Neosgo 邮件{label}提醒\n"
                f"From: {msg['sender']}\n"
                f"Subject: {msg['subject']}\n"
                f"Date: {msg['date_received']}\n\n"
                f"{msg['content']}"
            )
            telegram.append(_send_to_telegram(args.telegram_chat, text))

    imported = {}
    if args.import_events and args.db and args.event_csv_out:
        proc = subprocess.run(
            [
                "python3",
                str(Path(__file__).with_name("import_outreach_events.py")),
                "--db",
                args.db,
                "--csv",
                args.event_csv_out,
            ],
            capture_output=True,
            text=True,
            timeout=120,
            env=_subprocess_env(),
        )
        try:
            imported = json.loads(proc.stdout or "{}")
        except Exception:
            imported = {"returncode": proc.returncode, "stdout": proc.stdout.strip(), "stderr": proc.stderr.strip()}

    payload = {
        "account_name": args.account_name,
        "mailbox": args.mailbox,
        "message_count": len(messages),
        "messages": messages,
        "event_rows": event_rows,
        "suppression": suppression,
        "imported": imported,
        "telegram": telegram,
    }
    if args.json_out:
        out = Path(args.json_out)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    if args.event_csv_out:
        csv_out = Path(args.event_csv_out)
        csv_out.parent.mkdir(parents=True, exist_ok=True)
        _write_event_csv(csv_out, event_rows)
    print(json.dumps(payload, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
