#!/usr/bin/env python3
import argparse
import importlib.util
import json
import re
import time
from pathlib import Path
from urllib.parse import urlparse, unquote

RUNNER_PATH = Path.home() / '.openclaw' / 'workspace' / 'tools' / 'bin' / 'neosgo-seller-bulk-runner.py'
OUTPUT_DIR = Path.home() / '.openclaw' / 'workspace' / 'output' / 'neosgo-listing-description-optimizer'


def load_runner_module():
    spec = importlib.util.spec_from_file_location('neosgo_bulk', RUNNER_PATH)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def parse_args():
    p = argparse.ArgumentParser(description='Optimize existing Neosgo listing descriptions for SUBMITTED/REJECTED listings using safe plain text only.')
    p.add_argument('--statuses', nargs='*', default=['SUBMITTED', 'REJECTED'])
    p.add_argument('--page-size', type=int, default=100)
    p.add_argument('--max-pages', type=int, default=20)
    p.add_argument('--limit', type=int, default=0, help='0 means no extra cap')
    p.add_argument('--sku', action='append', dest='skus')
    p.add_argument('--dry-run', action='store_true')
    p.add_argument('--sleep-seconds', type=float, default=0.4)
    return p.parse_args()


def html_to_plain_text(value):
    if not isinstance(value, str):
        return ''
    text = value
    text = text.replace('<br>', '\n').replace('<br/>', '\n').replace('<br />', '\n')
    text = text.replace('</p>', '\n').replace('</div>', '\n').replace('</li>', '\n')
    text = re.sub(r'<[^>]+>', ' ', text)
    html_entities = {
        '&nbsp;': ' ', '&amp;': '&', '&lt;': '<', '&gt;': '>', '&quot;': '"', '&#39;': "'"
    }
    for k, v in html_entities.items():
        text = text.replace(k, v)
    text = re.sub(r'[ \t]+', ' ', text)
    text = re.sub(r'\s*\n\s*', '\n', text)
    text = re.sub(r'\n{2,}', '\n', text)
    return text.strip()


def clean_title(title):
    text = html_to_plain_text(title)
    text = re.sub(r'\s+', ' ', text).strip(' .')
    return text


def infer_image_signals(images):
    signals = []
    filenames = []
    for img in images or []:
        url = img.get('url') or ''
        if not url:
            continue
        path = urlparse(url).path
        name = unquote(path.split('/')[-1]).strip()
        if name:
            filenames.append(name)
    joined = ' '.join(filenames).lower()
    keyword_map = [
        ('anti fog', 'anti-fog function shown in product imagery'),
        ('dimmable', 'dimmable capability indicated in image assets'),
        ('led', 'LED-related labeling present in image assets'),
        ('touch', 'touch-control details suggested by image assets'),
        ('memory', 'memory-function details suggested by image assets'),
        ('farmhouse', 'farmhouse styling supported by product imagery'),
        ('rustic', 'rustic styling supported by product imagery'),
        ('vintage', 'vintage styling supported by product imagery'),
        ('modern', 'modern styling supported by product imagery'),
        ('mirror', 'mirror-focused bathroom use shown in image assets'),
        ('chandelier', 'chandelier fixture presentation shown in image assets'),
    ]
    for needle, sentence in keyword_map:
        if needle in joined:
            signals.append(sentence)
    return signals


def build_usage_sentence(title, room_tags, style_tags, material, signals):
    lowered = f"{title} {' '.join(room_tags)} {' '.join(style_tags)} {material} {' '.join(signals)}".lower()
    if 'mirror' in lowered:
        return 'Designed to provide practical task lighting around a vanity or bathroom mirror while supporting everyday grooming routines.'
    if 'chandelier' in lowered or 'pendant' in lowered:
        return 'Made to bring focused overhead illumination and decorative impact to dining areas, entryways, or other statement spaces.'
    if 'wall' in lowered or 'sconce' in lowered:
        return 'Works well as accent or supplemental wall lighting for hallways, bedrooms, bathrooms, and other interior spaces.'
    if 'outdoor' in lowered or 'lantern' in lowered:
        return 'Intended to add dependable illumination and a finished look to exterior doors, porches, patios, or other outdoor areas.'
    if 'lamp' in lowered:
        return 'Useful as everyday supplemental lighting for reading, relaxing, or adding warmth to living spaces.'
    return 'Designed as a practical decorative lighting piece that supports everyday use while helping complete the look of the space.'


