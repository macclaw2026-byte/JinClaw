#!/usr/bin/env python3
import argparse
import hashlib
import json
import os
import re
import signal
import subprocess
import time
import zipfile
from pathlib import Path

import duckdb

ARCHIVE_EXTS = {'.zip'}
CSV_EXTS = {'.csv'}
DEFAULT_STALE_SECONDS = 180

SCHEMA_SQL = '''
create table if not exists import_job_files (
  file_id varchar primary key,
  source_path varchar,
  file_name varchar,
  file_size bigint,
  mtime double,
  sha256 varchar,
  discovered_at timestamp default current_timestamp,
  status varchar,
  started_at timestamp,
  finished_at timestamp,
  rows_imported bigint,
  error_text varchar
);
'''

OPTIONAL_COLUMNS = [
    ("pid", "bigint"),
    ("progress_file", "varchar"),
    ("heartbeat_at", "timestamp"),
    ("attempt_count", "integer default 0"),
    ("last_progress_at", "timestamp"),
    ("exit_code", "integer"),
    ("member_name", "varchar"),
    ("archive_path", "varchar"),
]


def connect(db_path: str, read_only: bool = False):
    return duckdb.connect(db_path, read_only=read_only)


def ensure_schema(db_path: str):
    con = connect(db_path)
    con.execute(SCHEMA_SQL)
    for col, typ in OPTIONAL_COLUMNS:
        try:
            con.execute(f"alter table import_job_files add column {col} {typ}")
        except Exception:
            pass
    con.close()


def sha256_file(path: Path, chunk=1024 * 1024):
    h = hashlib.sha256()
    with path.open('rb') as f:
        while True:
            b = f.read(chunk)
            if not b:
                break
            h.update(b)
    return h.hexdigest()


def process_alive(pid):
    if pid in (None, 0):
        return False
    try:
        os.kill(int(pid), 0)
        return True
    except Exception:
        return False


def set_status(db_path: str, fid: str, **fields):
    con = connect(db_path)
    sets = []
    vals = []
    for k, v in fields.items():
        sets.append(f"{k}=?")
        vals.append(v)
    vals.append(fid)
    con.execute(f"update import_job_files set {', '.join(sets)} where file_id=?", vals)
    con.close()


def touch_running_status(db_path: str, fid: str, *, payload=None):
    payload = payload or {}
    fields = {
        "heartbeat_at": time.strftime('%Y-%m-%d %H:%M:%S'),
    }
    updated_at = payload.get("updated_at")
    if updated_at:
        fields["last_progress_at"] = time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(float(updated_at)))
    rows_imported = payload.get("rows_imported")
    if rows_imported is not None:
        fields["rows_imported"] = int(rows_imported)
    set_status(db_path, fid, **fields)


def progress_path_for(progress_dir: Path, archive_path: str, member_name: str):
    safe = hashlib.md5(f'{archive_path}::{member_name}'.encode()).hexdigest()
    return str(progress_dir / f'{safe}.json')


def load_progress(progress_file: str):
    path = Path(progress_file)
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding='utf-8'))
    except Exception:
        return None


def discover(db_path: str, roots, progress_dir: Path):
    rows = []
    for root in roots:
        r = Path(root).expanduser()
        if not r.exists():
            continue
        for p in sorted(r.rglob('*')):
            if not (p.is_file() and p.suffix.lower() in ARCHIVE_EXTS):
                continue
            st = p.stat()
            archive_sha = sha256_file(p)
            with zipfile.ZipFile(p) as z:
                for info in z.infolist():
                    if Path(info.filename).suffix.lower() not in CSV_EXTS:
                        continue
                    fid = hashlib.md5(f'{p}::{info.filename}'.encode()).hexdigest()
                    rows.append((
                        fid,
                        str(p),
                        p.name,
                        st.st_size,
                        st.st_mtime,
                        archive_sha,
                        info.filename,
                        progress_path_for(progress_dir, str(p), info.filename),
                    ))
    con = connect(db_path)
    for fid, source_path, file_name, file_size, mtime, sha256, member_name, progress_file in rows:
        existing = con.execute("select status from import_job_files where file_id=?", [fid]).fetchone()
        if existing is None:
            con.execute(
                '''insert into import_job_files(
                       file_id, source_path, file_name, file_size, mtime, sha256, status, progress_file, member_name, archive_path
                   ) values (?, ?, ?, ?, ?, ?, 'pending', ?, ?, ?)''',
                [fid, source_path, file_name, file_size, mtime, sha256, progress_file, member_name, source_path],
            )
        else:
            con.execute(
                '''update import_job_files
                   set source_path=?, file_name=?, file_size=?, mtime=?, sha256=?, progress_file=?, member_name=?, archive_path=?
                   where file_id=?''',
                [source_path, file_name, file_size, mtime, sha256, progress_file, member_name, source_path, fid],
            )
    con.close()
    return len(rows)


