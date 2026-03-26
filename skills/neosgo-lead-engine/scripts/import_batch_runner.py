#!/usr/bin/env python3
import argparse
import hashlib
import os
import re
import signal
import subprocess
import time
from pathlib import Path

import duckdb

ARCHIVE_EXTS = {'.zip'}
DEFAULT_STALE_SECONDS = 300

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
  ("heartbeat_at", "timestamp"),
  ("attempt_count", "integer default 0"),
  ("last_progress_at", "timestamp"),
  ("exit_code", "integer"),
]

TERMINAL_STATUSES = {"done"}
RETRYABLE_STATUSES = {None, "pending", "failed", "interrupted"}


def sha256_file(path: Path, chunk=1024 * 1024):
    h = hashlib.sha256()
    with path.open('rb') as f:
        while True:
            b = f.read(chunk)
            if not b:
                break
            h.update(b)
    return h.hexdigest()


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


def process_alive(pid):
    if pid in (None, 0):
        return False
    try:
        os.kill(int(pid), 0)
        return True
    except Exception:
        return False


def discover(db_path: str, roots):
    rows = []
    for root in roots:
        r = Path(root).expanduser()
        if not r.exists():
            continue
        for p in sorted(r.rglob('*')):
            if p.is_file() and p.suffix.lower() in ARCHIVE_EXTS:
                st = p.stat()
                fid = hashlib.md5(str(p).encode()).hexdigest()
                rows.append((fid, str(p), p.name, st.st_size, st.st_mtime, sha256_file(p)))

    con = connect(db_path)
    for fid, source_path, file_name, file_size, mtime, sha256 in rows:
        existing = con.execute(
            "select status from import_job_files where file_id=?", [fid]
        ).fetchone()
        if existing is None:
            con.execute(
                '''insert into import_job_files(
                       file_id, source_path, file_name, file_size, mtime, sha256, status
                   ) values (?, ?, ?, ?, ?, ?, 'pending')''',
                [fid, source_path, file_name, file_size, mtime, sha256],
            )
        else:
            con.execute(
                '''update import_job_files
                   set source_path=?, file_name=?, file_size=?, mtime=?, sha256=?
                   where file_id=?''',
                [source_path, file_name, file_size, mtime, sha256, fid],
            )
    con.close()
    return len(rows)


def heal_stale_running(db_path: str, stale_seconds: int):
    con = connect(db_path)
    rows = con.execute(
        """
        select file_id, file_name, pid,
               epoch(coalesce(heartbeat_at, last_progress_at, started_at)) as last_ts
        from import_job_files
        where status='running'
        """
    ).fetchall()
    healed = []
    now = time.time()
    for fid, file_name, pid, last_ts in rows:
        last_ts = float(last_ts) if last_ts is not None else None
        stale = (last_ts is None) or ((now - last_ts) > stale_seconds)
        alive = process_alive(pid)
        if not alive:
            reason = f"stale_running_recovered pid={pid} alive={alive} stale={stale}"
            con.execute(
                '''update import_job_files
                   set status='interrupted',
                       finished_at=current_timestamp,
                       error_text=?,
                       pid=null,
                       exit_code=null
                   where file_id=?''',
                [reason, fid],
            )
            healed.append((file_name, reason))
    con.close()
    return healed


def fetch_queue(db_path: str):
    con = connect(db_path, read_only=True)
    rows = con.execute(
        """
        select source_path, file_id, file_name, status, attempt_count
        from import_job_files
        where status is null or status in ('pending','failed','interrupted')
        order by source_path
        """
    ).fetchall()
    con.close()
    return rows


def update_running(db_path: str, fid: str, pid: int):
    con = connect(db_path)
    con.execute(
        '''update import_job_files
           set status='running',
               started_at=current_timestamp,
               heartbeat_at=current_timestamp,
               last_progress_at=current_timestamp,
               pid=?,
               exit_code=null,
               error_text=null,
               attempt_count=coalesce(attempt_count, 0) + 1
           where file_id=?''',
        [pid, fid],
    )
    con.close()


def update_child_pid(db_path: str, fid: str, pid: int):
    con = connect(db_path)
    con.execute(
        "update import_job_files set pid=?, heartbeat_at=current_timestamp, last_progress_at=current_timestamp where file_id=?",
        [pid, fid],
    )
    con.close()


