#!/usr/bin/env python3
"""Amazon premium wholesale pipeline v1.

This script is intentionally a local pipeline skeleton plus a working scoring core.
It is designed to reduce token burn by doing collection normalization, filtering,
scoring, novelty handling, and report-row generation locally.
"""
from __future__ import annotations
import json
from dataclasses import dataclass, asdict, field
from pathlib import Path
from datetime import datetime
from typing import List, Dict, Any
from urllib.parse import urlparse
import re

ROOT = Path('/Users/mac_claw/.openclaw/workspace')
STATE = ROOT / '.state' / 'amazon-premium-wholesale.json'
INPUT_DIR = ROOT / 'data' / 'amazon-premium-wholesale'
RAW_INPUT = INPUT_DIR / 'raw_candidates.json'
OUT = ROOT / 'output' / 'amazon-premium-wholesale'
OUT.mkdir(parents=True, exist_ok=True)
STATE.parent.mkdir(parents=True, exist_ok=True)
INPUT_DIR.mkdir(parents=True, exist_ok=True)

@dataclass
class Candidate:
    candidate_id: str
    product_name: str
    sub_niche: str
    source_mix: List[str]
    excluded: bool = False
    brand_risk: bool = False
    regulated: bool = False
    body_contact_formula: bool = False
    ingestible: bool = False
    trend_strength: float = 0.0
    search_intent_strength: float = 0.0
    customer_pain_clarity: float = 0.0
    repeat_need_strength: float = 0.0
    review_depth_proxy: float = 0.0
    price_ladder_strength: float = 0.0
    listing_density: float = 0.0
    mid_tier_survival_signal: float = 0.0
    competition_crowding: float = 0.0
    simplicity: float = 0.0
    margin_viability: float = 0.0
    fragility_risk: float = 0.0
    return_risk: float = 0.0
    manufacturability: float = 0.0
    clear_angle_exists: float = 0.0
    tool_gap_signal: float = 0.0
    improvement_room: float = 0.0
    competitor_positioning_gap: float = 0.0
    competitor_links: List[str] = field(default_factory=list)
    why_fit: str = ''
    scores: Dict[str, float] = field(default_factory=dict)
    sales_range: str = ''
    evidence_grade: str = ''
    recommendation: str = ''
    novelty_status: str = 'new'
    dedupe_key: str = ''
    dedupe_reason: str = ''


def hard_filter(c: Candidate) -> bool:
    return any([c.ingestible, c.regulated, c.body_contact_formula, c.brand_risk, c.excluded])


def score_candidate(c: Candidate) -> Candidate:
    demand = (c.trend_strength + c.search_intent_strength + c.customer_pain_clarity + c.repeat_need_strength) / 4 * 100
    proxy = (c.review_depth_proxy + c.price_ladder_strength + c.listing_density + c.mid_tier_survival_signal) / 4 * 100
    survivability = ((1 - c.competition_crowding) + c.mid_tier_survival_signal + c.clear_angle_exists + c.competitor_positioning_gap) / 4 * 100
    simplicity = (c.simplicity + c.manufacturability + (1 - c.fragility_risk) + (1 - c.return_risk)) / 4 * 100
    margin = c.margin_viability * 100
    differentiation = (c.clear_angle_exists + c.tool_gap_signal + c.improvement_room + c.competitor_positioning_gap) / 4 * 100

    total = demand*0.25 + proxy*0.20 + survivability*0.20 + simplicity*0.15 + margin*0.10 + differentiation*0.10

    penalty = 0
    if c.competition_crowding > 0.75:
        penalty += 8
    if c.return_risk > 0.7:
        penalty += 5
    if c.fragility_risk > 0.6:
        penalty += 4
    total = max(0, total - penalty)

    c.scores = {
        'demand_score': round(demand, 1),
        'proxy_sales_score': round(proxy, 1),
        'competition_survivability_score': round(survivability, 1),
        'simplicity_score': round(simplicity, 1),
        'margin_score': round(margin, 1),
        'differentiation_score': round(differentiation, 1),
        'total_score': round(total, 1),
    }

    if hard_filter(c):
        c.evidence_grade = 'C'
        c.recommendation = 'reject'
        c.sales_range = '0-10/day'
        return c

    if proxy >= 75 and survivability >= 60:
        c.sales_range = '80-150/day'
    elif proxy >= 55 and survivability >= 50:
        c.sales_range = '30-80/day'
    elif proxy >= 40:
        c.sales_range = '10-30/day'
    else:
        c.sales_range = '0-10/day'

    if total >= 75:
        c.recommendation = 'pursue'
    elif total >= 60:
        c.recommendation = 'validate'
    elif total >= 45:
        c.recommendation = 'test'
    else:
        c.recommendation = 'reject'

    if total >= 70 and proxy >= 55:
        c.evidence_grade = 'A'
    elif total >= 50:
        c.evidence_grade = 'B'
    else:
        c.evidence_grade = 'C'
    return c


