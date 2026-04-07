#!/usr/bin/env python3
import argparse
import json
import subprocess
from datetime import datetime
from pathlib import Path


ROOT = Path("/Users/mac_claw/.openclaw/workspace")
PREPARE_SCRIPT = ROOT / "skills/neosgo-lead-engine/scripts/prepare_state_outreach_batch.py"
MAIL_BRIDGE = ROOT / "skills/neosgo-lead-engine/scripts/apple_mail_bridge.py"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", required=True)
    ap.add_argument("--state", required=True)
    ap.add_argument("--segment", default="")
    ap.add_argument("--fit-tier", default="S")
    ap.add_argument("--min-fit-score", type=int, default=90)
    ap.add_argument("--limit", type=int, default=25)
    ap.add_argument("--account-name", default="Neosgo")
    ap.add_argument("--sender-name", default="Neosgo Lighting")
    ap.add_argument("--sender-email", default="cs@neosgo.com")
    ap.add_argument("--website-url", default="https://neosgo.com")
    ap.add_argument("--create-drafts", action="store_true")
    args = ap.parse_args()

    prep = subprocess.run(
        [
            "python3",
            str(PREPARE_SCRIPT),
            "--db",
            args.db,
            "--state",
            args.state,
            "--segment",
            args.segment,
            "--fit-tier",
            args.fit_tier,
            "--min-fit-score",
            str(args.min_fit_score),
            "--limit",
            str(args.limit),
            "--sender-name",
            args.sender_name,
            "--sender-email",
            args.sender_email,
            "--website-url",
            args.website_url,
        ],
        capture_output=True,
        text=True,
        check=True,
    )
    manifest = json.loads(prep.stdout or "{}")
    result = {
        "launched_at": datetime.now().isoformat(),
        "manifest": manifest,
        "drafts": {},
    }
    if args.create_drafts:
        proc = subprocess.run(
            [
                "python3",
                str(MAIL_BRIDGE),
                "create-drafts",
                "--account-name",
                args.account_name,
                "--csv",
                manifest["csv_out"],
                "--limit",
                str(manifest["rows"]),
            ],
            capture_output=True,
            text=True,
            timeout=180,
        )
        try:
            result["drafts"] = json.loads(proc.stdout or "{}")
        except Exception:
            result["drafts"] = {"returncode": proc.returncode, "stdout": proc.stdout.strip(), "stderr": proc.stderr.strip()}
    print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    main()
