#!/usr/bin/env python3
import argparse
import json
from pathlib import Path

ROOT = Path("/Users/mac_claw/.openclaw/workspace")


def plist(label: str, args: list[str], stdout_path: Path, stderr_path: Path) -> str:
    args_xml = "\n".join(f"      <string>{a}</string>" for a in args)
    return f'''<?xml version="1.0" encoding="UTF-8"?>
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
    <key>KeepAlive</key>
    <true/>
    <key>StandardOutPath</key>
    <string>{stdout_path}</string>
    <key>StandardErrorPath</key>
    <string>{stderr_path}</string>
  </dict>
</plist>
'''


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", required=True)
    ap.add_argument("--state", default="RI")
    ap.add_argument("--segment", default="")
    ap.add_argument("--fit-tier", default="S")
    ap.add_argument("--min-fit-score", type=int, default=80)
    ap.add_argument("--limit", type=int, default=50)
    ap.add_argument("--interval-seconds", type=int, default=1800)
    ap.add_argument("--telegram-chat", default="8528973600")
    ap.add_argument("--out-dir", default=str(Path.home() / "Library/LaunchAgents"))
    args = ap.parse_args()

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    label = f"com.neosgo.outreach-continuous.{args.state.lower()}"
    plist_path = out_dir / f"{label}.plist"
    stdout_path = ROOT / "output/neosgo/outreach-continuous.stdout.log"
    stderr_path = ROOT / "output/neosgo/outreach-continuous.stderr.log"

    cmd = [
        "python3",
        str(ROOT / "skills/neosgo-lead-engine/scripts/run_outreach_continuous_cycle.py"),
        "--db", args.db,
        "--state", args.state,
        "--segment", args.segment,
        "--fit-tier", args.fit_tier,
        "--min-fit-score", str(args.min_fit_score),
        "--limit", str(args.limit),
        "--batch-rest-min-seconds", "180",
        "--batch-rest-max-seconds", "720",
        "--loop-forever",
        "--send-telegram",
        "--telegram-chat", args.telegram_chat,
    ]
    plist_path.write_text(plist(label, cmd, stdout_path, stderr_path), encoding="utf-8")
    print(json.dumps({
        "plist": str(plist_path),
        "label": label,
        "load": f"launchctl bootstrap gui/{Path.home().owner() if False else '$(id -u)'} {plist_path}",
        "kickstart": f"launchctl kickstart -k gui/$(id -u)/{label}"
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
