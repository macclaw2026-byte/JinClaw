#!/usr/bin/env python3
from __future__ import annotations

import json
import re
import subprocess
import sys
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path

ROOT = Path('/Users/mac_claw/.openclaw/workspace')
CRAWL4AI = ROOT / 'tools' / 'bin' / 'crawl4ai'
OUT_DIR = ROOT / 'reports' / 'site-smoke-tests'
OUT_DIR.mkdir(parents=True, exist_ok=True)

TESTS = {
    'amazon': 'https://www.amazon.com/s?k=drawer+organizer',
    'walmart': 'https://www.walmart.com/search?q=drawer+organizer',
    'temu': 'https://www.temu.com/',
    '1688': 'https://www.1688.com/',
}

@dataclass
class Result:
    site: str
    url: str
    returncode: int
    stdout_len: int
    stderr_len: int
    classification: str
    warning_flags: list[str]
    evidence: dict


def clean_stderr(stderr: str) -> tuple[str, list[str]]:
    text = stderr or ''
    flags: list[str] = []
    if 'RequestsDependencyWarning' in text:
        flags.append('requests_dependency_warning')
        text = re.sub(
            r".*RequestsDependencyWarning:.*?\n\s*warnings\.warn\(\n?",
            '',
            text,
            flags=re.S,
        )
    return text.strip(), flags


def classify(site: str, stdout: str, stderr: str) -> tuple[str, list[str], dict]:
    s = stdout or ''
    cleaned_stderr, flags = clean_stderr(stderr)
    low = s.lower()
    err_low = cleaned_stderr.lower()

    if site == 'walmart' and ('robot or human' in low or 'confirm that you’re human' in low or "confirm that you're human" in low):
        return 'blocked_robot_check', flags, {
            'matched_text': 'robot or human',
            'readable': False,
        }

    if site == '1688' and len(s.strip()) < 20:
        return 'empty_or_unreadable', flags, {
            'matched_text': s[:80],
            'readable': False,
        }

    if site == 'amazon' and ('## skip to' in low or '/dp/' in low or 'results' in low):
        return 'readable_search_results', flags, {
            'matched_signals': [sig for sig in ['## skip to', '/dp/', 'results'] if sig in low],
            'readable': True,
        }

    if site == 'temu' and len(s.strip()) > 1000:
        return 'readable_public_homepage', flags, {
            'matched_text': s[:200],
            'readable': True,
        }

    if len(s.strip()) > 1000:
        return 'readable_other', flags, {
            'matched_text': s[:200],
            'readable': True,
        }

    return 'weak_or_partial', flags, {
        'matched_text': s[:200],
        'readable': len(s.strip()) > 200,
    }


def run_one(site: str, url: str) -> Result:
    proc = subprocess.run(
        [str(CRAWL4AI), url, '-o', 'markdown'],
        capture_output=True,
        text=True,
        timeout=90,
    )
    stdout = proc.stdout or ''
    raw_stderr = proc.stderr or ''
    cleaned_stderr, _ = clean_stderr(raw_stderr)
    classification, flags, evidence = classify(site, stdout, raw_stderr)
    if cleaned_stderr:
        evidence['cleaned_stderr_head'] = cleaned_stderr[:200]
    return Result(
        site=site,
        url=url,
        returncode=proc.returncode,
        stdout_len=len(stdout),
        stderr_len=len(cleaned_stderr),
        classification=classification,
        warning_flags=flags,
        evidence=evidence,
    )


def main() -> int:
    chosen = sys.argv[1:]
    tests = {k: v for k, v in TESTS.items() if not chosen or k in chosen}
    results = [asdict(run_one(site, url)) for site, url in tests.items()]

    priority = {
        'readable_search_results': 4,
        'readable_public_homepage': 3,
        'readable_other': 2,
        'weak_or_partial': 1,
        'blocked_robot_check': 0,
        'empty_or_unreadable': -1,
    }
    ranked = sorted(results, key=lambda r: (priority.get(r['classification'], -9), r['stdout_len']), reverse=True)

    payload = {
        'generated_at': datetime.now().astimezone().isoformat(),
        'tool': str(CRAWL4AI),
        'results': results,
        'ranking': [
            {
                'site': r['site'],
                'classification': r['classification'],
                'stdout_len': r['stdout_len'],
                'warning_flags': r['warning_flags'],
            }
            for r in ranked
        ],
    }

    out = OUT_DIR / f"site-smoke-test-{datetime.now().strftime('%Y%m%d-%H%M%S')}.json"
    out.write_text(json.dumps(payload, ensure_ascii=False, indent=2))
    print(out)
    print(json.dumps(payload['ranking'], ensure_ascii=False))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
