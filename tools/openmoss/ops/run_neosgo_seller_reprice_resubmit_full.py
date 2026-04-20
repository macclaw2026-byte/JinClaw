#!/usr/bin/env python3
# RULES-FIRST NOTICE:
# Before modifying this file, first read:
# - `JINCLAW_CONSTITUTION.md`
# - `AI_OPTIMIZATION_FRAMEWORK.md`
# Follow the constitution and framework:
# brain-first, one-doctor, fail-closed, evidence-over-narration,
# validate locally, then use the required PR workflow.
from __future__ import annotations

import importlib.util
import json
import time
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


WORKSPACE_ROOT = Path("/Users/mac_claw/.openclaw/workspace")
RUNNER_PATH = WORKSPACE_ROOT / "tools/bin/neosgo-seller-bulk-runner.py"
OUTPUT_ROOT = WORKSPACE_ROOT / "output/neosgo-seller-reprice-resubmit"
STATE_PATH = WORKSPACE_ROOT / "data/neosgo-seller-reprice-resubmit-state.json"
PAGE_SIZE = 100
MAX_PAGES = 50
SLEEP_SECONDS = 0.25
APPROVED_CHANGE_REQUEST_REASON = (
    "Align retail price to the bulk import template price plus 25 USD after the pricing rule correction."
)


