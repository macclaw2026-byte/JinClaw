#!/usr/bin/env python3
from __future__ import annotations

import json
from dataclasses import dataclass, asdict
from datetime import datetime
from pathlib import Path
from typing import Any

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

FIELD_HINTS = {
    'title': ['title', '商品', 'product', 'mouse'],
    'price': ['$', 'ca$', 'price', '售价', '价格'],
    'rating': ['rating', 'stars', '评分'],
    'reviews': ['reviews', 'review', '评价'],
    'link': ['http', '/dp/', '/ip/', '/offer/', 'href'],
    'promo': ['free shipping', 'coupon', '折扣', '优惠'],
}


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


def _extract_task_ready_fields(site: str, text: str) -> dict[str, Any]:
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    result = {
        'title': '',
        'price': '',
        'rating': '',
        'reviews': '',
        'link': '',
        'promo': '',
        'evidence_excerpt': lines[:5],
    }
    for line in lines[:200]:
        low = line.lower()
        if not result['title'] and any(k in low for k in ['amazon.com', 'walmart.com', 'temu', '采购批发平台', 'wireless mouse']):
            result['title'] = line[:240]
        if not result['price'] and any(k in low for k in ['$', 'ca$', 'price', '售价', '价格']):
            result['price'] = line[:120]
        if not result['rating'] and any(k in low for k in ['rating', 'stars', '评分']):
            result['rating'] = line[:120]
        if not result['reviews'] and any(k in low for k in ['reviews', 'review', '评价']):
            result['reviews'] = line[:120]
        if not result['link'] and ('http' in low or '/dp/' in low or '/ip/' in low or '/offer/' in low):
            result['link'] = line[:240]
        if not result['promo'] and any(k in low for k in ['free shipping', 'coupon', '折扣', '优惠']):
            result['promo'] = line[:120]
    if site == '1688':
        result = {
            'title': '', 'price': '', 'rating': '', 'reviews': '', 'link': '', 'promo': '',
            'evidence_excerpt': lines[:5],
        }
    return result


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
        reasons = [m for m in BLOCK_MARKERS.get(site, []) if m.lower() in text.lower()]
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
            field_completeness=field_score['completeness'],
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
            'current anonymous paths are blocked by human verification pages',
            'direct-http-html must not be treated as usable when it only returns the robot-or-human shell page',
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
        task_ready_fields = _extract_task_ready_fields(site, best_row.get('stdout_head', ''))

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
            field_completeness=field_score['completeness'],
            false_positive_reasons=reasons or (['none'] if status in ('usable', 'partial') and block_signal_count == 0 else []),
            notes=notes,
        )
        tool_decisions.append(decision)
        if decision.status in ('blocked', 'failed') or decision.block_signal_count > 0:
            blocked_tools.append(decision.tool)

    usable = [d for d in tool_decisions if d.status in ('usable', 'partial') and d.block_signal_count == 0]
    usable.sort(key=lambda d: (-d.score, -d.field_completeness, -d.product_signal_count, -d.stdout_chars))
    best = usable[0] if usable else None
    task_fields = _extract_task_ready_fields(site, next((r.get('stdout_head', '') for r in report['toolResults'] if best and r['tool'] == best.tool), ''))

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
