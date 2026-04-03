#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import math
import re
import subprocess
import sys
from pathlib import Path
from urllib.parse import urlparse, parse_qs, unquote_to_bytes

ROOT = Path("/Users/mac_claw/.openclaw/workspace")
VENV_PY = ROOT / "tools/matrix-venv/bin/python"

if sys.executable != str(VENV_PY) and VENV_PY.exists():
    try:
        import playwright  # type: ignore  # noqa: F401
    except Exception:
        raise SystemExit(subprocess.run([str(VENV_PY), __file__, *sys.argv[1:]]).returncode)

from playwright.sync_api import sync_playwright
from playwright_stealth import Stealth


DEFAULT_CDP = "http://127.0.0.1:18800"
OUT_DIR = ROOT / "output/cross-market-arbitrage-engine/1688"
OUT_DIR.mkdir(parents=True, exist_ok=True)
STATE_DIR = ROOT / ".state"
STATE_DIR.mkdir(parents=True, exist_ok=True)
DEFAULT_STATE_PATH = STATE_DIR / "1688-authorized-storage-state.json"

GATE_MARKERS = [
    "login.taobao.com",
    "login.1688.com",
    "member/signin",
    "短信登录",
    "密码登录",
    "请按住滑块",
    "punish",
    "x5secdata",
    "nocaptcha",
]

SESSION_DOMAINS = ("1688.com", "taobao.com", "alibaba.com", "alicdn.com")
VALID_SAME_SITE = {"Lax", "None", "Strict"}
SEARCH_INPUT_SELECTORS = [
    'input[name="keywords"]',
    'input[name="SearchText"]',
    'input[placeholder*="搜索"]',
    'input[type="text"]',
]
SEARCH_BUTTON_SELECTORS = [
    'button:has-text("搜索")',
    'input[type="submit"]',
    '.search-button',
    '.h1688-header-search-right button',
]
RESULT_TEXT_MARKERS = (
    "采购助手",
    "年销量:",
    "回头率",
    "开店:",
    "月代销:",
    "支持面单:",
    "48h揽收:",
    "后天达",
    "明天达",
    "退货包运费",
)
COMPANY_SUFFIXES = ("有限公司", "商行", "工厂", "集团", "经营部", "厂", "中心", "店")
BAD_COMPANY_PREFIXES = ("找", "搜", "批量", "全部", "热门", "最近")
NOISE_LINE_MARKERS = (
    "热门搜索",
    "最近搜索",
    "全部类目",
    "批量找货",
    "精选货源",
    "采购助手",
    "趋势",
    "类目:",
    "年销量:",
    "月代销:",
    "48h揽收:",
    "支持面单:",
    "上架日期:",
    "评论数:",
    "开店:",
    "明天达",
    "后天达",
    "包邮",
    "回头率",
    "同行都在采",
)


def _signals(final_url: str, title: str, text: str, html: str) -> dict[str, object]:
    gate_blob = "\n".join([final_url, title, text[:12000]]).lower()
    gated = any(marker.lower() in gate_blob for marker in GATE_MARKERS)
    offer_links = html.lower().count("/offer/")
    detail_links = html.lower().count("detail.1688.com")
    marker_hits = sum(text.count(marker) for marker in RESULT_TEXT_MARKERS)
    text_result_like = marker_hits >= 3
    return {
        "gated": gated,
        "offer_link_hits": offer_links,
        "detail_link_hits": detail_links,
        "result_marker_hits": marker_hits,
        "text_result_like": text_result_like,
        "has_search_results": ((offer_links + detail_links) > 0 or text_result_like) and not gated,
        "usable_search_page": (((offer_links + detail_links) > 0) or text_result_like) and not gated and len(text.strip()) > 120,
    }