def heal_or_wait_running(db_path: str, stale_seconds: int):
    con = connect(db_path, read_only=True)
    rows = con.execute(
        "select file_id,file_name,member_name,pid,progress_file,epoch(coalesce(last_progress_at, heartbeat_at, started_at)) from import_job_files where status='running'"
    ).fetchall()
    con.close()
    actions = []
    now = time.time()
    for fid, file_name, member_name, pid, progress_file, last_ts in rows:
        alive = process_alive(pid)
        payload = load_progress(progress_file) if progress_file else None
        progress_ts = payload.get('updated_at') if payload else None
        effective_ts = progress_ts or last_ts
        stale = effective_ts is None or ((now - float(effective_ts)) > stale_seconds)
        label = f"{file_name}::{member_name}"
        if not alive:
            set_status(
                db_path,
                fid,
                status='interrupted',
                pid=None,
                error_text=f'process_not_alive pid={pid}',
                exit_code=143,
                finished_at=time.strftime('%Y-%m-%d %H:%M:%S'),
            )
            actions.append({'healed': label, 'reason': 'dead-process'})
        elif stale:
            try:
                os.kill(int(pid), signal.SIGTERM)
            except Exception:
                pass
            set_status(
                db_path,
                fid,
                status='stalled',
                pid=None,
                error_text=f'stalled_progress_timeout pid={pid}',
                exit_code=124,
                finished_at=time.strftime('%Y-%m-%d %H:%M:%S'),
            )
            actions.append({'healed': label, 'reason': 'stalled-progress-timeout'})
        else:
            touch_running_status(db_path, fid, payload=payload)
            actions.append({'waiting': label, 'pid': pid, 'progress': payload})
    return actions


def fetch_queue(db_path: str):
    con = connect(db_path, read_only=True)
    rows = con.execute(
        "select archive_path,member_name,file_id,file_name,status,coalesce(attempt_count,0),progress_file from import_job_files where status is null or status in ('pending','failed','interrupted','stalled') order by archive_path, member_name"
    ).fetchall()
    con.close()
    return rows


def counts(db_path: str):
    con = connect(db_path, read_only=True)
    rows = con.execute("select coalesce(status,'null'), count(*) from import_job_files group by 1 order by 1").fetchall()
    con.close()
    return dict(rows)


def increment_attempt(db_path: str, fid: str):
    con = connect(db_path)
    con.execute("update import_job_files set attempt_count=coalesce(attempt_count,0)+1 where file_id=?", [fid])
    count = con.execute("select attempt_count from import_job_files where file_id=?", [fid]).fetchone()[0]
    con.close()
    return count


def parse_rows_imported(stdout: str):
    m = re.search(r'"rows_imported":\s*(\d+)', stdout or '')
    return int(m.group(1)) if m else None


def mark_done(db_path: str, fid: str, rows_imported, exit_code: int):
    set_status(db_path, fid, status='done', finished_at=time.strftime('%Y-%m-%d %H:%M:%S'), rows_imported=rows_imported, exit_code=exit_code, pid=None)


def mark_failed(db_path: str, fid: str, error_text: str, exit_code: int):
    set_status(db_path, fid, status='failed', finished_at=time.strftime('%Y-%m-%d %H:%M:%S'), error_text=error_text, exit_code=exit_code, pid=None)