def heartbeat(db_path: str, fid: str):
    try:
        con = connect(db_path)
        con.execute(
            "update import_job_files set heartbeat_at=current_timestamp where file_id=?",
            [fid],
        )
        con.close()
        return True
    except Exception:
        return False


def mark_done(db_path: str, fid: str, rows_imported, exit_code: int):
    con = connect(db_path)
    con.execute(
        '''update import_job_files
           set status='done',
               finished_at=current_timestamp,
               rows_imported=?,
               exit_code=?,
               heartbeat_at=current_timestamp,
               last_progress_at=current_timestamp,
               pid=null
           where file_id=?''',
        [rows_imported, exit_code, fid],
    )
    con.close()


def mark_failed(db_path: str, fid: str, error_text: str, exit_code: int):
    con = connect(db_path)
    con.execute(
        '''update import_job_files
           set status='failed',
               finished_at=current_timestamp,
               error_text=?,
               exit_code=?,
               heartbeat_at=current_timestamp,
               last_progress_at=current_timestamp,
               pid=null
           where file_id=?''',
        [error_text, exit_code, fid],
    )
    con.close()


def counts(db_path: str):
    con = connect(db_path, read_only=True)
    rows = con.execute(
        "select coalesce(status, 'null'), count(*) from import_job_files group by 1 order by 1"
    ).fetchall()
    con.close()
    return dict(rows)


def parse_rows_imported(stdout: str):
    m = re.search(r"'rows_imported':\s*(\d+)", stdout or "")
    return int(m.group(1)) if m else None


def run_one(importer: str, db_path: str, src: str, fid: str):
    supervisor_pid = os.getpid()
    update_running(db_path, fid, supervisor_pid)
    proc = subprocess.Popen(
        ['python3', importer, '--db', db_path, src],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    update_child_pid(db_path, fid, proc.pid)

    while True:
        rc = proc.poll()
        if rc is not None:
            out, err = proc.communicate()
            out = (out or '')[-12000:]
            err = (err or '')[-12000:]
            if rc == 0:
                mark_done(db_path, fid, parse_rows_imported(out), rc)
                return True, out, err, rc
            mark_failed(db_path, fid, (out + '\n' + err).strip(), rc)
            return False, out, err, rc
        heartbeat(db_path, fid)
        time.sleep(2)


def supervisor_loop(db_path: str, importer: str, stale_seconds: int, sleep_seconds: int, max_passes: int):
    pass_num = 0
    while True:
        pass_num += 1
        healed = heal_stale_running(db_path, stale_seconds)
        if healed:
            print({'healed_stale_running': healed})

        queue = fetch_queue(db_path)
        snapshot = counts(db_path)
        print({'pass': pass_num, 'queue_size': len(queue), 'status_counts': snapshot})

        if not queue:
            running_left = snapshot.get('running', 0)
            if running_left:
                print({'waiting_on_running': running_left})
                if pass_num >= max_passes:
                    break
                time.sleep(sleep_seconds)
                continue
            break

        for idx, (src, fid, file_name, status, attempt_count) in enumerate(queue, start=1):
            print({'importing': file_name, 'source': src, 'index': idx, 'queue_size': len(queue), 'prior_status': status, 'attempt_count': attempt_count})
            ok, out, err, code = run_one(importer, db_path, src, fid)
            if ok:
                print({'done': file_name, 'rows_imported': parse_rows_imported(out), 'exit_code': code})
            else:
                print({'failed': file_name, 'exit_code': code})

        if pass_num >= max_passes:
            print({'stopped_reason': 'max_passes_reached', 'max_passes': max_passes})
            break

        time.sleep(sleep_seconds)

    print({'final_status_counts': counts(db_path)})


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--db', required=True)
    ap.add_argument('--importer', required=True)
    ap.add_argument('--stale-seconds', type=int, default=DEFAULT_STALE_SECONDS)
    ap.add_argument('--sleep-seconds', type=int, default=2)
    ap.add_argument('--max-passes', type=int, default=1000)
    ap.add_argument('roots', nargs='+')
    args = ap.parse_args()

    ensure_schema(args.db)
    discovered = discover(args.db, args.roots)
    print({'discovered_archives': discovered})
    supervisor_loop(args.db, args.importer, args.stale_seconds, args.sleep_seconds, args.max_passes)


if __name__ == '__main__':
    main()
