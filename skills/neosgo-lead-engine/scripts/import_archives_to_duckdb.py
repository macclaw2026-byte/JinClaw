#!/usr/bin/env python3
import argparse
import csv
import hashlib
import json
import shutil
import tempfile
import time
import zipfile
from pathlib import Path

import duckdb

DEFAULT_CHUNK_ROWS = 5000

SCHEMA_SQL = '''
create table if not exists raw_import_files (
  file_id varchar primary key,
  source_archive varchar,
  member_name varchar,
  imported_at timestamp default current_timestamp,
  row_count bigint,
  header_json varchar,
  sha256 varchar
);

create table if not exists raw_contacts (
  file_id varchar,
  company_name varchar,
  address varchar,
  city varchar,
  state varchar,
  zip varchar,
  county varchar,
  phone varchar,
  contact_first varchar,
  contact_last varchar,
  contact_full varchar,
  title varchar,
  direct_phone varchar,
  email varchar,
  website varchar,
  employee_count varchar,
  annual_sales varchar,
  sic_code varchar,
  industry varchar,
  raw_json varchar
);
'''


def stable_file_id(source_archive: str, member_name: str) -> str:
    return hashlib.md5(f'{source_archive}::{member_name}'.encode()).hexdigest()


def sha256_file(path: Path, chunk: int = 1024 * 1024) -> str:
    h = hashlib.sha256()
    with path.open('rb') as f:
        while True:
            b = f.read(chunk)
            if not b:
                break
            h.update(b)
    return h.hexdigest()


def write_progress(progress_path: Path, payload: dict):
    progress_path.parent.mkdir(parents=True, exist_ok=True)
    tmp = progress_path.with_suffix(progress_path.suffix + '.tmp')
    payload = dict(payload)
    payload['updated_at'] = time.time()
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    tmp.replace(progress_path)


def extract_member_to_temp_csv(archive_path: Path, member_name: str, progress_path: Path) -> Path:
    tmp_dir = Path(tempfile.mkdtemp(prefix='lead-import-'))
    out_csv = tmp_dir / Path(member_name).name
    with zipfile.ZipFile(archive_path) as z:
        info = z.getinfo(member_name)
        with z.open(member_name, 'r') as src, out_csv.open('wb') as dst:
            copied = 0
            while True:
                chunk = src.read(1024 * 1024)
                if not chunk:
                    break
                dst.write(chunk)
                copied += len(chunk)
                write_progress(progress_path, {
                    'status': 'extracting',
                    'source_archive': str(archive_path),
                    'member_name': member_name,
                    'bytes_extracted': copied,
                    'member_size_bytes': info.file_size,
                })
    return out_csv


def read_header(csv_path: Path):
    with csv_path.open('r', encoding='utf-8', errors='ignore', newline='') as f:
        reader = csv.reader(f)
        return next(reader)


def import_member_via_duckdb(con, archive_path: Path, member_name: str, temp_csv: Path, progress_path: Path):
    file_id = stable_file_id(str(archive_path), member_name)
    con.execute('delete from raw_contacts where file_id=?', [file_id])
    con.execute('delete from raw_import_files where file_id=?', [file_id])

    header = read_header(temp_csv)
    sha = sha256_file(temp_csv)

    write_progress(progress_path, {
        'status': 'loading-duckdb',
        'source_archive': str(archive_path),
        'member_name': member_name,
        'file_id': file_id,
        'temp_csv': str(temp_csv),
        'header': header,
    })

    header_set = set(header)

    def col_expr(candidates):
        for c in candidates:
            if c in header_set:
                return f'coalesce("{c}", \'\')'
        return "''"

    sql = f"""
    insert into raw_contacts
    select
      '{file_id}' as file_id,
      {col_expr(['Company Name', 'Company'])} as company_name,
      {col_expr(['Address'])} as address,
      {col_expr(['City'])} as city,
      {col_expr(['State'])} as state,
      {col_expr(['Zip'])} as zip,
      {col_expr(['County'])} as county,
      {col_expr(['Phone'])} as phone,
      {col_expr(['Contact First'])} as contact_first,
      {col_expr(['Contact Last'])} as contact_last,
      {col_expr(['Contact'])} as contact_full,
      {col_expr(['Title'])} as title,
      {col_expr(['Direct Phone'])} as direct_phone,
      {col_expr(['Email'])} as email,
      {col_expr(['Website'])} as website,
      {col_expr(['Employee Count', 'Employees'])} as employee_count,
      {col_expr(['Annual Sales', 'Sales'])} as annual_sales,
      {col_expr(['SIC Code'])} as sic_code,
      {col_expr(['Industry'])} as industry,
      to_json(struct_pack(*COLUMNS(*))) as raw_json
    from read_csv_auto(
      '{str(temp_csv).replace("'", "''")}',
      header=true,
      sample_size=-1,
      ignore_errors=true,
      all_varchar=true
    )
    """
    con.execute(sql)
    row_count = con.execute('select count(*) from raw_contacts where file_id=?', [file_id]).fetchone()[0]
    con.execute(
        'insert into raw_import_files(file_id, source_archive, member_name, row_count, header_json, sha256) values (?, ?, ?, ?, ?, ?)',
        [file_id, str(archive_path), member_name, row_count, json.dumps(header, ensure_ascii=False), sha],
    )
    write_progress(progress_path, {
        'status': 'done',
        'source_archive': str(archive_path),
        'member_name': member_name,
        'file_id': file_id,
        'rows_imported': row_count,
        'temp_csv': str(temp_csv),
        'header': header,
    })
    return row_count


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--db', required=True)
    ap.add_argument('--archive', required=True)
    ap.add_argument('--member', required=True)
    ap.add_argument('--progress-file', required=True)
    ap.add_argument('--chunk-rows', type=int, default=DEFAULT_CHUNK_ROWS)
    args = ap.parse_args()

    db = Path(args.db).expanduser()
    db.parent.mkdir(parents=True, exist_ok=True)
    archive_path = Path(args.archive).expanduser()
    progress_path = Path(args.progress_file).expanduser()

    con = duckdb.connect(str(db))
    con.execute(SCHEMA_SQL)

    temp_csv = extract_member_to_temp_csv(archive_path, args.member, progress_path)
    try:
        rows_imported = import_member_via_duckdb(con, archive_path, args.member, temp_csv, progress_path)
    finally:
        shutil.rmtree(temp_csv.parent, ignore_errors=True)

    print(json.dumps({
        'db': str(db),
        'archive': str(archive_path),
        'member': args.member,
        'rows_imported': rows_imported,
    }, ensure_ascii=False))


if __name__ == '__main__':
    main()
