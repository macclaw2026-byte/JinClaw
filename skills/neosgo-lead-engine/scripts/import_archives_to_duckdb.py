#!/usr/bin/env python3
import argparse, csv, hashlib, os, tempfile, zipfile
from pathlib import Path
import duckdb

CSV_EXTS = {'.csv'}
ARCHIVE_EXTS = {'.zip'}

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
    h = hashlib.sha256(); h.update(data); return h.hexdigest()

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
        'raw_json': str(row),
    }

def import_csv_bytes(con, source_archive: str, member_name: str, data: bytes):
    file_id = hashlib.md5(f'{source_archive}::{member_name}'.encode()).hexdigest()
    text = data.decode('utf-8', 'ignore').splitlines()
    reader = csv.DictReader(text)
    rows = list(reader)
    header = reader.fieldnames or []
    con.execute('insert or replace into raw_import_files(file_id, source_archive, member_name, row_count, header_json, sha256) values (?, ?, ?, ?, ?, ?)',
                [file_id, source_archive, member_name, len(rows), str(header), sha256_bytes(data)])
    batch = []
    for row in rows:
        n = norm_row(row)
        batch.append([file_id, n['company_name'], n['address'], n['city'], n['state'], n['zip'], n['county'], n['phone'], n['contact_first'], n['contact_last'], n['contact_full'], n['title'], n['direct_phone'], n['email'], n['website'], n['employee_count'], n['annual_sales'], n['sic_code'], n['industry'], n['raw_json']])
    con.executemany('insert into raw_contacts values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)', batch)
    return len(rows)

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--db', required=True)
    ap.add_argument('paths', nargs='+')
    args = ap.parse_args()

    db = Path(args.db).expanduser()
    db.parent.mkdir(parents=True, exist_ok=True)
    con = duckdb.connect(str(db))
    con.execute(SCHEMA_SQL)

    total_rows = 0
    total_files = 0
    for p in args.paths:
        path = Path(p).expanduser()
        if not path.exists():
            continue
        if path.suffix.lower() in ARCHIVE_EXTS:
            with zipfile.ZipFile(path) as z:
                for name in z.namelist():
                    if Path(name).suffix.lower() not in CSV_EXTS:
                        continue
                    data = z.read(name)
                    total_rows += import_csv_bytes(con, str(path), name, data)
                    total_files += 1
        elif path.suffix.lower() in CSV_EXTS:
            data = path.read_bytes()
            total_rows += import_csv_bytes(con, str(path), path.name, data)
            total_files += 1
    print({'db': str(db), 'files_imported': total_files, 'rows_imported': total_rows})

if __name__ == '__main__':
    main()
