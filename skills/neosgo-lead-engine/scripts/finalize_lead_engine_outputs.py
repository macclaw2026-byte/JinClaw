#!/usr/bin/env python3
import argparse
from pathlib import Path

import duckdb


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--db', required=True)
    ap.add_argument('--report-out', required=True)
    args = ap.parse_args()

    con = duckdb.connect(args.db)
    con.execute("""
create or replace table persona_summary as
select
  segment_primary,
  buyer_type,
  decision_role_level,
  size_band,
  fit_tier,
  state,
  count(*) as lead_count,
  round(avg(fit_score), 2) as avg_fit_score,
  approx_count_distinct(company_key) as distinct_company_keys,
  approx_count_distinct(email_domain) as distinct_email_domains
from scored_prospects
group by 1,2,3,4,5,6
order by fit_tier, lead_count desc;

create or replace table outreach_ready_leads as
select
  md5(coalesce(email, website_host, company_key || '|' || state || '|' || city)) as queue_lead_id,
  file_id,
  company_name,
  contact_first,
  contact_last,
  coalesce(nullif(contact_full, ''), concat_ws(' ', contact_first, contact_last)) as contact_name,
  title,
  email,
  website,
  website_host,
  phone_digits as phone,
  city,
  state,
  industry,
  segment_primary,
  segment_secondary,
  buyer_type,
  decision_role_level,
  size_band,
  fit_score,
  fit_tier,
  fit_reason,
  case when fit_tier = 'S' then fit_score + 20 when fit_tier = 'A' then fit_score + 10 else fit_score end as outreach_priority_score
from scored_prospects
where segment_primary in ('designer','architect','contractor','builder','electrician','lighting','property_manager','hospitality','furniture_retailer','kitchen_bath','realtor');

create table if not exists campaign_variants (
  campaign_id varchar,
  segment_primary varchar,
  fit_tier varchar,
  variant_code varchar,
  channel varchar,
  subject_template varchar,
  body_template varchar,
  cta_type varchar,
  active_flag boolean,
  created_at timestamp default current_timestamp
);

create table if not exists outreach_queue (
  queue_id varchar,
  queue_lead_id varchar,
  lead_file_id varchar,
  campaign_id varchar,
  variant_code varchar,
  channel varchar,
  priority_score double,
  scheduled_at timestamp,
  status varchar,
  attempt_no integer,
  created_at timestamp default current_timestamp
);

create table if not exists outreach_events (
  event_id varchar,
  queue_id varchar,
  lead_file_id varchar,
  event_type varchar,
  event_time timestamp,
  payload_json varchar
);
""")

    con.execute("""
insert into campaign_variants
select * from (
  values
    ('trade_intro', 'designer', 'S', 'A', 'email', 'Trade pricing for your upcoming projects', 'Hi {{contact_name}}, we help design firms source lighting and home products with project pricing and fast quote support. Open to a quick fit check for your current pipeline?', 'reply', true, current_timestamp),
    ('trade_intro', 'designer', 'A', 'B', 'email', 'A simpler sourcing option for design projects', 'Hi {{contact_name}}, Neosgo supports design-led projects with trade pricing, quote turnaround, and curated product sourcing. Worth a short conversation if you are evaluating vendors this month?', 'reply', true, current_timestamp),
    ('builder_intro', 'builder', 'S', 'A', 'email', 'Project supply support for builders', 'Hi {{contact_name}}, we work with builders that need dependable sourcing, pricing support, and repeatable replenishment for lighting and related home products. Want a quick conversation on active projects?', 'reply', true, current_timestamp),
    ('contractor_intro', 'contractor', 'A', 'A', 'email', 'Support for remodel and contractor sourcing', 'Hi {{contact_name}}, we help contractors reduce sourcing friction on lighting and home product packages with responsive quote support. Interested in seeing if your current jobs are a fit?', 'reply', true, current_timestamp),
    ('channel_intro', 'furniture_retailer', 'A', 'A', 'email', 'Wholesale / dealer collaboration', 'Hi {{contact_name}}, we are building dealer and showroom partnerships for differentiated lighting and home products with margin room and repeat supply. Interested in discussing fit for your assortment?', 'reply', true, current_timestamp)
) as t(campaign_id, segment_primary, fit_tier, variant_code, channel, subject_template, body_template, cta_type, active_flag, created_at)
where not exists (
  select 1 from campaign_variants cv
  where cv.campaign_id = t.campaign_id and cv.segment_primary = t.segment_primary and cv.fit_tier = t.fit_tier and cv.variant_code = t.variant_code and cv.channel = t.channel
);
""")

    con.execute("""
insert into outreach_queue
select
  md5(queue_lead_id || '|' || segment_primary || '|email') as queue_id,
  file_id,
  case
    when segment_primary = 'designer' then 'trade_intro'
    when segment_primary = 'builder' then 'builder_intro'
    when segment_primary = 'contractor' then 'contractor_intro'
    when segment_primary in ('furniture_retailer','kitchen_bath') then 'channel_intro'
    else 'trade_intro'
  end as campaign_id,
  'A' as variant_code,
  'email' as channel,
  cast(outreach_priority_score as integer) as priority_score,
  current_timestamp as scheduled_at,
  'pending' as status,
  0 as attempt_no,
  current_timestamp as created_at
from outreach_ready_leads l
where fit_tier in ('S','A')
  and not exists (
    select 1 from outreach_queue q where q.queue_id = md5(l.queue_lead_id || '|' || l.segment_primary || '|email')
  );
""")

    rows = {
        'scored_prospects': con.execute('select count(*) from scored_prospects').fetchone()[0],
        'persona_summary': con.execute('select count(*) from persona_summary').fetchone()[0],
        'outreach_ready_leads': con.execute('select count(*) from outreach_ready_leads').fetchone()[0],
        'campaign_variants': con.execute('select count(*) from campaign_variants').fetchone()[0],
        'outreach_queue_pending': con.execute("select count(*) from outreach_queue where status='pending'").fetchone()[0],
    }
    top_segments = con.execute("select segment_primary, fit_tier, count(*) c from scored_prospects group by 1,2 order by c desc limit 12").fetchall()
    top_states = con.execute("select state, count(*) c from scored_prospects where fit_tier in ('S','A') group by 1 order by c desc limit 10").fetchall()
    con.close()

    lines = ['# Neosgo lead engine daily report', '']
    for k,v in rows.items():
        lines.append(f'- {k}: {v}')
    lines.append('')
    lines.append('## Top segment x tier')
    for seg, tier, c in top_segments:
        lines.append(f'- {seg} / {tier}: {c}')
    lines.append('')
    lines.append('## Top S/A states')
    for state, c in top_states:
        lines.append(f'- {state}: {c}')
    Path(args.report_out).write_text('\n'.join(lines)+'\n', encoding='utf-8')


if __name__ == '__main__':
    main()
