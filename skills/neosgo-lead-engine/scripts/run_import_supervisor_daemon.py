#!/usr/bin/env python3
import argparse
import json
import os
import signal
import subprocess
import time
from pathlib import Path

import duckdb

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
  error_text varchar,
  pid bigint,
  progress_file varchar,
  heartbeat_at timestamp,
  attempt_count integer default 0,
  last_progress_at timestamp,
  exit_code integer,
  member_name varchar,
  archive_path varchar
);
'''

ROOT_DEFAULT = str(Path('~/Downloads/US Business Data').expanduser())
RUNNER_DEFAULT = '/Users/mac_claw/.openclaw/workspace/skills/neosgo-lead-engine/scripts/import_batch_runner.py'
IMPORTER_DEFAULT = '/Users/mac_claw/.openclaw/workspace/skills/neosgo-lead-engine/scripts/import_archives_to_duckdb.py'
PROGRESS_DIR_DEFAULT = '/Users/mac_claw/.openclaw/workspace/tmp/lead-import-progress'
STATUS_FILE_DEFAULT = '/Users/mac_claw/.openclaw/workspace/tmp/lead-import-daemon-status.json'
STALE_SECONDS = 180


def counts(db_path):
    con = duckdb.connect(db_path, read_only=True)
    rows = dict(con.execute("select coalesce(status,'null'), count(*) from import_job_files group by 1").fetchall())
    raw = con.execute("select count(*) from raw_contacts").fetchone()[0]
    con.close()
    return rows, raw


def process_alive(pid):
    if pid in (None, 0):
        return False
    try:
        os.kill(int(pid), 0)
        return True
    except Exception:
        return False


def heal_stale_running(db_path):
    con = duckdb.connect(db_path)
    healed = []
    rows = con.execute("select file_id,file_name,member_name,pid,progress_file from import_job_files where status='running'").fetchall()
    now = time.time()
    for fid, name, member_name, pid, progress_file in rows:
        progress_ts = None
        if progress_file and Path(progress_file).exists():
            try:
                payload = json.loads(Path(progress_file).read_text())
                progress_ts = payload.get('updated_at')
            except Exception:
                progress_ts = None
        alive = process_alive(pid)
        stale = (progress_ts is None) or ((now - float(progress_ts)) > STALE_SECONDS)
        if (not alive) or stale:
            try:
                if alive:
                    os.kill(int(pid), signal.SIGTERM)
            except Exception:
                pass
            con.execute("update import_job_files set status='interrupted', pid=null, error_text=? where file_id=?", [f'daemon healed stale running pid={pid} alive={alive} stale={stale}', fid])
            healed.append({'file': name, 'member': member_name, 'pid': pid, 'alive': alive, 'stale': stale})
        else:
            con.execute(
                "update import_job_files set heartbeat_at=current_timestamp, last_progress_at=coalesce(to_timestamp(?), last_progress_at, heartbeat_at, started_at) where file_id=?",
                [progress_ts, fid],
            )
    con.close()
    return healed


def write_status(path, payload):
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix('.tmp')
    payload['updated_at'] = time.time()
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding='utf-8')
    tmp.replace(p)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--db', default='/Users/mac_claw/.openclaw/workspace/data/neosgo_leads.duckdb')
    ap.add_argument('--root', default=ROOT_DEFAULT)
    ap.add_argument('--runner', default=RUNNER_DEFAULT)
    ap.add_argument('--importer', default=IMPORTER_DEFAULT)
    ap.add_argument('--progress-dir', default=PROGRESS_DIR_DEFAULT)
    ap.add_argument('--status-file', default=STATUS_FILE_DEFAULT)
    ap.add_argument('--sleep-seconds', type=int, default=5)
    args = ap.parse_args()

    Path(args.progress_dir).mkdir(parents=True, exist_ok=True)

    cycle = 0
    while True:
        cycle += 1
        healed = heal_stale_running(args.db)
        status_counts, raw = counts(args.db)
        pending_like = sum(status_counts.get(k, 0) for k in ['pending', 'failed', 'interrupted', 'stalled'])
        running = status_counts.get('running', 0)
        write_status(args.status_file, {
            'cycle': cycle,
            'healed': healed,
            'status_counts': status_counts,
            'raw_contacts': raw,
            'phase': 'pre-launch-check'
        })
        if pending_like == 0 and running == 0:
            write_status(args.status_file, {
                'cycle': cycle,
                'status_counts': status_counts,
                'raw_contacts': raw,
                'phase': 'complete'
            })
            print(json.dumps({'complete': True, 'status_counts': status_counts, 'raw_contacts': raw}, ensure_ascii=False))
            break
        if running > 0:
            write_status(args.status_file, {
                'cycle': cycle,
                'status_counts': status_counts,
                'raw_contacts': raw,
                'phase': 'waiting-on-running'
            })
            time.sleep(args.sleep_seconds)
            continue
        cmd = [
            'python3', args.runner,
            '--db', args.db,
            '--importer', args.importer,
            '--progress-dir', args.progress_dir,
            '--chunk-rows', '5000',
            '--stale-seconds', str(STALE_SECONDS),
            '--sleep-seconds', '2',
            '--max-passes', '1000',
            args.root,
        ]
        write_status(args.status_file, {
            'cycle': cycle,
            'status_counts': status_counts,
            'raw_contacts': raw,
            'phase': 'launching-runner',
            'cmd': cmd,
        })
        proc = subprocess.run(cmd, capture_output=True, text=True)
        latest_counts, latest_raw = counts(args.db)
        write_status(args.status_file, {
            'cycle': cycle,
            'status_counts': latest_counts,
            'raw_contacts': latest_raw,
            'phase': 'runner-exited',
            'returncode': proc.returncode,
            'stdout_tail': (proc.stdout or '')[-4000:],
            'stderr_tail': (proc.stderr or '')[-4000:],
        })
        time.sleep(args.sleep_seconds)


if __name__ == '__main__':
    main()
