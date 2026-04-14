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
from dataclasses import dataclass, asdict
from datetime import datetime
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, unquote, urljoin, urlparse

ROOT = Path('/Users/mac_claw/.openclaw/workspace')
REPORT_DIR = ROOT / 'crawler' / 'reports'
SITE_PROFILE_DIR = ROOT / 'crawler' / 'site-profiles'
TOOLS_REGISTRY = [
    'crawl4ai-cli',
    'direct-http-html',
    'curl-cffi',
    'playwright',
    'playwright-stealth',
    'scrapy-cffi',
    'local-agent-browser-cli',
]

BLOCK_MARKERS = {
    'amazon': ['automated access', 'sorry! something went wrong', 'captcha'],
    'walmart': ['robot or human', 'activate and hold the button', 'confirm that you’re human', "confirm that you're human"],
    'temu': ['captcha', 'access denied', 'unusual traffic', 'too many requests'],
    '1688': ['登录', '密码登录', '短信登录', '请按住滑块', 'nocaptcha', 'punish', 'x5secdata', 'unusual traffic', '验证', '验证码'],
}

SITE_FORCED_BLOCKED_TOOLS = {
    '1688': {
        'local-agent-browser-cli': 'current anonymous browser output still lands in login-gated / challenged flow and must not be treated as task-usable',
    }
}

REQUIRED_FIELDS_BY_SITE = {
    'amazon': ['title', 'link'],
    'walmart': ['title', 'price', 'link'],
    'temu': ['title', 'price', 'link'],
    '1688': [],
    '1688-authenticated': ['title', 'price', 'link'],
}

FIELD_HINTS = {
    'title': ['title', '商品', 'product', 'mouse'],
    'price': ['$', 'ca$', 'price', '售价', '价格'],
    'rating': ['rating', 'stars', '评分'],
    'reviews': ['reviews', 'review', '评价'],
    'link': ['http', '/dp/', '/ip/', '/offer/', 'href'],
    'promo': ['free shipping', 'coupon', '折扣', '优惠'],
}

SHELL_PAGE_PREFIXES = (
    '<!doctype html',
    '<html',
    '![](',
)
PRICE_PATTERN = re.compile(r'((?:CA)?\$\s?\d[\d,]*(?:\.\d{2})?)', re.IGNORECASE)
URL_PATTERN = re.compile(r'(https?://[^\s)\]\">]+)', re.IGNORECASE)
OPENED_URL_PATTERN = re.compile(r'opened_url=(https?://[^\s]+)', re.IGNORECASE)
TITLE_PATTERNS = (
    re.compile(r'<title>(.*?)</title>', re.IGNORECASE | re.DOTALL),
    re.compile(r'property=["\']og:title["\'] content=["\']([^"\']+)["\']', re.IGNORECASE),
)
PROMO_MARKERS = ('off', 'coupon', 'free shipping', '折扣', '优惠')
PRICE_CONTEXT_MARKERS = ('price', 'sale', 'current', 'now', 'from', 'subtotal')
PRICE_BAD_CONTEXT_MARKERS = ('font-face', 'src:', '.woff', '.woff2', '.ttf', 'svg+xml', 'background-image')


@dataclass
class ToolDecision:
    tool: str
    status: str
    score: int
    product_signal_count: int
    block_signal_count: int
    stdout_chars: int
    field_completeness: float
    false_positive_reasons: list[str]
    notes: str | None = None


@dataclass
class SiteContract:
    site: str
    query: str
    mode: str
    first_run_rule: str
    repeat_run_rule: str
    auth_policy: dict[str, Any]
    tested_tools: list[str]
    preferred_tool_order: list[str]
    blocked_tools: list[str]
    comparison_summary: dict[str, Any]
    task_ready_fields: dict[str, Any]
    generated_at: str
    evidence_sources: list[str]


def _field_score(text: str) -> dict[str, Any]:
    lower = text.lower()
    hits = {}
    for field, hints in FIELD_HINTS.items():
        hits[field] = any(h in lower for h in hints)
    completeness = round(sum(1 for v in hits.values() if v) / len(FIELD_HINTS), 2)
    return {'hits': hits, 'completeness': completeness}


def _field_completeness_from_fields(fields: dict[str, Any]) -> float:
    populated = [name for name, value in (fields or {}).items() if name != 'evidence_excerpt' and str(value or '').strip()]
    return round(len(populated) / 6, 2)


