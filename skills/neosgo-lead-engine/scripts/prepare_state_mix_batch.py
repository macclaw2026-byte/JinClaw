#!/usr/bin/env python3
import argparse
import csv
import json
import subprocess
from datetime import datetime
from pathlib import Path


ROOT = Path("/Users/mac_claw/.openclaw/workspace")
EXPORT_SCRIPT = ROOT / "skills/neosgo-lead-engine/scripts/export_outreach_mail_batch.py"


def _parse_segment_limits(raw_items: list[str]) -> list[tuple[str, int]]:
    parsed: list[tuple[str, int]] = []
    for item in raw_items:
        segment, _, limit = item.partition(":")
        segment = segment.strip()
        if not segment:
            continue
        parsed.append((segment, int(limit or "0")))
    return parsed


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", required=True)
    ap.add_argument("--state", required=True)
    ap.add_argument("--segment-limit", action="append", default=[])
    ap.add_argument("--fit-tier", default="S")
    ap.add_argument("--min-fit-score", type=int, default=80)
    ap.add_argument("--sender-name", default="Neosgo Lighting")
    ap.add_argument("--sender-email", default="cs@neosgo.com")
    ap.add_argument("--website-url", default="https://neosgo.com")
    ap.add_argument("--out-dir", default=str(ROOT / "output/neosgo/batches"))
    args = ap.parse_args()

    segment_limits = _parse_segment_limits(args.segment_limit)
    ts = datetime.now().strftime("%Y%m%dT%H%M%S")
    slug = f"{args.state.upper()}-mix"
    out_dir = Path(args.out_dir) / slug / ts
    out_dir.mkdir(parents=True, exist_ok=True)

    all_rows: list[dict] = []
    seen_queue_ids: set[str] = set()
    source_batches = []
    for segment, limit in segment_limits:
        seg_slug = f"{segment}-{limit}"
        csv_out = out_dir / f"{seg_slug}.csv"
        json_out = out_dir / f"{seg_slug}.json"
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
            segment,
            "--fit-tier",
            args.fit_tier,
            "--min-fit-score",
            str(args.min_fit_score),
            "--limit",
            str(limit),
            "--csv-out",
            str(csv_out),
            "--json-out",
            str(json_out),
        ]
        proc = subprocess.run(cmd, capture_output=True, text=True, check=True)
        export_payload = json.loads(proc.stdout.strip() or "{}")
        rows = json.loads(json_out.read_text(encoding="utf-8")) if json_out.exists() else []
        kept = 0
        for row in rows:
            qid = str(row.get("queue_id") or "").strip()
            if not qid or qid in seen_queue_ids:
                continue
            seen_queue_ids.add(qid)
            all_rows.append(row)
            kept += 1
        source_batches.append({"segment": segment, "requested": limit, "exported": len(rows), "kept": kept, "csv_out": str(csv_out), "json_out": str(json_out), "export_payload": export_payload})

    combined_csv = out_dir / "mail-batch.csv"
    combined_json = out_dir / "mail-batch.json"
    manifest = out_dir / "batch-manifest.json"

    if all_rows:
        with combined_csv.open("w", encoding="utf-8", newline="") as fh:
            writer = csv.DictWriter(fh, fieldnames=list(all_rows[0].keys()))
            writer.writeheader()
            writer.writerows(all_rows)
    else:
        combined_csv.write_text("", encoding="utf-8")
    combined_json.write_text(json.dumps(all_rows, ensure_ascii=False, indent=2), encoding="utf-8")

    payload = {
        "created_at": datetime.now().isoformat(),
        "state": args.state.upper(),
        "fit_tier": args.fit_tier,
        "min_fit_score": args.min_fit_score,
        "sender_name": args.sender_name,
        "sender_email": args.sender_email,
        "website_url": args.website_url,
        "rows": len(all_rows),
        "queue_ids": [row.get("queue_id", "") for row in all_rows if row.get("queue_id")],
        "segments": source_batches,
        "csv_out": str(combined_csv),
        "json_out": str(combined_json),
    }
    manifest.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"manifest": str(manifest), **payload}, ensure_ascii=False))


if __name__ == "__main__":
    main()