def build_description(listing):
    title = clean_title(listing.get('title') or listing.get('name') or listing.get('sku') or 'NEOSGO product')
    brand = html_to_plain_text(listing.get('brand') or 'NEOSGO') or 'NEOSGO'
    dims = listing.get('dimensions') or {}
    length = dims.get('length') or listing.get('length')
    width = dims.get('width') or listing.get('width')
    height = dims.get('height') or listing.get('height')
    weight = dims.get('weight') or listing.get('weight')
    room_tags = [html_to_plain_text(x) for x in (listing.get('roomTags') or []) if html_to_plain_text(x)]
    style_tags = [html_to_plain_text(x) for x in (listing.get('styleTags') or []) if html_to_plain_text(x)]
    finish_tags = [html_to_plain_text(x) for x in (listing.get('finishTags') or []) if html_to_plain_text(x)]
    material = html_to_plain_text(listing.get('material') or '')
    images = listing.get('images') or []
    signals = infer_image_signals(images)

    parts = []
    parts.append(f'{brand} {title}.')
    parts.append(build_usage_sentence(title, room_tags, style_tags, material, signals))
    feature_bits = []
    if material:
        feature_bits.append(f'Material: {material}')
    if room_tags:
        feature_bits.append('Suggested spaces: ' + ', '.join(room_tags[:4]))
    if style_tags:
        feature_bits.append('Style: ' + ', '.join(style_tags[:4]))
    if finish_tags:
        feature_bits.append('Finish: ' + ', '.join(finish_tags[:4]))
    if feature_bits:
        parts.append('. '.join(feature_bits) + '.')
    dim_bits = []
    if length not in (None, '', '0'): dim_bits.append(f'length {length}')
    if width not in (None, '', '0'): dim_bits.append(f'width {width}')
    if height not in (None, '', '0'): dim_bits.append(f'height {height}')
    if weight not in (None, '', '0'): dim_bits.append(f'weight {weight}')
    if dim_bits:
        parts.append('Product dimensions and weight: ' + ', '.join(dim_bits) + '.')
    if signals:
        parts.append('Notable product details visible in the images: ' + '; '.join(signals[:4]) + '.')
    text = ' '.join(part.strip() for part in parts if part and part.strip())
    text = html_to_plain_text(text)
    text = re.sub(r'\s+', ' ', text).strip()
    return text


def fetch_all_listings(mod, base, token, statuses, page_size, max_pages, target_skus=None):
    out = []
    wanted = {str(s).strip() for s in (target_skus or []) if str(s).strip()}
    for status in statuses:
        page = 1
        while page <= max_pages:
            r = mod.request_with_retry('GET', base, token, f'/api/automation/seller/listings?status={status}&page={page}&pageSize={page_size}', attempts=2, sleep_seconds=0.5, timeout=30)
            if not r.get('ok'):
                out.append({'_fetch_error': True, 'status': status, 'page': page, 'error': r.get('error')})
                break
            data = r['resp'].get('data', {})
            items = data.get('items', []) or []
            if wanted:
                items = [x for x in items if str(x.get('sku') or '').strip() in wanted]
            out.extend(items)
            if wanted:
                seen = {str(x.get('sku') or '').strip() for x in out if isinstance(x, dict) and not x.get('_fetch_error')}
                if wanted.issubset(seen):
                    break
            if not items and not data.get('hasNextPage'):
                break
            if not data.get('hasNextPage'):
                break
            page += 1
    return out


