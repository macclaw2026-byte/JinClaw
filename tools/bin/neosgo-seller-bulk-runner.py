#!/usr/bin/env python3
import argparse
import json, uuid, time, traceback
from pathlib import Path
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError

SECRET_PATH = Path.home() / '.openclaw' / 'secrets' / 'neosgo-seller.env'
STATE_PATH = Path.home() / '.openclaw' / 'workspace' / 'data' / 'neosgo-seller-bulk-state.json'

CATEGORY_MAP = {
    'bathroom lighting': 'cml8b5hia0003t8jmxoxvko98',
    'bedroom lighting': 'cml8b5hhz0001t8jmowuzbnnl',
    'living room lighting': 'cml8b5hhz0001t8jmowuzbnnl',
    'dining room lighting': 'cml8b5hhz0001t8jmowuzbnnl',
    'outdoor lighting': 'cml8b5hia0003t8jmxoxvko98',
}
SHIPPING_TEMPLATE_ID = 'cmmu2i7uw0001yp5x1s8i1x0g'
DEFAULT_QTY = 24
DEFAULT_BRAND = 'NEOSGO'
PRICE_MARKUP_USD = 25
WAREHOUSE = {
    'warehouseType': 'SELLER_WAREHOUSE',
    'warehouseZip': '02865',
    'warehouseCity': 'Lincoln',
    'warehouseState': 'RI'
}


def parse_args():
    parser = argparse.ArgumentParser(description='Bulk import, patch, and submit Neosgo seller listings.')
    parser.add_argument('--limit', type=int, default=10, help='Maximum number of importable candidates to process.')
    parser.add_argument('--page-size', type=int, default=100, help='Number of GIGA candidates to fetch per page.')
    parser.add_argument('--max-pages', type=int, default=10, help='Maximum number of candidate pages to scan.')
    parser.add_argument('--sku', action='append', dest='skus', help='Specific SKU(s) to process. Can be passed multiple times.')
    parser.add_argument('--no-submit', action='store_true', help='Stop after readiness check; do not submit even if ready.')
    parser.add_argument('--sleep-seconds', type=float, default=1.0, help='Pause between processed SKUs.')
    return parser.parse_args()


def load_env(path):
    env = {}
    for line in path.read_text(encoding='utf-8').splitlines():
        line = line.strip()
        if not line or line.startswith('#') or '=' not in line:
            continue
        k, v = line.split('=', 1)
        env[k.strip()] = v.strip()
    return env


def request(method, base, token, path, body=None, idempotency=False):
    data = None if body is None else json.dumps(body).encode('utf-8')
    headers = {
        'Authorization': f'Bearer {token}',
        'Content-Type': 'application/json',
        'Accept': 'application/json',
        'User-Agent': 'OpenClaw-Neosgo-Seller-BulkRunner/1.0',
    }
    if idempotency:
        headers['Idempotency-Key'] = str(uuid.uuid4())
    req = Request(base.rstrip('/') + path, data=data, headers=headers, method=method)
    with urlopen(req, timeout=60) as resp:
        raw = resp.read().decode('utf-8', 'replace')
        return json.loads(raw)


def safe_request(*args, **kwargs):
    try:
        return {'ok': True, 'resp': request(*args, **kwargs)}
    except HTTPError as e:
        raw = e.read().decode('utf-8', 'replace')
        return {'ok': False, 'error': {'http_status': e.code, 'body': raw}}
    except URLError as e:
        return {'ok': False, 'error': {'network_error': str(e)}}
    except Exception as e:
        return {'ok': False, 'error': {'exception': repr(e)}}


def write_state(state):
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    STATE_PATH.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding='utf-8')


def pick_category_id(listing, candidate):
    category = listing.get('category') or {}
    if isinstance(category, dict) and category.get('id'):
        return category['id']
    return derive_category_id(candidate.get('category'))


def pick_quantity_available(listing):
    inventory = listing.get('inventory') or {}
    if isinstance(inventory, dict) and inventory.get('quantityAvailable'):
        return inventory['quantityAvailable']
    return DEFAULT_QTY


def pick_submission_price(listing):
    pricing = listing.get('pricing') or {}
    raw_price = (
        listing.get('basePrice')
        or listing.get('price')
        or (pricing.get('retailUnitPrice') if isinstance(pricing, dict) else None)
        or (pricing.get('platformUnitCost') if isinstance(pricing, dict) else None)
    )
    try:
        base = float(raw_price)
    except (TypeError, ValueError):
        base = 0.0
    return round(base + PRICE_MARKUP_USD, 2)


def pick_description(listing, candidate):
    description = listing.get('description')
    if isinstance(description, str) and description.strip():
        return description
    title = (
        listing.get('title')
        or listing.get('name')
        or candidate.get('productName')
        or candidate.get('sku')
        or 'Neosgo imported listing'
    )
    return f'<p>{title}</p>'


def extract_product_ids(imported):
    product_ids = []
    if not isinstance(imported, dict):
        return product_ids
    data = imported.get('data')
    if isinstance(data, dict):
        for key in ['productIds', 'listingIds', 'ids']:
            if isinstance(data.get(key), list):
                return data[key]
        results = data.get('results')
        if isinstance(results, list):
            for result in results:
                if isinstance(result, dict) and result.get('productId'):
                    product_ids.append(result['productId'])
            if product_ids:
                return product_ids
    for key in ['productIds', 'listingIds', 'ids']:
        if isinstance(imported.get(key), list):
            return imported[key]
    return product_ids