def load_state():
    if STATE.exists():
        return json.loads(STATE.read_text())
    return {'recent_products': [], 'recent_keys': [], 'runs': []}


def save_state(state):
    STATE.write_text(json.dumps(state, ensure_ascii=False, indent=2))


def slugify(text: str) -> str:
    text = re.sub(r'[^a-z0-9]+', '-', text.lower()).strip('-')
    return text or 'candidate'


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        if value is None or value == '':
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def _safe_bool(value: Any, default: bool = False) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {'1', 'true', 'yes', 'y'}:
            return True
        if normalized in {'0', 'false', 'no', 'n'}:
            return False
    return default


def normalize_title_for_dedupe(text: str) -> str:
    text = text.lower()
    text = re.sub(r'\b\d+\s*(pack|pcs|piece|pieces|count)\b', ' ', text)
    text = re.sub(r'\b(extra large|large|medium|small|black|white|gray|grey|clear|natural)\b', ' ', text)
    text = re.sub(r'[^a-z0-9]+', ' ', text)
    tokens = [t for t in text.split() if t not in {
        'for','and','with','the','pack','pcs','piece','pieces','organizer','storage','tray','box','set','kitchen','bathroom','office','bedroom'
    }]
    return ' '.join(tokens)


def infer_family_key(product_name: str, sub_niche: str, competitor_links: List[str]) -> str:
    base = normalize_title_for_dedupe(product_name)
    family_patterns = [
        'drawer divider', 'silverware organizer', 'under sink organizer', 'cable management box', 'drawer organizer', 'clear drawer'
    ]
    family_prefix = ''
    for pattern in family_patterns:
        if all(part in base for part in pattern.split()):
            family_prefix = pattern.replace(' ', '-')
            break
    if not family_prefix:
        family_prefix = slugify(sub_niche or product_name)
    meaningful = [
        t for t in base.split()
        if t not in {'adjustable', 'expandable', 'pull', 'out', 'clear', 'plastic', 'bamboo', 'kitchen', 'bathroom', 'office', 'pack'}
    ]
    core = '-'.join(meaningful[:3]) if meaningful else family_prefix
    return f'{family_prefix}::{core}'


def dedupe_same_run(candidates: List[Candidate]) -> List[Candidate]:
    grouped: Dict[str, Candidate] = {}
    for c in candidates:
        c.dedupe_key = infer_family_key(c.product_name, c.sub_niche, c.competitor_links)
        existing = grouped.get(c.dedupe_key)
        if not existing:
            grouped[c.dedupe_key] = c
            c.dedupe_reason = 'kept-best-in-family'
            continue
        current_score = c.scores.get('total_score', 0)
        existing_score = existing.scores.get('total_score', 0)
        if current_score > existing_score:
            existing.novelty_status = 'same-run-family-suppressed'
            existing.dedupe_reason = f'replaced-by-higher-score:{c.dedupe_key}'
            c.dedupe_reason = 'kept-best-in-family'
            grouped[c.dedupe_key] = c
        else:
            c.novelty_status = 'same-run-family-suppressed'
            c.dedupe_reason = f'lower-score-same-family:{c.dedupe_key}'
    return list(grouped.values())


def load_daily_recent_keys() -> set[str]:
    daily_state = ROOT / '.state' / 'product-selection-daily-report.json'
    if not daily_state.exists():
        return set()
    try:
        payload = json.loads(daily_state.read_text())
    except Exception:
        return set()
    recent = payload.get('recentProducts', []) or []
    return {slugify(x) for x in recent if isinstance(x, str)}


