#!/usr/bin/env python3

from __future__ import annotations

import importlib.util
import json
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
import fcntl
from datetime import timedelta


WORKSPACE_ROOT = Path("/Users/mac_claw/.openclaw/workspace")
RUNNER_PATH = WORKSPACE_ROOT / "tools/bin/neosgo-seller-bulk-runner.py"
DESCRIPTION_OPTIMIZER_PATH = WORKSPACE_ROOT / "tools/bin/neosgo_listing_description_optimizer.py"
OUTPUT_ROOT = WORKSPACE_ROOT / "output/neosgo-seller-maintenance"
STATE_PATH = WORKSPACE_ROOT / "data/neosgo-seller-maintenance-state.json"
LOCK_PATH = WORKSPACE_ROOT / "data/neosgo-seller-maintenance.lock"
CANDIDATE_SCAN_STATE_PATH = WORKSPACE_ROOT / "data/neosgo-seller-maintenance-candidate-scan.json"

DEFAULT_PAGE_SIZE = 100
DEFAULT_MAX_PAGES = 50
DEFAULT_IMPORT_LIMIT = 500
DEFAULT_SLEEP_SECONDS = 0.4
DEFAULT_INCREMENTAL_WARM_PAGES = 5
DEFAULT_INCREMENTAL_STABLE_PAGES = 3
DEFAULT_FULL_RESCAN_DAYS = 7


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _load_module(path: Path, module_name: str):
    spec = importlib.util.spec_from_file_location(module_name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


RUNNER = _load_module(RUNNER_PATH, "neosgo_bulk_runner")
DESC_OPTIMIZER = _load_module(DESCRIPTION_OPTIMIZER_PATH, "neosgo_listing_description_optimizer")


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _write_progress(progress: dict[str, Any]) -> None:
    _write_json(STATE_PATH, {"progress": progress, "updated_at": _utc_now_iso()})


def _read_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return default


def _load_env() -> tuple[str, str]:
    env = RUNNER.load_env(RUNNER.SECRET_PATH)
    return env["NEOSGO_SELLER_API_BASE_URL"], env["NEOSGO_SELLER_AUTOMATION_KEY"]


def _candidate_fingerprint(candidate: dict) -> str:
    return "|".join(
        [
            str(candidate.get("sku") or "").strip(),
            str(candidate.get("candidateStatus") or "").strip(),
            str(candidate.get("canImport")),
            str(candidate.get("importedProductStatus") or "").strip(),
            str(candidate.get("importedProductId") or "").strip(),
            str(candidate.get("quantityAvailable") or "").strip(),
        ]
    )


def _parse_iso_datetime(value: str) -> datetime | None:
    raw = str(value or "").strip()
    if not raw:
        return None
    try:
        return datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        return None


def _fetch_candidate_page(base: str, token: str, page: int, page_size: int) -> dict:
    return RUNNER.request_with_retry(
        "GET",
        base,
        token,
        f"/api/automation/seller/giga/candidates?page={page}&pageSize={page_size}",
        attempts=2,
        sleep_seconds=0.5,
        timeout=30,
    )


def _load_candidate_scan_state() -> dict:
    return _read_json(
        CANDIDATE_SCAN_STATE_PATH,
        {
            "last_full_scan_at": "",
            "known_candidate_fingerprints": {},
            "last_scan_meta": {},
        },
    )


def _write_candidate_scan_state(payload: dict) -> None:
    _write_json(CANDIDATE_SCAN_STATE_PATH, payload)


def _fetch_all_candidates(base: str, token: str, page_size: int = DEFAULT_PAGE_SIZE, max_pages: int = DEFAULT_MAX_PAGES) -> tuple[list[dict], dict]:
    scan_state = _load_candidate_scan_state()
    known_fingerprints = dict(scan_state.get("known_candidate_fingerprints") or {})
    now = datetime.now(timezone.utc)
    last_full_scan_at = _parse_iso_datetime(str(scan_state.get("last_full_scan_at") or ""))
    full_scan_required = (
        not last_full_scan_at
        or now - last_full_scan_at >= timedelta(days=DEFAULT_FULL_RESCAN_DAYS)
    )
    candidates: list[dict] = []
    pages_scanned = 0
    consecutive_stable_pages = 0
    newly_changed_count = 0
    mode = "full" if full_scan_required else "incremental"
    updated_fingerprints = dict(known_fingerprints)
    for page in range(1, max_pages + 1):
        payload = _fetch_candidate_page(base, token, page, page_size)
        if not payload.get("ok"):
            break
        data = (payload.get("resp") or {}).get("data", {}) or {}
        items = data.get("candidates") or []
        if not items:
            break
        pages_scanned += 1
        candidates.extend(items)
        page_has_change_signal = False
        for item in items:
            sku = str(item.get("sku") or "").strip()
            if not sku:
                continue
            fingerprint = _candidate_fingerprint(item)
            if known_fingerprints.get(sku) != fingerprint:
                page_has_change_signal = True
                newly_changed_count += 1
            if item.get("canImport") or RUNNER.is_new_import_candidate(item):
                page_has_change_signal = True
            updated_fingerprints[sku] = fingerprint
        if mode == "incremental":
            if page_has_change_signal:
                consecutive_stable_pages = 0
            else:
                consecutive_stable_pages += 1
            if page >= DEFAULT_INCREMENTAL_WARM_PAGES and consecutive_stable_pages >= DEFAULT_INCREMENTAL_STABLE_PAGES:
                break
        if not data.get("hasNextPage"):
            break
    _write_candidate_scan_state(
        {
            "last_full_scan_at": now.isoformat() if mode == "full" else str(scan_state.get("last_full_scan_at") or ""),
            "known_candidate_fingerprints": updated_fingerprints,
            "last_scan_meta": {
                "mode": mode,
                "pages_scanned": pages_scanned,
                "newly_changed_count": newly_changed_count,
                "consecutive_stable_pages": consecutive_stable_pages,
                "candidate_count": len(candidates),
                "updated_at": now.isoformat(),
            },
        }
    )
    return candidates, {
        "mode": mode,
        "pages_scanned": pages_scanned,
        "newly_changed_count": newly_changed_count,
        "consecutive_stable_pages": consecutive_stable_pages,
        "candidate_count": len(candidates),
    }


def _candidate_map(candidates: list[dict]) -> dict[str, dict]:
    mapping: dict[str, dict] = {}
    for candidate in candidates:
        sku = str(candidate.get("sku") or "").strip()
        if sku:
            mapping[sku] = candidate
    return mapping


def _fetch_listings_by_status(base: str, token: str, status: str, page_size: int = DEFAULT_PAGE_SIZE, max_pages: int = DEFAULT_MAX_PAGES) -> list[dict]:
    rows: list[dict] = []
    page = 1
    while page <= max_pages:
        payload = RUNNER.request_with_retry(
            "GET",
            base,
            token,
            f"/api/automation/seller/listings?status={status}&page={page}&pageSize={page_size}",
            attempts=2,
            sleep_seconds=0.5,
            timeout=30,
        )
        if not payload.get("ok"):
            break
        data = (payload.get("resp") or {}).get("data", {}) or {}
        items = data.get("items") or []
        if not items:
            break
        rows.extend(items)
        if not data.get("hasNextPage"):
            break
        page += 1
    return rows


def _fetch_listing_detail(base: str, token: str, product_id: str) -> dict:
    payload = RUNNER.request("GET", base, token, f"/api/automation/seller/listings/{product_id}")
    data = payload.get("data", {}) or {}
    return data.get("listing", data)


def _fetch_listing_status(base: str, token: str, product_id: str) -> dict:
    payload = RUNNER.request_with_retry(
        "GET",
        base,
        token,
        f"/api/automation/seller/listings/{product_id}/status",
        attempts=2,
        sleep_seconds=0.5,
        timeout=30,
    )
    if not payload.get("ok"):
        return {}
    return ((payload.get("resp") or {}).get("data", {}) or {})


def _fetch_readiness(base: str, token: str, product_id: str) -> dict:
    payload = RUNNER.request_with_retry(
        "GET",
        base,
        token,
        f"/api/automation/seller/listings/{product_id}/readiness",
        attempts=2,
        sleep_seconds=0.5,
        timeout=30,
    )
    if not payload.get("ok"):
        return payload
    return payload


def _build_listing_payload(listing: dict, candidate: dict | None) -> dict:
    quantity_available = None
    if candidate:
        try:
            candidate_qty = int(candidate.get("quantityAvailable"))
            if candidate_qty > 0:
                quantity_available = candidate_qty
        except (TypeError, ValueError):
            quantity_available = None
    if quantity_available is None:
        quantity_available = RUNNER.pick_quantity_available(listing)
    return {
        "brand": listing.get("brand") or RUNNER.DEFAULT_BRAND,
        "categoryId": RUNNER.pick_category_id(listing, candidate or {}),
        "basePrice": RUNNER.pick_submission_price(listing),
        "description": DESC_OPTIMIZER.build_description(listing),
        "shippingTemplateId": listing.get("shippingTemplateId") or RUNNER.SHIPPING_TEMPLATE_ID,
        "quantityAvailable": quantity_available,
        "packingUnits": RUNNER.normalize_packing_units(listing),
        **RUNNER.WAREHOUSE,
    }


def _patch_listing(base: str, token: str, product_id: str, payload: dict) -> dict:
    result = RUNNER.request_with_retry(
        "PATCH",
        base,
        token,
        f"/api/automation/seller/listings/{product_id}",
        payload,
        idempotency=True,
        attempts=2,
        sleep_seconds=0.8,
        timeout=60,
    )
    if RUNNER.patch_requires_packing_unit_fix(result):
        listing = _fetch_listing_detail(base, token, product_id)
        payload = dict(payload)
        payload["packingUnits"] = RUNNER.derive_packing_units(listing)
        result = RUNNER.request_with_retry(
            "PATCH",
            base,
            token,
            f"/api/automation/seller/listings/{product_id}",
            payload,
            idempotency=True,
            attempts=2,
            sleep_seconds=0.8,
            timeout=60,
        )
    return result


def _submit_listing(base: str, token: str, product_id: str) -> dict:
    return RUNNER.request_with_retry(
        "POST",
        base,
        token,
        f"/api/automation/seller/listings/{product_id}/submit",
        {},
        idempotency=True,
        attempts=2,
        sleep_seconds=0.8,
        timeout=60,
    )


def _run_import_phase(base: str, token: str, candidates: list[dict], import_limit: int) -> dict:
    draft_listing_skus = RUNNER.fetch_draft_listing_skus(base, token, page_size=DEFAULT_PAGE_SIZE, max_pages=DEFAULT_MAX_PAGES)
    todo = [
        c
        for c in candidates
        if c.get("canImport")
        and RUNNER.is_new_import_candidate(c)
        and str(c.get("sku") or "").strip() not in draft_listing_skus
    ]
    todo = sorted(todo, key=lambda candidate: RUNNER._candidate_priority_key(candidate, "balanced"))[:import_limit]
    rows: list[dict] = []
    for candidate in todo:
        sku = str(candidate.get("sku") or "").strip()
        row: dict[str, Any] = {"sku": sku, "candidateStatus": candidate.get("candidateStatus")}
        try:
            imp = RUNNER.request_with_retry(
                "POST",
                base,
                token,
                "/api/automation/seller/giga/import",
                {"skus": [sku]},
                idempotency=True,
            )
            row["import_ok"] = bool(imp.get("ok"))
            if not imp.get("ok"):
                row["error"] = RUNNER.extract_request_error_message("import", imp)
                rows.append(row)
                continue
            imported = imp.get("resp") or {}
            import_failure_message = RUNNER.extract_import_failure_message(imported)
            if import_failure_message:
                row["error"] = import_failure_message
            product_ids = RUNNER.extract_product_ids(imported)
            if not product_ids:
                match = RUNNER.fetch_listing_by_sku(base, token, sku, page_size=DEFAULT_PAGE_SIZE, max_pages=DEFAULT_MAX_PAGES, status="DRAFT")
                if not match:
                    match = RUNNER.fetch_listing_by_sku(base, token, sku, page_size=DEFAULT_PAGE_SIZE, max_pages=DEFAULT_MAX_PAGES, status=None)
                if match and match.get("id"):
                    product_ids = [match["id"]]
            if not product_ids:
                row["error"] = "imported product id not found"
                rows.append(row)
                continue
            product_id = product_ids[0]
            row["product_id"] = product_id
            listing = _fetch_listing_detail(base, token, product_id)
            status_payload = _fetch_listing_status(base, token, product_id)
            row["post_import_status"] = listing.get("status") or status_payload.get("status")
            row["editable_via_automation"] = bool(
                listing.get("editableViaAutomation", status_payload.get("editableViaAutomation"))
            )
            row["inventory_editable_via_automation"] = bool(
                listing.get("inventoryEditableViaAutomation", status_payload.get("inventoryEditableViaAutomation"))
            )
            if not row["editable_via_automation"]:
                candidate_qty = candidate.get("quantityAvailable")
                current_qty = ((listing.get("inventory") or {}).get("quantityAvailable"))
                row["skipped_reason"] = "import_resolved_to_noneditable_existing_listing"
                if row["inventory_editable_via_automation"]:
                    try:
                        candidate_qty_int = int(candidate_qty)
                    except (TypeError, ValueError):
                        candidate_qty_int = None
                    if candidate_qty_int and candidate_qty_int > 0 and current_qty != candidate_qty_int:
                        inventory_patch = _patch_listing(base, token, product_id, {"quantityAvailable": candidate_qty_int})
                        row["inventory_patch_ok"] = bool(inventory_patch.get("ok"))
                        if not inventory_patch.get("ok"):
                            row["error"] = RUNNER.extract_request_error_message("inventory_patch", inventory_patch)
                    else:
                        row["inventory_patch_ok"] = False
                rows.append(row)
                time.sleep(DEFAULT_SLEEP_SECONDS)
                continue
            payload = _build_listing_payload(listing, candidate)
            patch = _patch_listing(base, token, product_id, payload)
            row["patch_ok"] = bool(patch.get("ok"))
            if not patch.get("ok"):
                row["error"] = RUNNER.extract_request_error_message("patch", patch)
                rows.append(row)
                continue
            readiness = _fetch_readiness(base, token, product_id)
            row["readiness_ok"] = bool(readiness.get("ok"))
            if not readiness.get("ok"):
                row["error"] = RUNNER.extract_request_error_message("readiness", readiness)
                rows.append(row)
                continue
            readiness_data = ((readiness.get("resp") or {}).get("data", {}) or {}).get("submissionReadiness", {}) or {}
            row["can_submit"] = bool(readiness_data.get("canSubmit"))
            if row["can_submit"]:
                submit = _submit_listing(base, token, product_id)
                row["submit_ok"] = bool(submit.get("ok"))
                if not submit.get("ok"):
                    row["error"] = RUNNER.extract_request_error_message("submit", submit)
        except Exception as exc:
            row["exception"] = repr(exc)
        rows.append(row)
        time.sleep(DEFAULT_SLEEP_SECONDS)
    return {
        "bulk_state": {
            "eligibleCount": len(todo),
            "processedCount": len(rows),
            "successCount": sum(1 for row in rows if row.get("submit_ok")),
            "failureCount": sum(1 for row in rows if (row.get("error") or row.get("exception")) and not row.get("skipped_reason")),
            "draftListingSkuCount": len(draft_listing_skus),
        },
        "rows": rows,
    }


def _process_listings_for_submit(base: str, token: str, status: str, candidates_by_sku: dict[str, dict]) -> dict:
    listings = _fetch_listings_by_status(base, token, status)
    results: list[dict] = []
    for item in listings:
        product_id = str(item.get("id") or "").strip()
        sku = str(item.get("sku") or "").strip()
        if not product_id or not sku:
            continue
        row: dict[str, Any] = {
            "product_id": product_id,
            "sku": sku,
            "starting_status": status,
        }
        try:
            listing = _fetch_listing_detail(base, token, product_id)
            status_payload = _fetch_listing_status(base, token, product_id)
            payload = _build_listing_payload(listing, candidates_by_sku.get(sku))
            patch = _patch_listing(base, token, product_id, payload)
            row["patch_ok"] = bool(patch.get("ok"))
            row["inventory_editable"] = bool(status_payload.get("inventoryEditableViaAutomation"))
            row["editable_via_automation"] = bool(status_payload.get("editableViaAutomation"))
            row["review_status"] = status_payload.get("reviewStatus")
            if not patch.get("ok"):
                row["error"] = RUNNER.extract_request_error_message("patch", patch)
                results.append(row)
                time.sleep(DEFAULT_SLEEP_SECONDS)
                continue
            readiness = _fetch_readiness(base, token, product_id)
            row["readiness_ok"] = bool(readiness.get("ok"))
            if not readiness.get("ok"):
                row["error"] = RUNNER.extract_request_error_message("readiness", readiness)
                results.append(row)
                time.sleep(DEFAULT_SLEEP_SECONDS)
                continue
            readiness_data = ((readiness.get("resp") or {}).get("data", {}) or {}).get("submissionReadiness", {}) or {}
            row["can_submit"] = bool(readiness_data.get("canSubmit"))
            row["blocking_issue_codes"] = readiness_data.get("issueCodes") or []
            if row["can_submit"]:
                submit = _submit_listing(base, token, product_id)
                row["submit_ok"] = bool(submit.get("ok"))
                if submit.get("ok"):
                    submit_data = ((submit.get("resp") or {}).get("data", {}) or {})
                    row["final_status"] = submit_data.get("status")
                    row["final_review_status"] = submit_data.get("reviewStatus")
                else:
                    row["error"] = RUNNER.extract_request_error_message("submit", submit)
            results.append(row)
        except Exception as exc:
            row["exception"] = repr(exc)
            results.append(row)
        time.sleep(DEFAULT_SLEEP_SECONDS)
    return {
        "status": status,
        "enumerated_count": len(listings),
        "processed_count": len(results),
        "submitted_count": sum(1 for row in results if row.get("submit_ok")),
        "blocked_count": sum(1 for row in results if row.get("can_submit") is False),
        "rows": results,
    }


def _sync_uploaded_inventory(base: str, token: str, candidates_by_sku: dict[str, dict]) -> dict:
    rows: list[dict] = []
    listings = []
    for status in ("APPROVED", "SUBMITTED"):
        listings.extend(_fetch_listings_by_status(base, token, status))
    for item in listings:
        product_id = str(item.get("id") or "").strip()
        sku = str(item.get("sku") or "").strip()
        candidate = candidates_by_sku.get(sku)
        if not product_id or not sku or not candidate:
            continue
        try:
            candidate_qty = int(candidate.get("quantityAvailable"))
        except (TypeError, ValueError):
            continue
        if candidate_qty <= 0:
            continue
        current_qty = ((item.get("inventory") or {}).get("quantityAvailable"))
        row: dict[str, Any] = {
            "product_id": product_id,
            "sku": sku,
            "listing_status": item.get("status"),
            "current_quantity": current_qty,
            "candidate_quantity": candidate_qty,
            "inventory_editable": bool(item.get("inventoryEditableViaAutomation")),
        }
        if not row["inventory_editable"] or current_qty == candidate_qty:
            row["patched"] = False
            rows.append(row)
            continue
        patch = _patch_listing(base, token, product_id, {"quantityAvailable": candidate_qty})
        row["patched"] = bool(patch.get("ok"))
        if not patch.get("ok"):
            row["error"] = RUNNER.extract_request_error_message("inventory_patch", patch)
        rows.append(row)
        time.sleep(DEFAULT_SLEEP_SECONDS)
    return {
        "enumerated_count": len(listings),
        "processed_count": len(rows),
        "patched_count": sum(1 for row in rows if row.get("patched")),
        "rows": rows,
    }


def _write_markdown_report(report: dict, path: Path) -> None:
    lines = [
        "# Neosgo Seller Maintenance Cycle",
        "",
        f"- Started: {report.get('started_at')}",
        f"- Finished: {report.get('finished_at')}",
        f"- New imports processed: {report.get('import_phase', {}).get('bulk_state', {}).get('processedCount', 0)}",
        f"- Draft submitted: {report.get('draft_phase', {}).get('submitted_count', 0)}",
        f"- Rejected resubmitted: {report.get('rejected_phase', {}).get('submitted_count', 0)}",
        f"- Inventory patched: {report.get('inventory_sync_phase', {}).get('patched_count', 0)}",
        "",
        "## Next Steps",
    ]
    for step in report.get("next_steps", []):
        lines.append(f"- {step}")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    LOCK_PATH.parent.mkdir(parents=True, exist_ok=True)
    lock_handle = LOCK_PATH.open("w", encoding="utf-8")
    try:
        fcntl.flock(lock_handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        print(json.dumps({"error": "maintenance_cycle_already_running", "lock_path": str(LOCK_PATH)}, ensure_ascii=False))
        return 2
    try:
        base, token = _load_env()
        started_at = _utc_now_iso()
        _write_progress({"stage": "bootstrap"})
        report: dict[str, Any] = {
            "started_at": started_at,
            "workflow_id": f"neosgo-seller-maintenance-{int(time.time())}",
            "phases": [
                "import_new_giga_candidates",
                "optimize_and_submit_drafts",
                "repair_and_resubmit_rejected",
                "sync_uploaded_listing_inventory",
            ],
        }
        _write_progress({"stage": "fetch_candidates"})
        candidates, candidate_scan_meta = _fetch_all_candidates(base, token)
        candidates_by_sku = _candidate_map(candidates)
        report["candidate_summary"] = {
            "candidate_count": len(candidates),
            "new_import_count": sum(1 for item in candidates if item.get("canImport") and RUNNER.is_new_import_candidate(item)),
            "approved_count": sum(1 for item in candidates if str(item.get("candidateStatus") or "").strip().upper() == "APPROVED"),
        }
        report["candidate_scan_meta"] = candidate_scan_meta
        _write_progress({"stage": "import_phase", "candidate_summary": report["candidate_summary"]})
        report["import_phase"] = _run_import_phase(base, token, candidates, DEFAULT_IMPORT_LIMIT)
        _write_progress({"stage": "draft_phase", "import_phase": report["import_phase"]["bulk_state"]})
        report["draft_phase"] = _process_listings_for_submit(base, token, "DRAFT", candidates_by_sku)
        _write_progress({"stage": "rejected_phase", "draft_phase": {
            "enumerated_count": report["draft_phase"]["enumerated_count"],
            "submitted_count": report["draft_phase"]["submitted_count"],
            "blocked_count": report["draft_phase"]["blocked_count"],
        }})
        report["rejected_phase"] = _process_listings_for_submit(base, token, "REJECTED", candidates_by_sku)
        _write_progress({"stage": "inventory_sync_phase", "rejected_phase": {
            "enumerated_count": report["rejected_phase"]["enumerated_count"],
            "submitted_count": report["rejected_phase"]["submitted_count"],
            "blocked_count": report["rejected_phase"]["blocked_count"],
        }})
        report["inventory_sync_phase"] = _sync_uploaded_inventory(base, token, candidates_by_sku)
        report["finished_at"] = _utc_now_iso()
        report["next_steps"] = []
        if report["draft_phase"]["blocked_count"]:
            report["next_steps"].append("review draft listings that remain blocked after readiness checks")
        if report["rejected_phase"]["blocked_count"]:
            report["next_steps"].append("review rejected listings whose readiness still reports blockers")
        if report["inventory_sync_phase"]["processed_count"] == 0:
            report["next_steps"].append("no uploaded listing inventory drift detected in this cycle")
        OUTPUT_ROOT.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        json_path = OUTPUT_ROOT / f"neosgo-seller-maintenance-{stamp}.json"
        md_path = OUTPUT_ROOT / f"neosgo-seller-maintenance-{stamp}.md"
        _write_json(json_path, report)
        _write_markdown_report(report, md_path)
        _write_json(
            STATE_PATH,
            {
                "last_run_at": report["finished_at"],
                "last_report_json": str(json_path),
                "last_report_md": str(md_path),
                "candidate_summary": report["candidate_summary"],
                "candidate_scan_meta": report.get("candidate_scan_meta", {}),
                "import_phase": report["import_phase"]["bulk_state"],
                "draft_phase": {
                    "enumerated_count": report["draft_phase"]["enumerated_count"],
                    "submitted_count": report["draft_phase"]["submitted_count"],
                    "blocked_count": report["draft_phase"]["blocked_count"],
                },
                "rejected_phase": {
                    "enumerated_count": report["rejected_phase"]["enumerated_count"],
                    "submitted_count": report["rejected_phase"]["submitted_count"],
                    "blocked_count": report["rejected_phase"]["blocked_count"],
                },
                "inventory_sync_phase": {
                    "processed_count": report["inventory_sync_phase"]["processed_count"],
                    "patched_count": report["inventory_sync_phase"]["patched_count"],
                },
            },
        )
        print(json.dumps({"json": str(json_path), "md": str(md_path), "state": str(STATE_PATH)}, ensure_ascii=False))
        return 0
    finally:
        fcntl.flock(lock_handle.fileno(), fcntl.LOCK_UN)
        lock_handle.close()


if __name__ == "__main__":
    raise SystemExit(main())