def _strip_tags(text: str) -> str:
    return re.sub(r'<[^>]+>', ' ', str(text or '')).replace('&amp;', '&').strip()


def _normalize_excerpt(lines: list[str]) -> list[str]:
    return [line[:240] for line in lines[:5]]


def _normalize_url_candidate(candidate: str, source_url: str) -> str:
    cleaned = str(candidate or '').strip().replace('&amp;', '&')
    if not cleaned:
        return ''
    if cleaned.startswith('/'):
        cleaned = urljoin(source_url or '', cleaned)
    parsed = urlparse(cleaned)
    if '/sp/track' in parsed.path:
        redirected = (parse_qs(parsed.query).get('rd') or [''])[0]
        if redirected:
            cleaned = unquote(redirected)
            parsed = urlparse(cleaned)
    if cleaned.startswith('/'):
        cleaned = urljoin(source_url or '', cleaned)
    return cleaned[:240]


def _extract_title(site: str, text: str, lines: list[str]) -> str:
    site_block_markers = [str(marker).lower() for marker in BLOCK_MARKERS.get(site, [])]
    for pattern in TITLE_PATTERNS:
        match = pattern.search(text)
        if match:
            candidate = _strip_tags(match.group(1))
            if candidate:
                return candidate[:240]
    for line in lines[:80]:
        lowered = line.lower()
        if lowered.startswith('opened_url='):
            continue
        if any(marker in lowered for marker in site_block_markers):
            continue
        if '|' in line or ' : ' in line:
            if site in lowered or any(token in lowered for token in ('wireless mouse', 'search')):
                return line[:240]
        if line.startswith('StaticText "') and any(token in lowered for token in ('wireless mouse', 'search', site)):
            return line.replace('StaticText "', '').rstrip('"')[:240]
    return ''


def _extract_link(text: str, source_url: str) -> str:
    match = OPENED_URL_PATTERN.search(text)
    opened_url = _normalize_url_candidate(match.group(1), source_url) if match else ""
    fallback_candidate = ''
    for match in URL_PATTERN.finditer(text):
        candidate = _normalize_url_candidate(match.group(1), source_url)
        if not candidate:
            continue
        if any(token in candidate for token in ('/dp/', '/ip/', '/offer/')):
            return candidate
        if not fallback_candidate and any(token in candidate for token in ('/brand/', '/search', '/s?')):
            fallback_candidate = candidate
    if opened_url:
        return opened_url
    if fallback_candidate:
        return fallback_candidate
    return _normalize_url_candidate(str(source_url or '').strip(), source_url)


def _extract_price_and_promo(text: str, lines: list[str]) -> tuple[str, str]:
    price = ''
    promo = ''
    price_candidates: list[tuple[int, int, str]] = []
    for index, match in enumerate(PRICE_PATTERN.finditer(text[:300000])):
        candidate = match.group(1)[:120]
        numeric_candidate = candidate.lower().replace('ca$', '').replace('$', '').replace(',', '').strip()
        if numeric_candidate in {'0', '0.0', '0.00'}:
            continue
        start = max(0, match.start() - 120)
        end = min(len(text), match.end() + 120)
        context = text[start:end]
        lowered = context.lower()
        if any(marker in lowered for marker in PRICE_BAD_CONTEXT_MARKERS):
            continue
        if any(marker in lowered for marker in PROMO_MARKERS):
            if not promo:
                promo = _strip_tags(context)[:120]
            continue
        score = 0
        if any(marker in lowered for marker in PRICE_CONTEXT_MARKERS):
            score += 3
        if any(marker in lowered for marker in ('<h3', '<span', 'price', 'currentprice', 'product-price')):
            score += 2
        if 'statictext "' in lowered and 'orders over' not in lowered and 'special for you' not in lowered:
            score += 2
        if '<' not in context and '>' not in context:
            score += 1
        if 'orders over' in lowered or 'shipping' in lowered:
            score -= 2
        price_candidates.append((score, index, candidate))
    if price_candidates:
        price = sorted(price_candidates, key=lambda item: (-item[0], item[1]))[0][2]
    if not promo:
        for line in lines[:160]:
            lowered = line.lower()
            if any(marker in lowered for marker in PROMO_MARKERS):
                promo = line[:120]
                break
    return price, promo


