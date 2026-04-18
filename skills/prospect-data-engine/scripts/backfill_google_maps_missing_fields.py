#!/usr/bin/env python3

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import textwrap
from pathlib import Path
from typing import Any

from google_maps_capture_core import read_json, root_domain, write_json


WORKSPACE_ROOT = Path("/Users/mac_claw/.openclaw/workspace")
if str(WORKSPACE_ROOT) not in sys.path:
    sys.path.insert(0, str(WORKSPACE_ROOT))

from tools.openmoss.ops.local_data_platform_bridge import sync_marketing_suite


PHONE_RE = re.compile(r"(?:\+1[-.\s]?)?\(?\d{3}\)?[-.\s]\d{3}[-.\s]\d{4}")
NON_BUSINESS_HOSTS = (
    "google.com",
    "googleusercontent.com",
    "gstatic.com",
    "accounts.google.com",
    "support.google.com",
    "maps.google.com",
)
PLACE_DETAIL_BATCH_SIZE = 12


def _record_key(item: dict[str, Any]) -> str:
    return str(item.get("source_url") or item.get("place_url") or item.get("website") or item.get("company_name") or "").strip()


def _missing_fields(item: dict[str, Any]) -> list[str]:
    missing: list[str] = []
    if not str(item.get("website") or "").strip():
        missing.append("website")
    if not str(item.get("phone") or "").strip():
        missing.append("phone")
    if not str(item.get("email") or "").strip():
        missing.append("email")
    return missing


