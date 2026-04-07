-- Neosgo lead engine rebuild
-- Creates normalized, deduped, scored, persona, and outreach-ready layers from raw_contacts.

create or replace table normalized_contacts as
with base as (
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
    raw_json
  from raw_contacts
), enriched as (
  select
    *,
    lower(company_name) as company_l,
    lower(title) as title_l,
    lower(industry) as industry_l,
    regexp_replace(lower(company_name), '[^a-z0-9]+', '', 'g') as company_key,
    regexp_replace(lower(coalesce(contact_full, concat_ws(' ', contact_first, contact_last))), '[^a-z0-9]+', '', 'g') as contact_key,
    case
      when website like 'http://%' then regexp_replace(replace(website, 'http://', ''), '/.*$', '')
      when website like 'https://%' then regexp_replace(replace(website, 'https://', ''), '/.*$', '')
      else regexp_replace(website, '/.*$', '')
    end as website_host,
    case
      when strpos(email, '@') > 0 then split_part(email, '@', 2)
      else ''
    end as email_domain,
    case
      when email ~ '^[^@\s]+@[^@\s]+\.[^@\s]+$' then 1 else 0
    end as has_valid_email,
    case
      when website <> '' then 1 else 0
    end as has_website,
    case
      when length(phone_digits) between 10 and 11 or length(direct_phone_digits) between 10 and 11 then 1 else 0
    end as has_phone,
    case
      when coalesce(contact_full, '') <> '' or coalesce(contact_first, '') <> '' or coalesce(contact_last, '') <> '' then 1 else 0
    end as has_named_contact,
    case employee_count
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
  from base
)
select * from enriched;

create or replace table deduped_contacts as
with ranked as (
  select
    *,
    coalesce(nullif(email, ''), nullif(website_host, ''), nullif(company_key || '|' || state || '|' || city, '||')) as dedupe_key,
    row_number() over (
      partition by coalesce(nullif(email, ''), nullif(website_host, ''), nullif(company_key || '|' || state || '|' || city, '||'), file_id)
      order by has_valid_email desc, has_website desc, has_phone desc, has_named_contact desc, employee_band_rank desc nulls last, length(company_name) desc
    ) as rn
  from normalized_contacts
)
select * exclude (rn)
from ranked
where rn = 1;

create or replace table scored_prospects as
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
    case
      when state in ('CA','TX','FL','NY','NJ','IL','WA','GA','NC','VA','MA') then 5 else 0
    end as score_market_priority
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
  concat_ws(' | ',
    concat('segment=', segment_primary),
    concat('buyer_type=', buyer_type),
    concat('role=', decision_role_level),
    concat('size=', size_band),
    concat('email=', cast(has_valid_email as varchar)),
    concat('phone=', cast(has_phone as varchar)),
    concat('website=', cast(has_website as varchar))
  ) as fit_reason
from scored
where has_valid_email = 1 and has_website = 1;

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
  case
    when fit_tier = 'S' then fit_score + 20
    when fit_tier = 'A' then fit_score + 10
    else fit_score
  end as outreach_priority_score
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

drop table if exists outreach_queue;
create table outreach_queue (
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

drop table if exists outreach_events;
create table outreach_events (
  event_id varchar,
  queue_id varchar,
  lead_file_id varchar,
  event_type varchar,
  event_time timestamp,
  payload_json varchar
);

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

insert into outreach_queue
select
  md5(queue_lead_id || '|' || segment_primary || '|email') as queue_id,
  queue_lead_id,
  file_id as lead_file_id,
  case
    when segment_primary = 'designer' then 'trade_intro'
    when segment_primary = 'builder' then 'builder_intro'
    when segment_primary = 'contractor' then 'contractor_intro'
    when segment_primary in ('furniture_retailer','kitchen_bath') then 'channel_intro'
    else 'trade_intro'
  end as campaign_id,
  'A' as variant_code,
  'email' as channel,
  outreach_priority_score as priority_score,
  current_timestamp as scheduled_at,
  'pending' as status,
  0 as attempt_no,
  current_timestamp as created_at
from outreach_ready_leads l
where fit_tier in ('S','A')
  and not exists (
    select 1 from outreach_queue q where q.queue_id = md5(l.queue_lead_id || '|' || l.segment_primary || '|email')
  );