def _normalize_cookie(item: dict[str, object]) -> dict[str, object] | None:
    name = str(item.get("name") or "").strip()
    value = str(item.get("value") or "")
    domain = str(item.get("domain") or "").strip()
    path = str(item.get("path") or "/").strip() or "/"
    if not name or not value or not domain:
        return None
    if not any(token in domain for token in SESSION_DOMAINS):
        return None
    if not path.startswith("/"):
        path = "/" + path.lstrip("/")
    same_site = str(item.get("sameSite") or "Lax").strip() or "Lax"
    if same_site not in VALID_SAME_SITE:
        same_site = "Lax"
    expires = item.get("expires", -1)
    try:
        expires_value = float(expires)
    except Exception:
        expires_value = -1
    if math.isnan(expires_value) or math.isinf(expires_value):
        expires_value = -1
    return {
        "name": name,
        "value": value,
        "domain": domain,
        "path": path,
        "expires": expires_value,
        "httpOnly": bool(item.get("httpOnly", False)),
        "secure": bool(item.get("secure", False)),
        "sameSite": same_site,
    }


def _filter_storage_state(raw: dict[str, object]) -> dict[str, object]:
    cookies = []
    for item in list(raw.get("cookies") or []):
        if not isinstance(item, dict):
            continue
        normalized = _normalize_cookie(item)
        if normalized:
            cookies.append(normalized)
    origins = []
    for item in list(raw.get("origins") or []):
        origin = str((item or {}).get("origin") or "")
        if any(token in origin for token in SESSION_DOMAINS):
            origins.append(item)
    return {"cookies": cookies, "origins": origins}


def _capture_storage_state(context, state_path: Path) -> dict[str, object]:
    try:
        raw_state = context.storage_state()
    except Exception as exc:
        return {"ok": False, "error": str(exc)}
    filtered = _filter_storage_state(raw_state if isinstance(raw_state, dict) else {})
    try:
        state_path.write_text(json.dumps(filtered, ensure_ascii=False, indent=2), encoding="utf-8")
    except OSError as exc:
        return {"ok": False, "error": str(exc)}
    return {
        "ok": True,
        "path": str(state_path),
        "cookie_count": len(filtered.get("cookies") or []),
        "origin_count": len(filtered.get("origins") or []),
    }


def _collect_page_payload(page, *, wait_seconds: float) -> dict[str, object]:
    api_events: list[dict[str, object]] = []

    def record_response(response) -> None:
        resp_url = str(response.url or "")
        lowered = resp_url.lower()
        if not any(
            marker in lowered
            for marker in (
                "h5api.wapa.1688.com",
                "h5api.m.1688.com",
                "offer_search",
                "mtop",
                "search",
            )
        ):
            return
        content_type = str(response.headers.get("content-type", ""))
        body = ""
        try:
            if "json" in content_type.lower() or "/mtop." in lowered or "h5api." in lowered:
                body = response.text()
            elif "javascript" in content_type.lower() or "html" in content_type.lower():
                body = response.text()
        except Exception:
            body = ""
        body = str(body or "")[:12000]
        offer_hits = len(re.findall(r"/offer/", body, flags=re.I))
        detail_hits = len(re.findall(r"detail\\.1688\\.com", body, flags=re.I))
        api_events.append(
            {
                "url": resp_url,
                "status": response.status,
                "content_type": content_type,
                "offer_hits": offer_hits,
                "detail_hits": detail_hits,
                "body": body,
            }
        )

    page.on("response", record_response)
    page.wait_for_timeout(max(0, int(wait_seconds * 1000)))
    final_url = page.url
    title = page.title()
    try:
        visible_text = page.locator("body").inner_text(timeout=3000)
    except Exception:
        visible_text = ""
    try:
        html = page.content()
    except Exception:
        html = ""
    decoded_query = _decode_1688_query(final_url)
    result_rows = _extract_result_rows(visible_text, decoded_query)
    signals = {
        **_signals(final_url, title, visible_text, html),
        "network_event_count": len(api_events),
        "network_offer_hits": sum(int(item.get("offer_hits") or 0) for item in api_events),
        "network_detail_hits": sum(int(item.get("detail_hits") or 0) for item in api_events),
        "network_result_like": any(
            (int(item.get("offer_hits") or 0) + int(item.get("detail_hits") or 0)) > 0 for item in api_events
        ),
    }
    home_like = final_url.rstrip("/") == "https://www.1688.com" or "阿里1688首页" in title
    search_like = "offer_search" in final_url or "selloffer" in final_url or (decoded_query and decoded_query in title)
    if result_rows:
        signals["has_search_results"] = True
        signals["usable_search_page"] = True
    elif home_like and not search_like:
        signals["has_search_results"] = False
        signals["usable_search_page"] = False
    return {
        "url": final_url,
        "title": title,
        "visible_text": visible_text,
        "html": html,
        "signals": signals,
        "network_events": api_events[:20],
        "result_rows": result_rows,
    }


