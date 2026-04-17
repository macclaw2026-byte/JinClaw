#!/usr/bin/env python3
import argparse
import json, uuid, time, traceback, re
from datetime import datetime
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
    parser.add_argument('--batch-bias', default='balanced', help='Scheduler-provided batch bias for candidate ordering.')
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


def request(method, base, token, path, body=None, idempotency=False, timeout=60):
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
    with urlopen(req, timeout=timeout) as resp:
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


def is_timeout_result(result):
    if not isinstance(result, dict) or result.get('ok'):
        return False
    error = result.get('error') or {}
    joined = f"{error.get('network_error') or ''} {error.get('exception') or ''}".lower()
    return 'timed out' in joined or 'timeout' in joined


def request_with_retry(method, base, token, path, body=None, idempotency=False, attempts=3, sleep_seconds=1.5, timeout=60):
    last = None
    for attempt in range(1, attempts + 1):
        result = safe_request(method, base, token, path, body, idempotency=idempotency, timeout=timeout)
        if result.get('ok'):
            result['attempts'] = attempt
            return result
        last = result
        if not is_timeout_result(result) or attempt >= attempts:
            break
        time.sleep(sleep_seconds * attempt)
    if isinstance(last, dict):
        last['attempts'] = attempts
    return last


def extract_request_error_message(step, result):
    if not isinstance(result, dict) or result.get('ok'):
        return None
    error = result.get('error') or {}
    if not isinstance(error, dict):
        return f'{step} request failed'
    http_status = error.get('http_status')
    if http_status:
        return f'{step} http {http_status}'
    network_error = str(error.get('network_error') or '').strip()
    exception = str(error.get('exception') or '').strip()
    joined = f'{network_error} {exception}'.strip()
    if joined:
        return f'{step} request failed: {joined}'
    return f'{step} request failed'


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


def html_to_plain_text(value):
    if not isinstance(value, str):
        return ''
    text = value
    text = text.replace('<br>', '\n').replace('<br/>', '\n').replace('<br />', '\n')
    text = text.replace('</p>', '\n').replace('</div>', '\n').replace('</li>', '\n')
    import re
    text = re.sub(r'<[^>]+>', ' ', text)
    text = text.replace('&nbsp;', ' ').replace('&amp;', '&').replace('&lt;', '<').replace('&gt;', '>').replace('&quot;', '"').replace('&#39;', "'")
    text = re.sub(r'[ \t]+', ' ', text)
    text = re.sub(r'\n\s*\n+', '\n', text)
    return text.strip()


def pick_description(listing, candidate):
    # Hard rule: descriptions must always be persisted and submitted as plain text only.
    description = listing.get('description')
    if isinstance(description, str) and description.strip():
        cleaned = html_to_plain_text(description)
        if cleaned:
            return cleaned
    title = (
        listing.get('title')
        or listing.get('name')
        or candidate.get('productName')
        or candidate.get('sku')
        or 'Neosgo imported listing'
    )
    return html_to_plain_text(str(title))


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


def extract_import_failure_message(imported):
    if not isinstance(imported, dict):
        return None
    data = imported.get('data')
    if not isinstance(data, dict):
        return None
    results = data.get('results')
    if not isinstance(results, list):
        return None
    for result in results:
        if not isinstance(result, dict):
            continue
        if str(result.get('status') or '').strip().upper() != 'FAILED':
            continue
        message = str(result.get('message') or '').strip()
        if message:
            return message
    return None


def fetch_candidates(base, token, page_size, max_pages, target_skus=None):
    candidates = []
    wanted = {str(s).strip() for s in (target_skus or []) if str(s).strip()}
    page = 1
    while page <= max_pages:
        payload = request_with_retry('GET', base, token, f'/api/automation/seller/giga/candidates?page={page}&pageSize={page_size}', attempts=2, sleep_seconds=0.5, timeout=30)
        if not payload.get('ok'):
            break
        payload = payload['resp']
        data = payload.get('data') or {}
        items = data.get('candidates') or []
        if not items:
            break
        candidates.extend(items)
        if wanted:
            found = {str(item.get('sku') or '').strip() for item in candidates}
            if wanted.issubset(found):
                break
        if not data.get('hasNextPage'):
            break
        page += 1
    return candidates


def normalize_text(value):
    if value is None:
        return ''
    return str(value).strip().lower()


def _parse_candidate_timestamp(candidate):
    for key in ('updatedAt', 'candidateUpdatedAt', 'createdAt', 'candidateCreatedAt'):
        raw = str(candidate.get(key) or '').strip()
        if not raw:
            continue
        try:
            return datetime.fromisoformat(raw.replace('Z', '+00:00')).timestamp()
        except ValueError:
            continue
    return 0.0


def _candidate_priority_key(candidate, batch_bias):
    bias = str(batch_bias or '').strip().lower()
    recent_first = bias in {'repair_backpressure_batch', 'targeted_fix_batch'}
    timestamp_rank = -_parse_candidate_timestamp(candidate) if recent_first else 0.0
    return (
        timestamp_rank,
        str(candidate.get('candidateStatus') or ''),
        str(candidate.get('sku') or ''),
    )