def novelty_check(candidates: List[Candidate], state: dict) -> List[Candidate]:
    recent_products = set(state.get('recent_products', []))
    recent_keys = set(state.get('recent_keys', []))
    daily_recent_keys = load_daily_recent_keys()
    kept: List[Candidate] = []
    for c in candidates:
        product_slug = slugify(c.product_name)
        family_key = c.dedupe_key or infer_family_key(c.product_name, c.sub_niche, c.competitor_links)
        if c.product_name in recent_products or product_slug in daily_recent_keys:
            c.novelty_status = 'repeat-suppressed'
            c.dedupe_reason = 'matched-recent-product'
        elif family_key in recent_keys:
            c.novelty_status = 'family-repeat-suppressed'
            c.dedupe_reason = 'matched-recent-family'
        else:
            c.novelty_status = 'new'
            if not c.dedupe_reason:
                c.dedupe_reason = 'new-family'
        if c.novelty_status in ('repeat-suppressed', 'family-repeat-suppressed') and c.recommendation not in ('pursue',):
            continue
        kept.append(c)
    return kept


def normalize_raw_candidate(raw: Dict[str, Any]) -> Candidate:
    demand = raw.get('demand_features', {})
    marketplace = raw.get('marketplace_features', {})
    business = raw.get('business_features', {})
    differentiation = raw.get('differentiation_features', {})
    flags = raw.get('category_flags', {})

    product_name = raw.get('product_name') or raw.get('entity') or raw.get('query') or 'Unnamed Candidate'
    candidate_id = raw.get('candidate_id') or slugify(product_name)

    return Candidate(
        candidate_id=candidate_id,
        product_name=product_name,
        sub_niche=raw.get('sub_niche', ''),
        source_mix=raw.get('source_mix', []),
        excluded=_safe_bool(flags.get('excluded', raw.get('excluded', False))),
        brand_risk=_safe_bool(flags.get('brand_risk', raw.get('brand_risk', False))),
        regulated=_safe_bool(flags.get('regulated', raw.get('regulated', False))),
        body_contact_formula=_safe_bool(flags.get('body_contact_formula', raw.get('body_contact_formula', False))),
        ingestible=_safe_bool(flags.get('ingestible', raw.get('ingestible', False))),
        trend_strength=_safe_float(demand.get('trend_strength', raw.get('trend_strength', 0.0))),
        search_intent_strength=_safe_float(demand.get('search_intent_strength', raw.get('search_intent_strength', 0.0))),
        customer_pain_clarity=_safe_float(demand.get('customer_pain_clarity', raw.get('customer_pain_clarity', 0.0))),
        repeat_need_strength=_safe_float(demand.get('repeat_need_strength', raw.get('repeat_need_strength', 0.0))),
        review_depth_proxy=_safe_float(marketplace.get('review_depth_proxy', raw.get('review_depth_proxy', 0.0))),
        price_ladder_strength=_safe_float(marketplace.get('price_ladder_strength', raw.get('price_ladder_strength', 0.0))),
        listing_density=_safe_float(marketplace.get('listing_density', raw.get('listing_density', 0.0))),
        mid_tier_survival_signal=_safe_float(marketplace.get('mid_tier_survival_signal', raw.get('mid_tier_survival_signal', 0.0))),
        competition_crowding=_safe_float(marketplace.get('competition_crowding', raw.get('competition_crowding', 0.0))),
        simplicity=_safe_float(business.get('simplicity', raw.get('simplicity', 0.0))),
        margin_viability=_safe_float(business.get('margin_viability', raw.get('margin_viability', 0.0))),
        fragility_risk=_safe_float(business.get('fragility_risk', raw.get('fragility_risk', 0.0))),
        return_risk=_safe_float(business.get('return_risk', raw.get('return_risk', 0.0))),
        manufacturability=_safe_float(business.get('manufacturability', raw.get('manufacturability', 0.0))),
        clear_angle_exists=_safe_float(differentiation.get('clear_angle_exists', raw.get('clear_angle_exists', 0.0))),
        tool_gap_signal=_safe_float(differentiation.get('tool_gap_signal', raw.get('tool_gap_signal', 0.0))),
        improvement_room=_safe_float(differentiation.get('improvement_room', raw.get('improvement_room', 0.0))),
        competitor_positioning_gap=_safe_float(differentiation.get('competitor_positioning_gap', raw.get('competitor_positioning_gap', 0.0))),
        competitor_links=raw.get('competitor_links', []),
        why_fit=raw.get('why_fit', ''),
    )


