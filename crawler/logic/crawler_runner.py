#!/usr/bin/env python3
# RULES-FIRST NOTICE:
# Before modifying this file, first read:
# - `JINCLAW_CONSTITUTION.md`
# - `AI_OPTIMIZATION_FRAMEWORK.md`
# Follow the constitution and framework:
# brain-first, one-doctor, fail-closed, evidence-over-narration,
# validate locally, then use the required PR workflow.
from __future__ import annotations

import argparse
import json
import subprocess
from datetime import datetime
from pathlib import Path
from urllib.parse import quote_plus

from crawler.logic.crawler_contract import (
    _extract_task_ready_fields,
    _field_completeness_from_fields,
    _field_score,
    _meets_required_fields,
    save_contract,
    summarize_site_from_matrix,
)

ROOT = Path('/Users/mac_claw/.openclaw/workspace')
SITE_PROFILES = ROOT / 'crawler' / 'logic' / 'site_profiles.json'
SITE_PROFILE_DIR = ROOT / 'crawler' / 'site-profiles'
REPORT_DIR = ROOT / 'crawler' / 'reports'
STATE_DIR = ROOT / 'crawler' / 'state'
STATE_DIR.mkdir(parents=True, exist_ok=True)
FIRST_RUN_STATE = STATE_DIR / 'first_run_state.json'
REPORT_DIR.mkdir(parents=True, exist_ok=True)
MATRIX_SCRIPT = ROOT / 'tools' / 'site_tool_matrix_v2.py'
MATRIX_JSON = ROOT / 'reports' / 'site-tool-matrix' / 'tool-matrix-v2.json'

SITE_URLS = {
    'amazon': lambda q: f'https://www.amazon.com/s?k={quote_plus(q)}',
    'walmart': lambda q: f'https://www.walmart.com/search?q={quote_plus(q)}',
    'temu': lambda q: f'https://www.temu.com/search_result.html?search_key={quote_plus(q)}',
    '1688': lambda q: f'https://s.1688.com/selloffer/offer_search.htm?keywords={quote_plus(q)}',
    '1688-authenticated': lambda q: f'https://s.1688.com/selloffer/offer_search.htm?keywords={quote_plus(q)}',
}


def _normalize_site_profile(site: str, profile: dict) -> dict:
    if not profile:
        return profile
    if 'preferredTools' in profile:
        return profile
    preferred = profile.get('preferred_tool_order', [])
    fallback = profile.get('fallback_policy', '')
    notes = profile.get('notes', [])
    if not notes:
        notes = [
            f"selected_tool={profile.get('selected_tool', '') or 'none'}",
            f"mode={profile.get('mode', '')}",
            f"confidence={profile.get('confidence', '')}",
        ]
    return {
        'site': site,
        'lastEvaluated': profile.get('last_evaluated'),
        'confidence': profile.get('confidence'),
        'mode': profile.get('mode'),
        'preferredTools': preferred,
        'fallbackPolicy': fallback,
        'notes': notes,
    }


def load_profiles() -> dict:
    profiles = {}
    if SITE_PROFILES.exists():
        raw = json.loads(SITE_PROFILES.read_text())
        for site, profile in raw.items():
            profiles[site] = _normalize_site_profile(site, profile)
    for path in SITE_PROFILE_DIR.glob('*.json'):
        try:
            raw_profile = json.loads(path.read_text())
        except Exception:
            continue
        site = raw_profile.get('site') or path.stem
        profiles[site] = _normalize_site_profile(site, raw_profile)
    return profiles


def save_profiles(profiles: dict) -> None:
    SITE_PROFILES.write_text(json.dumps(profiles, ensure_ascii=False, indent=2) + '\n')


def load_matrix() -> dict:
    return json.loads(MATRIX_JSON.read_text())


def load_first_run_state() -> dict:
    if not FIRST_RUN_STATE.exists():
        return {}
    return json.loads(FIRST_RUN_STATE.read_text())


def save_first_run_state(state: dict) -> None:
    FIRST_RUN_STATE.write_text(json.dumps(state, ensure_ascii=False, indent=2) + '\n')


def site_has_completed_first_run(site: str) -> bool:
    state = load_first_run_state()
    return bool(state.get(site, {}).get('completed'))


def mark_site_first_run_completed(site: str, query: str) -> None:
    state = load_first_run_state()
    state[site] = {
        'completed': True,
        'completedAt': datetime.now().astimezone().isoformat(),
        'query': query,
        'matrix': str(MATRIX_JSON),
    }
    save_first_run_state(state)


