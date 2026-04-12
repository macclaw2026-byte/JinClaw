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
import shutil
import subprocess
import sys
import time
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path("/Users/mac_claw/.openclaw/workspace")
VENV_PY = ROOT / "tools/matrix-venv/bin/python"
PROJECT_ROOT = ROOT / "projects/amazon-product-selection-engine"
DEFAULT_CDP = "http://127.0.0.1:9222"
PRODUCT_RESEARCH_BASE = "https://www.sellersprite.com/v3/product-research"
EXPORT_LOG_URL = "https://www.sellersprite.com/v2/export-log"
DEFAULT_OUTPUT_DIR = ROOT / "data/amazon-product-selection/seller-sprite"
DEFAULT_VALIDATION_REPORT = PROJECT_ROOT / "reports/stage1-real-export-validation.json"


def _load_sync_playwright():
    try:
        from playwright.sync_api import sync_playwright  # type: ignore
    except Exception:
        if __name__ == "__main__" and sys.executable != str(VENV_PY) and VENV_PY.exists():
            raise SystemExit(subprocess.run([str(VENV_PY), __file__, *sys.argv[1:]], check=False).returncode)
        raise
    return sync_playwright


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _log(enabled: bool, message: str) -> None:
    if enabled:
        print(f"[stage1] {message}", file=sys.stderr, flush=True)


def build_product_research_url(
    market: str = "US",
    month_name: str = "bsr_sales_nearly",
    seller_types: list[str] | None = None,
    pkg_dimension_types: list[str] | None = None,
) -> str:
    params = {
        "market": market,
        "page": "1",
        "size": "60",
        "symbolFlag": "true",
        "monthName": month_name,
        "selectType": "2",
        "filterSub": "false",
        "weightUnit": "g",
        "order[field]": "amz_unit",
        "order[desc]": "true",
        "productTags": "[]",
        "nodeIdPaths": "[]",
        "sellerTypes": json.dumps(seller_types or ["FBM"], separators=(",", ":")),
        "eligibility": "[]",
        "pkgDimensionTypeList": json.dumps(pkg_dimension_types or ["LS"], separators=(",", ":")),
        "sellerNationList": "[]",
        "lowPrice": "N",
        "video": "",
    }
    return f"{PRODUCT_RESEARCH_BASE}?{urllib.parse.urlencode(params)}"


def _page_with_prefix(context, prefix: str):
    for page in context.pages:
        if page.url.startswith(prefix):
            return page
    return context.new_page()


def _goto(page, url: str) -> None:
    last_error = None
    for _ in range(2):
        try:
            page.goto(url, wait_until="domcontentloaded", timeout=60000)
            return
        except Exception as exc:  # noqa: BLE001
            last_error = exc
            if "ERR_ABORTED" not in str(exc):
                break
            page.wait_for_timeout(1000)
    raise RuntimeError(f"could not navigate to {url}: {last_error}") from last_error


def _click_named_action(page, label: str) -> bool:
    candidates = [
        page.get_by_role("button", name=label),
        page.get_by_role("link", name=label),
        page.get_by_text(label, exact=True),
        page.locator(f"text={label}"),
    ]
    for locator in candidates:
        try:
            if locator.count() == 0:
                continue
            locator.first.click(timeout=5000)
            page.wait_for_timeout(1000)
            return True
        except Exception:
            continue
    return False


def _latest_export_href(page) -> str:
    anchors = page.locator("a[href$='.xlsx']")
    count = anchors.count()
    for index in range(count):
        href = anchors.nth(index).get_attribute("href")
        if href and "/batch-exports/" in href:
            return href
    return ""


def _download_export(href: str, output_dir: Path) -> dict[str, str]:
    output_dir.mkdir(parents=True, exist_ok=True)
    file_name = Path(urllib.parse.urlparse(href).path).name or f"seller-sprite-export-{int(time.time())}.xlsx"
    raw_path = output_dir / file_name
    latest_path = output_dir / "latest-export.xlsx"
    with urllib.request.urlopen(href) as response, raw_path.open("wb") as handle:
        shutil.copyfileobj(response, handle)
    shutil.copyfile(raw_path, latest_path)
    return {
        "raw_path": str(raw_path),
        "latest_path": str(latest_path),
        "file_name": file_name,
    }


