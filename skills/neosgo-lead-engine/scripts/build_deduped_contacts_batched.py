#!/usr/bin/env python3
import argparse
import json
import time
from pathlib import Path

import duckdb

SCHEMA_SQL = r'''
create table if not exists deduped_contacts (
  file_id varchar,
  company_name varchar,
  address varchar,
  city varchar,
  state varchar,
  zip varchar,
  county varchar,
  phone_digits varchar,
  contact_first varchar,
  contact_last varchar,
  contact_full varchar,
  title varchar,
  direct_phone_digits varchar,
  email varchar,
  website varchar,
  employee_count varchar,
  annual_sales varchar,
  sic_code varchar,
  industry varchar,
  raw_json varchar,
  company_l varchar,
  title_l varchar,
  industry_l varchar,
  company_key varchar,
  contact_key varchar,
  website_host varchar,
  email_domain varchar,
  has_valid_email integer,
  has_website integer,
  has_phone integer,
  has_named_contact integer,
  employee_band_rank integer,
  dedupe_key varchar
);
'''

INSERT_SQL = r'''
insert into deduped_contacts
with ranked as (
  select
    *,
    coalesce(nullif(email, ''), nullif(website_host, ''), nullif(company_key || '|' || state || '|' || city, '||')) as dedupe_key,
    row_number() over (
      partition by coalesce(nullif(email, ''), nullif(website_host, ''), nullif(company_key || '|' || state || '|' || city, '||'), file_id)
      order by has_valid_email desc, has_website desc, has_phone desc, has_named_contact desc, employee_band_rank desc nulls last, length(company_name) desc
    ) as rn
  from normalized_contacts
  where file_id = ?
)
select * exclude (rn)
from ranked
where rn = 1;
'''


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--db', required=True)
    ap.add_argument('--state-file', required=True)
    args = ap.parse_args()

    state_path = Path(args.state_file)
    con = duckdb.connect(args.db)
    con.execute(SCHEMA_SQL)

    done = set()
    if state_path.exists():
        try:
            payload = json.loads(state_path.read_text(encoding='utf-8'))
            done = set(payload.get('done_file_ids', []))
        except Exception:
            pass

    file_rows = con.execute('select file_id, row_count, source_archive, member_name from raw_import_files order by source_archive, member_name').fetchall()
    total_rows = con.execute('select count(*) from deduped_contacts').fetchone()[0]

    for idx, (file_id, row_count, source_archive, member_name) in enumerate(file_rows, start=1):
        if file_id in done:
            continue
        t0 = time.time()
        con.execute('delete from deduped_contacts where file_id = ?', [file_id])
        con.execute(INSERT_SQL, [file_id])
        inserted = con.execute('select count(*) from deduped_contacts where file_id = ?', [file_id]).fetchone()[0]
        total_rows += inserted
        done.add(file_id)
        payload = {
            'done_file_ids': sorted(done),
            'completed_files': len(done),
            'total_files': len(file_rows),
            'last_file_id': file_id,
            'last_member_name': member_name,
            'last_source_archive': source_archive,
            'last_rows_expected': row_count,
            'last_rows_inserted': inserted,
            'deduped_contacts_rows': total_rows,
            'updated_at': time.time(),
        }
        state_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
        print(json.dumps({
            'file_index': idx,
            'completed_files': len(done),
            'total_files': len(file_rows),
            'member_name': member_name,
            'rows_inserted': inserted,
            'elapsed_s': round(time.time() - t0, 2),
            'deduped_contacts_rows': total_rows,
        }, ensure_ascii=False), flush=True)

    print(json.dumps({'done': True, 'deduped_contacts_rows': con.execute('select count(*) from deduped_contacts').fetchone()[0]}, ensure_ascii=False), flush=True)
    con.close()


if __name__ == '__main__':
    main()