def run_full_matrix() -> None:
    subprocess.run(['python3', str(MATRIX_SCRIPT)], cwd=str(ROOT), check=True)


def choose_best(tool_results: list[dict], site: str | None = None) -> dict | None:
    forced_blocked = {
        '1688': {'local-agent-browser-cli'},
    }
    blocked_for_site = forced_blocked.get(site or '', set())
    survivors = [
        r for r in tool_results
        if r['status'] in ('usable', 'partial')
        and r['block_signal_count'] == 0
        and r['tool'] not in blocked_for_site
    ]
    if survivors:
        ranked = []
        for row in survivors:
            text = f"{row.get('stdout_head', '')}\n{row.get('stderr_head', '')}"
            task_fields = _extract_task_ready_fields(site or '', row.get('stdout_head', ''), row.get('url', '')) if site else {}
            required_fields_met = _meets_required_fields(site or '', task_fields) if site else True
            field_completeness = max(
                float(row.get('field_completeness', 0) or 0),
                _field_completeness_from_fields(task_fields),
                _field_score(text).get('completeness', 0),
            )
            ranked.append(
                (
                    1 if required_fields_met else 0,
                    field_completeness,
                    int(row.get('score', 0) or 0),
                    int(row.get('product_signal_count', 0) or 0),
                    int(row.get('stdout_chars', 0) or 0),
                    row,
                )
            )
        ranked.sort(key=lambda item: (-item[0], -item[1], -item[2], -item[3], -item[4]))
        if site:
            for item in ranked:
                if item[0] > 0:
                    return item[-1]
            return None
        return ranked[0][-1]
    return None


def refresh_site_profile_from_matrix(site: str) -> dict:
    matrix = load_matrix()
    summary = summarize_site_from_matrix(site, matrix)
    profiles = load_profiles()
    profiles[site] = summary['json_profile']
    save_profiles(profiles)
    (SITE_PROFILE_DIR / f'{site}.md').write_text(summary['markdown'])
    return summary['json_profile']


def run_site(site: str, query: str, first_run: bool = False, refresh_profile: bool = False) -> dict:
    profiles = load_profiles()
    profile = profiles.get(site)
    state_site = site
    matrix_site = site
    if site == '1688-authenticated':
        matrix_site = '1688'
    first_run_missing = not site_has_completed_first_run(state_site)
    should_full_eval = first_run or refresh_profile or not profile or first_run_missing
    if should_full_eval:
        run_full_matrix()
        if site != '1688-authenticated':
            profile = refresh_site_profile_from_matrix(site)
        mark_site_first_run_completed(state_site, query)
    matrix = load_matrix()
    site_row = next((s for s in matrix['sites'] if s['site'] == matrix_site), None)
    if not site_row:
        raise SystemExit(f'No matrix data for site: {site}')

    preferred = profile['preferredTools'] if profile else [r['tool'] for r in site_row['tool_results']]
    ordered = sorted(site_row['tool_results'], key=lambda r: preferred.index(r['tool']) if r['tool'] in preferred else 999)
    best = choose_best(ordered, site=site)

    result = {
        'site': site,
        'query': query,
        'url': SITE_URLS[site](query),
        'usedProfile': bool(profile),
        'firstRunMode': should_full_eval,
        'preferredOrder': preferred,
        'bestTool': best['tool'] if best else None,
        'bestStatus': best['status'] if best else 'blocked',
        'bestScore': best['score'] if best else 0,
        'taskReadySummary': {
            'recommendedAction': 'use-best-tool' if best else 'insufficient-evidence-or-blocked',
            'confidence': 'high' if best and best['score'] >= 80 else 'medium' if best else 'low',
            'notes': profile['notes'] if profile else [],
        },
        'toolResults': ordered,
        'generatedAt': datetime.now().astimezone().isoformat(),
    }

    out = REPORT_DIR / f'{site}-latest-run.json'
    out.write_text(json.dumps(result, ensure_ascii=False, indent=2))
    save_contract(site)
    return result


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument('site', choices=SITE_URLS.keys())
    ap.add_argument('--query', default='wireless mouse')
    ap.add_argument('--first-run', action='store_true')
    ap.add_argument('--refresh-profile', action='store_true')
    args = ap.parse_args()
    result = run_site(args.site, args.query, first_run=args.first_run, refresh_profile=args.refresh_profile)
    print(json.dumps({
        'site': result['site'],
        'bestTool': result['bestTool'],
        'bestStatus': result['bestStatus'],
        'report': str(REPORT_DIR / f'{args.site}-latest-run.json')
    }, ensure_ascii=False))


if __name__ == '__main__':
    main()