def load_raw_input_candidates() -> List[Candidate]:
    if not RAW_INPUT.exists():
        return []
    payload = json.loads(RAW_INPUT.read_text())
    raw_candidates = payload.get('candidates', payload if isinstance(payload, list) else [])
    if not isinstance(raw_candidates, list):
        return []
    return [normalize_raw_candidate(item) for item in raw_candidates if isinstance(item, dict)]


def build_demo_candidates() -> List[Candidate]:
    raw = [
        Candidate('drawer-organizer','Drawer Organizer','adjustable / stackable', ['amazon_public','customer_voice'], trend_strength=0.7, search_intent_strength=0.7, customer_pain_clarity=0.9, repeat_need_strength=0.8, review_depth_proxy=0.7, price_ladder_strength=0.6, listing_density=0.6, mid_tier_survival_signal=0.7, competition_crowding=0.4, simplicity=0.9, margin_viability=0.6, fragility_risk=0.1, return_risk=0.2, manufacturability=0.9, clear_angle_exists=0.8, tool_gap_signal=0.8, improvement_room=0.9, competitor_positioning_gap=0.7, competitor_links=['https://www.amazon.com/s?k=drawer+organizer+set'], why_fit='Clear pain point, strong simplicity, room for modular differentiation'),
        Candidate('car-mount','Car Phone Mount','vehicle-fit / no-blocking-controls', ['amazon_public','customer_voice','competitor_page'], trend_strength=0.7, search_intent_strength=0.8, customer_pain_clarity=0.9, repeat_need_strength=0.7, review_depth_proxy=0.8, price_ladder_strength=0.7, listing_density=0.8, mid_tier_survival_signal=0.6, competition_crowding=0.7, simplicity=0.8, margin_viability=0.6, fragility_risk=0.1, return_risk=0.3, manufacturability=0.9, clear_angle_exists=0.8, tool_gap_signal=0.7, improvement_room=0.8, competitor_positioning_gap=0.8, competitor_links=['https://www.amazon.com/s?k=car+phone+mount'], why_fit='Demand is real; differentiated route is fit and control-area-safe designs'),
        Candidate('toe-spacers','Toe Spacers','professional foot-function direction', ['amazon_public','customer_voice','competitor_page'], trend_strength=0.8, search_intent_strength=0.8, customer_pain_clarity=0.8, repeat_need_strength=0.6, review_depth_proxy=0.8, price_ladder_strength=0.5, listing_density=0.8, mid_tier_survival_signal=0.5, competition_crowding=0.8, simplicity=0.9, margin_viability=0.5, fragility_risk=0.05, return_risk=0.2, manufacturability=0.9, clear_angle_exists=0.7, tool_gap_signal=0.5, improvement_room=0.6, competitor_positioning_gap=0.7, competitor_links=['https://www.amazon.com/s?k=toe+spacers'], why_fit='Real demand but needs trust-driven premium sub-angle'),
    ]
    return raw


def run():
    state = load_state()
    input_candidates = load_raw_input_candidates()
    using_real_input = bool(input_candidates)
    scored_candidates = [score_candidate(c) for c in (input_candidates or build_demo_candidates())]
    pre_dedupe_count = len(scored_candidates)
    family_deduped = dedupe_same_run(scored_candidates)
    candidates = novelty_check(family_deduped, state)
    candidates.sort(key=lambda x: x.scores['total_score'], reverse=True)
    result = {
        'run_at': datetime.now().astimezone().isoformat(),
        'input_mode': 'raw_input' if using_real_input else 'demo_fallback',
        'input_path': str(RAW_INPUT),
        'pre_dedupe_count': pre_dedupe_count,
        'post_family_dedupe_count': len(family_deduped),
        'candidate_count': len(candidates),
        'candidates': [asdict(c) for c in candidates],
    }
    (OUT/'latest.json').write_text(json.dumps(result, ensure_ascii=False, indent=2))
    state['recent_products'] = [c.product_name for c in candidates[:20]]
    state['recent_keys'] = [c.dedupe_key for c in candidates[:20]]
    state['runs'].append({
        'run_at': result['run_at'],
        'count': len(candidates),
        'input_mode': result['input_mode'],
        'pre_dedupe_count': pre_dedupe_count,
        'post_family_dedupe_count': len(family_deduped),
    })
    save_state(state)
    print(OUT/'latest.json')

if __name__ == '__main__':
    run()
