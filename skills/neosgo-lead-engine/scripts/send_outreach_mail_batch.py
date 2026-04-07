#!/usr/bin/env python3
import argparse
import csv
import json
import random
import subprocess
import time
from datetime import datetime
from pathlib import Path


EVENT_FIELDS = ["queue_id", "file_id", "event_type", "event_time", "payload_json"]


def _run_osascript(lines: list[str]) -> subprocess.CompletedProcess[str]:
    cmd = ["osascript"]
    for line in lines:
        cmd.extend(["-e", line])
    return subprocess.run(cmd, capture_output=True, text=True)


def _escape(value: str) -> str:
    return value.replace("\\", "\\\\").replace('"', '\\"')


def _send_one(row: dict[str, str]) -> dict:
    subject = _escape(row.get("subject", ""))
    body = _escape(row.get("body", ""))
    recipient = _escape(row.get("recipient_email", ""))
    sender = _escape(row.get("sender_display") or row.get("sender_email") or "")
    script = [
        'tell application "Mail"',
        'set m to make new outgoing message with properties {visible:false, subject:"' + subject + '", content:"' + body + '" & return}',
        'tell m',
        'set sender to "' + sender + '"',
        'make new to recipient at end of to recipients with properties {address:"' + recipient + '"}',
        'send',
        'return subject of m',
        'end tell',
        'end tell',
    ]
    proc = _run_osascript(script)
    return {"returncode": proc.returncode, "stdout": proc.stdout.strip(), "stderr": proc.stderr.strip()}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--csv", required=True)
    ap.add_argument("--events-csv", required=True)
    ap.add_argument("--sleep-seconds", type=float, default=2.0)
    ap.add_argument("--sleep-min-seconds", type=float, default=5.0)
    ap.add_argument("--sleep-max-seconds", type=float, default=30.0)
    args = ap.parse_args()

    csv_path = Path(args.csv)
    events_csv = Path(args.events_csv)
    rows = []
    with csv_path.open("r", encoding="utf-8", newline="") as fh:
        rows = list(csv.DictReader(fh))

    sent_rows = []
    failures = []
    event_rows = []
    for idx, row in enumerate(rows, start=1):
        result = _send_one(row)
        record = {
            "index": idx,
            "queue_id": row.get("queue_id", ""),
            "recipient_email": row.get("recipient_email", ""),
            "subject": row.get("subject", ""),
            **result,
        }
        if result["returncode"] == 0:
            sent_rows.append(record)
            event_rows.append(
                {
                    "queue_id": row.get("queue_id", ""),
                    "file_id": row.get("file_id", ""),
                    "event_type": "sent",
                    "event_time": datetime.now().isoformat(sep=" "),
                    "payload_json": json.dumps(
                        {
                            "recipient_email": row.get("recipient_email", ""),
                            "subject": row.get("subject", ""),
                            "segment_primary": row.get("segment_primary", ""),
                            "template_version": row.get("template_version", ""),
                            "sender_display": row.get("sender_display", ""),
                        },
                        ensure_ascii=False,
                    ),
                }
            )
        else:
            failures.append(record)
        if idx < len(rows):
            if args.sleep_max_seconds >= args.sleep_min_seconds and args.sleep_max_seconds > 0:
                delay = random.uniform(args.sleep_min_seconds, args.sleep_max_seconds)
            else:
                delay = args.sleep_seconds
            if delay > 0:
                time.sleep(delay)

    events_csv.parent.mkdir(parents=True, exist_ok=True)
    with events_csv.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=EVENT_FIELDS)
        writer.writeheader()
        writer.writerows(event_rows)

    print(
        json.dumps(
            {
                "csv": str(csv_path),
                "events_csv": str(events_csv),
                "attempted": len(rows),
                "sent": len(sent_rows),
                "failed": len(failures),
                "failures": failures[:10],
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
