#!/usr/bin/env python3
import argparse
import json
import os
import subprocess
from datetime import datetime, timedelta
from pathlib import Path

import duckdb


OPENCLAW_BIN = "/opt/homebrew/bin/openclaw"
DEFAULT_TELEGRAM_TARGET = "8528973600"
DEFAULT_PATH = "/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin"
TRACKED_TYPES = [
    "sent",
    "delivered",
    "bounced",
    "opened",
    "clicked",
    "reply",
    "unsubscribe",
    "do_not_contact",
    "qualified",
    "quote_request",
    "sample_requested",
    "meeting_booked",
    "won",
    "lost",
]


def _subprocess_env() -> dict[str, str]:
    env = os.environ.copy()
    env["PATH"] = f"{DEFAULT_PATH}:{env.get('PATH', '')}".strip(":")
    return env


def _send_to_telegram(chat_id: str, text: str, attachments: list[Path]) -> list[dict]:
    deliveries = []
    text_proc = subprocess.run(
        [OPENCLAW_BIN, "message", "send", "--channel", "telegram", "--target", chat_id, "--message", text, "--json"],
        capture_output=True,
        text=True,
        timeout=120,
        env=_subprocess_env(),
    )
    try:
        payload = json.loads(text_proc.stdout or "{}")
    except Exception:
        payload = {"raw_stdout": text_proc.stdout.strip()}
    deliveries.append({"type": "text", "returncode": text_proc.returncode, "payload": payload, "stderr": text_proc.stderr.strip()})
    for path in attachments:
        proc = subprocess.run(
            [OPENCLAW_BIN, "message", "send", "--channel", "telegram", "--target", chat_id, "--media", str(path), "--force-document", "--json"],
            capture_output=True,
            text=True,
            timeout=180,
            env=_subprocess_env(),
        )
        try:
            payload = json.loads(proc.stdout or "{}")
        except Exception:
            payload = {"raw_stdout": proc.stdout.strip()}
        deliveries.append({"type": "media", "path": str(path), "returncode": proc.returncode, "payload": payload, "stderr": proc.stderr.strip()})
    return deliveries


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", required=True)
    ap.add_argument("--manifest", required=True)
    ap.add_argument("--hours", type=int, default=6)
    ap.add_argument("--out", required=True)
    ap.add_argument("--json-out")
    ap.add_argument("--send-telegram", action="store_true")
    ap.add_argument("--telegram-chat", default=DEFAULT_TELEGRAM_TARGET)
    args = ap.parse_args()

    manifest = json.loads(Path(args.manifest).read_text(encoding="utf-8"))
    queue_ids = manifest.get("queue_ids") or []
    queue_clause = ",".join(["?"] * len(queue_ids)) if queue_ids else "''"
    since = datetime.now() - timedelta(hours=args.hours)

    con = duckdb.connect(args.db, read_only=True)
    counts = {k: 0 for k in TRACKED_TYPES}
    batch_totals = {k: 0 for k in TRACKED_TYPES}
    if queue_ids:
        batch_rows = con.execute(
            f"""
            select event_type, count(*)
            from outreach_events
            where queue_id in ({queue_clause})
            group by 1
            """,
            [*queue_ids],
        ).fetchall()
        for event_type, c in batch_rows:
            batch_totals[str(event_type)] = int(c)
        rows = con.execute(
            f"""
            select event_type, count(*)
            from outreach_events
            where queue_id in ({queue_clause})
              and event_time >= ?
            group by 1
            """,
            [*queue_ids, since],
        ).fetchall()
        for event_type, c in rows:
            counts[str(event_type)] = int(c)
        recent_replies = con.execute(
            f"""
            select event_time, queue_id, payload_json
            from outreach_events
            where queue_id in ({queue_clause})
              and event_type = 'reply'
              and event_time >= ?
            order by event_time desc
            limit 10
            """,
            [*queue_ids, since],
        ).fetchall()
    else:
        recent_replies = []
    con.close()

    lines = [
        "# Neosgo outreach task report",
        "",
        f"- Window: last {args.hours} hours",
        f"- State: {manifest.get('state','')}",
        f"- Segment: {manifest.get('segment','all') or 'all'}",
        f"- Batch rows: {manifest.get('rows', 0)}",
        "",
        "## Task cumulative",
        f"- Sent: {batch_totals['sent']}",
        f"- Delivered: {batch_totals['delivered']}",
        f"- Failed/Bounced: {batch_totals['bounced']}",
        f"- Opened: {batch_totals['opened']}",
        f"- Clicked: {batch_totals['clicked']}",
        f"- Replied: {batch_totals['reply']}",
        f"- Unsubscribed: {batch_totals['unsubscribe']}",
        f"- Do-not-contact: {batch_totals['do_not_contact']}",
        "",
        "## Recent window",
        f"- Sent: {counts['sent']}",
        f"- Delivered: {counts['delivered']}",
        f"- Failed/Bounced: {counts['bounced']}",
        f"- Opened: {counts['opened']}",
        f"- Clicked: {counts['clicked']}",
        f"- Replied: {counts['reply']}",
        f"- Unsubscribed: {counts['unsubscribe']}",
        f"- Do-not-contact: {counts['do_not_contact']}",
        "",
        "## Recent replies",
    ]
    if recent_replies:
        for event_time, queue_id, payload_json in recent_replies:
            try:
                payload = json.loads(payload_json or "{}")
            except Exception:
                payload = {"raw_payload": payload_json}
            lines.append(f"- {event_time} | {queue_id} | {json.dumps(payload, ensure_ascii=False)}")
    else:
        lines.append("- No replies in this window.")

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    payload = {
        "generated_at": datetime.now().isoformat(),
        "window_hours": args.hours,
        "manifest": manifest,
        "counts": counts,
        "batch_totals": batch_totals,
        "recent_replies": [
            {"event_time": str(event_time), "queue_id": queue_id, "payload": json.loads(payload_json or "{}")}
            for event_time, queue_id, payload_json in recent_replies
        ],
        "out": str(out_path),
    }
    if args.json_out:
        Path(args.json_out).write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    if args.send_telegram:
        summary = (
            f"Neosgo {manifest.get('state','')} outreach report\n"
            f"Window: last {args.hours}h\n"
            f"Task total: Sent {batch_totals['sent']} | Delivered {batch_totals['delivered']} | Bounced {batch_totals['bounced']}\n"
            f"Recent {args.hours}h: Opened {counts['opened']} | Clicked {counts['clicked']} | Replies {counts['reply']}\n"
            f"Unsubscribed {batch_totals['unsubscribe']} | DNC {batch_totals['do_not_contact']}"
        )
        payload["telegram"] = _send_to_telegram(args.telegram_chat, summary, [out_path])

    print(json.dumps(payload, ensure_ascii=False))


if __name__ == "__main__":
    main()