def is_new_import_candidate(candidate):
    status_fields = [
        candidate.get('uploadStatus'),
        candidate.get('importStatus'),
        candidate.get('candidateStatus'),
        candidate.get('status'),
    ]
    normalized = {normalize_text(value) for value in status_fields if value is not None}
    return 'new import' in normalized or 'new_import' in normalized


def collect_candidate_status_snapshot(candidate):
    return {
        'uploadStatus': candidate.get('uploadStatus'),
        'importStatus': candidate.get('importStatus'),
        'candidateStatus': candidate.get('candidateStatus'),
        'status': candidate.get('status'),
    }


def evaluate_candidate_guards(candidate, draft_listing_skus):
    sku = str(candidate.get('sku') or '').strip()
    status_snapshot = collect_candidate_status_snapshot(candidate)
    is_new_import = is_new_import_candidate(candidate)
    draft_listing_exists = bool(sku) and sku in draft_listing_skus
    reasons = []
    if not candidate.get('canImport'):
        reasons.append('canImport=false')
    if not is_new_import:
        reasons.append('not-new-import')
    if draft_listing_exists:
        reasons.append('draft-listing-sku-exists')
    return {
        'sku': sku or None,
        'canImport': bool(candidate.get('canImport')),
        'isNewImport': is_new_import,
        'draftListingSkuExists': draft_listing_exists,
        'statusSnapshot': status_snapshot,
        'reasons': reasons,
    }


def fetch_draft_listing_skus(base, token, page_size=100, max_pages=20):
    skus = set()
    page = 1
    while page <= max_pages:
        payload = request_with_retry('GET', base, token, f'/api/automation/seller/listings?status=DRAFT&page={page}&pageSize={page_size}', attempts=2, sleep_seconds=0.5, timeout=30)
        if not payload.get('ok'):
            break
        payload = payload['resp']
        data = payload.get('data') or {}
        items = data.get('items') or []
        if not items:
            break
        for item in items:
            sku = item.get('sku')
            if sku:
                skus.add(str(sku).strip())
        if not data.get('hasNextPage'):
            break
        page += 1
    return skus


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


def _positive_number(value, default):
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return default
    return parsed if parsed > 0 else default


def normalize_packing_units(listing):
    units = listing.get('packingUnits') or []
    normalized = []
    if not isinstance(units, list) or not units:
        return derive_packing_units(listing)
    for unit in units:
        if not isinstance(unit, dict):
            continue
        normalized.append({
            'unitType': unit.get('unitType') or 'BOX',
            'length': round(_positive_number(unit.get('length'), 18), 2),
            'width': round(_positive_number(unit.get('width'), 18), 2),
            'height': round(_positive_number(unit.get('height'), 12), 2),
            'weight': round(_positive_number(unit.get('weight'), 8), 2),
            'piecesPerUnit': max(1, int(_positive_number(unit.get('piecesPerUnit'), 1))),
            'unitQuantity': max(1, int(_positive_number(unit.get('unitQuantity'), 1))),
        })
    return normalized or derive_packing_units(listing)


def fetch_listing_by_sku(base, token, sku, page_size=100, max_pages=20, status=None):
    page = 1
    while page <= max_pages:
        suffix = f'/api/automation/seller/listings?page={page}&pageSize={page_size}'
        if status:
            suffix = f'/api/automation/seller/listings?status={status}&page={page}&pageSize={page_size}'
        payload = request_with_retry('GET', base, token, suffix, attempts=2, sleep_seconds=0.5, timeout=30)
        if not payload.get('ok'):
            break
        payload = payload['resp']
        data = payload.get('data') or {}
        items = data.get('items') or []
        if not items:
            break
        for item in items:
            if str(item.get('sku') or '').strip() == str(sku).strip():
                return item
        if not data.get('hasNextPage'):
            break
        page += 1
    return None


