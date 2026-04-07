#!/usr/bin/env python3
import argparse
import csv
import json
from pathlib import Path

import duckdb

SCHEMA_SQL = '''
create table if not exists outreach_events (
  event_id varchar,
  queue_id varchar,
  file_id varchar,
  event_type varchar,
  event_time timestamp,
  payload_json varchar,
  created_at timestamp default current_timestamp
);
'''


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--db', required=True)
    ap.add_argument('--csv', required=True)
    args = ap.parse_args()

    csv_path = Path(args.csv)
    con = duckdb.connect(args.db)
    con.execute(SCHEMA_SQL)

    inserted = 0
    skipped = 0
    with csv_path.open('r', encoding='utf-8', newline='') as f:
        reader = csv.DictReader(f)
        for row in reader:
            queue_id = (row.get('queue_id') or '').strip()
            file_id = (row.get('file_id') or '').strip()
            event_type = (row.get('event_type') or '').strip()
            event_time = (row.get('event_time') or '').strip()
            payload_json = (row.get('payload_json') or '').strip()
            if not (queue_id and file_id and event_type and event_time):
                skipped += 1
                continue
            if payload_json:
                try:
                    json.loads(payload_json)
                except Exception:
                    skipped += 1
                    continue
            event_id = f"{queue_id}|{event_type}|{event_time}"
            exists = con.execute('select 1 from outreach_events where event_id=? limit 1', [event_id]).fetchone()
            if exists:
                skipped += 1
                continue
            con.execute(
                'insert into outreach_events(event_id, queue_id, file_id, event_type, event_time, payload_json) values (?, ?, ?, ?, ?, ?)',
                [event_id, queue_id, file_id, event_type, event_time, payload_json or '{}']
            )
            inserted += 1

    total = con.execute('select count(*) from outreach_events').fetchone()[0]
    con.close()
    print(json.dumps({'csv': str(csv_path), 'inserted': inserted, 'skipped': skipped, 'outreach_events_total': total}, ensure_ascii=False))


if __name__ == '__main__':
    main()
