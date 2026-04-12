#!/usr/bin/env python3
# RULES-FIRST NOTICE:
# Before modifying this file, first read:
# - `JINCLAW_CONSTITUTION.md`
# - `AI_OPTIMIZATION_FRAMEWORK.md`
# Follow the constitution and framework:
# brain-first, one-doctor, fail-closed, evidence-over-narration,
# validate locally, then use the required PR workflow.
import json
import os
from pathlib import Path
import duckdb

ROOT = Path(__file__).resolve().parents[1]
CONFIG_PATH = ROOT / 'config' / 'data_sources.json'
SQL_VIEWS_PATH = ROOT / 'sql' / 'views.sql'

CREATE_TABLE_SQL = '''
CREATE TABLE IF NOT EXISTS businesses (
  source_file VARCHAR,
  row_id BIGINT,
  company_name VARCHAR,
  address VARCHAR,
  city VARCHAR,
  state VARCHAR,
  zip VARCHAR,
  county VARCHAR,
  phone VARCHAR,
  contact_first VARCHAR,
  contact_last VARCHAR,
  contact_full_name VARCHAR,
  title VARCHAR,
  direct_phone VARCHAR,
  email VARCHAR,
  website VARCHAR,
  employee_count INTEGER,
  annual_sales DOUBLE,
  sic_code VARCHAR,
  industry VARCHAR,
  has_email BOOLEAN,
  has_website BOOLEAN,
  domain VARCHAR
);
'''


def load_config():
    with open(CONFIG_PATH, 'r', encoding='utf-8') as f:
        return json.load(f)


def ensure_dirs(cfg):
    for key in ['database_path', 'parquet_dir', 'export_dir']:
        path = Path(cfg[key])
        if path.suffix:
            path.parent.mkdir(parents=True, exist_ok=True)
        else:
            path.mkdir(parents=True, exist_ok=True)
    (ROOT / 'data' / 'cache').mkdir(parents=True, exist_ok=True)
    (ROOT / 'data' / 'raw').mkdir(parents=True, exist_ok=True)


def init_db(con, views_sql: str):
    con.execute(CREATE_TABLE_SQL)
    con.execute('CREATE SEQUENCE IF NOT EXISTS businesses_row_seq START 1;')
    con.execute(views_sql)


def import_csv_to_parquet(con, csv_path: str, parquet_path: Path):
    csv_path_escaped = csv_path.replace("'", "''")
    parquet_path_escaped = str(parquet_path).replace("'", "''")
    con.execute(f"""
        COPY (
          SELECT
            '{os.path.basename(csv_path_escaped)}' AS source_file,
            row_number() OVER () AS row_id,
            trim("Company Name") AS company_name,
            trim(Address) AS address,
            trim(City) AS city,
            upper(trim(State)) AS state,
            trim(Zip) AS zip,
            trim(County) AS county,
            regexp_replace(coalesce(trim(Phone), ''), '[^0-9]', '', 'g') AS phone,
            trim("Contact First") AS contact_first,
            trim("Contact Last") AS contact_last,
            trim(concat_ws(' ', nullif(trim("Contact First"), ''), nullif(trim("Contact Last"), ''))) AS contact_full_name,
            trim(Title) AS title,
            regexp_replace(coalesce(trim("Direct Phone"), ''), '[^0-9]', '', 'g') AS direct_phone,
            lower(trim(Email)) AS email,
            lower(trim(Website)) AS website,
            TRY_CAST(NULLIF(regexp_replace(trim("Employee Count"), '[^0-9]', '', 'g'), '') AS INTEGER) AS employee_count,
            TRY_CAST(NULLIF(regexp_replace(trim("Annual Sales"), '[$, ]', '', 'g'), '') AS DOUBLE) AS annual_sales,
            trim("SIC Code") AS sic_code,
            trim(Industry) AS industry,
            CASE WHEN nullif(trim(Email), '') IS NOT NULL THEN TRUE ELSE FALSE END AS has_email,
            CASE WHEN nullif(trim(Website), '') IS NOT NULL THEN TRUE ELSE FALSE END AS has_website,
            CASE
              WHEN nullif(trim(Website), '') IS NULL THEN NULL
              ELSE regexp_replace(lower(trim(Website)), '^https?://(www\\.)?', '')
            END AS domain
          FROM read_csv_auto('{csv_path_escaped}', header = TRUE, sample_size = 50000, ignore_errors = TRUE, all_varchar = TRUE)
        ) TO '{parquet_path_escaped}' (FORMAT PARQUET, COMPRESSION ZSTD);
    """)


def rebuild_businesses_table(con, parquet_files):
    con.execute('DELETE FROM businesses;')
    for parquet_file in parquet_files:
        parquet_path_escaped = str(parquet_file).replace("'", "''")
        con.execute(f"INSERT INTO businesses SELECT * FROM read_parquet('{parquet_path_escaped}');")


def main():
    cfg = load_config()
    ensure_dirs(cfg)
    views_sql = SQL_VIEWS_PATH.read_text(encoding='utf-8')

    db_path = cfg['database_path']
    parquet_dir = Path(cfg['parquet_dir'])

    con = duckdb.connect(db_path)
    con.execute("PRAGMA threads=4;")
    con.execute("PRAGMA enable_progress_bar=true;")
    init_db(con, views_sql)

    parquet_files = []
    for src in cfg['sources']:
        src_path = Path(src)
        if not src_path.exists():
            raise FileNotFoundError(f'Missing source file: {src}')
        parquet_path = parquet_dir / (src_path.stem + '.parquet')
        print(f'Converting {src_path.name} -> {parquet_path.name}')
        import_csv_to_parquet(con, str(src_path), parquet_path)
        parquet_files.append(parquet_path)

    print('Rebuilding DuckDB table from Parquet...')
    rebuild_businesses_table(con, parquet_files)
    con.execute(views_sql)

    total = con.execute('SELECT COUNT(*) FROM businesses').fetchone()[0]
    with_email = con.execute('SELECT COUNT(*) FROM businesses WHERE has_email').fetchone()[0]
    print(f'Imported rows: {total}')
    print(f'Rows with email: {with_email}')
    print(f'Database: {db_path}')
    print(f'Parquet dir: {parquet_dir}')


if __name__ == '__main__':
    main()
