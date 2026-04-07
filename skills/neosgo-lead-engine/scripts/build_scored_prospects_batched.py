#!/usr/bin/env python3
import argparse
import json
import time
from pathlib import Path

import duckdb

SCHEMA_SQL = r'''
create table if not exists scored_prospects (
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
  dedupe_key varchar,
  segment_primary varchar,
  segment_secondary varchar,
  decision_role_level varchar,
  size_band varchar,
  buyer_type varchar,
  score_industry_fit integer,
  score_influence integer,
  score_scale integer,
  score_neosgo_fit integer,
  score_contactability integer,
  score_market_priority integer,
  fit_score integer,
  fit_tier varchar,
  fit_reason varchar
);
'''

INSERT_SQL = r'''
insert into scored_prospects
with classified as (
  select
    *,
    case
      when industry_l like '%interior decorator%' or industry_l like '%design consultant%' or industry_l like '%interior design%' then 'designer'
      when industry_l like '%architect%' then 'architect'
      when industry_l like '%general contractor%' or industry_l like '%contractor%' or industry_l like '%remodel%' then 'contractor'
      when industry_l like '%home builder%' or industry_l like '%builder%' or sic_code in ('152103','152112','153107') then 'builder'
      when industry_l like '%lighting fixture%' or industry_l like '%lighting consultant%' or industry_l like '%lighting%' then 'lighting'
      when industry_l like '%electric%' then 'electrician'
      when industry_l like '%furniture-dealers-retail%' or industry_l like '%home furnishing%' or industry_l like '%furniture%' then 'furniture_retailer'
      when industry_l like '%property management%' then 'property_manager'
      when industry_l like '%hotel%' or industry_l like '%motels%' or industry_l like '%hospitality%' then 'hospitality'
      when industry_l like '%real estate agent%' or title_l like '%realtor%' or title_l like '%real estate agent%' or industry_l like '%brokerage%' then 'realtor'
      when industry_l like '%kitchen cabinets%' or industry_l like '%cabinet%' then 'kitchen_bath'
      else 'other'
    end as segment_primary,
    case
      when industry_l like '%lighting%' then 'lighting'
      when industry_l like '%furniture%' then 'furniture'
      when industry_l like '%decor%' or industry_l like '%design%' then 'home_decor'
      when industry_l like '%cabinet%' or industry_l like '%kitchen%' or industry_l like '%bath%' then 'kitchen_bath'
      when industry_l like '%hotel%' or industry_l like '%motels%' then 'hospitality'
      when industry_l like '%property management%' then 'multifamily'
      when industry_l like '%architect%' or industry_l like '%builder%' or industry_l like '%contractor%' then 'project'
      else 'general'
    end as segment_secondary,
    case
      when title_l like '%owner%' or title_l like '%president%' or title_l like '%principal%' or title_l like '%partner%' or title_l like '%founder%' or title_l like '%chief executive%' or title_l = 'ceo' then 'owner_exec'
      when title_l like '%director%' or title_l like '%manager%' or title_l like '%vice president%' or title_l like '%vp%' or title_l like '%procurement%' or title_l like '%purchasing%' then 'manager_director'
      when title_l like '%designer%' or title_l like '%architect%' or title_l like '%agent%' or title_l like '%realtor%' or title_l like '%project%' then 'practitioner'
      else 'unclear'
    end as decision_role_level,
    case
      when employee_band_rank between 2 and 6 then 'core_smb'
      when employee_band_rank = 1 then 'micro'
      when employee_band_rank >= 7 then 'large'
      else 'unknown'
    end as size_band
  from deduped_contacts
  where file_id = ?
), scored as (
  select
    *,
    case
      when segment_primary in ('designer','architect','contractor','builder','electrician','lighting','property_manager','hospitality') then 'trade_buyer'
      when segment_primary in ('furniture_retailer','kitchen_bath') then 'channel_buyer'
      when segment_primary = 'realtor' then 'influencer'
      else 'low_fit'
    end as buyer_type,
    case
      when segment_primary = 'designer' then 30
      when segment_primary = 'architect' then 29
      when segment_primary = 'builder' then 28
      when segment_primary = 'contractor' then 27
      when segment_primary in ('electrician','lighting') then 25
      when segment_primary = 'property_manager' then 24
      when segment_primary = 'hospitality' then 23
      when segment_primary in ('furniture_retailer','kitchen_bath') then 22
      when segment_primary = 'realtor' then 15
      else 0
    end as score_industry_fit,
    case
      when title_l like '%owner%' or title_l like '%president%' or title_l like '%principal%' or title_l like '%partner%' or title_l like '%founder%' or title_l like '%chief executive%' or title_l = 'ceo' then 20
      when title_l like '%director%' or title_l like '%manager%' or title_l like '%vice president%' or title_l like '%vp%' or title_l like '%procurement%' or title_l like '%purchasing%' then 14
      when title_l like '%designer%' or title_l like '%architect%' or title_l like '%agent%' or title_l like '%realtor%' or title_l like '%project%' then 10
      else 0
    end as score_influence,
    case
      when employee_band_rank between 2 and 6 then 15
      when employee_band_rank = 1 then 10
      when employee_band_rank >= 7 then 8
      else 5
    end as score_scale,
    case
      when segment_primary in ('designer','architect','contractor','builder','electrician','lighting','property_manager','hospitality') then 20
      when segment_primary in ('furniture_retailer','kitchen_bath') then 18
      when segment_primary = 'realtor' then 10
      else 0
    end as score_neosgo_fit,
    (has_valid_email * 6 + has_phone * 2 + has_website * 1 + has_named_contact * 1) as score_contactability,
    case when state in ('CA','TX','FL','NY','NJ','IL','WA','GA','NC','VA','MA') then 5 else 0 end as score_market_priority
  from classified
)
select
  *,
  score_industry_fit + score_influence + score_scale + score_neosgo_fit + score_contactability + score_market_priority as fit_score,
  case
    when score_industry_fit + score_influence + score_scale + score_neosgo_fit + score_contactability + score_market_priority >= 75 then 'S'
    when score_industry_fit + score_influence + score_scale + score_neosgo_fit + score_contactability + score_market_priority >= 60 then 'A'
    when score_industry_fit + score_influence + score_scale + score_neosgo_fit + score_contactability + score_market_priority >= 40 then 'B'
    else 'C'
  end as fit_tier,
  concat_ws(' | ', concat('segment=', segment_primary), concat('buyer_type=', buyer_type), concat('role=', decision_role_level), concat('size=', size_band), concat('email=', cast(has_valid_email as varchar)), concat('phone=', cast(has_phone as varchar)), concat('website=', cast(has_website as varchar))) as fit_reason
from scored
where has_valid_email = 1 and has_website = 1;
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
    file_rows = con.execute('select file_id, source_archive, member_name from raw_import_files order by source_archive, member_name').fetchall()
    total_rows = con.execute('select count(*) from scored_prospects').fetchone()[0]
    for idx, (file_id, source_archive, member_name) in enumerate(file_rows, start=1):
        if file_id in done:
            continue
        t0=time.time()
        con.execute('delete from scored_prospects where file_id = ?', [file_id])
        con.execute(INSERT_SQL, [file_id])
        inserted = con.execute('select count(*) from scored_prospects where file_id = ?', [file_id]).fetchone()[0]
        total_rows += inserted
        done.add(file_id)
        payload = {'done_file_ids': sorted(done), 'completed_files': len(done), 'total_files': len(file_rows), 'last_file_id': file_id, 'last_member_name': member_name, 'last_source_archive': source_archive, 'last_rows_inserted': inserted, 'scored_prospects_rows': total_rows, 'updated_at': time.time()}
        state_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
        print(json.dumps({'file_index': idx, 'completed_files': len(done), 'total_files': len(file_rows), 'member_name': member_name, 'rows_inserted': inserted, 'elapsed_s': round(time.time()-t0,2), 'scored_prospects_rows': total_rows}, ensure_ascii=False), flush=True)
    print(json.dumps({'done': True, 'scored_prospects_rows': con.execute('select count(*) from scored_prospects').fetchone()[0]}, ensure_ascii=False), flush=True)
    con.close()

if __name__ == '__main__':
    main()
