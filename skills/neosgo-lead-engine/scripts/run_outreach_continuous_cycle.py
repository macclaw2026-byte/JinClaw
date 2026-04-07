#!/usr/bin/env python3
import argparse
import json
import os
import random
import subprocess
import time
from datetime import datetime
from pathlib import Path

ROOT = Path("/Users/mac_claw/.openclaw/workspace")
PREPARE = ROOT / "skills/neosgo-lead-engine/scripts/prepare_state_outreach_batch.py"
SEND = ROOT / "skills/neosgo-lead-engine/scripts/send_outreach_mail_batch.py"
REPORT = ROOT / "skills/neosgo-lead-engine/scripts/generate_outreach_task_report.py"
DEFAULT_PATH = "/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin"


def _env() -> dict[str, str]:
    env = os.environ.copy()
    env["PATH"] = f"{DEFAULT_PATH}:{env.get('PATH', '')}".strip(":")
    return env


def _run(cmd: list[str]) -> tuple[int, str, str]:
    proc = subprocess.run(cmd, capture_output=True, text=True, env=_env())
    return proc.returncode, proc.stdout, proc.stderr


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", required=True)
    ap.add_argument("--state", default="")
    ap.add_argument("--segment", default="")
    ap.add_argument("--fit-tier", default="S")
    ap.add_argument("--min-fit-score", type=int, default=80)
    ap.add_argument("--limit", type=int, default=50)
    ap.add_argument("--states", default="RI,MA,NH,VT,CT,ME,NY,NJ,PA,DE,MD,DC,VA,NC,SC,GA,FL,AL,MS,LA,TN,KY,WV,OH,MI,IN,IL,WI,MN,IA,MO,AR,TX,OK,KS,NE,SD,ND,CO,WY,MT,ID,UT,AZ,NM,NV,CA,OR,WA")
    ap.add_argument("--segments", default="designer,architect,builder,contractor,electrician,furniture_retailer,kitchen_bath")
    ap.add_argument("--sender-name", default="Neosgo Lighting")
    ap.add_argument("--sender-email", default="cs@neosgo.com")
    ap.add_argument("--website-url", default="https://neosgo.com")
    ap.add_argument("--events-dir", default=str(ROOT / "output/neosgo/events"))
    ap.add_argument("--sleep-seconds", type=float, default=2.0)
    ap.add_argument("--report-hours", type=int, default=6)
    ap.add_argument("--batch-rest-min-seconds", type=int, default=180)
    ap.add_argument("--batch-rest-max-seconds", type=int, default=720)
    ap.add_argument("--loop-forever", action="store_true")
    ap.add_argument("--send-telegram", action="store_true")
    ap.add_argument("--telegram-chat", default="8528973600")
    args = ap.parse_args()

    ts = datetime.now().strftime("%Y%m%dT%H%M%S")
    events_dir = Path(args.events_dir)
    events_dir.mkdir(parents=True, exist_ok=True)
    states = [s.strip().upper() for s in str(args.states).split(',') if s.strip()]
    segments = [s.strip() for s in str(args.segments).split(',') if s.strip()]
    if args.state:
        states = [args.state.strip().upper()]
    if args.segment:
        segments = [args.segment.strip()]

    def run_pass() -> dict:
        ts_local = datetime.now().strftime("%Y%m%dT%H%M%S")
        pass_result = {
            "started_at": datetime.now().isoformat(),
            "states": states,
            "segments": segments,
            "cycles": [],
        }
        sent_batches = 0
        for state in states:
            for segment in segments:
                events_csv = events_dir / f"{state}-{segment}-{ts_local}.sent-events.csv"
                cycle = {
                    "state": state,
                    "segment": segment,
                    "prepare": {},
                    "send": {},
                    "report": {},
                }
                prep_cmd = [
                    "python3", str(PREPARE),
                    "--db", args.db,
                    "--state", state,
                    "--segment", segment,
                    "--fit-tier", args.fit_tier,
                    "--min-fit-score", str(args.min_fit_score),
                    "--limit", str(args.limit),
                    "--sender-name", args.sender_name,
                    "--sender-email", args.sender_email,
                    "--website-url", args.website_url,
                    "--sent-events-glob", str(events_dir / "*.sent-events.csv"),
                ]
                prep_code, prep_out, prep_err = _run(prep_cmd)
                cycle["prepare"] = {"returncode": prep_code, "stderr": prep_err.strip()}
                if prep_code != 0:
                    cycle["prepare"]["stdout"] = prep_out.strip()
                    pass_result["cycles"].append(cycle)
                    continue
                manifest = json.loads(prep_out or "{}")
                cycle["prepare"]["manifest"] = manifest.get("manifest")
                cycle["prepare"]["rows"] = manifest.get("rows")
                if not int(manifest.get("rows") or 0):
                    pass_result["cycles"].append(cycle)
                    continue

                send_cmd = [
                    "python3", str(SEND),
                    "--csv", manifest["csv_out"],
                    "--events-csv", str(events_csv),
                    "--sleep-min-seconds", "5",
                    "--sleep-max-seconds", "30",
                ]
                send_code, send_out, send_err = _run(send_cmd)
                cycle["send"] = {"returncode": send_code, "stderr": send_err.strip()}
                try:
                    cycle["send"].update(json.loads(send_out or "{}"))
                except Exception:
                    cycle["send"]["stdout"] = send_out.strip()
                if int((cycle.get("send") or {}).get("sent") or 0) > 0:
                    sent_batches += 1

                report_md = ROOT / "output/neosgo/reports" / f"{state.lower()}-{segment}-continuous-6h.md"
                report_json = ROOT / "output/neosgo/reports" / f"{state.lower()}-{segment}-continuous-6h.json"
                report_cmd = [
                    "python3", str(REPORT),
                    "--db", args.db,
                    "--manifest", manifest["manifest"],
                    "--hours", str(args.report_hours),
                    "--out", str(report_md),
                    "--json-out", str(report_json),
                ]
                if args.send_telegram:
                    report_cmd.extend(["--send-telegram", "--telegram-chat", args.telegram_chat])
                report_code, report_out, report_err = _run(report_cmd)
                cycle["report"] = {"returncode": report_code, "stderr": report_err.strip()}
                try:
                    cycle["report"].update(json.loads(report_out or "{}"))
                except Exception:
                    cycle["report"]["stdout"] = report_out.strip()
                pass_result["cycles"].append(cycle)
                if sent_batches > 0:
                    delay = random.randint(args.batch_rest_min_seconds, args.batch_rest_max_seconds)
                    cycle["post_batch_rest_seconds"] = delay
                    time.sleep(delay)
        return pass_result

    if args.loop_forever:
        while True:
            print(json.dumps(run_pass(), ensure_ascii=False, indent=2), flush=True)
    else:
        print(json.dumps(run_pass(), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
