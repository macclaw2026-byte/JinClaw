#!/usr/bin/env python3
from __future__ import annotations

import json
import re
import subprocess
import sys
from datetime import datetime
from hashlib import sha1
from pathlib import Path
from urllib.parse import quote_plus, unquote, urlparse, parse_qs

ROOT = Path('/Users/mac_claw/.openclaw/workspace')
CRAWL4AI = ROOT / 'tools' / 'bin' / 'crawl4ai'
OUT_DIR = ROOT / 'data' / 'amazon-premium-wholesale'
OUT_DIR.mkdir(parents=True, exist_ok=True)
RAW_OUT = OUT_DIR / 'raw_candidates.json'

DEFAULT_QUERIES = [
    'adjustable drawer organizer',
    'drawer dividers adjustable',
    'expandable silverware organizer',
    'clear drawer organizer trays',
    'under sink organizer pull out',
    'cable management box organizer',
]

BRAND_RISK_TERMS = {
    'oxo', 'simplehuman', 'rubbermaid', 'nike', 'apple', 'sony', 'pokemon', 'disney', 'dyson', 'shark'
}

MIN_CANDIDATES = 20
MIN_FIELD_COMPLETENESS = 0.80
MIN_CLEAN_DP_LINK_RATIO = 0.85
MAX_BRAND_RISK_RATIO = 0.15
MAX_PER_QUERY = 8
CRAWL_TIMEOUT_SECONDS = 120


def _looks_like_amazon_error(markdown: str) -> bool:
    sample = (markdown or '')[:4000].lower()
    return any(
        marker in sample
        for marker in [
            'sorry! something went wrong on our end',
            'dogs of amazon',
            'ref=cs_503',
            '/images/g/01/error/',
            'robot check',
            'enter the characters you see below',
        ]
    )


def _crawl_command_variants(url: str, query: str) -> list[list[str]]:
    session_seed = sha1(f'{query}:{datetime.now().date().isoformat()}'.encode('utf-8')).hexdigest()[:12]
    hardened_browser = 'user_agent_mode=random,java_script_enabled=true,text_mode=false'
    hardened_crawler = (
        'wait_until=domcontentloaded,'
        'simulate_user=true,'
        'override_navigator=true,'
        'magic=true,'
        'delay_before_return_html=2,'
        'scan_full_page=true,'
        'page_timeout=120000,'
        f'session_id=amazon-public-{session_seed}'
    )
    medium_crawler = (
        'wait_until=load,'
        'simulate_user=true,'
        'override_navigator=true,'
        'delay_before_return_html=1.5,'
        'page_timeout=90000,'
        f'session_id=amazon-public-{session_seed}'
    )
    return [
        [str(CRAWL4AI), url, '-o', 'markdown', '--bypass-cache', '-b', hardened_browser, '-c', hardened_crawler],
        [str(CRAWL4AI), url, '-o', 'markdown', '--bypass-cache', '-b', 'user_agent_mode=random', '-c', medium_crawler],
        [str(CRAWL4AI), url, '-o', 'markdown', '--bypass-cache', '-c', 'wait_until=load'],
        [str(CRAWL4AI), url, '-o', 'markdown'],
    ]


def run_crawl(query: str) -> str:
    url = f'https://www.amazon.com/s?k={quote_plus(query)}'
    last_error = None
    for command in _crawl_command_variants(url, query):
        try:
            proc = subprocess.run(
                command,
                capture_output=True,
                text=True,
                check=True,
                timeout=CRAWL_TIMEOUT_SECONDS,
            )
        except subprocess.TimeoutExpired as exc:
            last_error = RuntimeError(f'crawl4ai timed out for query: {query} via {command}')
            continue
        except subprocess.CalledProcessError as exc:
            last_error = exc
            continue
        output = proc.stdout.strip()
        if len(output) <= 1000:
            last_error = RuntimeError(f'crawl4ai returned undersized output for query: {query}')
            continue
        if _looks_like_amazon_error(output):
            last_error = RuntimeError(f'crawl4ai returned Amazon error page for query: {query}')
            continue
        return output
    if last_error:
        raise last_error
    raise RuntimeError(f'crawl4ai returned no usable output for query: {query}')


def normalize_amazon_url(url: str) -> str:
    url = url.strip()
    if not url:
        return url
    if url.startswith('https://www.amazon.com/sspa/click'):
        parsed = urlparse(url)
        inner = parse_qs(parsed.query).get('url', [None])[0]
        if inner:
            inner = unquote(inner)
            if inner.startswith('/'):
                inner = 'https://www.amazon.com' + inner
            url = inner
    url = unquote(url)
    url = url.replace('https://www.amazon.comhttps://www.amazon.com', 'https://www.amazon.com')
    parsed = urlparse(url)
    path = parsed.path
    m = re.search(r'(/(?:[^/]+/)?dp/[A-Z0-9]{10})', path)
    if m:
        return f'https://www.amazon.com{m.group(1)}'
    return f'https://www.amazon.com{path}' if path.startswith('/') else url.split('?')[0]


