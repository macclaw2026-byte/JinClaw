#!/usr/bin/env python3
import argparse
import csv
import json
import subprocess
from pathlib import Path


def _run_osascript(lines: list[str]) -> subprocess.CompletedProcess[str]:
    cmd = ["osascript"]
    for line in lines:
        cmd.extend(["-e", line])
    return subprocess.run(cmd, capture_output=True, text=True)


def list_accounts() -> int:
    proc = _run_osascript(
        [
            'tell application "Mail"',
            'set namesList to name of every account',
            'set AppleScript\'s text item delimiters to linefeed',
            'return namesList as text',
            'end tell',
        ]
    )
    print(
        json.dumps(
            {"returncode": proc.returncode, "stdout": proc.stdout.strip(), "stderr": proc.stderr.strip()},
            ensure_ascii=False,
        )
    )
    return proc.returncode


def _apple_escape(value: str) -> str:
    return value.replace("\\", "\\\\").replace('"', '\\"')


def create_drafts(*, account_name: str, csv_path: Path, limit: int) -> int:
    rows = []
    with csv_path.open("r", encoding="utf-8", newline="") as fh:
        reader = csv.DictReader(fh)
        for idx, row in enumerate(reader):
            if idx >= limit:
                break
            rows.append(row)

    created = []
    errors = []
    for row in rows:
        subject = _apple_escape(row.get("subject", ""))
        body = _apple_escape(row.get("body", ""))
        recipient = _apple_escape(row.get("recipient_email", ""))
        sender = _apple_escape(account_name)
        sender_display = _apple_escape(row.get("sender_display") or row.get("sender_email") or account_name)
        proc = _run_osascript(
            [
                'tell application "Mail"',
                f'set targetAccount to first account whose name is "{sender}"',
                'set newMessage to make new outgoing message with properties {visible:false, subject:"'
                + subject
                + '", content:"'
                + body
                + '" & return & return}',
                'tell newMessage',
                'make new to recipient at end of to recipients with properties {address:"' + recipient + '"}',
                'set sender to "' + sender_display + '"',
                'save',
                'end tell',
                'return id of newMessage',
                'end tell',
            ]
        )
        if proc.returncode == 0:
            created.append(
                {
                    "queue_id": row.get("queue_id"),
                    "recipient_email": row.get("recipient_email"),
                    "subject": row.get("subject"),
                    "mail_message_id": proc.stdout.strip(),
                }
            )
        else:
            errors.append(
                {
                    "queue_id": row.get("queue_id"),
                    "recipient_email": row.get("recipient_email"),
                    "stderr": proc.stderr.strip(),
                    "stdout": proc.stdout.strip(),
                }
            )
    print(json.dumps({"created": created, "errors": errors}, ensure_ascii=False, indent=2))
    return 0 if not errors else 1


def main() -> None:
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)

    sub.add_parser("list-accounts")

    drafts = sub.add_parser("create-drafts")
    drafts.add_argument("--account-name", required=True)
    drafts.add_argument("--csv", required=True)
    drafts.add_argument("--limit", type=int, default=10)

    args = ap.parse_args()
    if args.cmd == "list-accounts":
        raise SystemExit(list_accounts())
    if args.cmd == "create-drafts":
        raise SystemExit(create_drafts(account_name=args.account_name, csv_path=Path(args.csv), limit=args.limit))


if __name__ == "__main__":
    main()