def run_stage1_export(
    cdp_url: str,
    output_dir: Path,
    preset_label: str,
    poll_seconds: int,
    poll_interval_seconds: int,
    verbose: bool = False,
) -> dict[str, object]:
    product_url = build_product_research_url()
    sync_playwright = _load_sync_playwright()
    with sync_playwright() as playwright:
        _log(verbose, f"connecting to Chrome CDP at {cdp_url}")
        browser = playwright.chromium.connect_over_cdp(cdp_url)
        if not browser.contexts:
            raise RuntimeError("no browser context available on the connected Chrome session")
        context = browser.contexts[0]
        product_page = context.new_page()
        export_page = context.new_page()

        try:
            _log(verbose, "opening My Exported Data")
            _goto(export_page, EXPORT_LOG_URL)
            export_page.wait_for_timeout(1000)
            before_href = _latest_export_href(export_page)
            _log(verbose, f"latest existing export: {before_href or 'none'}")

            _log(verbose, "opening Product Research with canonical query")
            _goto(product_page, product_url)
            product_page.wait_for_timeout(2000)
            preset_clicked = _click_named_action(product_page, preset_label) if preset_label else False
            _log(verbose, f"preset clicked: {preset_clicked}")
            search_clicked = _click_named_action(product_page, "Search Now")
            if not search_clicked:
                raise RuntimeError("could not trigger Search Now on the SellerSprite Product Research page")
            _log(verbose, "Search Now triggered")
            product_page.wait_for_timeout(4000)
            export_clicked = _click_named_action(product_page, "Export")
            if not export_clicked:
                raise RuntimeError("could not trigger Export on the SellerSprite Product Research page")
            _log(verbose, "Export triggered")

            deadline = time.time() + poll_seconds
            latest_href = ""
            while time.time() < deadline:
                _log(verbose, "polling My Exported Data for a new completed export")
                _goto(export_page, EXPORT_LOG_URL)
                export_page.wait_for_timeout(1000)
                latest_href = _latest_export_href(export_page)
                if latest_href and latest_href != before_href:
                    _log(verbose, f"new export discovered: {latest_href}")
                    break
                time.sleep(poll_interval_seconds)

            if not latest_href or latest_href == before_href:
                raise RuntimeError("timed out waiting for a new completed Product Research export in My Exported Data")
        finally:
            product_page.close()
            export_page.close()

    download_info = _download_export(latest_href, output_dir)
    return {
        "status": "ok",
        "export_url": latest_href,
        "preset_clicked": preset_clicked,
        "search_clicked": search_clicked,
        "export_clicked": export_clicked,
        "downloaded_at": utc_now(),
        **download_info,
    }


def run_validator(input_path: Path, report_path: Path) -> None:
    report_path.parent.mkdir(parents=True, exist_ok=True)
    validator = PROJECT_ROOT / "scripts/validate_stage1_export.py"
    subprocess.run(
        [sys.executable, str(validator), "--input", str(input_path), "--report", str(report_path)],
        check=True,
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="Trigger the official SellerSprite stage 1 export and download the resulting xlsx artifact.")
    parser.add_argument("--cdp-url", default=DEFAULT_CDP, help="Chrome CDP endpoint exposed by the OpenClaw-controlled browser session.")
    parser.add_argument("--output-dir", default=str(DEFAULT_OUTPUT_DIR), help="Directory where the exported xlsx files should be saved.")
    parser.add_argument("--preset-label", default="中件FBM", help="Preferred SellerSprite preset label for the requested FBM medium-parcel mode.")
    parser.add_argument("--poll-seconds", type=int, default=90, help="Maximum time to wait for a new completed export.")
    parser.add_argument("--poll-interval-seconds", type=int, default=3, help="Refresh interval while waiting for a new export.")
    parser.add_argument("--report", default=str(DEFAULT_VALIDATION_REPORT), help="Path for the local validation report JSON.")
    parser.add_argument("--verbose", action="store_true", help="Print progress logs while the export flow runs.")
    args = parser.parse_args()

    output_dir = Path(args.output_dir).expanduser().resolve()
    report_path = Path(args.report).expanduser().resolve()

    try:
        result = run_stage1_export(
            cdp_url=args.cdp_url,
            output_dir=output_dir,
            preset_label=args.preset_label,
            poll_seconds=args.poll_seconds,
            poll_interval_seconds=args.poll_interval_seconds,
            verbose=args.verbose,
        )
        run_validator(Path(result["latest_path"]), report_path)
    except Exception as exc:  # noqa: BLE001
        payload = {
            "status": "error",
            "error": str(exc),
            "failed_at": utc_now(),
        }
        print(json.dumps(payload, ensure_ascii=True, indent=2))
        return 1

    payload = {
        **result,
        "validation_report": str(report_path),
    }
    print(json.dumps(payload, ensure_ascii=True, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