def patch_requires_packing_unit_fix(result):
    if not isinstance(result, dict) or result.get('ok'):
        return False
    error = result.get('error') or {}
    body = str(error.get('body') or '')
    lowered = body.lower()
    return 'packingunits' in lowered and 'piecesperunit' in lowered and 'too small' in lowered


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
            'batch_bias': args.batch_bias,
            'no_submit': args.no_submit,
            'sleep_seconds': args.sleep_seconds,
        },
        'processed': [],
    }
    write_state(state)

    candidates = fetch_candidates(base, token, args.page_size, args.max_pages, target_skus=args.skus or [])
    draft_listing_skus = fetch_draft_listing_skus(base, token, page_size=args.page_size, max_pages=args.max_pages)

    evaluated_candidates = [evaluate_candidate_guards(c, draft_listing_skus) for c in candidates]
    eligible_skus = {item['sku'] for item in evaluated_candidates if item['sku'] and not item['reasons']}
    todo = [c for c in candidates if str(c.get('sku') or '').strip() in eligible_skus]
    if args.skus:
        requested = {str(s).strip() for s in args.skus if str(s).strip()}
        todo = [c for c in todo if str(c.get('sku') or '').strip() in requested]
        evaluated_candidates = [item for item in evaluated_candidates if item['sku'] in requested]
    else:
        todo = sorted(todo, key=lambda candidate: _candidate_priority_key(candidate, args.batch_bias))

    skipped = [
        {
            'sku': item['sku'],
            'canImport': item['canImport'],
            'candidateStatus': item['statusSnapshot'].get('candidateStatus'),
            'uploadStatus': item['statusSnapshot'].get('uploadStatus'),
            'importStatus': item['statusSnapshot'].get('importStatus'),
            'status': item['statusSnapshot'].get('status'),
            'reasons': item['reasons'],
        }
        for item in evaluated_candidates
        if item['reasons']
    ]

    state['draftListingSkuCount'] = len(draft_listing_skus)
    state['eligibleCount'] = len(todo)
    state['skipped'] = skipped
    state['selectionAudit'] = {
        'candidateCount': len(evaluated_candidates),
        'eligibleSkuCount': len(eligible_skus),
        'newImportEligibleCount': sum(1 for item in evaluated_candidates if item['isNewImport'] and not item['draftListingSkuExists'] and item['canImport']),
        'blockedNotNewImportCount': sum(1 for item in evaluated_candidates if 'not-new-import' in item['reasons']),
        'blockedDraftSkuCount': sum(1 for item in evaluated_candidates if 'draft-listing-sku-exists' in item['reasons']),
        'requestedSkuFilterApplied': bool(args.skus),
    }
    write_state(state)

    for c in todo[:args.limit]:
        sku = c['sku']
        row = {'sku': sku, 'candidateStatus': c.get('candidateStatus')}
        try:
            initial_guard = evaluate_candidate_guards(c, draft_listing_skus)
            row['guardChecks'] = {
                'isNewImport': initial_guard['isNewImport'],
                'draftListingSkuExists': initial_guard['draftListingSkuExists'],
                'canImport': initial_guard['canImport'],
                'statusSnapshot': initial_guard['statusSnapshot'],
            }
            if initial_guard['reasons']:
                row['skipped'] = True
                row['skipReason'] = ','.join(initial_guard['reasons'])
                state['processed'].append(row)
                write_state(state)
                continue

            latest_draft_listing = fetch_listing_by_sku(base, token, sku, page_size=args.page_size, max_pages=args.max_pages, status='DRAFT')
            if latest_draft_listing and latest_draft_listing.get('id'):
                row['preImportDuplicateDraftListing'] = {
                    'id': latest_draft_listing.get('id'),
                    'status': latest_draft_listing.get('status'),
                    'sku': latest_draft_listing.get('sku'),
                }
                row['skipped'] = True
                row['skipReason'] = 'draft-listing-sku-exists-preimport-recheck'
                state['processed'].append(row)
                write_state(state)
                continue

            imp = request_with_retry('POST', base, token, '/api/automation/seller/giga/import', {'skus': [sku]}, idempotency=True)
            row['import'] = imp
            if not imp['ok']:
                row['error'] = extract_request_error_message('import', imp)
                state['processed'].append(row)
                write_state(state)
                continue
            imported = imp['resp']
            import_failure_message = extract_import_failure_message(imported)
            if import_failure_message:
                row['error'] = import_failure_message
            product_ids = extract_product_ids(imported)
            if not product_ids:
                match = fetch_listing_by_sku(base, token, sku, page_size=args.page_size, max_pages=args.max_pages, status='DRAFT')
                if not match:
                    match = fetch_listing_by_sku(base, token, sku, page_size=args.page_size, max_pages=args.max_pages, status=None)
                if match and match.get('id'):
                    product_ids = [match['id']]
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
                'packingUnits': normalize_packing_units(listing),
                **WAREHOUSE,
            }
            row['payload'] = payload
            patch = request_with_retry('PATCH', base, token, f'/api/automation/seller/listings/{product_id}', payload, idempotency=True)
            row['patch'] = patch
            if patch_requires_packing_unit_fix(patch):
                payload['packingUnits'] = derive_packing_units(listing)
                row['payload_retry'] = payload
                patch = request_with_retry('PATCH', base, token, f'/api/automation/seller/listings/{product_id}', payload, idempotency=True)
                row['patch_retry'] = patch
                row['patch'] = patch
            if not patch['ok']:
                row['error'] = extract_request_error_message('patch', patch)
                state['processed'].append(row)
                write_state(state)
                continue
            ready = request_with_retry('GET', base, token, f'/api/automation/seller/listings/{product_id}/readiness')
            row['readiness'] = ready
            if not ready['ok']:
                row['error'] = extract_request_error_message('readiness', ready)
            can_submit = False
            if ready['ok']:
                can_submit = ready['resp'].get('data', {}).get('submissionReadiness', {}).get('canSubmit', False)
            if can_submit and not args.no_submit:
                submit = request_with_retry('POST', base, token, f'/api/automation/seller/listings/{product_id}/submit', {}, idempotency=True)
                row['submit'] = submit
                if not submit['ok']:
                    row['error'] = extract_request_error_message('submit', submit)
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
