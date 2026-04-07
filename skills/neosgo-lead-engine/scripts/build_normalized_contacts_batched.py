#!/usr/bin/env python3
import argparse
import json
import time
from pathlib import Path

import duckdb

SCHEMA_SQL = r'''
create table if not exists normalized_contacts (
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
  employee_band_rank integer
);
'''

INSERT_SQL = r'''
insert into normalized_contacts
select
  file_id,
  trim(coalesce(company_name, '')) as company_name,
  trim(coalesce(address, '')) as address,
  trim(coalesce(city, '')) as city,
  upper(trim(coalesce(state, ''))) as state,
  regexp_replace(trim(coalesce(zip, '')), '[^0-9-]', '', 'g') as zip,
  trim(coalesce(county, '')) as county,
  regexp_replace(trim(coalesce(phone, '')), '[^0-9]', '', 'g') as phone_digits,
  trim(coalesce(contact_first, '')) as contact_first,
  trim(coalesce(contact_last, '')) as contact_last,
  trim(coalesce(contact_full, '')) as contact_full,
  trim(coalesce(title, '')) as title,
  regexp_replace(trim(coalesce(direct_phone, '')), '[^0-9]', '', 'g') as direct_phone_digits,
  lower(trim(coalesce(email, ''))) as email,
  lower(trim(coalesce(website, ''))) as website,
  trim(coalesce(employee_count, '')) as employee_count,
  trim(coalesce(annual_sales, '')) as annual_sales,
  trim(coalesce(sic_code, '')) as sic_code,
  trim(coalesce(industry, '')) as industry,
  raw_json,
  lower(trim(coalesce(company_name, ''))) as company_l,
  lower(trim(coalesce(title, ''))) as title_l,
  lower(trim(coalesce(industry, ''))) as industry_l,
  regexp_replace(lower(trim(coalesce(company_name, ''))), '[^a-z0-9]+', '', 'g') as company_key,
  regexp_replace(lower(trim(coalesce(coalesce(contact_full, ''), concat_ws(' ', contact_first, contact_last)))), '[^a-z0-9]+', '', 'g') as contact_key,
  case
    when lower(trim(coalesce(website, ''))) like 'http://%' then regexp_replace(replace(lower(trim(coalesce(website, ''))), 'http://', ''), '/.*$', '')
    when lower(trim(coalesce(website, ''))) like 'https://%' then regexp_replace(replace(lower(trim(coalesce(website, ''))), 'https://', ''), '/.*$', '')
    else regexp_replace(lower(trim(coalesce(website, ''))), '/.*$', '')
  end as website_host,
  case when strpos(lower(trim(coalesce(email, ''))), '@') > 0 then split_part(lower(trim(coalesce(email, ''))), '@', 2) else '' end as email_domain,
  case when lower(trim(coalesce(email, ''))) ~ '^[^@\\s]+@[^@\\s]+\\.[^@\\s]+$' then 1 else 0 end as has_valid_email,
  case when trim(coalesce(website, '')) <> '' then 1 else 0 end as has_website,
  case when length(regexp_replace(trim(coalesce(phone, '')), '[^0-9]', '', 'g')) between 10 and 11 or length(regexp_replace(trim(coalesce(direct_phone, '')), '[^0-9]', '', 'g')) between 10 and 11 then 1 else 0 end as has_phone,
  case when trim(coalesce(contact_full, '')) <> '' or trim(coalesce(contact_first, '')) <> '' or trim(coalesce(contact_last, '')) <> '' then 1 else 0 end as has_named_contact,
  case trim(coalesce(employee_count, ''))
    when '1 To 4' then 1
    when '5 To 9' then 2
    when '10 To 19' then 3
    when '20 To 49' then 4
    when '50 To 99' then 5
    when '100 To 249' then 6
    when '250 To 499' then 7
    when '500 To 999' then 8
    when '1,000 To 4,999' then 9
    when '5,000 To 9,999' then 10
    when 'Over 10,000' then 11
    else null
  end as employee_band_rank
from raw_contacts
where file_id = ?;
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
    total_rows = con.execute('select count(*) from normalized_contacts').fetchone()[0]

    for idx, (file_id, row_count, source_archive, member_name) in enumerate(file_rows, start=1):
        if file_id in done:
            continue
        t0 = time.time()
        con.execute('delete from normalized_contacts where file_id = ?', [file_id])
        con.execute(INSERT_SQL, [file_id])
        inserted = con.execute('select count(*) from normalized_contacts where file_id = ?', [file_id]).fetchone()[0]
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
            'normalized_contacts_rows': total_rows,
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
            'normalized_contacts_rows': total_rows,
        }, ensure_ascii=False), flush=True)

    print(json.dumps({'done': True, 'normalized_contacts_rows': con.execute('select count(*) from normalized_contacts').fetchone()[0]}, ensure_ascii=False), flush=True)
    con.close()


if __name__ == '__main__':
    main()
