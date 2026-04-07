#!/usr/bin/env python3
import argparse
import json
import subprocess
from datetime import datetime
from pathlib import Path


ROOT = Path("/Users/mac_claw/.openclaw/workspace")
EXPORT_SCRIPT = ROOT / "skills/neosgo-lead-engine/scripts/export_outreach_mail_batch.py"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", required=True)
    ap.add_argument("--state", required=True)
    ap.add_argument("--segment", default="")
    ap.add_argument("--fit-tier", default="S")
    ap.add_argument("--min-fit-score", type=int, default=90)
    ap.add_argument("--limit", type=int, default=50)
    ap.add_argument("--sender-name", default="Neosgo Lighting")
    ap.add_argument("--sender-email", default="cs@neosgo.com")
    ap.add_argument("--website-url", default="https://neosgo.com")
    ap.add_argument("--out-dir", default=str(ROOT / "output/neosgo/batches"))
    ap.add_argument("--sent-events-glob", default=str(ROOT / "output/neosgo/events/*.sent-events.csv"))
    args = ap.parse_args()

    ts = datetime.now().strftime("%Y%m%dT%H%M%S")
    slug_parts = [args.state.upper()]
    if args.segment:
        slug_parts.append(args.segment)
    slug = "-".join(slug_parts)
    out_dir = Path(args.out_dir) / slug / ts
    out_dir.mkdir(parents=True, exist_ok=True)
    csv_out = out_dir / "mail-batch.csv"
    json_out = out_dir / "mail-batch.json"
    manifest_out = out_dir / "batch-manifest.json"

    cmd = [
        "python3",
        str(EXPORT_SCRIPT),
        "--db",
        args.db,
        "--sender-email",
        args.sender_email,
        "--sender-name",
        args.sender_name,
        "--website-url",
        args.website_url,
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
        "--sent-events-glob",
        str(args.sent_events_glob),
        "--csv-out",
        str(csv_out),
        "--json-out",
        str(json_out),
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True, check=True)
    export_payload = json.loads(proc.stdout.strip() or "{}")
    rows = json.loads(json_out.read_text(encoding="utf-8")) if json_out.exists() else []
    queue_ids = [row.get("queue_id", "") for row in rows if row.get("queue_id")]
    manifest = {
        "created_at": datetime.now().isoformat(),
        "state": args.state.upper(),
        "segment": args.segment,
        "fit_tier": args.fit_tier,
        "min_fit_score": args.min_fit_score,
        "limit": args.limit,
        "sender_name": args.sender_name,
        "sender_email": args.sender_email,
        "website_url": args.website_url,
        "rows": len(rows),
        "queue_ids": queue_ids,
        "csv_out": str(csv_out),
        "json_out": str(json_out),
        "export_payload": export_payload,
    }
    manifest_out.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"manifest": str(manifest_out), **manifest}, ensure_ascii=False))


if __name__ == "__main__":
    main()