def _extract_task_ready_fields(site: str, text: str, source_url: str = '') -> dict[str, Any]:
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    result = {
        'title': '',
        'price': '',
        'rating': '',
        'reviews': '',
        'link': '',
        'promo': '',
        'evidence_excerpt': _normalize_excerpt(lines),
    }
    result['title'] = _extract_title(site, text, lines)
    result['link'] = _extract_link(text, source_url)
    result['price'], result['promo'] = _extract_price_and_promo(text, lines)
    for line in lines[:200]:
        low = line.lower()
        if not result['title'] and any(k in low for k in ['amazon.com', 'walmart.com', 'temu', '采购批发平台', 'wireless mouse']):
            result['title'] = line[:240]
        if not result['price'] and any(k in low for k in ['price', '售价', '价格']) and PRICE_PATTERN.search(line):
            result['price'] = PRICE_PATTERN.search(line).group(1)[:120]
        if not result['rating'] and any(k in low for k in ['rating', 'stars', '评分']):
            result['rating'] = line[:120]
        if not result['reviews'] and any(k in low for k in ['reviews', 'review', '评价']):
            result['reviews'] = line[:120]
        if not result['link'] and ('http' in low or '/dp/' in low or '/ip/' in low or '/offer/' in low):
            result['link'] = line[:240]
        if not result['promo'] and any(k in low for k in PROMO_MARKERS):
            result['promo'] = line[:120]
    if site == '1688':
        result = {
            'title': '', 'price': '', 'rating': '', 'reviews': '', 'link': '', 'promo': '',
            'evidence_excerpt': _normalize_excerpt(lines),
        }
    return _sanitize_task_ready_fields(site, result)


def _sanitize_task_ready_fields(site: str, fields: dict[str, Any]) -> dict[str, Any]:
    """
    清洗 task-ready 字段，避免把整段 HTML、站点壳页标题或明显的 shell 输出误判成可交付字段。
    """
    cleaned = dict(fields or {})
    site_block_markers = [str(marker).lower() for marker in BLOCK_MARKERS.get(site, [])]
    for key in ('title', 'price', 'rating', 'reviews', 'link', 'promo'):
        value = str(cleaned.get(key, '') or '').strip()
        lowered = value.lower()
        if any(lowered.startswith(prefix) for prefix in SHELL_PAGE_PREFIXES):
            cleaned[key] = ''
            continue
        if '<html' in lowered or '<head' in lowered or '<body' in lowered:
            cleaned[key] = ''
            continue
        if len(value) > 180 and ('<' in value and '>' in value):
            cleaned[key] = ''
            continue
        if '<script' in lowered or '</script>' in lowered or 'data-nscript' in lowered:
            cleaned[key] = ''
            continue
        if key == 'title' and any(marker in lowered for marker in site_block_markers):
            cleaned[key] = ''
        elif key == 'price' and any(marker in lowered for marker in PROMO_MARKERS):
            cleaned[key] = ''
        elif key == 'price' and lowered.replace('ca$', '').replace('$', '').replace(',', '').strip() in {'0', '0.0', '0.00'}:
            cleaned[key] = ''
        elif key == 'link' and value and not (
            value.startswith('http') or value.startswith('/') or '/dp/' in value or '/ip/' in value or '/offer/' in value
        ):
            cleaned[key] = ''
        elif key == 'link' and value:
            cleaned[key] = _normalize_url_candidate(value, '')
    return cleaned


def _row_task_ready_fields(site: str, row: dict[str, Any]) -> dict[str, Any]:
    """
    中文注解：
    - 功能：优先使用 tool row 自带的结构化 task_ready_fields；若缺失再回退到 stdout_head 抽取。
    - 设计意图：matrix 采集阶段看到的是更完整的原始输出，后续 contract 不应退化成只从截断 head 重新猜字段。
    """
    row_fields = row.get('task_ready_fields', {}) or {}
    if isinstance(row_fields, dict) and any(str(row_fields.get(key, '')).strip() for key in ('title', 'price', 'link', 'promo', 'rating', 'reviews')):
        normalized = dict(row_fields)
        normalized.setdefault('evidence_excerpt', [])
        return _sanitize_task_ready_fields(site, normalized)
    return _extract_task_ready_fields(site, row.get('stdout_head', ''), row.get('url', ''))


