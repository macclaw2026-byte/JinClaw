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
        'success': [r'/goods\.html', r'\$\d+(?:\.\d{2})?', r'No results for', r'Submit search', r'Free shipping'],
        'block': [r'captcha', r'puzzle', r'access denied', r'unusual traffic', r'429', r'too many requests'],
    },
    '1688': {
        'success': [r'offer', r'¥\d+(?:\.\d+)?', r'成交'],
        'block': [r'登录', r'请按住滑块', r'短信登录', r'密码登录', r'captcha', r'punish', r'x5secdata', r'nocaptcha', r'unusual traffic'],
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
    current_url_match = re.search(r'^opened_url=(.+)$', stdout, flags=re.M)
    current_url = current_url_match.group(1).strip() if current_url_match else ''
    redirected_cross_site = False
    if current_url:
        expected_host = url.split('/')[2]
        redirected_cross_site = expected_host not in current_url
    product_signal_count = sum(len(re.findall(p, stdout, flags=re.I)) for p in rules['success'])
    block_signal_count = sum(len(re.findall(p, stdout, flags=re.I)) for p in rules['block'])
    if redirected_cross_site:
        block_signal_count += 3
        notes = f"{notes}; cross-site-redirect={current_url}"
    chars = len(stdout.strip())

    shell_indicators = [
        'window.__npm_package_config__', 'window.__cdn_img__', 'sessionstorage.x5referer',
        'window.location.replace(', 'cf.aliyun.com/nocaptcha', 'robot or human?',
        'activate and hold the button', 'captcha interception',
        'window.__initiallanguage__', 'window.__initiali18nstore__',
        'window.__pxappid', 'press & hold human challenge',
        'please slide to verify', 'sorry, we have detected unusual traffic from your network',
        'password login', '短信登录', '密码登录'
    ]
    shell_signal_count = sum(1 for sig in shell_indicators if sig in stdout.lower())

    score = 0
    if returncode == 0:
        score += 20
    if chars > 300:
        score += 10
    if chars > 3000:
        score += 5
    if product_signal_count > 0:
        score += min(40, 8 + product_signal_count * 4)
    if shell_signal_count > 0:
        score -= min(35, shell_signal_count * 10)
    if block_signal_count > 0:
        score -= min(55, 20 + block_signal_count * 10)
    score = max(0, min(100, score))

    if block_signal_count > 0 or shell_signal_count >= 2:
        status = 'blocked'
    elif product_signal_count >= 2 and chars > 1200 and shell_signal_count == 0:
        status = 'usable'
    elif product_signal_count >= 1 and chars > 300 and shell_signal_count <= 1:
        status = 'partial'
    elif chars > 100 and shell_signal_count == 0:
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
    p2 = run([str(AGENT_BROWSER), 'get', 'url'])
    p3 = run([str(AGENT_BROWSER), 'get', 'title'])
    p4 = run([str(AGENT_BROWSER), 'snapshot'])
    current_url = (p2.stdout or '').strip()
    title = (p3.stdout or '').strip()
    redirected = bool(current_url) and current_url.rstrip('/') != url.rstrip('/')
    redirect_note = f'opened_url={current_url}\n' if current_url else ''
    stdout = redirect_note + '\n'.join([title, p4.stdout or ''])
    stderr = '\n'.join(x for x in [p1.stderr, p2.stderr, p3.stderr, p4.stderr] if x)
    rc = max(p1.returncode, p2.returncode, p3.returncode, p4.returncode)
    notes = 'local agent-browser CLI connected to Chrome CDP'
    if redirected:
        notes += f'; redirected-to={current_url}'
    return analyze(site, 'local-agent-browser-cli', url, stdout, stderr, rc, notes)


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
