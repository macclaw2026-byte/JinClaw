#!/usr/bin/env python3
# RULES-FIRST NOTICE:
# Before modifying this file, first read:
# - `JINCLAW_CONSTITUTION.md`
# - `AI_OPTIMIZATION_FRAMEWORK.md`
# Follow the constitution and framework:
# brain-first, one-doctor, fail-closed, evidence-over-narration,
# validate locally, then use the required PR workflow.
from __future__ import annotations

import json
import re
import subprocess
import sys
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from urllib.parse import quote_plus

ROOT = Path('/Users/mac_claw/.openclaw/workspace')
OUT_DIR = ROOT / 'reports' / 'site-tool-matrix'
OUT_DIR.mkdir(parents=True, exist_ok=True)
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
CRAWL4AI = ROOT / 'tools' / 'bin' / 'crawl4ai'
AGENT_BROWSER = ROOT / 'tools' / 'agent-browser-local' / 'node_modules' / 'agent-browser' / 'bin' / 'agent-browser-darwin-arm64'
VENV_PY = ROOT / 'tools' / 'matrix-venv' / 'bin' / 'python'

from crawler.logic.crawler_contract import _extract_task_ready_fields, _field_completeness_from_fields, _meets_required_fields, _missing_required_fields

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

SITE_SHELL_INDICATORS = {
    'amazon': [
        'robot or human?',
        'captcha interception',
        'sorry, we have detected unusual traffic from your network',
    ],
    'walmart': [
        'robot or human?',
        'activate and hold the button',
        'press & hold human challenge',
    ],
    'temu': [
        'window.__initiallanguage__',
        'window.__initiali18nstore__',
        'window.__pxappid',
        'window.__px',
        'window.___browsercheck___',
        'window.___grecaptcha_cfg',
        'no results for',
        'organizing categories',
    ],
    '1688': [
        'window.__npm_package_config__',
        'window.__cdn_img__',
        'sessionstorage.x5referer',
        'window.location.replace(',
        'cf.aliyun.com/nocaptcha',
        'please slide to verify',
        'password login',
        '短信登录',
        '密码登录',
        'window.location.href = decodeuricomponent',
        'window.location.href=decodeuricomponent',
        'login.1688.com/member/signin',
        'login.taobao.com',
        'x5secdata',
    ],
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
    field_completeness: float
    required_fields_met: bool
    missing_required_fields: list[str]
    task_ready_fields: dict[str, object]
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

    shell_indicators = SITE_SHELL_INDICATORS.get(site, [])
    shell_signal_count = sum(1 for sig in shell_indicators if sig in stdout.lower())
    task_ready_fields = _extract_task_ready_fields(site, stdout[:300000], current_url or url)
    field_completeness = _field_completeness_from_fields(task_ready_fields)
    required_fields_met = _meets_required_fields(site, task_ready_fields)
    missing_required_fields = _missing_required_fields(site, task_ready_fields)

    score = 0
    if returncode == 0:
        score += 20
    if chars > 300:
        score += 10
    if chars > 3000:
        score += 5
    if product_signal_count > 0:
        score += min(40, 8 + product_signal_count * 4)
    if required_fields_met:
        score += 10
    elif field_completeness > 0:
        score += min(8, int(field_completeness * 10))
    if shell_signal_count > 0:
        score -= min(35, shell_signal_count * 10)
    if block_signal_count > 0:
        score -= min(55, 20 + block_signal_count * 10)
    score = max(0, min(100, score))

    if block_signal_count > 0 or shell_signal_count >= 2:
        status = 'blocked'
    elif site == 'temu' and shell_signal_count >= 1:
        status = 'blocked'
    elif site == '1688' and ('login.1688.com' in stdout.lower() or 'login.taobao.com' in stdout.lower() or 'x5secdata' in stdout.lower()):
        status = 'blocked'
    elif product_signal_count >= 2 and chars > 1200 and shell_signal_count == 0:
        status = 'usable'
    elif product_signal_count >= 1 and chars > 300 and shell_signal_count <= 1:
        status = 'partial'
    elif chars > 100 and shell_signal_count == 0:
        status = 'partial'
    else:
        status = 'failed'
    if status == 'partial' and required_fields_met and field_completeness >= 0.5 and block_signal_count == 0 and shell_signal_count <= 1:
        status = 'usable'

    return ToolResult(
        site,
        tool,
        url,
        returncode,
        len(stdout),
        len(stderr),
        product_signal_count,
        block_signal_count,
        status,
        score,
        notes,
        field_completeness,
        required_fields_met,
        missing_required_fields,
        task_ready_fields,
        stdout[:2200],
        stderr[:1200],
    )


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
    p = run([str(VENV_PY), '-c', code, url])
    return analyze(site, 'direct-http-html', url, p.stdout, p.stderr, p.returncode, 'raw urllib HTTP fetch via matrix-venv')


def curl_cffi_tool(site, url):
    code = (
        'from curl_cffi import requests; import sys; '
        'u=sys.argv[1]; '
        'r=requests.get(u, impersonate="chrome124", timeout=30); '
        'print(r.text[:300000])'
    )
    p = run([str(VENV_PY), '-c', code, url])
    return analyze(site, 'curl-cffi', url, p.stdout, p.stderr, p.returncode, 'curl_cffi browser-impersonated HTTP fetch')


def _playwright_capture_tool(site, url, *, tool_name: str, stealth: bool, scroll_steps: int, notes: str):
    """
    中文注解：
    - 功能：统一生成 Playwright 系列浏览器抓取 runner。
    - 设计意图：让 plain/stealth/scroll 这些浏览器执行变体共享同一套实现，而不是复制多份脚本。
    """
    stealth_import = "from playwright_stealth import Stealth\n" if stealth else ""
    stealth_apply = "    Stealth().apply_stealth_sync(page)\n" if stealth else ""
    scroll_loop = ""
    if scroll_steps > 0:
        scroll_loop = (
            f"    for _ in range({int(scroll_steps)}):\n"
            "        page.mouse.wheel(0, 2200)\n"
            "        page.wait_for_timeout(700)\n"
            "        try:\n"
            "            page.wait_for_load_state(\"networkidle\", timeout=3000)\n"
            "        except Exception:\n"
            "            pass\n"
        )
    code = (
        "from playwright.sync_api import sync_playwright\n"
        f"{stealth_import}"
        "import sys\n"
        "u=sys.argv[1]\n"
        "with sync_playwright() as p:\n"
        "    browser=p.chromium.launch(headless=True)\n"
        "    page=browser.new_page()\n"
        f"{stealth_apply}"
        "    page.goto(u, wait_until=\"load\", timeout=45000)\n"
        "    try:\n"
        "        page.wait_for_load_state(\"networkidle\", timeout=8000)\n"
        "    except Exception:\n"
        "        pass\n"
        f"{scroll_loop}"
        "    print(f\"opened_url={page.url}\")\n"
        "    print(page.content()[:300000])\n"
        "    browser.close()\n"
    )
    p = run([str(VENV_PY), '-c', code, url])
    return analyze(site, tool_name, url, p.stdout, p.stderr, p.returncode, notes)


def playwright_tool(site, url):
    return _playwright_capture_tool(
        site,
        url,
        tool_name='playwright',
        stealth=False,
        scroll_steps=0,
        notes='plain Playwright Chromium render',
    )


def playwright_scroll_tool(site, url):
    return _playwright_capture_tool(
        site,
        url,
        tool_name='playwright-scroll',
        stealth=False,
        scroll_steps=4,
        notes='Playwright Chromium render with repeated scroll capture for lazy-loaded content',
    )


def playwright_stealth_tool(site, url):
    return _playwright_capture_tool(
        site,
        url,
        tool_name='playwright-stealth',
        stealth=True,
        scroll_steps=0,
        notes='Playwright + playwright_stealth render',
    )


def playwright_stealth_scroll_tool(site, url):
    return _playwright_capture_tool(
        site,
        url,
        tool_name='playwright-stealth-scroll',
        stealth=True,
        scroll_steps=4,
        notes='Playwright + playwright_stealth render with repeated scroll capture for dynamic lists',
    )


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
            asdict(playwright_scroll_tool(site, url)),
            asdict(playwright_stealth_tool(site, url)),
            asdict(playwright_stealth_scroll_tool(site, url)),
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

    md = ['# 9 tools × 4 sites matrix report', '', f'- Query: `{QUERY}`', f'- Generated at: {payload["generated_at"]}', '']
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