def run_one(importer: str, db_path: str, archive_path: str, member_name: str, fid: str, progress_file: str, chunk_rows: int, stale_seconds: int):
    attempt_count = increment_attempt(db_path, fid)
    proc = subprocess.Popen(
        ['python3', importer, '--db', db_path, '--archive', archive_path, '--member', member_name, '--chunk-rows', str(chunk_rows), '--progress-file', progress_file],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    set_status(db_path, fid, status='running', started_at=time.strftime('%Y-%m-%d %H:%M:%S'), pid=proc.pid, error_text=None, exit_code=None, attempt_count=attempt_count)
    last_progress = time.time()
    last_payload = None
    while True:
        rc = proc.poll()
        payload = load_progress(progress_file)
        if payload and payload.get('updated_at'):
            last_progress = payload['updated_at']
            last_payload = payload
            touch_running_status(db_path, fid, payload=payload)
        else:
            touch_running_status(db_path, fid, payload={})
        if rc is not None:
            out, err = proc.communicate()
            out = (out or '')[-12000:]
            err = (err or '')[-12000:]
            if rc == 0:
                rows_imported = parse_rows_imported(out)
                if rows_imported is None and last_payload:
                    rows_imported = last_payload.get('rows_imported')
                mark_done(db_path, fid, rows_imported, rc)
                return True, out, err, rc, last_payload
            mark_failed(db_path, fid, (out + '\n' + err).strip(), rc)
            return False, out, err, rc, last_payload
        if (time.time() - last_progress) > stale_seconds:
            try:
                os.kill(proc.pid, signal.SIGTERM)
            except Exception:
                pass
            mark_failed(db_path, fid, f'stalled_progress_file_timeout pid={proc.pid}', 124)
            return False, '', 'stalled_progress_file_timeout', 124, last_payload
        time.sleep(2)


def supervisor_loop(db_path: str, importer: str, stale_seconds: int, sleep_seconds: int, max_passes: int, progress_dir: Path, chunk_rows: int):
    pass_num = 0
    while True:
        pass_num += 1
        actions = heal_or_wait_running(db_path, stale_seconds)
        if actions:
            print(json.dumps({'running_actions': actions}, ensure_ascii=False))
            if any('waiting' in a for a in actions):
                if pass_num >= max_passes:
                    break
                time.sleep(sleep_seconds)
                continue
        queue = fetch_queue(db_path)
        print(json.dumps({'pass': pass_num, 'queue_size': len(queue), 'status_counts': counts(db_path)}, ensure_ascii=False))
        if not queue:
            if counts(db_path).get('running', 0):
                if pass_num >= max_passes:
                    break
                time.sleep(sleep_seconds)
                continue
            break
        archive_path, member_name, fid, file_name, status, attempt_count, progress_file = queue[0]
        print(json.dumps({'importing': f'{file_name}::{member_name}', 'prior_status': status, 'attempt_count': attempt_count}, ensure_ascii=False))
        ok, out, err, code, payload = run_one(importer, db_path, archive_path, member_name, fid, progress_file, chunk_rows, stale_seconds)
        if ok:
            print(json.dumps({'done': f'{file_name}::{member_name}', 'rows_imported': parse_rows_imported(out), 'progress': payload, 'exit_code': code}, ensure_ascii=False))
        else:
            print(json.dumps({'failed': f'{file_name}::{member_name}', 'progress': payload, 'exit_code': code}, ensure_ascii=False))
        if pass_num >= max_passes:
            break
        time.sleep(sleep_seconds)
    print(json.dumps({'final_status_counts': counts(db_path)}, ensure_ascii=False))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--db', required=True)
    ap.add_argument('--importer', required=True)
    ap.add_argument('--progress-dir', required=True)
    ap.add_argument('--chunk-rows', type=int, default=5000)
    ap.add_argument('--stale-seconds', type=int, default=DEFAULT_STALE_SECONDS)
    ap.add_argument('--sleep-seconds', type=int, default=2)
    ap.add_argument('--max-passes', type=int, default=1000)
    ap.add_argument('roots', nargs='+')
    args = ap.parse_args()

    progress_dir = Path(args.progress_dir).expanduser()
    progress_dir.mkdir(parents=True, exist_ok=True)

    ensure_schema(args.db)
    discovered = discover(args.db, args.roots, progress_dir)
    print(json.dumps({'discovered_members': discovered}, ensure_ascii=False))
    supervisor_loop(args.db, args.importer, args.stale_seconds, args.sleep_seconds, args.max_passes, progress_dir, args.chunk_rows)


if __name__ == '__main__':
    main()