def parse_price(text: str) -> str | None:
    prices = re.findall(r'\$(\d+(?:\.\d{2})?)', text)
    if not prices:
        return None
    for candidate in prices:
        try:
            value = float(candidate)
        except ValueError:
            continue
        if 8 <= value <= 80:
            return f'${candidate}'
    return f'${prices[0]}'


def parse_rating(text: str) -> str | None:
    m = re.search(r'(\d\.\d)\[ _\1 out of 5 stars_', text)
    return m.group(1) if m else None


def parse_reviews(text: str) -> str | None:
    m = re.search(r'\[\((\d+(?:\.\d+)?[KM]?)\) \]', text)
    return m.group(1) if m else None


def parse_bought(text: str) -> str | None:
    m = re.search(r'(\d+(?:\.\d+)?[KM]?\+ bought in past month)', text)
    return m.group(1) if m else None


def is_probably_sponsored(title: str, link: str, block: str) -> bool:
    if '/sspa/' in link or 'sspa/click' in link:
        return True
    first_chunk = block[:220].lower()
    if 'sponsored' in first_chunk:
        return True
    if title.lower().startswith('sponsored ad'):
        return True
    return False


def detect_brand_risk(title: str) -> bool:
    low = title.lower()
    return any(term in low for term in BRAND_RISK_TERMS)


def score_from_public_signals(block: str) -> dict:
    rating = parse_rating(block)
    reviews = parse_reviews(block)
    bought = parse_bought(block)
    price = parse_price(block) or ''

    review_depth = 0.35
    if reviews:
        if 'K' in reviews:
            review_depth = 0.8
        else:
            try:
                review_depth = 0.7 if int(reviews.replace(',', '')) >= 500 else 0.5
            except Exception:
                pass

    search_intent = 0.72
    customer_pain = 0.82
    repeat_need = 0.76
    trend_strength = 0.62
    listing_density = 0.75
    mid_tier_survival = 0.55
    competition_crowding = 0.72
    simplicity = 0.88
    margin_viability = 0.58
    fragility_risk = 0.1
    return_risk = 0.22
    manufacturability = 0.9
    clear_angle = 0.62
    tool_gap = 0.45
    improvement_room = 0.64
    competitor_gap = 0.48

    if bought and any(token in bought for token in ['30K+', '20K+', '8K+', '6K+', '4K+', '3K+', '2K+', '1K+']):
        review_depth = max(review_depth, 0.78)
        trend_strength = 0.7
    if price:
        try:
            p = float(price.replace('$', ''))
            if 14 <= p <= 35:
                margin_viability = 0.62
            elif p < 8:
                margin_viability = 0.42
        except Exception:
            pass
    if rating:
        try:
            r = float(rating)
            if r >= 4.6:
                mid_tier_survival = 0.62
            elif r < 4.4:
                mid_tier_survival = 0.48
        except Exception:
            pass

    return {
        'demand_features': {
            'trend_strength': trend_strength,
            'search_intent_strength': search_intent,
            'customer_pain_clarity': customer_pain,
            'repeat_need_strength': repeat_need,
        },
        'marketplace_features': {
            'review_depth_proxy': review_depth,
            'price_ladder_strength': 0.62,
            'listing_density': listing_density,
            'mid_tier_survival_signal': mid_tier_survival,
            'competition_crowding': competition_crowding,
        },
        'business_features': {
            'simplicity': simplicity,
            'margin_viability': margin_viability,
            'fragility_risk': fragility_risk,
            'return_risk': return_risk,
            'manufacturability': manufacturability,
        },
        'differentiation_features': {
            'clear_angle_exists': clear_angle,
            'tool_gap_signal': tool_gap,
            'improvement_room': improvement_room,
            'competitor_positioning_gap': competitor_gap,
        },
    }


