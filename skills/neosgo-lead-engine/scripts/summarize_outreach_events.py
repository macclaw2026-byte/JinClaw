#!/usr/bin/env python3
import argparse
from pathlib import Path

import duckdb


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--db', required=True)
    ap.add_argument('--out', required=True)
    args = ap.parse_args()

    con = duckdb.connect(args.db, read_only=True)
    totals = con.execute("""
        select event_type, count(*) as c
        from outreach_events
        group by 1
        order by c desc, event_type
    """).fetchall()
    recent = con.execute("""
        select event_time, event_type, file_id, payload_json
        from outreach_events
        order by event_time desc
        limit 20
    """).fetchall()
    con.close()

    lines = ['# Outreach events summary', '']
    lines.append('## Totals by event type')
    for event_type, c in totals:
        lines.append(f'- {event_type}: {c}')
    lines.append('')
    lines.append('## Recent events')
    for event_time, event_type, file_id, payload_json in recent:
        lines.append(f'- {event_time} | {event_type} | file_id={file_id} | payload={payload_json}')

    Path(args.out).write_text('\n'.join(lines) + '\n', encoding='utf-8')


if __name__ == '__main__':
    main()
