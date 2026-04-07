#!/usr/bin/env python3
import argparse
from pathlib import Path
import duckdb


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--db', required=True)
    ap.add_argument('--out', required=True)
    ap.add_argument('--limit', type=int, default=5000)
    ap.add_argument('--segments', default='designer,architect,builder,contractor,electrician,lighting,furniture_retailer,kitchen_bath,property_manager,hospitality,realtor')
    ap.add_argument('--tiers', default='S,A')
    args = ap.parse_args()

    segments = [s.strip() for s in args.segments.split(',') if s.strip()]
    tiers = [t.strip() for t in args.tiers.split(',') if t.strip()]
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)

    con = duckdb.connect(args.db, read_only=True)
    seg_sql = ','.join(["'" + s.replace("'", "''") + "'" for s in segments])
    tier_sql = ','.join(["'" + t.replace("'", "''") + "'" for t in tiers])
    sql = f"""
    copy (
      select
        queue_lead_id,
        company_name,
        contact_name,
        title,
        email,
        phone,
        website,
        city,
        state,
        industry,
        segment_primary,
        buyer_type,
        decision_role_level,
        size_band,
        fit_score,
        fit_tier,
        fit_reason,
        outreach_priority_score
      from outreach_ready_leads
      where segment_primary in ({seg_sql})
        and fit_tier in ({tier_sql})
      qualify row_number() over (
        partition by coalesce(website_host, email, company_name || '|' || state || '|' || city)
        order by outreach_priority_score desc, fit_score desc
      ) = 1
      order by outreach_priority_score desc, fit_score desc
      limit {int(args.limit)}
    ) to '{str(out).replace("'", "''")}' (header, delimiter ',');
    """
    con.execute(sql)
    out_sql = str(out).replace("'", "''")
    rows = con.execute("select count(*) from read_csv_auto(?, header=true)", [str(out)]).fetchone()[0]
    con.close()
    print(f'exported_rows={rows}')


if __name__ == '__main__':
    main()