def _decode_1688_query(url: str) -> str:
    raw = parse_qs(urlparse(url).query).get("keywords", [""])[0]
    if not raw:
        return ""
    try:
        return unquote_to_bytes(raw).decode("gb18030", "ignore").strip()
    except Exception:
        return raw.strip()


def _looks_like_offer_title(line: str, query: str) -> bool:
    text = str(line or "").strip()
    if len(text) < 8 or len(text) > 90:
        return False
    if "锟斤拷" in text:
        return False
    if any(marker in text for marker in NOISE_LINE_MARKERS):
        return False
    if text.endswith(COMPANY_SUFFIXES):
        return False
    if re.fullmatch(r"[0-9A-Za-z .,+-]+", text):
        return False
    if "¥" in text or "件" in text:
        return False
    query_tokens = [token for token in re.findall(r"[\u4e00-\u9fff]{1,4}", query) if len(token) >= 2]
    if query_tokens and sum(1 for token in query_tokens if token in text) >= max(1, min(2, len(query_tokens))):
        return True
    product_markers = ("收纳", "抽屉", "隔板", "分隔", "置物", "整理", "盒", "架", "板", "柜")
    return sum(1 for token in product_markers if token in text) >= 2


def _extract_price_hint(block: str) -> float | None:
    found = re.search(r"¥\s*([0-9]+)\s*(?:\.\s*([0-9]+))?", block)
    if not found:
        return None
    raw = found.group(1)
    if found.group(2):
        raw += "." + found.group(2)
    try:
        return float(raw)
    except Exception:
        return None


def _extract_sales_hint(block: str) -> str:
    for pattern in (r"售\s*([0-9.]+万?\+?)\s*件", r"年销量:\s*([0-9.]+万?\+?)件"):
        found = re.search(pattern, block)
        if found:
            return str(found.group(1))
    return ""


def _extract_result_rows(text: str, query: str) -> list[dict[str, object]]:
    lines = [line.strip() for line in str(text or "").splitlines() if line.strip()]

    def collect(effective_query: str) -> list[dict[str, object]]:
        rows: list[dict[str, object]] = []
        seen_titles: set[str] = set()
        for idx, line in enumerate(lines):
            if not line.endswith(COMPANY_SUFFIXES):
                continue
            if any(line.startswith(prefix) for prefix in BAD_COMPANY_PREFIXES):
                continue
            company = line
            start = max(0, idx - 14)
            window = lines[start : idx + 1]
            title = ""
            for candidate in reversed(window[:-1]):
                if _looks_like_offer_title(candidate, effective_query):
                    title = candidate
                    break
            if not title or title in seen_titles:
                continue
            block = "\n".join(window)
            rows.append(
                {
                    "title": title,
                    "price_cny": _extract_price_hint(block),
                    "sales_hint": _extract_sales_hint(block),
                    "company": company,
                    "excerpt": block[:600],
                }
            )
            seen_titles.add(title)
            if len(rows) >= 12:
                break
        return rows

    rows = collect(query)
    if rows:
        return rows
    return collect("")


def _interactive_search(page, *, query: str, wait_seconds: float) -> dict[str, object] | None:
    if not query:
        return None
    page.goto("https://www.1688.com/", wait_until="domcontentloaded", timeout=15000)
    page.wait_for_timeout(1800)
    used_selector = ""
    for selector in SEARCH_INPUT_SELECTORS:
        try:
            page.locator(selector).first.fill(query, timeout=2000)
            used_selector = selector
            break
        except Exception:
            continue
    if not used_selector:
        return None
    page.wait_for_timeout(400)
    clicked = False
    for selector in SEARCH_BUTTON_SELECTORS:
        try:
            page.locator(selector).first.click(timeout=1500)
            clicked = True
            break
        except Exception:
            continue
    if not clicked:
        try:
            page.locator(used_selector).first.press("Enter")
        except Exception:
            page.keyboard.press("Enter")
    payload = _collect_page_payload(page, wait_seconds=wait_seconds + 1.5)
    payload["interactive_search"] = {
        "ok": True,
        "query": query,
        "input_selector": used_selector,
        "clicked_button": clicked,
    }
    payload["fetch_mode"] = "cdp_interactive_search"
    return payload