def main():
    args = parse_args()
    mod = load_runner_module()
    env = mod.load_env(mod.SECRET_PATH)
    base = env['NEOSGO_SELLER_API_BASE_URL']
    token = env['NEOSGO_SELLER_AUTOMATION_KEY']
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    started = time.time()
    report = {
        'startedAt': started,
        'statuses': args.statuses,
        'dryRun': args.dry_run,
        'rows': [],
    }
    listings = fetch_all_listings(mod, base, token, args.statuses, args.page_size, args.max_pages, target_skus=args.skus)
    real_listings = [x for x in listings if isinstance(x, dict) and not x.get('_fetch_error')]
    if args.limit and args.limit > 0:
        real_listings = real_listings[:args.limit]
    report['enumeratedCount'] = len(real_listings)
    report['fetchErrors'] = [x for x in listings if isinstance(x, dict) and x.get('_fetch_error')]

    for item in real_listings:
        sku = item.get('sku')
        pid = item.get('id')
        row = {'sku': sku, 'id': pid, 'status': item.get('status')}
        try:
            detail = mod.request('GET', base, token, f'/api/automation/seller/listings/{pid}')
            data = detail.get('data', {})
            listing = data.get('listing', data)
            description = build_description(listing)
            row['newDescription'] = description
            row['newDescriptionLength'] = len(description)
            row['containsHtml'] = bool(re.search(r'<[^>]+>', description))
            try:
                submission_price = mod.pick_submission_price(listing)
            except ValueError as exc:
                row['patchOk'] = False
                row['priceBlocker'] = str(exc)
                row['platformUnitCost'] = ((listing.get('pricing') or {}).get('platformUnitCost'))
                row['retailUnitPrice'] = ((listing.get('pricing') or {}).get('retailUnitPrice'))
                report['rows'].append(row)
                time.sleep(args.sleep_seconds)
                continue
            payload = {
                'brand': listing.get('brand') or mod.DEFAULT_BRAND,
                'categoryId': mod.pick_category_id(listing, item),
                'basePrice': submission_price,
                'description': description,
                'shippingTemplateId': listing.get('shippingTemplateId') or mod.SHIPPING_TEMPLATE_ID,
                'quantityAvailable': mod.pick_quantity_available(listing),
                'packingUnits': mod.normalize_packing_units(listing),
                **mod.WAREHOUSE,
            }
            row['payloadPreview'] = {k: payload[k] for k in ['brand', 'categoryId', 'basePrice', 'description', 'shippingTemplateId', 'quantityAvailable']}
            if not args.dry_run:
                patch = mod.request_with_retry('PATCH', base, token, f'/api/automation/seller/listings/{pid}', payload, idempotency=True, attempts=2, sleep_seconds=0.8, timeout=60)
                row['patchOk'] = bool(patch.get('ok'))
                if not patch.get('ok'):
                    row['patchError'] = patch.get('error')
                else:
                    row['updatedAt'] = (patch.get('resp') or {}).get('data', {}).get('updatedAt')
            else:
                row['patchOk'] = None
        except Exception as e:
            row['exception'] = repr(e)
        report['rows'].append(row)
        time.sleep(args.sleep_seconds)

    report['finishedAt'] = time.time()
    report['processedCount'] = len(report['rows'])
    report['successCount'] = sum(1 for r in report['rows'] if r.get('patchOk') is True)
    report['failureCount'] = sum(1 for r in report['rows'] if r.get('patchOk') is False or r.get('exception'))
    stamp = time.strftime('%Y%m%dT%H%M%SZ', time.gmtime(report['finishedAt']))
    out_json = OUTPUT_DIR / f'neosgo-listing-description-optimizer-{stamp}.json'
    out_md = OUTPUT_DIR / f'neosgo-listing-description-optimizer-{stamp}.md'
    out_json.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    lines = [
        '# Neosgo Listing Description Optimizer Report',
        '',
        f'- Processed: {report["processedCount"]}',
        f'- Success: {report["successCount"]}',
        f'- Failed: {report["failureCount"]}',
        f'- Dry run: {report["dryRun"]}',
        '',
        '## Rows',
        ''
    ]
    for r in report['rows']:
        lines.append(f"- SKU `{r.get('sku')}` | status={r.get('status')} | patchOk={r.get('patchOk')} | html={r.get('containsHtml')} | len={r.get('newDescriptionLength')}")
    out_md.write_text('\n'.join(lines) + '\n', encoding='utf-8')
    print(json.dumps({'json': str(out_json), 'md': str(out_md), 'processedCount': report['processedCount'], 'successCount': report['successCount'], 'failureCount': report['failureCount']}, ensure_ascii=False))


if __name__ == '__main__':
    main()