def _meets_required_fields(site: str, fields: dict[str, Any]) -> bool:
    required = REQUIRED_FIELDS_BY_SITE.get(site, [])
    if not required:
        return True
    return all(bool(str(fields.get(name, '')).strip()) for name in required)


def _missing_required_fields(site: str, fields: dict[str, Any]) -> list[str]:
    required = REQUIRED_FIELDS_BY_SITE.get(site, [])
    return [name for name in required if not bool(str((fields or {}).get(name, '')).strip())]


def _site_aliases(site: str) -> list[str]:
    if site == '1688-authenticated':
        return ['1688-authenticated', '1688']
    return [site]


def load_latest_report(site: str) -> dict[str, Any]:
    return json.loads((REPORT_DIR / f'{site}-latest-run.json').read_text())


def summarize_site_from_matrix(site: str, matrix: dict[str, Any]) -> dict[str, Any]:
    site_row = next((s for s in matrix['sites'] if s['site'] == site), None)
    if not site_row:
        raise ValueError(f'No matrix data for site: {site}')

    tool_decisions: list[ToolDecision] = []
    blocked_tools: list[str] = []
    usable: list[ToolDecision] = []
    forced_blocked = SITE_FORCED_BLOCKED_TOOLS.get(site, {})

    for row in site_row['tool_results']:
        text = f"{row.get('stdout_head', '')}\n{row.get('stderr_head', '')}"
        reasons = [m for alias in _site_aliases(site) for m in BLOCK_MARKERS.get(alias, []) if m.lower() in text.lower()]
        task_ready_fields = _row_task_ready_fields(site, row)
        field_score = _field_score(text)
        notes = row.get('notes')
        status = row['status']
        block_signal_count = row['block_signal_count']
        if row['tool'] in forced_blocked:
            status = 'blocked'
            block_signal_count = max(block_signal_count, 1)
            reasons = reasons + [forced_blocked[row['tool']]]
            notes = forced_blocked[row['tool']]
        decision = ToolDecision(
            tool=row['tool'],
            status=status,
            score=row['score'],
            product_signal_count=row['product_signal_count'],
            block_signal_count=block_signal_count,
            stdout_chars=row['stdout_chars'],
            field_completeness=max(_field_completeness_from_fields(task_ready_fields), field_score['completeness']),
            false_positive_reasons=reasons or (['none'] if status in ('usable', 'partial') and block_signal_count == 0 else []),
            notes=notes,
        )
        tool_decisions.append(decision)
        if decision.status in ('usable', 'partial') and decision.block_signal_count == 0:
            usable.append(decision)
        else:
            blocked_tools.append(decision.tool)

    usable.sort(key=lambda d: (-d.score, -d.field_completeness, -d.product_signal_count, -d.stdout_chars))
    preferred = [d.tool for d in usable] + [d.tool for d in tool_decisions if d.tool not in {u.tool for u in usable}]
    best = usable[0] if usable else None

    confidence = 'high' if best and best.score >= 80 else 'medium' if best else 'low'
    if site == '1688' and not best:
        confidence = 'high'

    if site == 'amazon':
        mode = 'anonymous-public'
        fallback_policy = 'start-primary-then-fallback-ordered'
        notes = [
            'browser-rendered and crawl4ai flows currently produce the strongest anonymous public results',
            'direct-http-html fails outright in current tests',
            'curl-cffi tends to hit Amazon automated-access defenses',
        ]
    elif site == 'walmart':
        mode = 'anonymous-public-route-specific'
        fallback_policy = 'blocked-under-current-anonymous-paths-require-full-reevaluation-on-change'
        notes = [
            'most anonymous Walmart paths still encounter human verification pages',
            'direct-http-html is only promotable when required fields are present with a clean non-zero price and a decoded destination link',
        ]
    elif site == 'temu':
        mode = 'browser-first-anonymous'
        fallback_policy = 'browser-first-then-light-probe-then-re-evaluate'
        notes = [
            'local-agent-browser-cli is the only clearly usable route in the latest matrix',
            'HTTP-oriented outputs trend shell-heavy or blocked and need stronger normalize-time validation',
        ]
    else:
        mode = 'anonymous-blocked'
        fallback_policy = 'do-not-run-as-normal-anonymous-production-target'
        notes = [
            'anonymous access consistently falls into login, slider, punish, nocaptcha, or redirect flows',
            'authenticated mode must be treated as a separate profile and separate run history',
        ]

    task_ready_fields = {'title': '', 'price': '', 'rating': '', 'reviews': '', 'link': '', 'promo': '', 'evidence_excerpt': []}
    if best:
        best_row = next(r for r in site_row['tool_results'] if r['tool'] == best.tool)
        task_ready_fields = _row_task_ready_fields(site, best_row)
    if best and not _meets_required_fields(site, task_ready_fields):
        blocked_tools.append(best.tool)
        usable = [d for d in usable if d.tool != best.tool]
        preferred = [d.tool for d in usable] + [d.tool for d in tool_decisions if d.tool not in {u.tool for u in usable}]
        best = usable[0] if usable else None
        task_ready_fields = {'title': '', 'price': '', 'rating': '', 'reviews': '', 'link': '', 'promo': '', 'evidence_excerpt': []}
        if best:
            best_row = next(r for r in site_row['tool_results'] if r['tool'] == best.tool)
            task_ready_fields = _row_task_ready_fields(site, best_row)

    markdown_lines = [
        f'# {site.capitalize()} Site Profile',
        '',
        f'- Last evaluated: {datetime.now().date().isoformat()}',
        f'- Confidence: {confidence}',
        f'- Recommended mode: {mode}',
        '',
        '## Preferred tool order',
    ]
    for i, tool in enumerate(preferred, start=1):
        markdown_lines.append(f'{i}. {tool}')
    markdown_lines += [
        '',
        '## Recommended default',
        f"- Primary: {best.tool if best else 'none'}",
        f"- Extraction decision: {'best_single_tool_output' if best else 'blocked_or_insufficient_evidence'}",
        '',
        '## Task-ready fields from current best result',
        f"- title: {task_ready_fields['title'] or '(empty)'}",
        f"- price: {task_ready_fields['price'] or '(empty)'}",
        f"- rating: {task_ready_fields['rating'] or '(empty)'}",
        f"- reviews: {task_ready_fields['reviews'] or '(empty)'}",
        f"- link: {task_ready_fields['link'] or '(empty)'}",
        f"- promo: {task_ready_fields['promo'] or '(empty)'}",
        '',
        '## Known behavior',
    ]
    for d in tool_decisions:
        markdown_lines.append(
            f"- {d.tool}: status={d.status}, arbitration_score={d.score}, field_completeness={d.field_completeness}, false_positive_reasons={d.false_positive_reasons}"
        )
    markdown_lines += [
        '',
        '## Repeat-run policy',
        '- Start with the first preferred tool',
        '- If blocked or weak, try the next fallback in order',
        '- If the top path degrades materially, trigger a fresh all-tools first-run evaluation',
    ]
    if site == '1688':
        markdown_lines += [
            '',
            '## Auth note',
            '- 需要用户明确授权后才可进入登录态自动化。',
            '- 优先使用浏览器型工具完成一次正常登录，而不是把凭证分发给所有抓取栈。',
            '- 登录态 profile 与匿名 profile 必须分开记录。',
            '- 若遇到 slider/captcha/device-risk，需要人工介入，不做绕过。',
        ]

    json_profile = {
        'lastEvaluated': datetime.now().date().isoformat(),
        'confidence': confidence,
        'mode': mode,
        'preferredTools': preferred,
        'fallbackPolicy': fallback_policy,
        'notes': notes,
    }
    return {
        'json_profile': json_profile,
        'markdown': '\n'.join(markdown_lines) + '\n',
        'tool_decisions': [asdict(d) for d in tool_decisions],
    }


