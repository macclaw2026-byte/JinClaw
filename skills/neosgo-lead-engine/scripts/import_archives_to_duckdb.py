#!/usr/bin/env python3
import argparse
import csv
import hashlib
import json
import tempfile
import time
import zipfile
from io import TextIOWrapper
from pathlib import Path
from typing import Optional

import duckdb

CSV_EXTS = {'.csv'}
ARCHIVE_EXTS = {'.zip'}
DEFAULT_CHUNK_ROWS = 5000
PROGRESS_FLUSH_SECONDS = 2.0

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


def sha256_bytes(data: bytes) -> str:
    h = hashlib.sha256()
    h.update(data)
    return h.hexdigest()


def sha256_file(path: Path, chunk: int = 1024 * 1024) -> str:
    h = hashlib.sha256()
    with path.open('rb') as f:
        while True:
            b = f.read(chunk)
            if not b:
                break
            h.update(b)
    return h.hexdigest()


def stable_file_id(source_archive: str, member_name: str) -> str:
    return hashlib.md5(f'{source_archive}::{member_name}'.encode()).hexdigest()


def norm_row(row: dict):
    return {
        'company_name': row.get('Company Name') or row.get('Company') or '',
        'address': row.get('Address') or '',
        'city': row.get('City') or '',
        'state': row.get('State') or '',
        'zip': row.get('Zip') or '',
        'county': row.get('County') or '',
        'phone': row.get('Phone') or '',
        'contact_first': row.get('Contact First') or '',
        'contact_last': row.get('Contact Last') or '',
        'contact_full': row.get('Contact') or '',
        'title': row.get('Title') or '',
        'direct_phone': row.get('Direct Phone') or '',
        'email': row.get('Email') or '',
        'website': row.get('Website') or '',
        'employee_count': row.get('Employee Count') or row.get('Employees') or '',
        'annual_sales': row.get('Annual Sales') or row.get('Sales') or '',
        'sic_code': row.get('SIC Code') or '',
        'industry': row.get('Industry') or '',
        'raw_json': json.dumps(row, ensure_ascii=False),
    }


def write_progress(progress_path: Path, payload: dict):
    progress_path.parent.mkdir(parents=True, exist_ok=True)
    tmp = progress_path.with_suffix(progress_path.suffix + '.tmp')
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + '\n')
    tmp.replace(progress_path)


def insert_batch(con, batch):
    if not batch:
        return
    con.executemany(
        'insert into raw_contacts values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)',
        batch,
    )


def import_csv_stream(con, source_archive: str, member_name: str, text_stream, *, progress_path: Path, chunk_rows: int, source_sha256: Optional[str] = None):
    file_id = stable_file_id(source_archive, member_name)
    reader = csv.DictReader(text_stream)
    header = reader.fieldnames or []
    con.execute('delete from raw_contacts where file_id=?', [file_id])
    con.execute('delete from raw_import_files where file_id=?', [file_id])

    batch = []
    row_count = 0
    last_flush = 0.0
    sha = hashlib.sha256()

    write_progress(progress_path, {
        'status': 'running',
        'source_archive': source_archive,
        'member_name': member_name,
        'file_id': file_id,
        'rows_imported': 0,
        'chunk_rows': chunk_rows,
        'header': header,
        'updated_at': time.time(),
    })

    for row in reader:
        normalized = norm_row(row)
        batch.append([
            file_id,
            normalized['company_name'], normalized['address'], normalized['city'], normalized['state'], normalized['zip'],
            normalized['county'], normalized['phone'], normalized['contact_first'], normalized['contact_last'],
            normalized['contact_full'], normalized['title'], normalized['direct_phone'], normalized['email'],
            normalized['website'], normalized['employee_count'], normalized['annual_sales'], normalized['sic_code'],
            normalized['industry'], normalized['raw_json'],
        ])
        sha.update((normalized['raw_json'] + '\n').encode('utf-8', 'ignore'))
        row_count += 1
        if len(batch) >= chunk_rows:
            insert_batch(con, batch)
            batch.clear()
        now = time.time()
        if now - last_flush >= PROGRESS_FLUSH_SECONDS:
            write_progress(progress_path, {
                'status': 'running',
                'source_archive': source_archive,
                'member_name': member_name,
                'file_id': file_id,
                'rows_imported': row_count,
                'chunk_rows': chunk_rows,
                'header': header,
                'updated_at': now,
            })
            last_flush = now

    insert_batch(con, batch)
    sha_hex = source_sha256 or sha.hexdigest()
    con.execute(
        'insert into raw_import_files(file_id, source_archive, member_name, row_count, header_json, sha256) values (?, ?, ?, ?, ?, ?)',
        [file_id, source_archive, member_name, row_count, json.dumps(header, ensure_ascii=False), sha_hex],
    )
    write_progress(progress_path, {
        'status': 'done',
        'source_archive': source_archive,
        'member_name': member_name,
        'file_id': file_id,
        'rows_imported': row_count,
        'chunk_rows': chunk_rows,
        'header': header,
        'updated_at': time.time(),
    })
    return row_count


def import_path(con, path: Path, *, progress_path: Path, chunk_rows: int):
    total_rows = 0
    total_files = 0
    if path.suffix.lower() in ARCHIVE_EXTS:
        archive_sha = sha256_file(path)
        with zipfile.ZipFile(path) as z:
            for name in z.namelist():
                if Path(name).suffix.lower() not in CSV_EXTS:
                    continue
                with z.open(name, 'r') as raw:
                    text_stream = TextIOWrapper(raw, encoding='utf-8', errors='ignore', newline='')
                    total_rows += import_csv_stream(
                        con,
                        str(path),
                        name,
                        text_stream,
                        progress_path=progress_path,
                        chunk_rows=chunk_rows,
                        source_sha256=archive_sha,
                    )
                    total_files += 1
    elif path.suffix.lower() in CSV_EXTS:
        with path.open('rb') as raw:
            text_stream = TextIOWrapper(raw, encoding='utf-8', errors='ignore', newline='')
            total_rows += import_csv_stream(
                con,
                str(path),
                path.name,
                text_stream,
                progress_path=progress_path,
                chunk_rows=chunk_rows,
                source_sha256=sha256_file(path),
            )
            total_files += 1
    return total_files, total_rows


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--db', required=True)
    ap.add_argument('--progress-file', required=True)
    ap.add_argument('--chunk-rows', type=int, default=DEFAULT_CHUNK_ROWS)
    ap.add_argument('paths', nargs='+')
    args = ap.parse_args()

    db = Path(args.db).expanduser()
    db.parent.mkdir(parents=True, exist_ok=True)
    progress_path = Path(args.progress_file).expanduser()

    con = duckdb.connect(str(db))
    con.execute(SCHEMA_SQL)

    total_rows = 0
    total_files = 0
    current_path = None
    try:
        for p in args.paths:
            path = Path(p).expanduser()
            current_path = str(path)
            if not path.exists():
                continue
            files_imported, rows_imported = import_path(
                con,
                path,
                progress_path=progress_path,
                chunk_rows=args.chunk_rows,
            )
            total_files += files_imported
            total_rows += rows_imported
        print(json.dumps({'db': str(db), 'files_imported': total_files, 'rows_imported': total_rows}, ensure_ascii=False))
    except Exception as e:
        write_progress(progress_path, {
            'status': 'failed',
            'source_archive': current_path,
            'rows_imported': total_rows,
            'updated_at': time.time(),
            'error': repr(e),
        })
        raise
    finally:
        con.close()


if __name__ == '__main__':
    main()
