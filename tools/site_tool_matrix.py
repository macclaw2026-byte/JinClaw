#!/usr/bin/env python3
from __future__ import annotations

import json
import re
import subprocess
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Callable
from urllib.parse import quote_plus

ROOT = Path('/Users/mac_claw/.openclaw/workspace')
OUT_DIR = ROOT / 'reports' / 'site-tool-matrix'
OUT_DIR.mkdir(parents=True, exist_ok=True)
CRAWL4AI = ROOT / 'tools' / 'bin' / 'crawl4ai'
AGENT_BROWSER = ROOT / 'tools' / 'agent-browser-local' / 'node_modules' / 'agent-browser' / 'bin' / 'agent-browser-darwin-arm64'

QUERY = 'wireless mouse'
SITES = {
    'amazon': f'https://www.amazon.com/s?k={quote_plus(QUERY)}',
    'walmart': f'https://www.walmart.com/search?q={quote_plus(QUERY)}',
    'temu': f'https://www.temu.com/search_result.html?search_key={quote_plus(QUERY)}',
    '1688': f'https://s.1688.com/selloffer/offer_search.htm?keywords={quote_plus(QUERY)}',
}

SITE_RULES = {
    'amazon': {
        'success': [r'/dp/[A-Z0-9]{10}', r'\b\d+(?:\.\d+)?[KM]?\+ bought in past month\b', r'\b\d\.\d\b'],
        'block': [r'captcha', r'robot check', r'sorry, we just need to make sure', r'enter the characters you see below'],
    },
    'walmart': {
        'success': [r'/ip/', r'\$\d+(?:\.\d{2})?', r'Add to cart'],
        'block': [r'robot or human', r'confirm that you.?re human', r'activate and hold the button'],
    },
    'temu': {
        'success': [r'/goods\.html', r'\$\d+(?:\.\d{2})?', r'sold'],
        'block': [r'captcha', r'puzzle', r'verify', r'access denied'],
    },
    '1688': {
        'success': [r'offer', r'¥\d+(?:\.\d+)?', r'成交'],
        'block': [r'登录', r'login', r'请按住滑块', r'短信登录', r'密码登录'],
    },
}

@dataclass
class ToolResult:
    site: str
    tool: str
    url: str
    returncode: int
    stdout_chars: int
    stderr_chars: int
    product_signal_count: int
    block_signal_count: int
    status: str
    score: int
    notes: str
    stdout_head: str
    stderr_head: str


def run(cmd: list[str]) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, capture_output=True, text=True)


def analyze(site: str, tool: str, url: str, stdout: str, stderr: str, returncode: int, notes: str) -> ToolResult:
    stdout = (stdout or '').replace('\x00', '')
    stderr = (stderr or '').replace('\x00', '')
    rules = SITE_RULES[site]
    product_signal_count = sum(len(re.findall(p, stdout, flags=re.I)) for p in rules['success'])
    block_signal_count = sum(len(re.findall(p, stdout, flags=re.I)) for p in rules['block'])

    score = 0
    if returncode == 0:
        score += 20
    if len(stdout.strip()) > 300:
        score += 15
    if product_signal_count > 0:
        score += min(45, 10 + product_signal_count * 5)
    if block_signal_count > 0:
        score -= min(50, 15 + block_signal_count * 10)
    score = max(0, min(100, score))

    if block_signal_count > 0:
        status = 'blocked'
    elif product_signal_count > 0 and len(stdout.strip()) > 500:
        status = 'usable'
    elif len(stdout.strip()) > 100:
        status = 'partial'
    else:
        status = 'failed'

    return ToolResult(
        site=site,
        tool=tool,
        url=url,
        returncode=returncode,
        stdout_chars=len(stdout),
        stderr_chars=len(stderr),
        product_signal_count=product_signal_count,
        block_signal_count=block_signal_count,
        status=status,
        score=score,
        notes=notes,
        stdout_head=stdout[:2200],
        stderr_head=stderr[:1200],
    )


def tool_crawl4ai(site: str, url: str) -> ToolResult:
    proc = run([str(CRAWL4AI), url, '-o', 'markdown', '--bypass-cache', '-c', 'wait_until=load'])
    return analyze(site, 'crawl4ai-cli', url, proc.stdout, proc.stderr, proc.returncode, 'Local crawl4ai CLI markdown extraction')


def tool_web_fetch(site: str, url: str) -> ToolResult:
    proc = run(['python3', '-c', (
        'import json,sys,urllib.request; '\
        'u=sys.argv[1]; '\
        'req=urllib.request.Request(u, headers={"User-Agent":"Mozilla/5.0"}); '\
        'resp=urllib.request.urlopen(req, timeout=30); '\
        'data=resp.read().decode("utf-8","ignore"); '\
        'print(data[:300000])'
    ), url])
    return analyze(site, 'raw-http-fetch', url, proc.stdout, proc.stderr, proc.returncode, 'Raw HTTP fetch approximation to compare with higher-level tools')


def tool_browser_snapshot(site: str, url: str) -> ToolResult:
    proc = run(['python3', '-c', (
        'import json,subprocess,sys; '\
        'u=sys.argv[1]; '\
        'cmd1=["openclaw-browser-placeholder"]; print("")'
    ), url])
    return analyze(site, 'browser-tool-snapshot', url, '', 'placeholder', 1, 'Filled by outer orchestrator; kept for schema compatibility')


def tool_agent_browser(site: str, url: str) -> ToolResult:
    proc = run([str(AGENT_BROWSER), 'open', url])
    snap = run([str(AGENT_BROWSER), 'snapshot'])
    title = run([str(AGENT_BROWSER), 'get', 'title'])
    combined_stdout = '\n'.join([(title.stdout or ''), (snap.stdout or '')])
    combined_stderr = '\n'.join(x for x in [proc.stderr, snap.stderr, title.stderr] if x)
    rc = 0 if proc.returncode == 0 and snap.returncode == 0 else max(proc.returncode, snap.returncode)
    return analyze(site, 'agent-browser-cli', url, combined_stdout, combined_stderr, rc, 'Local guarded agent-browser CLI using real browser rendering + accessibility snapshot')


def main() -> int:
    results: list[dict] = []
    for site, url in SITES.items():
        site_results = [
            asdict(tool_crawl4ai(site, url)),
            asdict(tool_web_fetch(site, url)),
            asdict(tool_agent_browser(site, url)),
        ]
        site_results.sort(key=lambda x: (-x['score'], x['tool']))
        results.append({'site': site, 'url': url, 'tool_results': site_results})

    payload = {
        'generated_at': datetime.now().astimezone().isoformat(),
        'query': QUERY,
        'sites': results,
    }
    out_json = OUT_DIR / 'tool-matrix-partial.json'
    out_json.write_text(json.dumps(payload, ensure_ascii=False, indent=2))
    print(out_json)
    print(json.dumps({'sites': [x['site'] for x in results]}, ensure_ascii=False))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