def build_contract(site: str) -> SiteContract:
    report = load_latest_report(site)
    tool_decisions: list[ToolDecision] = []
    blocked_tools: list[str] = []
    forced_blocked = SITE_FORCED_BLOCKED_TOOLS.get(site, {})

    for row in report['toolResults']:
        text = f"{row.get('stdout_head', '')}\n{row.get('stderr_head', '')}"
        reasons = [m for m in BLOCK_MARKERS.get(site, []) if m.lower() in text.lower()]
        task_fields = _row_task_ready_fields(site, row)
        field_score = _field_score(text)
        notes = row.get('notes')
        status = row['status']
        block_signal_count = row['block_signal_count']
        if row['tool'] in forced_blocked:
            status = 'blocked'
            block_signal_count = max(block_signal_count, 1)
            reasons = reasons + [forced_blocked[row['tool']]]
            notes = forced_blocked[row['tool']]
        decision = ToolDecision(
            tool=row['tool'],
            status=status,
            score=row['score'],
            product_signal_count=row['product_signal_count'],
            block_signal_count=block_signal_count,
            stdout_chars=row['stdout_chars'],
            field_completeness=max(_field_completeness_from_fields(task_fields), field_score['completeness']),
            false_positive_reasons=reasons or (['none'] if status in ('usable', 'partial') and block_signal_count == 0 else []),
            notes=notes,
        )
        tool_decisions.append(decision)
        if decision.status in ('blocked', 'failed') or decision.block_signal_count > 0:
            blocked_tools.append(decision.tool)

    row_map = {str(row.get('tool', '')).strip(): row for row in report['toolResults']}
    usable = [d for d in tool_decisions if d.status in ('usable', 'partial') and d.block_signal_count == 0]
    usable.sort(
        key=lambda d: (
            -(
                1
                if _meets_required_fields(
                    site,
                    _row_task_ready_fields(site, row_map.get(d.tool, {}) or {}),
                )
                else 0
            ),
            -d.field_completeness,
            -d.score,
            -d.product_signal_count,
            -d.stdout_chars,
        )
    )
    best = usable[0] if usable else None
    task_fields = _row_task_ready_fields(
        site,
        next((r for r in report['toolResults'] if best and r['tool'] == best.tool), {}),
    )
    disqualified_tools: list[dict[str, Any]] = []
    while best and not _meets_required_fields(site, task_fields):
        missing_fields = _missing_required_fields(site, task_fields)
        blocked_tools.append(best.tool)
        disqualified_tools.append(
            {
                'tool': best.tool,
                'reason': 'missing_required_fields',
                'missing_required_fields': missing_fields,
            }
        )
        usable = [d for d in usable if d.tool != best.tool]
        best = usable[0] if usable else None
        task_fields = _row_task_ready_fields(
            site,
            next((r for r in report['toolResults'] if best and r['tool'] == best.tool), {}),
        )
    if not best:
        task_fields = {'title': '', 'price': '', 'rating': '', 'reviews': '', 'link': '', 'promo': '', 'evidence_excerpt': []}

    auth_policy = {
        'anonymous_mode': 'allowed' if site != '1688' else 'truth-check-only',
        'authenticated_mode': 'separate-profile-required',
        'credential_use': 'browser-login-only-with-explicit-user-authorization',
        'captcha_policy': 'do-not-bypass; require human intervention if challenged',
    }

    return SiteContract(
        site=site,
        query=report['query'],
        mode='anonymous_truth_check_only' if site == '1688' else ('insufficient-evidence-or-blocked' if site == 'walmart' and not best else report['taskReadySummary']['recommendedAction']),
        first_run_rule='run-all-known-tools-then-compare-normalize-and-record-order',
        repeat_run_rule='start-with-primary-then-fallback-in-recorded-order-and-re-evaluate-on-degradation',
        auth_policy=auth_policy,
        tested_tools=TOOLS_REGISTRY,
        preferred_tool_order=report['preferredOrder'],
        blocked_tools=blocked_tools,
        comparison_summary={
            'best_tool': best.tool if best else None,
            'best_status': best.status if best else 'blocked',
            'best_score': best.score if best else 0,
            'required_fields_met': bool(best and _meets_required_fields(site, task_fields)),
            'missing_required_fields': _missing_required_fields(site, task_fields) if best else REQUIRED_FIELDS_BY_SITE.get(site, []),
            'disqualified_tools': disqualified_tools,
            'usable_tools': [asdict(d) for d in usable],
            'all_tools': [asdict(d) for d in tool_decisions],
        },
        task_ready_fields=task_fields,
        generated_at=datetime.now().astimezone().isoformat(),
        evidence_sources=[str(REPORT_DIR / f'{site}-latest-run.json'), str(SITE_PROFILE_DIR / f'{site}.md')],
    )


def save_contract(site: str) -> Path:
    contract = build_contract(site)
    out = REPORT_DIR / f'{site}-contract.json'
    out.write_text(json.dumps(asdict(contract), ensure_ascii=False, indent=2))
    return out


def save_all() -> list[Path]:
    return [save_contract(site) for site in ['amazon', 'walmart', 'temu', '1688']]


if __name__ == '__main__':
    for path in save_all():
        print(path)