def extract_candidates(markdown: str, query: str, limit: int = MAX_PER_QUERY) -> list[dict]:
    chunks = re.split(r'\n## \[', markdown)
    candidates = []
    for chunk in chunks[1:]:
        head, _, rest = chunk.partition(')')
        title_match = re.match(r'([^\]]+)\]\((https://www\.amazon\.com/[^\s)]+)', head)
        if not title_match:
            continue
        title = title_match.group(1).strip()
        raw_link = title_match.group(2)
        link = normalize_amazon_url(raw_link)
        body = rest[:1500]
        sponsored = is_probably_sponsored(title, raw_link, body)
        brand_risk = detect_brand_risk(title)
        rating = parse_rating(body)
        reviews = parse_reviews(body)
        price = parse_price(body)
        bought = parse_bought(body)
        if sponsored:
            continue
        if brand_risk:
            continue
        if not (title and link and '/dp/' in link):
            continue
        row = {
            'candidate_id': re.sub(r'[^a-z0-9]+', '-', title.lower()).strip('-')[:80],
            'product_name': title,
            'sub_niche': query,
            'query_terms': [query],
            'source_mix': ['amazon_public'],
            'category_flags': {
                'excluded': False,
                'brand_risk': brand_risk,
                'regulated': False,
                'body_contact_formula': False,
                'ingestible': False,
            },
            'public_fields': {
                'query': query,
                'title': title,
                'price': price,
                'rating': rating,
                'review_count': reviews,
                'bought_past_month': bought,
                'link': link,
                'source_tool': 'crawl4ai',
                'confidence': 'medium',
            },
            'competitor_links': [link],
            'why_fit': f'Public Amazon result for query: {query}',
        }
        row.update(score_from_public_signals(body))
        candidates.append(row)
        if len(candidates) >= limit:
            break
    return candidates


def dedupe_candidates(candidates: list[dict]) -> list[dict]:
    deduped = []
    seen = set()
    for item in candidates:
        key = item['public_fields'].get('link') or item.get('candidate_id')
        if key in seen:
            continue
        seen.add(key)
        deduped.append(item)
    return deduped


def calc_quality_gate(candidates: list[dict]) -> dict:
    total = len(candidates)
    if total == 0:
        return {
            'passed': False,
            'candidate_count': 0,
            'field_completeness': 0.0,
            'clean_dp_link_ratio': 0.0,
            'brand_risk_ratio': 0.0,
            'reasons': ['no_candidates'],
        }
    complete = 0
    clean_dp = 0
    brand_risk = 0
    for item in candidates:
        pf = item.get('public_fields', {})
        required = [pf.get('title'), pf.get('price'), pf.get('rating'), pf.get('review_count'), pf.get('link')]
        if all(required):
            complete += 1
        if isinstance(pf.get('link'), str) and '/dp/' in pf.get('link', '') and 'sspa/click' not in pf.get('link', ''):
            clean_dp += 1
        if item.get('category_flags', {}).get('brand_risk'):
            brand_risk += 1
    field_completeness = round(complete / total, 3)
    clean_dp_ratio = round(clean_dp / total, 3)
    brand_risk_ratio = round(brand_risk / total, 3)
    reasons = []
    if total < MIN_CANDIDATES:
        reasons.append('candidate_count_below_threshold')
    if field_completeness < MIN_FIELD_COMPLETENESS:
        reasons.append('field_completeness_below_threshold')
    if clean_dp_ratio < MIN_CLEAN_DP_LINK_RATIO:
        reasons.append('clean_dp_link_ratio_below_threshold')
    if brand_risk_ratio > MAX_BRAND_RISK_RATIO:
        reasons.append('brand_risk_ratio_above_threshold')
    return {
        'passed': not reasons,
        'candidate_count': total,
        'field_completeness': field_completeness,
        'clean_dp_link_ratio': clean_dp_ratio,
        'brand_risk_ratio': brand_risk_ratio,
        'reasons': reasons,
        'thresholds': {
            'min_candidates': MIN_CANDIDATES,
            'min_field_completeness': MIN_FIELD_COMPLETENESS,
            'min_clean_dp_link_ratio': MIN_CLEAN_DP_LINK_RATIO,
            'max_brand_risk_ratio': MAX_BRAND_RISK_RATIO,
        }
    }


def main() -> int:
    queries = sys.argv[1:] or DEFAULT_QUERIES
    all_candidates = []
    per_query = {}
    query_errors = {}
    for query in queries:
        try:
            markdown = run_crawl(query)
            extracted = extract_candidates(markdown, query)
        except Exception as exc:
            extracted = []
            query_errors[query] = str(exc)
        per_query[query] = len(extracted)
        all_candidates.extend(extracted)

    all_candidates = dedupe_candidates(all_candidates)
    quality_gate = calc_quality_gate(all_candidates)
    payload = {
        'generated_at': datetime.now().astimezone().isoformat(),
        'queries': queries,
        'source_tool': 'crawl4ai',
        'confidence': 'medium',
        'candidate_count': len(all_candidates),
        'per_query_count': per_query,
        'query_errors': query_errors,
        'quality_gate': quality_gate,
        'candidates': all_candidates,
    }
    RAW_OUT.write_text(json.dumps(payload, ensure_ascii=False, indent=2))
    print(RAW_OUT)
    print(json.dumps({'candidate_count': len(all_candidates), 'queries': queries, 'per_query_count': per_query, 'query_errors': query_errors, 'quality_gate': quality_gate}, ensure_ascii=False))
    return 0 if quality_gate.get('passed') else 1


if __name__ == '__main__':
    raise SystemExit(main())
