#!/usr/bin/env python3
from __future__ import annotations

import json
import re
import subprocess
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from time import time
from urllib.parse import quote_plus

ROOT = Path('/Users/mac_claw/.openclaw/workspace')
CRAWL4AI = ROOT / 'tools' / 'bin' / 'crawl4ai'
OUT_DIR = ROOT / 'reports' / 'site-probe'
OUT_DIR.mkdir(parents=True, exist_ok=True)

SITES = {
    'amazon': {
        'url': lambda q: f'https://www.amazon.com/s?k={quote_plus(q)}',
        'success_patterns': [r'/dp/[A-Z0-9]{10}', r'\b\d+(?:\.\d+)?[KM]?\+ bought in past month\b', r'\b\d\.\d\b'],
        'block_patterns': [r'captcha', r'robot check', r'sorry, we just need to make sure', r'enter the characters you see below'],
        'notes': 'Amazon public search pages can often be fetched in markdown and parsed for product cards.'
    },
    'walmart': {
        'url': lambda q: f'https://www.walmart.com/search?q={quote_plus(q)}',
        'success_patterns': [r'/ip/', r'\$\d+(?:\.\d{2})?', r'Add to cart'],
        'block_patterns': [r'robot or human', r'confirm that you.?re human', r'activate and hold the button'],
        'notes': 'Walmart commonly serves anti-bot verification interstitials.'
    },
    'temu': {
        'url': lambda q: f'https://www.temu.com/search_result.html?search_key={quote_plus(q)}',
        'success_patterns': [r'/goods\.html', r'\$\d+(?:\.\d{2})?', r'sold'],
        'block_patterns': [r'captcha', r'verify', r'puzzle', r'access denied'],
        'notes': 'Temu often returns sparse/JS-heavy output or verification walls to unattended crawlers.'
    },
    '1688': {
        'url': lambda q: f'https://s.1688.com/selloffer/offer_search.htm?keywords={quote_plus(q)}',
        'success_patterns': [r'offer', r'¥\d+(?:\.\d+)?', r'成交'],
        'block_patterns': [r'登录', r'login', r'请按住滑块', r'短信登录', r'密码登录'],
        'notes': '1688 search commonly redirects to login / slider verification for unattended access.'
    },
}

@dataclass
class ProbeResult:
    site: str
    query: str
    url: str
    returncode: int
    elapsed_sec: float
    stdout_chars: int
    stderr_chars: int
    product_signal_count: int
    block_signal_count: int
    status: str
    score: int
    strengths: list[str]
    issues: list[str]
    notes: str
    stdout_head: str
    stderr_head: str


def run_probe(site: str, query: str) -> ProbeResult:
    spec = SITES[site]
    url = spec['url'](query)
    cmd = [str(CRAWL4AI), url, '-o', 'markdown', '--bypass-cache', '-c', 'wait_until=load']
    t0 = time()
    proc = subprocess.run(cmd, capture_output=True, text=True)
    elapsed = round(time() - t0, 2)
    stdout = (proc.stdout or '').replace('\x00', '')
    stderr = (proc.stderr or '').replace('\x00', '')

    product_signal_count = sum(len(re.findall(p, stdout, flags=re.I)) for p in spec['success_patterns'])
    block_signal_count = sum(len(re.findall(p, stdout, flags=re.I)) for p in spec['block_patterns'])

    strengths: list[str] = []
    issues: list[str] = []
    score = 0
    status = 'failed'

    if proc.returncode == 0:
        score += 20
    else:
        issues.append('crawl4ai command returned non-zero exit code')

    if len(stdout.strip()) > 500:
        score += 15
        strengths.append('returned meaningful page content length')
    else:
        issues.append('returned little or no useful page content')

    if product_signal_count > 0:
        score += min(45, 10 + product_signal_count * 5)
        strengths.append(f'detected {product_signal_count} product-like/public-commerce signals')
    else:
        issues.append('did not detect stable product-card signals in output')

    if block_signal_count > 0:
        score -= min(50, 15 + block_signal_count * 10)
        issues.append(f'detected {block_signal_count} anti-bot/login/verification signals')

    if 'robot or human' in stdout.lower() or '请按住滑块' in stdout or '密码登录' in stdout:
        status = 'blocked'
    elif product_signal_count > 0 and block_signal_count == 0 and len(stdout.strip()) > 500:
        status = 'usable'
    elif len(stdout.strip()) > 100 and (product_signal_count > 0 or block_signal_count == 0):
        status = 'partial'
    else:
        status = 'blocked' if block_signal_count > 0 else 'failed'

    score = max(0, min(100, score))
    return ProbeResult(
        site=site,
        query=query,
        url=url,
        returncode=proc.returncode,
        elapsed_sec=elapsed,
        stdout_chars=len(stdout),
        stderr_chars=len(stderr),
        product_signal_count=product_signal_count,
        block_signal_count=block_signal_count,
        status=status,
        score=score,
        strengths=strengths,
        issues=issues,
        notes=spec['notes'],
        stdout_head=stdout[:3000],
        stderr_head=stderr[:1200],
    )


def main() -> int:
    query = 'wireless mouse'
    if len(sys.argv) > 1:
        query = ' '.join(sys.argv[1:])
    results = [run_probe(site, query) for site in SITES]
    results.sort(key=lambda r: (-r.score, r.site))
    payload = {
        'generated_at': __import__('datetime').datetime.now().astimezone().isoformat(),
        'query': query,
        'results': [asdict(r) for r in results],
        'ranking': [r.site for r in results],
    }
    out_json = OUT_DIR / 'latest-site-probe.json'
    out_md = OUT_DIR / 'latest-site-probe-report.md'
    out_json.write_text(json.dumps(payload, ensure_ascii=False, indent=2))

    lines = [
        '# Cross-site public crawling probe',
        '',
        f'- Query: `{query}`',
        f'- Generated at: {payload["generated_at"]}',
        '',
        '## Ranking',
        '',
    ]
    for i, r in enumerate(results, 1):
        lines.append(f'{i}. **{r.site}** — score {r.score}/100 — status: {r.status}')
    lines += ['', '## Detailed results', '']
    for r in results:
        lines += [
            f'### {r.site}',
            f'- URL: {r.url}',
            f'- Score: {r.score}/100',
            f'- Status: {r.status}',
            f'- Elapsed: {r.elapsed_sec}s',
            f'- stdout chars: {r.stdout_chars}',
            f'- product signals: {r.product_signal_count}',
            f'- block signals: {r.block_signal_count}',
            f'- Strengths: {"; ".join(r.strengths) if r.strengths else "none"}',
            f'- Issues: {"; ".join(r.issues) if r.issues else "none"}',
            f'- Notes: {r.notes}',
            '',
            'stdout sample:',
            '```text',
            r.stdout_head[:1200],
            '```',
            '',
        ]
    out_md.write_text('\n'.join(lines))
    print(out_json)
    print(out_md)
    print(json.dumps({'ranking': payload['ranking'], 'scores': {r.site: r.score for r in results}}, ensure_ascii=False))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
