#!/usr/bin/env python3
from __future__ import annotations

import json
import re
import subprocess
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from urllib.parse import quote_plus

ROOT = Path('/Users/mac_claw/.openclaw/workspace')
OUT_DIR = ROOT / 'reports' / 'site-tool-matrix'
OUT_DIR.mkdir(parents=True, exist_ok=True)
CRAWL4AI = ROOT / 'tools' / 'bin' / 'crawl4ai'
AGENT_BROWSER = ROOT / 'tools' / 'agent-browser-local' / 'node_modules' / 'agent-browser' / 'bin' / 'agent-browser-darwin-arm64'
VENV_PY = ROOT / 'tools' / 'matrix-venv' / 'bin' / 'python'

QUERY = 'wireless mouse'
SITES = {
    'amazon': f'https://www.amazon.com/s?k={quote_plus(QUERY)}',
    'walmart': f'https://www.walmart.com/search?q={quote_plus(QUERY)}',
    'temu': f'https://www.temu.com/search_result.html?search_key={quote_plus(QUERY)}',
    '1688': f'https://s.1688.com/selloffer/offer_search.htm?keywords={quote_plus(QUERY)}',
}

RULES = {
    'amazon': {
        'success': [r'/dp/[A-Z0-9]{10}', r'\b\d+(?:\.\d+)?[KM]?\+ bought in past month\b', r'\b\d\.\d\b', r'Add to cart'],
        'block': [r'captcha', r'robot check', r'sorry, we just need to make sure', r'enter the characters you see below', r'api-services-support@amazon\.com'],
    },
    'walmart': {
        'success': [r'/ip/', r'\$\d+(?:\.\d{2})?', r'Add to cart', r'out of 5 Stars'],
        'block': [r'robot or human', r'confirm that you.?re human', r'activate and hold the button'],
    },
    'temu': {
        'success': [r'/goods\.html', r'\$\d+(?:\.\d{2})?', r'No results for', r'Submit search'],
        'block': [r'captcha', r'puzzle', r'verify', r'access denied', r'login', r'sign in'],
    },
    '1688': {
        'success': [r'offer', r'¥\d+(?:\.\d+)?', r'成交'],
        'block': [r'登录', r'login', r'请按住滑块', r'短信登录', r'密码登录', r'captcha', r'punish', r'x5secdata'],
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
    rules = RULES[site]
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

    return ToolResult(site, tool, url, returncode, len(stdout), len(stderr), product_signal_count, block_signal_count, status, score, notes, stdout[:2200], stderr[:1200])


def crawl4ai_tool(site, url):
    p = run([str(CRAWL4AI), url, '-o', 'markdown', '--bypass-cache', '-c', 'wait_until=load'])
    return analyze(site, 'crawl4ai-cli', url, p.stdout, p.stderr, p.returncode, 'crawl4ai CLI markdown extraction')


def direct_http_tool(site, url):
    code = (
        'import sys,urllib.request; '
        'u=sys.argv[1]; '
        'req=urllib.request.Request(u, headers={"User-Agent":"Mozilla/5.0"}); '
        'resp=urllib.request.urlopen(req, timeout=30); '
        'print(resp.read().decode("utf-8","ignore")[:300000])'
    )
    p = run(['python3', '-c', code, url])
    return analyze(site, 'direct-http-html', url, p.stdout, p.stderr, p.returncode, 'raw urllib HTTP fetch')


def curl_cffi_tool(site, url):
    code = (
        'from curl_cffi import requests; import sys; '
        'u=sys.argv[1]; '
        'r=requests.get(u, impersonate="chrome124", timeout=30); '
        'print(r.text[:300000])'
    )
    p = run([str(VENV_PY), '-c', code, url])
    return analyze(site, 'curl-cffi', url, p.stdout, p.stderr, p.returncode, 'curl_cffi browser-impersonated HTTP fetch')


def playwright_tool(site, url):
    code = r'''
from playwright.sync_api import sync_playwright
import sys
u=sys.argv[1]
with sync_playwright() as p:
    browser=p.chromium.launch(headless=True)
    page=browser.new_page()
    page.goto(u, wait_until="load", timeout=45000)
    try:
        page.wait_for_load_state("networkidle", timeout=8000)
    except Exception:
        pass
    print(page.content()[:300000])
    browser.close()
'''
    p = run([str(VENV_PY), '-c', code, url])
    return analyze(site, 'playwright', url, p.stdout, p.stderr, p.returncode, 'plain Playwright Chromium render')


def playwright_stealth_tool(site, url):
    code = r'''
from playwright.sync_api import sync_playwright
from playwright_stealth import Stealth
import sys
u=sys.argv[1]
with sync_playwright() as p:
    browser=p.chromium.launch(headless=True)
    page=browser.new_page()
    Stealth().apply_stealth_sync(page)
    page.goto(u, wait_until="load", timeout=45000)
    try:
        page.wait_for_load_state("networkidle", timeout=8000)
    except Exception:
        pass
    print(page.content()[:300000])
    browser.close()
'''
    p = run([str(VENV_PY), '-c', code, url])
    return analyze(site, 'playwright-stealth', url, p.stdout, p.stderr, p.returncode, 'Playwright + playwright_stealth render')


def scrapy_cffi_tool(site, url):
    code = r'''
import sys
from curl_cffi import requests
from parsel import Selector
u=sys.argv[1]
r=requests.get(u, impersonate="chrome124", timeout=30)
sel=Selector(r.text)
texts=' '.join(t.strip() for t in sel.css('body ::text').getall() if t.strip())
print(texts[:300000])
'''
    p = run([str(VENV_PY), '-c', code, url])
    return analyze(site, 'scrapy-cffi', url, p.stdout, p.stderr, p.returncode, 'Scrapy-style extraction stack using curl_cffi + parsel')


def agent_browser_tool(site, url):
    _ = run([str(AGENT_BROWSER), 'connect', 'http://127.0.0.1:18800'])
    p1 = run([str(AGENT_BROWSER), 'open', url])
    p2 = run([str(AGENT_BROWSER), 'get', 'title'])
    p3 = run([str(AGENT_BROWSER), 'snapshot'])
    stdout = '\n'.join([p2.stdout or '', p3.stdout or ''])
    stderr = '\n'.join(x for x in [p1.stderr, p2.stderr, p3.stderr] if x)
    rc = max(p1.returncode, p2.returncode, p3.returncode)
    return analyze(site, 'local-agent-browser-cli', url, stdout, stderr, rc, 'local agent-browser CLI connected to Chrome CDP')


def main():
    site_payloads = []
    for site, url in SITES.items():
        tool_results = [
            asdict(crawl4ai_tool(site, url)),
            asdict(direct_http_tool(site, url)),
            asdict(curl_cffi_tool(site, url)),
            asdict(playwright_tool(site, url)),
            asdict(playwright_stealth_tool(site, url)),
            asdict(scrapy_cffi_tool(site, url)),
            asdict(agent_browser_tool(site, url)),
        ]
        tool_results.sort(key=lambda x: (-x['score'], x['tool']))
        site_payloads.append({'site': site, 'url': url, 'tool_results': tool_results})

    payload = {
        'generated_at': datetime.now().astimezone().isoformat(),
        'query': QUERY,
        'sites': site_payloads,
    }
    out_json = OUT_DIR / 'tool-matrix-v2.json'
    out_json.write_text(json.dumps(payload, ensure_ascii=False, indent=2))

    md = ['# 7 tools × 4 sites matrix report', '', f'- Query: `{QUERY}`', f'- Generated at: {payload["generated_at"]}', '']
    for site in site_payloads:
        md.append(f'## {site["site"]}')
        md.append('')
        md.append('| Tool | Score | Status | Product signals | Block signals |')
        md.append('|---|---:|---|---:|---:|')
        for r in site['tool_results']:
            md.append(f'| {r["tool"]} | {r["score"]} | {r["status"]} | {r["product_signal_count"]} | {r["block_signal_count"]} |')
        md.append('')
    out_md = OUT_DIR / 'tool-matrix-v2-report.md'
    out_md.write_text('\n'.join(md))
    print(out_json)
    print(out_md)
    print(json.dumps({'sites':[s['site'] for s in site_payloads]}, ensure_ascii=False))

if __name__ == '__main__':
    main()
