#!/usr/bin/env python3
import argparse
import json
from pathlib import Path


WORKSPACE = Path("/Users/mac_claw/.openclaw/workspace")


def _plist(label: str, program_args: list[str], start_interval: int, stdout_path: Path, stderr_path: Path) -> str:
    args_xml = "\n".join(f"      <string>{arg}</string>" for arg in program_args)
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
  <dict>
    <key>Label</key>
    <string>{label}</string>
    <key>ProgramArguments</key>
    <array>
{args_xml}
    </array>
    <key>RunAtLoad</key>
    <true/>
    <key>StartInterval</key>
    <integer>{start_interval}</integer>
    <key>StandardOutPath</key>
    <string>{stdout_path}</string>
    <key>StandardErrorPath</key>
    <string>{stderr_path}</string>
  </dict>
</plist>
"""


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", required=True)
    ap.add_argument("--manifest", required=True)
    ap.add_argument("--telegram-chat", default="8528973600")
    ap.add_argument("--reply-interval-seconds", type=int, default=300)
    ap.add_argument("--report-interval-seconds", type=int, default=21600)
    ap.add_argument("--out-dir", default=str(Path.home() / "Library/LaunchAgents"))
    args = ap.parse_args()

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    reports_dir = WORKSPACE / "output/neosgo/reports"
    reports_dir.mkdir(parents=True, exist_ok=True)
    monitor_json = WORKSPACE / "output/neosgo/mail-replies-live.json"
    monitor_csv = WORKSPACE / "output/neosgo/mail-replies-live.csv"
    report_md = reports_dir / "task-6h.md"
    report_json = reports_dir / "task-6h.json"

    reply_plist = out_dir / "com.neosgo.reply-monitor.plist"
    report_plist = out_dir / "com.neosgo.task-report.plist"

    reply_cmd = [
        "python3",
        str(WORKSPACE / "skills/neosgo-lead-engine/scripts/watch_mail_replies.py"),
        "--account-name",
        "Neosgo",
        "--mailbox",
        "INBOX",
        "--limit",
        "20",
        "--unread-only",
        "--db",
        args.db,
        "--json-out",
        str(monitor_json),
        "--event-csv-out",
        str(monitor_csv),
        "--import-events",
        "--send-telegram",
        "--telegram-chat",
        args.telegram_chat,
    ]
    report_cmd = [
        "python3",
        str(WORKSPACE / "skills/neosgo-lead-engine/scripts/generate_outreach_task_report.py"),
        "--db",
        args.db,
        "--manifest",
        args.manifest,
        "--hours",
        "6",
        "--out",
        str(report_md),
        "--json-out",
        str(report_json),
        "--send-telegram",
        "--telegram-chat",
        args.telegram_chat,
    ]

    reply_plist.write_text(
        _plist(
            "com.neosgo.reply-monitor",
            reply_cmd,
            args.reply_interval_seconds,
            WORKSPACE / "output/neosgo/reply-monitor.stdout.log",
            WORKSPACE / "output/neosgo/reply-monitor.stderr.log",
        ),
        encoding="utf-8",
    )
    report_plist.write_text(
        _plist(
            "com.neosgo.task-report",
            report_cmd,
            args.report_interval_seconds,
            WORKSPACE / "output/neosgo/task-report.stdout.log",
            WORKSPACE / "output/neosgo/task-report.stderr.log",
        ),
        encoding="utf-8",
    )

    payload = {
        "reply_plist": str(reply_plist),
        "report_plist": str(report_plist),
        "load_commands": [
            f"launchctl load -w {reply_plist}",
            f"launchctl load -w {report_plist}",
        ],
    }
    print(json.dumps(payload, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
