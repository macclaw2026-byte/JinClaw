#!/usr/bin/env python3
import argparse
from datetime import datetime
from pathlib import Path

import duckdb


def q1(con, sql):
    try:
        return con.execute(sql).fetchone()[0]
    except Exception:
        return None


def qrows(con, sql, n=10):
    try:
        return con.execute(sql).fetchall()[:n]
    except Exception:
        return []


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--db', required=True)
    ap.add_argument('--out', '--output', dest='out', required=True)
    args = ap.parse_args()

    con = duckdb.connect(args.db, read_only=True)
    now = datetime.now().strftime('%Y-%m-%d %H:%M')
    raw_contacts = q1(con, 'select count(*) from raw_contacts')
    raw_files = q1(con, 'select count(*) from raw_import_files')
    deduped = q1(con, 'select count(*) from deduped_contacts')
    scored = q1(con, 'select count(*) from scored_prospects')
    outreach = q1(con, "select count(*) from outreach_queue where status='pending'")
    top_segments = qrows(con, 'select segment_primary, fit_tier, count(*) as c from scored_prospects group by 1,2 order by c desc limit 12')
    top_states = qrows(con, 'select state, count(*) as c from scored_prospects where fit_tier in (\'S\',\'A\') group by 1 order by c desc limit 10')
    top_personas = qrows(con, 'select segment_primary, decision_role_level, size_band, round(avg(fit_score),2), count(*) from scored_prospects where fit_tier in (\'S\',\'A\') group by 1,2,3 order by 5 desc limit 10')
    con.close()

    lines = []
    lines.append(f'# Neosgo lead engine daily report\n')
    lines.append(f'- Generated at: {now}')
    lines.append(f'- Raw import files: {raw_files}')
    lines.append(f'- Raw contacts: {raw_contacts}')
    lines.append(f'- Deduped contacts: {deduped}')
    lines.append(f'- Scored prospects: {scored}')
    lines.append(f'- Outreach-ready pending queue: {outreach}\n')

    lines.append('## Top segment x tier counts')
    for seg, tier, c in top_segments:
        lines.append(f'- {seg} / {tier}: {c}')

    lines.append('\n## Top S/A states')
    for state, c in top_states:
        lines.append(f'- {state}: {c}')

    lines.append('\n## Top S/A personas')
    for seg, role, size_band, avg_score, c in top_personas:
        lines.append(f'- {seg} | {role} | {size_band} | avg_score={avg_score} | leads={c}')

    Path(args.out).write_text('\n'.join(lines) + '\n', encoding='utf-8')


if __name__ == '__main__':
    main()