def fetch_page(*, cdp_url: str, url: str, wait_seconds: float, state_path: Path) -> dict[str, object]:
    with sync_playwright() as p:
        browser = p.chromium.connect_over_cdp(cdp_url)
        context = browser.contexts[0] if browser.contexts else browser.new_context()
        state_capture = _capture_storage_state(context, state_path)
        page = context.new_page()
        Stealth().apply_stealth_sync(page)
        page.goto(url, wait_until="domcontentloaded", timeout=15000)
        payload = _collect_page_payload(page, wait_seconds=wait_seconds)
        query = _decode_1688_query(url)
        if not bool((payload.get("signals") or {}).get("usable_search_page")) and query:
            interactive_payload = _interactive_search(page, query=query, wait_seconds=wait_seconds)
            if interactive_payload is not None:
                payload["interactive_attempt"] = {
                    "ok": True,
                    "signals": interactive_payload.get("signals") or {},
                    "fetch_mode": interactive_payload.get("fetch_mode"),
                }
                if bool((interactive_payload.get("signals") or {}).get("usable_search_page")):
                    payload = interactive_payload
            else:
                payload["interactive_attempt"] = {"ok": False, "reason": "query_or_input_unavailable"}
        page.close()
    payload["state_capture"] = state_capture
    payload.setdefault("fetch_mode", "cdp_live")
    return payload


def replay_with_state(*, url: str, wait_seconds: float, state_path: Path) -> dict[str, object]:
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(storage_state=str(state_path))
        page = context.new_page()
        Stealth().apply_stealth_sync(page)
        page.goto(url, wait_until="domcontentloaded", timeout=15000)
        payload = _collect_page_payload(page, wait_seconds=wait_seconds)
        page.close()
        browser.close()
    payload["fetch_mode"] = "state_replay"
    payload["state_capture"] = {
        "ok": True,
        "path": str(state_path),
    }
    return payload


def main() -> int:
    parser = argparse.ArgumentParser(description="Fetch 1688 page through current logged-in Chrome session via CDP")
    parser.add_argument("--url", required=True)
    parser.add_argument("--cdp", default=DEFAULT_CDP)
    parser.add_argument("--wait-seconds", type=float, default=3.0)
    parser.add_argument("--save-prefix", default="latest")
    parser.add_argument("--state-path", default=str(DEFAULT_STATE_PATH))
    parser.add_argument("--replay-if-gated", action="store_true")
    args = parser.parse_args()

    state_path = Path(args.state_path)
    payload = fetch_page(cdp_url=args.cdp, url=args.url, wait_seconds=args.wait_seconds, state_path=state_path)
    if args.replay_if_gated and bool((payload.get("signals") or {}).get("gated")) and state_path.exists():
        try:
            replay_payload = replay_with_state(url=args.url, wait_seconds=args.wait_seconds, state_path=state_path)
            payload["replay_attempt"] = {
                "ok": True,
                "signals": replay_payload.get("signals") or {},
                "fetch_mode": replay_payload.get("fetch_mode"),
            }
            if bool((replay_payload.get("signals") or {}).get("usable_search_page")):
                payload = replay_payload
        except Exception as exc:
            payload["replay_attempt"] = {"ok": False, "error": str(exc)}
    prefix = OUT_DIR / args.save_prefix
    (prefix.with_suffix(".txt")).write_text(str(payload.get("visible_text") or ""), encoding="utf-8")
    (prefix.with_suffix(".html")).write_text(str(payload.get("html") or ""), encoding="utf-8")
    (prefix.with_suffix(".json")).write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    result = {
        "url": payload["url"],
        "title": payload["title"],
        "signals": payload["signals"],
        "result_rows": payload.get("result_rows") or [],
        "network_events": payload.get("network_events") or [],
        "state_capture": payload.get("state_capture") or {},
        "replay_attempt": payload.get("replay_attempt") or {},
        "fetch_mode": payload.get("fetch_mode"),
        "text_path": str(prefix.with_suffix(".txt")),
        "html_path": str(prefix.with_suffix(".html")),
        "json_path": str(prefix.with_suffix(".json")),
    }
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
