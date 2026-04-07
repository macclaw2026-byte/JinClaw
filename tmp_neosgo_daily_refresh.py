from pathlib import Path
import datetime
import os
import time
import duckdb

DB = '/Users/mac_claw/.openclaw/workspace/data/neosgo_leads.duckdb'
SQL = '/Users/mac_claw/.openclaw/workspace/skills/neosgo-lead-engine/scripts/build_lead_engine_views.sql'
OUT = '/Users/mac_claw/.openclaw/workspace/output/neosgo-lead-engine-daily-report-latest.md'
REPORT = '/Users/mac_claw/.openclaw/workspace/skills/neosgo-lead-engine/scripts/generate_daily_report.py'

con = duckdb.connect(DB)
stamp = datetime.datetime.now().strftime('%Y%m%d_%H%M%S')
for table in ['outreach_queue', 'outreach_events']:
    exists = con.execute(f"select count(*) from information_schema.tables where table_name='{table}'").fetchone()[0]
    if exists:
        backup = f'{table}_backup_{stamp}'
        con.execute(f'create table {backup} as select * from {table}')
        print(f'backed up {table} -> {backup}')
with open(SQL, 'r', encoding='utf-8') as f:
    sql = f.read()
t0 = time.time()
con.execute(sql)
con.close()
print(f'SQL rebuild done in {time.time()-t0:.2f}s')
os.system(f'python3 {REPORT} --db {DB} --output {OUT}')
con = duckdb.connect(DB, read_only=True)
print('raw_contacts', con.execute('select count(*) from raw_contacts').fetchone()[0])
print('deduped_contacts', con.execute('select count(*) from deduped_contacts').fetchone()[0])
print('scored_prospects', con.execute('select count(*) from scored_prospects').fetchone()[0])
print('outreach_queue_pending', con.execute("select count(*) from outreach_queue where status='pending'").fetchone()[0])
print('top_segments', con.execute("select segment_primary, fit_tier, count(*) as c from scored_prospects group by 1,2 order by c desc limit 10").fetchall())
print('report_exists', Path(OUT).exists())
print('report_mtime', datetime.datetime.fromtimestamp(Path(OUT).stat().st_mtime).isoformat())
con.close()
