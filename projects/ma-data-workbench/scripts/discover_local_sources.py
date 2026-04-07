#!/usr/bin/env python3
import argparse
import json
import os
from pathlib import Path

DEFAULT_ROOTS = [
    Path('/Users/mac_claw/Downloads'),
]

PATTERNS = {
    'csv': ['*.csv'],
    'zip': ['*.zip'],
    'parquet': ['*.parquet'],
    'duckdb': ['*.duckdb'],
    'sqlite': ['*.sqlite', '*.sqlite3', '*.db'],
}


def classify(path: Path) -> str:
    suffix = path.suffix.lower()
    if suffix == '.csv':
        return 'csv'
    if suffix == '.zip':
        return 'zip'
    if suffix == '.parquet':
        return 'parquet'
    if suffix == '.duckdb':
        return 'duckdb'
    if suffix in {'.sqlite', '.sqlite3', '.db'}:
        return 'sqlite'
    return 'other'


def iter_matches(root: Path, max_depth: int):
    root = root.expanduser()
    if not root.exists():
        return
    root_depth = len(root.parts)
    for dirpath, dirnames, filenames in os.walk(root):
        depth = len(Path(dirpath).parts) - root_depth
        if depth >= max_depth:
            dirnames[:] = []
        for name in filenames:
            p = Path(dirpath) / name
            kind = classify(p)
            if kind != 'other':
                yield p, kind


def infer_state_code(path: Path):
    stem = path.stem.upper()
    parts = stem.replace('-', '_').split('_')
    for part in parts:
        if len(part) == 2 and part.isalpha():
            return part
    return None


def main():
    parser = argparse.ArgumentParser(description='Discover local external data sources for MA Data Workbench / NeosGo lead engine.')
    parser.add_argument('--root', action='append', help='Root path to scan. Can be repeated.')
    parser.add_argument('--max-depth', type=int, default=3)
    parser.add_argument('--limit', type=int, default=5000)
    parser.add_argument('--json', action='store_true', help='Emit JSON instead of text.')
    args = parser.parse_args()

    roots = [Path(r) for r in args.root] if args.root else DEFAULT_ROOTS
    found = []
    seen = set()

    for root in roots:
        for path, kind in iter_matches(root, args.max_depth):
            if path in seen:
                continue
            seen.add(path)
            try:
                size = path.stat().st_size
            except OSError:
                size = None
            found.append({
                'path': str(path),
                'kind': kind,
                'state_hint': infer_state_code(path),
                'size_bytes': size,
                'in_project': str(path).startswith('/Users/mac_claw/.openclaw/workspace/'),
            })
            if len(found) >= args.limit:
                break
        if len(found) >= args.limit:
            break

    found.sort(key=lambda x: (x['kind'], x['path']))

    summary = {}
    for item in found:
        summary[item['kind']] = summary.get(item['kind'], 0) + 1

    payload = {
        'roots': [str(r) for r in roots],
        'count': len(found),
        'summary': summary,
        'items': found,
    }

    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        print('Roots:')
        for root in payload['roots']:
            print(f'  - {root}')
        print('Summary:')
        for kind, n in sorted(summary.items()):
            print(f'  - {kind}: {n}')
        print('Items:')
        for item in found:
            print(f"  - [{item['kind']}] {item['path']} | state_hint={item['state_hint']} | size={item['size_bytes']}")


if __name__ == '__main__':
    main()
