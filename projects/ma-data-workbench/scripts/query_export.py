#!/usr/bin/env python3
import argparse
import json
from datetime import datetime
from pathlib import Path
import duckdb

ROOT = Path(__file__).resolve().parents[1]
CONFIG_PATH = ROOT / 'config' / 'data_sources.json'


def build_query(args):
    where = []
    params = []

    if args.primary_profession != 'any':
        where.append('primary_profession = ?')
        params.append(args.primary_profession)
    if args.min_score is not None:
        where.append('total_score >= ?')
        params.append(args.min_score)
    if args.lead_grade != 'any':
        where.append('lead_grade = ?')
        params.append(args.lead_grade)
    if args.city:
        where.append('city ILIKE ?')
        params.append(f'%{args.city}%')
    if args.county:
        where.append('county ILIKE ?')
        params.append(f'%{args.county}%')
    if args.industry_keyword:
        where.append('industry ILIKE ?')
        params.append(f'%{args.industry_keyword}%')
    if args.company_keyword:
        where.append('company_name ILIKE ?')
        params.append(f'%{args.company_keyword}%')
    if args.title_keyword:
        where.append('title ILIKE ?')
        params.append(f'%{args.title_keyword}%')
    if args.has_email != 'any':
        where.append('has_email = ?')
        params.append(args.has_email == 'yes')
    if args.has_website != 'any':
        where.append('has_website = ?')
        params.append(args.has_website == 'yes')
    if args.min_employees is not None:
        where.append('employee_count >= ?')
        params.append(args.min_employees)
    if args.max_employees is not None:
        where.append('employee_count <= ?')
        params.append(args.max_employees)
    if args.min_sales is not None:
        where.append('annual_sales >= ?')
        params.append(args.min_sales)
    if args.max_sales is not None:
        where.append('annual_sales <= ?')
        params.append(args.max_sales)

    sql = f'SELECT * FROM {args.view}'
    if where:
        sql += ' WHERE ' + ' AND '.join(where)
    sql += ' ORDER BY company_name NULLS LAST'
    if args.limit:
        sql += f' LIMIT {int(args.limit)}'
    return sql, params


def main():
    parser = argparse.ArgumentParser(description='Filter and export MA business data.')
    parser.add_argument('--view', default='v_businesses', choices=['v_businesses', 'v_professional_leads', 'v_neosgo_priority_leads'])
    parser.add_argument('--primary-profession', choices=['any', 'interior_designer', 'builder', 'real_estate', 'contractor', 'electrician', 'other'], default='any')
    parser.add_argument('--lead-grade', choices=['any', 'A+', 'A', 'B', 'C', 'D'], default='any')
    parser.add_argument('--min-score', type=int)
    parser.add_argument('--city')
    parser.add_argument('--county')
    parser.add_argument('--industry-keyword')
    parser.add_argument('--company-keyword')
    parser.add_argument('--title-keyword')
    parser.add_argument('--has-email', choices=['yes', 'no', 'any'], default='any')
    parser.add_argument('--has-website', choices=['yes', 'no', 'any'], default='any')
    parser.add_argument('--min-employees', type=int)
    parser.add_argument('--max-employees', type=int)
    parser.add_argument('--min-sales', type=float)
    parser.add_argument('--max-sales', type=float)
    parser.add_argument('--limit', type=int, default=1000)
    parser.add_argument('--format', choices=['csv', 'xlsx', 'parquet'], default='csv')
    args = parser.parse_args()

    with open(CONFIG_PATH, 'r', encoding='utf-8') as f:
        cfg = json.load(f)

    export_dir = Path(cfg['export_dir'])
    export_dir.mkdir(parents=True, exist_ok=True)
    con = duckdb.connect(cfg['database_path'], read_only=True)

    sql, params = build_query(args)
    df = con.execute(sql, params).fetchdf()

    stamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    out = export_dir / f'query_result_{stamp}.{args.format}'

    if args.format == 'csv':
        df.to_csv(out, index=False)
    elif args.format == 'xlsx':
        df.to_excel(out, index=False)
    else:
        df.to_parquet(out, index=False)

    print(f'Rows exported: {len(df)}')
    print(f'Output: {out}')
    if len(df):
        print(df.head(10).to_string(index=False))


if __name__ == '__main__':
    main()