def fetch_candidates(base, token, page_size, max_pages):
    candidates = []
    page = 1
    while page <= max_pages:
        payload = request('GET', base, token, f'/api/automation/seller/giga/candidates?page={page}&pageSize={page_size}')
        data = payload.get('data') or {}
        items = data.get('candidates') or []
        if not items:
            break
        candidates.extend(items)
        if not data.get('hasNextPage'):
            break
        page += 1
    return candidates


def derive_category_id(category_name):
    return CATEGORY_MAP.get((category_name or '').strip().lower(), 'cml8b5hhz0001t8jmowuzbnnl')


def derive_packing_units(listing):
    length = float(listing.get('dimensions', {}).get('length') or 18)
    width = float(listing.get('dimensions', {}).get('width') or 18)
    height = float(listing.get('dimensions', {}).get('height') or 12)
    weight = float(listing.get('dimensions', {}).get('weight') or 8)
    return [{
        'unitType': 'BOX',
        'length': round(length, 2),
        'width': round(width, 2),
        'height': round(height, 2),
        'weight': round(weight, 2),
        'piecesPerUnit': 1,
        'unitQuantity': 1,
    }]


def main():
    args = parse_args()
    env = load_env(SECRET_PATH)
    base = env['NEOSGO_SELLER_API_BASE_URL']
    token = env['NEOSGO_SELLER_AUTOMATION_KEY']
    state = {
        'startedAt': time.time(),
        'args': {
            'limit': args.limit,
            'page_size': args.page_size,
            'max_pages': args.max_pages,
            'skus': args.skus or [],
            'no_submit': args.no_submit,
            'sleep_seconds': args.sleep_seconds,
        },
        'processed': [],
    }
    write_state(state)

    candidates = fetch_candidates(base, token, args.page_size, args.max_pages)
    todo = [c for c in candidates if c.get('canImport')]
    if args.skus:
        requested = set(args.skus)
        todo = [c for c in todo if c.get('sku') in requested]

    for c in todo[:args.limit]:
        sku = c['sku']
        row = {'sku': sku, 'candidateStatus': c.get('candidateStatus')}
        try:
            imp = safe_request('POST', base, token, '/api/automation/seller/giga/import', {'skus': [sku]}, idempotency=True)
            row['import'] = imp
            if not imp['ok']:
                state['processed'].append(row)
                write_state(state)
                continue
            imported = imp['resp']
            product_ids = extract_product_ids(imported)
            if not product_ids:
                q = request('GET', base, token, '/api/automation/seller/listings?status=DRAFT&page=1&pageSize=100')
                items = q['data']['items']
                matches = [x for x in items if x.get('sku') == sku]
                if matches:
                    product_ids = [matches[0]['id']]
            if not product_ids:
                row['error'] = 'imported product id not found'
                state['processed'].append(row)
                write_state(state)
                continue
            product_id = product_ids[0]
            row['productId'] = product_id
            detail = request('GET', base, token, f'/api/automation/seller/listings/{product_id}')
            listing = detail['data']['listing'] if 'listing' in detail.get('data', {}) else detail['data']
            payload = {
                'brand': listing.get('brand') or DEFAULT_BRAND,
                'categoryId': pick_category_id(listing, c),
                'basePrice': pick_submission_price(listing),
                'description': pick_description(listing, c),
                'shippingTemplateId': listing.get('shippingTemplateId') or SHIPPING_TEMPLATE_ID,
                'quantityAvailable': pick_quantity_available(listing),
                'packingUnits': listing.get('packingUnits') or derive_packing_units(listing),
                **WAREHOUSE,
            }
            row['payload'] = payload
            patch = safe_request('PATCH', base, token, f'/api/automation/seller/listings/{product_id}', payload, idempotency=True)
            row['patch'] = patch
            if not patch['ok']:
                state['processed'].append(row)
                write_state(state)
                continue
            ready = safe_request('GET', base, token, f'/api/automation/seller/listings/{product_id}/readiness')
            row['readiness'] = ready
            can_submit = False
            if ready['ok']:
                can_submit = ready['resp'].get('data', {}).get('submissionReadiness', {}).get('canSubmit', False)
            if can_submit and not args.no_submit:
                submit = safe_request('POST', base, token, f'/api/automation/seller/listings/{product_id}/submit', {}, idempotency=True)
                row['submit'] = submit
        except Exception as exc:
            row['exception'] = repr(exc)
            row['traceback'] = traceback.format_exc()
        state['processed'].append(row)
        state['processedCount'] = len(state['processed'])
        state['successCount'] = sum(1 for item in state['processed'] if item.get('submit', {}).get('ok'))
        state['failureCount'] = state['processedCount'] - state['successCount']
        write_state(state)
        time.sleep(args.sleep_seconds)

    state['finishedAt'] = time.time()
    state['processedCount'] = len(state['processed'])
    state['successCount'] = sum(1 for item in state['processed'] if item.get('submit', {}).get('ok'))
    state['failureCount'] = state['processedCount'] - state['successCount']
    write_state(state)
    print(json.dumps(state, ensure_ascii=False, indent=2))

if __name__ == '__main__':
    main()