def _load_module(path: Path, module_name: str):
    spec = importlib.util.spec_from_file_location(module_name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader is not None
    spec.loader.exec_module(module)
    return module


RUNNER = _load_module(RUNNER_PATH, "neosgo_seller_bulk_runner")


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _parse_float(value: Any) -> float | None:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    return parsed


def _fetch_all_listings(base: str, token: str) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for page in range(1, MAX_PAGES + 1):
        payload = RUNNER.request_with_retry(
            "GET",
            base,
            token,
            f"/api/automation/seller/listings?page={page}&pageSize={PAGE_SIZE}",
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
        total = int(data.get("total") or 0)
        page_size = int(data.get("pageSize") or PAGE_SIZE)
        if total > 0 and page * page_size >= total:
            break
    return rows


def _fetch_listing_detail(base: str, token: str, product_id: str) -> dict[str, Any]:
    detail = RUNNER.request("GET", base, token, f"/api/automation/seller/listings/{product_id}")
    data = detail.get("data", {}) or {}
    return data.get("listing", data)


def _fetch_readiness(base: str, token: str, product_id: str) -> dict[str, Any]:
    return RUNNER.request_with_retry(
        "GET",
        base,
        token,
        f"/api/automation/seller/listings/{product_id}/readiness",
        attempts=2,
        sleep_seconds=0.5,
        timeout=30,
    )


def _submit_listing(base: str, token: str, product_id: str) -> dict[str, Any]:
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


def _patch_price(
    base: str,
    token: str,
    product_id: str,
    price: float,
    *,
    change_request_reason: str | None = None,
) -> dict[str, Any]:
    payload: dict[str, Any] = {"basePrice": price}
    if change_request_reason:
        payload["changeRequestReason"] = str(change_request_reason).strip()
    return RUNNER.request_with_retry(
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


def _requires_approved_change_request(row: dict[str, Any]) -> bool:
    status = str(row.get("status") or "").strip().upper()
    return not bool(row.get("editable_via_automation")) and bool(row.get("is_active")) and status in {"APPROVED", "PENDING"}


def _is_bulk_import_listing(item: dict[str, Any]) -> bool:
    source = str(item.get("source") or "").strip().upper()
    original_platform = str(item.get("originalPlatform") or "").strip().lower()
    return source == "GIGA" or original_platform == "gigacloud" or bool(item.get("gigaImportedListing"))


def _write_markdown_report(report: dict[str, Any], path: Path) -> None:
    lines = [
        "# Neosgo Seller Full Reprice And Resubmit",
        "",
        f"- Started: {report.get('started_at')}",
        f"- Finished: {report.get('finished_at')}",
        f"- Enumerated bulk-import listings: {report.get('summary', {}).get('enumerated_bulk_import_count', 0)}",
        f"- Missing price baseline: {report.get('summary', {}).get('missing_price_baseline_count', 0)}",
        f"- Editable listings: {report.get('summary', {}).get('editable_count', 0)}",
        f"- Platform-blocked listings: {report.get('summary', {}).get('noneditable_count', 0)}",
        f"- Approved change requests patched: {report.get('summary', {}).get('approved_change_request_patch_count', 0)}",
        f"- Price patched: {report.get('summary', {}).get('patched_count', 0)}",
        f"- Price already correct: {report.get('summary', {}).get('already_desired_price_count', 0)}",
        f"- Submit attempted: {report.get('summary', {}).get('submit_attempt_count', 0)}",
        f"- Submit succeeded: {report.get('summary', {}).get('submit_ok_count', 0)}",
        "",
        "## Status Counts",
        "",
    ]
    for key, value in sorted((report.get("summary", {}).get("status_counts") or {}).items()):
        lines.append(f"- {key}: {value}")
    lines.extend(
        [
            "",
            "## Blocking Reasons",
            "",
        ]
    )
    for key, value in sorted((report.get("summary", {}).get("blocking_reason_counts") or {}).items()):
        lines.append(f"- {key}: {value}")
    lines.extend(
        [
            "",
            "## Sample Rows",
            "",
        ]
    )
    for row in (report.get("rows") or [])[:20]:
        lines.append(
            "- "
            + f"SKU `{row.get('sku')}` | status={row.get('status')} | active={row.get('is_active')} | "
            + f"original_price={row.get('originalPrice')} | baseline_source={row.get('price_baseline_source')} | template_price={row.get('template_price_usd')} | "
            + f"desired_submit_price={row.get('desired_submission_price_usd')} | route={row.get('price_update_route', '') or 'none'} | patch_ok={row.get('patch_ok')} | "
            + f"can_submit={row.get('can_submit')} | submit_ok={row.get('submit_ok')} | blocker={row.get('blocking_reason') or row.get('error')}"
        )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    env = RUNNER.load_env(RUNNER.SECRET_PATH)
    base = env["NEOSGO_SELLER_API_BASE_URL"]
    token = env["NEOSGO_SELLER_AUTOMATION_KEY"]
    started_at = _utc_now_iso()
    report: dict[str, Any] = {
        "started_at": started_at,
        "workflow": "neosgo_seller_full_reprice_resubmit",
        "price_rule": {
            "baseline_source_priority": [
                "historical bulk submission report",
                "live approved listing retail/base price",
                "live submitted/draft original bulk import price",
            ],
            "submission_markup_usd": RUNNER.PRICE_MARKUP_USD,
            "fail_closed_when_missing_price_baseline": True,
            "approved_listing_change_request_patch": {
                "field": "basePrice",
                "reason_field": "changeRequestReason",
                "requires_reason": True,
                "creates_pending_change_request": True,
                "reason": APPROVED_CHANGE_REQUEST_REASON,
            },
        },
        "rows": [],
    }
    _write_json(STATE_PATH, {"stage": "enumerate_listings", "updated_at": started_at})
    listings = [item for item in _fetch_all_listings(base, token) if _is_bulk_import_listing(item)]
    for index, item in enumerate(listings, start=1):
        product_id = str(item.get("id") or "").strip()
        sku = str(item.get("sku") or "").strip()
        if not product_id or not sku:
            continue
        row: dict[str, Any] = {
            "index": index,
            "product_id": product_id,
            "sku": sku,
            "status": item.get("status"),
            "review_status": item.get("reviewStatus"),
            "is_active": bool(item.get("isActive")),
            "source": item.get("source"),
            "originalPlatform": item.get("originalPlatform"),
        }
        try:
            listing = _fetch_listing_detail(base, token, product_id)
            pricing = listing.get("pricing") or {}
            row["originalPrice"] = listing.get("originalPrice")
            row["platformUnitCost"] = pricing.get("platformUnitCost")
            row["retailUnitPrice"] = pricing.get("retailUnitPrice")
            row["current_base_price"] = listing.get("basePrice")
            row["current_price"] = listing.get("price")
            row["editable_via_automation"] = bool(listing.get("editableViaAutomation"))
            row["inventory_editable_via_automation"] = bool(listing.get("inventoryEditableViaAutomation"))
            try:
                desired_submission_price, baseline = RUNNER.resolve_submission_price(
                    listing,
                    product_id=product_id,
                    sku=sku,
                    prefer_active_noneditable=_requires_approved_change_request(row),
                )
                template_price = round(desired_submission_price - RUNNER.PRICE_MARKUP_USD, 2)
            except ValueError as exc:
                row["error"] = str(exc)
                row["blocking_reason"] = "missing_price_baseline"
                report["rows"].append(row)
                _write_json(STATE_PATH, {"stage": "repricing", "updated_at": _utc_now_iso(), "last_sku": sku, "processed_count": len(report["rows"])})
                time.sleep(SLEEP_SECONDS)
                continue

            row["template_price_usd"] = template_price
            row["desired_submission_price_usd"] = desired_submission_price
            row["price_baseline_source"] = baseline.get("source")
            current_base_price = _parse_float(listing.get("basePrice"))
            row["price_already_desired"] = current_base_price is not None and abs(current_base_price - desired_submission_price) < 0.011

            if row["price_already_desired"]:
                row["patch_ok"] = True
                row["patch_skipped"] = "already_at_desired_price"
                row["price_update_route"] = "no_change_required"
            elif row["editable_via_automation"]:
                row["price_update_route"] = "automation_listing_patch"
                if row["price_already_desired"]:
                    row["patch_ok"] = True
                    row["patch_skipped"] = "already_at_desired_price"
                else:
                    patch = _patch_price(base, token, product_id, desired_submission_price)
                    row["patch_ok"] = bool(patch.get("ok"))
                    if not patch.get("ok"):
                        row["error"] = RUNNER.extract_request_error_message("patch", patch)
                        row["blocking_reason"] = "patch_failed"
                    else:
                        row["patched_price_to"] = desired_submission_price
            elif _requires_approved_change_request(row):
                row["price_update_route"] = "automation_price_change_request"
                row["price_change_reason"] = APPROVED_CHANGE_REQUEST_REASON
                patch = _patch_price(
                    base,
                    token,
                    product_id,
                    desired_submission_price,
                    change_request_reason=APPROVED_CHANGE_REQUEST_REASON,
                )
                row["patch_ok"] = bool(patch.get("ok"))
                if not patch.get("ok"):
                    row["error"] = RUNNER.extract_request_error_message("approved_change_request_patch", patch)
                    row["blocking_reason"] = "approved_change_request_patch_failed"
                else:
                    patch_data = ((patch.get("resp") or {}).get("data", {}) or {})
                    row["change_request_created"] = bool(patch_data.get("changeRequestCreated"))
                    row["direct_changes_applied"] = bool(patch_data.get("directChangesApplied"))
                    row["patched_price_to"] = desired_submission_price
            else:
                row["patch_ok"] = False
                row["blocking_reason"] = "listing_not_editable_via_automation"
                row["price_update_route"] = "blocked_before_patch"

            readiness = _fetch_readiness(base, token, product_id)
            row["readiness_ok"] = bool(readiness.get("ok"))
            if readiness.get("ok"):
                readiness_data = ((readiness.get("resp") or {}).get("data", {}) or {}).get("submissionReadiness", {}) or {}
                row["can_submit"] = bool(readiness_data.get("canSubmit"))
                row["blocking_issue_codes"] = readiness_data.get("issueCodes") or []
                row["blocking_issues"] = readiness_data.get("issues") or []
            else:
                row["error"] = row.get("error") or RUNNER.extract_request_error_message("readiness", readiness)
                row["blocking_reason"] = row.get("blocking_reason") or "readiness_failed"

            if row.get("patch_ok") and row.get("can_submit"):
                submit = _submit_listing(base, token, product_id)
                row["submit_ok"] = bool(submit.get("ok"))
                if submit.get("ok"):
                    submit_data = ((submit.get("resp") or {}).get("data", {}) or {})
                    row["final_status"] = submit_data.get("status")
                    row["final_review_status"] = submit_data.get("reviewStatus")
                else:
                    row["error"] = RUNNER.extract_request_error_message("submit", submit)
                    row["blocking_reason"] = "submit_failed"
            else:
                row["submit_ok"] = False
                if not row.get("blocking_reason") and not row.get("can_submit"):
                    row["blocking_reason"] = "submission_not_allowed_by_readiness"
        except Exception as exc:
            row["exception"] = repr(exc)
            row["error"] = row.get("error") or repr(exc)
            row["blocking_reason"] = row.get("blocking_reason") or "exception"
        report["rows"].append(row)
        _write_json(
            STATE_PATH,
            {
                "stage": "repricing",
                "updated_at": _utc_now_iso(),
                "last_sku": sku,
                "processed_count": len(report["rows"]),
                "enumerated_bulk_import_count": len(listings),
            },
        )
        time.sleep(SLEEP_SECONDS)

    status_counts = Counter(str(row.get("status") or "UNKNOWN") for row in report["rows"])
    blocking_reason_counts = Counter(str(row.get("blocking_reason") or "") for row in report["rows"] if row.get("blocking_reason"))
    report["finished_at"] = _utc_now_iso()
    report["summary"] = {
        "enumerated_bulk_import_count": len(report["rows"]),
        "status_counts": dict(status_counts),
        "blocking_reason_counts": dict(blocking_reason_counts),
        "missing_price_baseline_count": sum(1 for row in report["rows"] if row.get("blocking_reason") == "missing_price_baseline"),
        "editable_count": sum(1 for row in report["rows"] if row.get("editable_via_automation")),
        "noneditable_count": sum(1 for row in report["rows"] if row.get("blocking_reason") == "listing_not_editable_via_automation"),
        "approved_change_request_patch_count": sum(1 for row in report["rows"] if row.get("price_update_route") == "automation_price_change_request" and row.get("patch_ok")),
        "patched_count": sum(1 for row in report["rows"] if row.get("patched_price_to") is not None),
        "already_desired_price_count": sum(1 for row in report["rows"] if row.get("patch_skipped") == "already_at_desired_price"),
        "submit_attempt_count": sum(1 for row in report["rows"] if row.get("patch_ok") and row.get("can_submit")),
        "submit_ok_count": sum(1 for row in report["rows"] if row.get("submit_ok")),
    }
    OUTPUT_ROOT.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    json_path = OUTPUT_ROOT / f"neosgo-seller-reprice-resubmit-{stamp}.json"
    md_path = OUTPUT_ROOT / f"neosgo-seller-reprice-resubmit-{stamp}.md"
    _write_json(json_path, report)
    _write_markdown_report(report, md_path)
    _write_json(
        STATE_PATH,
        {
            "stage": "done",
            "updated_at": report["finished_at"],
            "last_report_json": str(json_path),
            "last_report_md": str(md_path),
            "summary": report["summary"],
        },
    )
    print(json.dumps({"json": str(json_path), "md": str(md_path), "state": str(STATE_PATH)}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
