#!/usr/bin/env python3
import argparse
import json
from datetime import datetime
from pathlib import Path

import duckdb


TRACKED_TYPES = ["sent", "delivered", "bounced", "opened", "clicked", "reply", "unsubscribe", "do_not_contact", "qualified", "quote_request", "sample_requested", "meeting_booked", "won", "lost"]


def _counts_for_day(con: duckdb.DuckDBPyConnection, day: str) -> dict[str, int]:
    rows = con.execute(
        """
        select event_type, count(*) as c
        from outreach_events
        where cast(event_time as date) = cast(? as date)
        group by 1
        """,
        [day],
    ).fetchall()
    counts = {k: 0 for k in TRACKED_TYPES}
    for event_type, c in rows:
        counts[str(event_type)] = int(c)
    return counts


def _pending_stats(con: duckdb.DuckDBPyConnection) -> dict[str, int]:
    pending = con.execute("select count(*) from outreach_queue where status='pending'").fetchone()[0]
    scheduled = con.execute("select count(*) from outreach_queue where status='scheduled'").fetchone()[0]
    sent = con.execute("select count(*) from outreach_queue where status='sent'").fetchone()[0]
    return {
        "queue_pending": int(pending),
        "queue_scheduled": int(scheduled),
        "queue_sent": int(sent),
    }


def _recent_replies(con: duckdb.DuckDBPyConnection, day: str, limit: int) -> list[dict]:
    rows = con.execute(
        """
        select event_time, queue_id, file_id, payload_json
        from outreach_events
        where event_type = 'reply'
          and cast(event_time as date) = cast(? as date)
        order by event_time desc
        limit ?
        """,
        [day, limit],
    ).fetchall()
    out = []
    for event_time, queue_id, file_id, payload_json in rows:
        payload = {}
        try:
            payload = json.loads(payload_json or "{}")
        except Exception:
            payload = {"raw_payload": payload_json}
        out.append(
            {
                "event_time": str(event_time),
                "queue_id": queue_id,
                "file_id": file_id,
                "payload": payload,
            }
        )
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", required=True)
    ap.add_argument("--date", default=datetime.now().strftime("%Y-%m-%d"))
    ap.add_argument("--out", required=True)
    ap.add_argument("--json-out")
    args = ap.parse_args()

    con = duckdb.connect(args.db, read_only=True)
    counts = _counts_for_day(con, args.date)
    queue = _pending_stats(con)
    replies = _recent_replies(con, args.date, limit=20)
    con.close()

    lines = [
        "# Neosgo outreach delivery report",
        "",
        f"- Date: {args.date}",
        f"- Sent: {counts['sent']}",
        f"- Delivered: {counts['delivered']}",
        f"- Failed/Bounced: {counts['bounced']}",
        f"- Opened: {counts['opened']}",
        f"- Clicked: {counts['clicked']}",
        f"- Replied: {counts['reply']}",
        f"- Unsubscribed: {counts['unsubscribe']}",
        f"- Do-not-contact: {counts['do_not_contact']}",
        f"- Qualified: {counts['qualified']}",
        f"- Quote requested: {counts['quote_request']}",
        f"- Sample requested: {counts['sample_requested']}",
        f"- Meeting booked: {counts['meeting_booked']}",
        f"- Won: {counts['won']}",
        f"- Lost: {counts['lost']}",
        "",
        "## Queue snapshot",
        f"- Pending: {queue['queue_pending']}",
        f"- Scheduled: {queue['queue_scheduled']}",
        f"- Sent status rows: {queue['queue_sent']}",
        "",
        "## Recent replies",
    ]
    if replies:
        for item in replies:
            lines.append(f"- {item['event_time']} | queue_id={item['queue_id']} | payload={json.dumps(item['payload'], ensure_ascii=False)}")
    else:
        lines.append("- No reply events recorded for this date.")

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    payload = {"date": args.date, "counts": counts, "queue": queue, "recent_replies": replies}
    if args.json_out:
        json_path = Path(args.json_out)
        json_path.parent.mkdir(parents=True, exist_ok=True)
        json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    print(json.dumps({"out": str(out_path), "json_out": args.json_out or "", **payload}, ensure_ascii=False))


if __name__ == "__main__":
    main()