def _build_missing_backlog(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    backlog: list[dict[str, Any]] = []
    for item in items:
        missing = _missing_fields(item)
        if not missing:
            continue
        backlog.append(
            {
                "record_key": _record_key(item),
                "query_family": str(item.get("query_family") or ""),
                "account_type": str(item.get("account_type") or ""),
                "company_name": str(item.get("company_name") or ""),
                "geo": str(item.get("geo") or ""),
                "website": str(item.get("website") or ""),
                "phone": str(item.get("phone") or ""),
                "email": str(item.get("email") or ""),
                "place_url": str(item.get("place_url") or item.get("source_url") or ""),
                "website_fit_status": str(item.get("website_fit_status") or ""),
                "email_validation_reason": str(item.get("email_validation_reason") or ""),
                "missing_fields": missing,
            }
        )
    return backlog


def _is_business_link(url: str) -> bool:
    lowered = url.lower().strip()
    if not lowered.startswith(("http://", "https://")):
        return False
    host = root_domain(lowered)
    return bool(host) and not any(host == blocked or host.endswith(f".{blocked}") for blocked in NON_BUSINESS_HOSTS)


def _normalize_phone(raw: str) -> str:
    match = PHONE_RE.search(raw or "")
    if not match:
        return ""
    digits = re.sub(r"\D", "", match.group(0))
    if len(digits) == 11 and digits.startswith("1"):
        digits = digits[1:]
    if len(digits) == 10:
        return f"({digits[:3]}) {digits[3:6]}-{digits[6:]}"
    return match.group(0).strip()


def _extract_place_detail(raw: dict[str, Any]) -> dict[str, Any]:
    links = list(raw.get("links") or [])
    buttons = list(raw.get("buttons") or [])
    body = str(raw.get("body") or "")

    website = ""
    for link in links:
        href = str(link.get("href") or "").strip()
        if not _is_business_link(href):
            continue
        text_blob = " ".join(
            [
                str(link.get("text") or ""),
                str(link.get("aria") or ""),
                str(link.get("dataItemId") or ""),
            ]
        ).lower()
        if "website" in text_blob or "authority" in text_blob:
            website = href
            break
    if not website:
        business_links = [str(link.get("href") or "").strip() for link in links if _is_business_link(str(link.get("href") or "").strip())]
        if len(business_links) == 1:
            website = business_links[0]

    phone = ""
    for link in links:
        href = str(link.get("href") or "").strip()
        if href.startswith("tel:"):
            phone = _normalize_phone(href.removeprefix("tel:"))
            if phone:
                break
    if not phone:
        for entry in [*buttons, *links]:
            phone = _normalize_phone(
                " ".join(
                    [
                        str(entry.get("text") or ""),
                        str(entry.get("aria") or ""),
                        str(entry.get("dataItemId") or ""),
                    ]
                )
            )
            if phone:
                break
    if not phone:
        phone = _normalize_phone(body)

    has_add_website_prompt = "add website" in body.lower()
    return {
        "website": website,
        "phone": phone,
        "maps_missing_website_prompt": has_add_website_prompt,
    }


def _fetch_place_detail_batch(place_urls: list[str]) -> dict[str, dict[str, Any]]:
    venv_python = WORKSPACE_ROOT / "tools" / "matrix-venv" / "bin" / "python"
    if not venv_python.exists():
        raise RuntimeError(f"playwright runtime missing at {venv_python}")
    script = textwrap.dedent(
        """
        from playwright.sync_api import sync_playwright
        import json
        import sys

        urls = json.loads(sys.argv[1])

        def normalize(text: str) -> str:
            return " ".join(str(text or "").split())

        results = []
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page(viewport={"width": 1440, "height": 1400})
            for url in urls:
                try:
                    page.goto(url, wait_until="domcontentloaded", timeout=25000)
                    try:
                        page.wait_for_load_state("networkidle", timeout=6000)
                    except Exception:
                        pass
                    page.wait_for_timeout(1200)
                    payload = page.evaluate(
                        '''() => {
                          const normalize = (text) => (text || '').replace(/\\s+/g, ' ').trim();
                          const links = [...document.querySelectorAll('a[href]')].map((el) => ({
                            href: el.href || '',
                            text: normalize(el.innerText || ''),
                            aria: normalize(el.getAttribute('aria-label') || ''),
                            dataItemId: el.getAttribute('data-item-id') || ''
                          }));
                          const buttons = [...document.querySelectorAll('button,[role="button"]')].map((el) => ({
                            text: normalize(el.innerText || ''),
                            aria: normalize(el.getAttribute('aria-label') || ''),
                            dataItemId: el.getAttribute('data-item-id') || ''
                          }));
                          return {
                            body: normalize((document.body && document.body.innerText) || '').slice(0, 6000),
                            links,
                            buttons
                          };
                        }'''
                    )
                    results.append({"place_url": url, "ok": True, "payload": payload})
                except Exception as exc:
                    results.append({"place_url": url, "ok": False, "error": str(exc)})
            browser.close()
        print(json.dumps({"items": results}, ensure_ascii=False))
        """
    )
    completed = subprocess.run(
        [str(venv_python), "-c", script, json.dumps(place_urls, ensure_ascii=False)],
        capture_output=True,
        text=True,
        timeout=max(90, len(place_urls) * 12),
        check=False,
    )
    if completed.returncode != 0:
        raise RuntimeError((completed.stderr or completed.stdout or "playwright place-detail fetch failed").strip())
    payload = json.loads(completed.stdout or "{}")
    results: dict[str, dict[str, Any]] = {}
    for item in list(payload.get("items") or []):
        place_url = str(item.get("place_url") or "").strip()
        if not place_url:
            continue
        if not item.get("ok"):
            results[place_url] = {"error": str(item.get("error") or "unknown_error")}
            continue
        results[place_url] = _extract_place_detail(dict(item.get("payload") or {}))
    return results


def _fetch_place_details(place_urls: list[str]) -> dict[str, dict[str, Any]]:
    if not place_urls:
        return {}
    results: dict[str, dict[str, Any]] = {}
    urls = list(place_urls)
    for start in range(0, len(urls), PLACE_DETAIL_BATCH_SIZE):
        chunk = urls[start : start + PLACE_DETAIL_BATCH_SIZE]
        try:
            results.update(_fetch_place_detail_batch(chunk))
        except Exception as exc:
            if len(chunk) == 1:
                results[chunk[0]] = {"error": str(exc)}
                continue
            for place_url in chunk:
                try:
                    results.update(_fetch_place_detail_batch([place_url]))
                except Exception as single_exc:
                    results[place_url] = {"error": str(single_exc)}
    return results


def _merge_place_detail(item: dict[str, Any], detail: dict[str, Any]) -> tuple[dict[str, Any], list[str]]:
    updated = dict(item)
    changed: list[str] = []
    website = str(updated.get("website") or "").strip()
    phone = str(updated.get("phone") or "").strip()

    detail_website = str(detail.get("website") or "").strip()
    detail_phone = str(detail.get("phone") or "").strip()

    if not website and detail_website:
        updated["website"] = detail_website
        updated["website_root_domain"] = root_domain(detail_website)
        changed.append("website")
    elif website and not str(updated.get("website_root_domain") or "").strip():
        updated["website_root_domain"] = root_domain(website)

    if not phone and detail_phone:
        updated["phone"] = detail_phone
        changed.append("phone")

    if detail.get("maps_missing_website_prompt"):
        signals = list(updated.get("signals") or [])
        signal = "google_maps_prompt_add_website"
        if signal not in signals:
            signals.append(signal)
            updated["signals"] = signals
    if changed:
        signals = list(updated.get("signals") or [])
        marker = "google_maps_targeted_place_backfill"
        if marker not in signals:
            signals.append(marker)
            updated["signals"] = signals
    return updated, changed


def main() -> int:
    parser = argparse.ArgumentParser(description="Backfill missing website/phone fields for Google Maps records and export a missing backlog.")
    parser.add_argument("--project-root", required=True)
    parser.add_argument("--max-place-targets", type=int, default=60)
    args = parser.parse_args()

    project_root = Path(args.project_root).expanduser().resolve()
    raw_root = project_root / "data" / "raw-imports"
    output_root = project_root / "output" / "prospect-data-engine"
    source_path = raw_root / "discovered-google-maps-places.json"
    validated_path = raw_root / "discovered-google-maps-validated-contacts.json"
    report_path = output_root / "google-maps-missing-field-backfill-report.json"
    backlog_path = output_root / "google-maps-missing-field-backlog.json"

    places_payload = read_json(source_path, {})
    validated_payload = read_json(validated_path, {})
    places = list(places_payload.get("items") or [])
    validated = list(validated_payload.get("items") or [])

    before_backlog = _build_missing_backlog(validated)
    place_targets = [
        item
        for item in validated
        if str(item.get("place_url") or item.get("source_url") or "").strip()
        and ("website" in _missing_fields(item) or "phone" in _missing_fields(item))
    ]
    place_targets.sort(
        key=lambda item: (
            0 if not str(item.get("website") or "").strip() else 1,
            0 if not str(item.get("phone") or "").strip() else 1,
            str(item.get("query_family") or ""),
            str(item.get("company_name") or ""),
        )
    )
    selected_targets = place_targets[: max(0, int(args.max_place_targets or 0))]
    detail_map = _fetch_place_details(
        [str(item.get("place_url") or item.get("source_url") or "").strip() for item in selected_targets]
    ) if selected_targets else {}

    detail_by_place_url: dict[str, dict[str, Any]] = {}
    detail_updates = {
        "website_fills": 0,
        "phone_fills": 0,
        "target_count": len(selected_targets),
        "success_count": 0,
        "error_count": 0,
    }
    for item in selected_targets:
        place_url = str(item.get("place_url") or item.get("source_url") or "").strip()
        detail = dict(detail_map.get(place_url) or {})
        if detail.get("error"):
            detail_updates["error_count"] += 1
            continue
        _, changed = _merge_place_detail(item, detail)
        detail_by_place_url[place_url] = detail
        if changed:
            detail_updates["success_count"] += 1
        if "website" in changed:
            detail_updates["website_fills"] += 1
        if "phone" in changed:
            detail_updates["phone_fills"] += 1

    def apply_updates(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
        merged_items: list[dict[str, Any]] = []
        for item in items:
            place_url = str(item.get("place_url") or item.get("source_url") or "").strip()
            detail = detail_by_place_url.get(place_url)
            if not detail:
                merged_items.append(item)
                continue
            merged, _ = _merge_place_detail(item, detail)
            merged_items.append(merged)
        return merged_items

    if detail_by_place_url:
        places = apply_updates(places)
        validated = apply_updates(validated)
        write_json(source_path, {"items": places})
        write_json(validated_path, {"items": validated})

    after_backlog = _build_missing_backlog(validated)
    write_json(backlog_path, {"items": after_backlog})

    summary_before = {
        "missing_website": sum(1 for item in before_backlog if "website" in list(item.get("missing_fields") or [])),
        "missing_phone": sum(1 for item in before_backlog if "phone" in list(item.get("missing_fields") or [])),
        "missing_email": sum(1 for item in before_backlog if "email" in list(item.get("missing_fields") or [])),
    }
    summary_after = {
        "missing_website": sum(1 for item in after_backlog if "website" in list(item.get("missing_fields") or [])),
        "missing_phone": sum(1 for item in after_backlog if "phone" in list(item.get("missing_fields") or [])),
        "missing_email": sum(1 for item in after_backlog if "email" in list(item.get("missing_fields") or [])),
    }

    report = {
        "status": "ok",
        "selected_target_count": len(selected_targets),
        "before": summary_before,
        "after": summary_after,
        "detail_updates": detail_updates,
        "backlog_path": str(backlog_path),
        "source_path": str(source_path),
        "validated_path": str(validated_path),
    }
    report["data_platform_sync"] = sync_marketing_suite(project_root=project_root)
    write_json(report_path, report)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
