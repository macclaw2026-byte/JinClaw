#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import math
import re
import subprocess
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable
from urllib.parse import quote_plus

from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill
from openpyxl.utils import get_column_letter


ROOT = Path("/Users/mac_claw/.openclaw/workspace")
STATE_DIR = ROOT / ".state"
STATE_DIR.mkdir(parents=True, exist_ok=True)
STATE_PATH = STATE_DIR / "cross-market-arbitrage-engine.json"
OUT_DIR = ROOT / "output" / "cross-market-arbitrage-engine"
OUT_DIR.mkdir(parents=True, exist_ok=True)

TOOLS_ROOT = ROOT / "tools"
CRAWL4AI = TOOLS_ROOT / "bin" / "crawl4ai"
AGENT_BROWSER = TOOLS_ROOT / "agent-browser-local" / "node_modules" / "agent-browser" / "bin" / "agent-browser-darwin-arm64"
VENV_PY = TOOLS_ROOT / "matrix-venv" / "bin" / "python"
SITE_PREFS_PATH = ROOT / "tools/openmoss/runtime/autonomy/learning/crawler_site_preferences.json"

DISCOVERY_INTERVAL_SECONDS = 30 * 60
MATCH_INTERVAL_SECONDS = 60 * 60
REPORT_TZ_OFFSET = -4  # New York summer target for this local rollout; can be upgraded to zoneinfo later.
REPORT_HOUR = 18

DEFAULT_DISCOVERY_QUERIES = [
    "drawer organizer",
    "cable clips",
    "wall hooks",
    "storage basket",
    "under sink organizer",
]

SELL_PLATFORM_SEARCH = {
    "temu": lambda q: f"https://www.temu.com/search_result.html?search_key={quote_plus(q)}",
    "amazon": lambda q: f"https://www.amazon.com/s?k={quote_plus(q)}",
    "walmart": lambda q: f"https://www.walmart.com/search?q={quote_plus(q)}",
}

SOURCE_PLATFORM_SEARCH = {
    "1688": lambda q: f"https://s.1688.com/selloffer/offer_search.htm?keywords={quote_plus(q)}",
    "yiwugo": lambda q: f"https://en.yiwugo.com/search/s.htm?q={quote_plus(q)}",
    "made_in_china": lambda q: (
        "https://www.made-in-china.com/productdirectory.do?"
        f"subaction=hunt&style=b&mode=and&code=0&comProvince=nolimit&order=0&isOpenCorrection=1&org=top&keyword=&file=&searchType=0&word={quote_plus(q)}"
    ),
}

BLOCK_PATTERNS = {
    "temu": [r"verify", r"captcha", r"login", r"access denied", r"unusual traffic"],
    "amazon": [r"captcha", r"robot check", r"automated access", r"sorry, we just need to make sure"],
    "walmart": [r"robot or human", r"confirm that you.?re human", r"activate and hold the button"],
    "1688": [r"登录", r"请按住滑块", r"短信登录", r"密码登录", r"punish", r"x5secdata", r"nocaptcha", r"unusual traffic"],
    "yiwugo": [r"captcha", r"forbidden", r"access denied"],
    "made_in_china": [r"captcha", r"access denied", r"forbidden"],
}

RESTRICTED_PATTERNS = [
    r"\bbattery\b",
    r"\blithium\b",
    r"\bli[- ]?ion\b",
    r"\brechargeable\b",
    r"\bliquid\b",
    r"\bgel\b",
    r"\bspray\b",
    r"\bcosmetic\b",
    r"\bserum\b",
    r"\bcream\b",
    r"\btoner\b",
    r"\bfood\b",
    r"\bsnack\b",
    r"\bdrink\b",
    r"\bmedicine\b",
    r"\bdrug\b",
    r"\bcapsule\b",
    r"化妆",
    r"食品",
    r"药",
    r"锂电",
    r"液体",
]

WEIGHT_PATTERNS = [
    r"(\d+(?:\.\d+)?)\s*(kg|公斤)",
    r"(\d+(?:\.\d+)?)\s*(g|克)",
    r"weight[^\\d]{0,10}(\d+(?:\.\d+)?)\s*(kg|g)",
    r"净重[^\\d]{0,10}(\d+(?:\.\d+)?)\s*(kg|g|公斤|克)",
    r"毛重[^\\d]{0,10}(\d+(?:\.\d+)?)\s*(kg|g|公斤|克)",
]

PRICE_PATTERNS = [
    r"\$(\d+(?:\.\d{2})?)",
    r"¥\s*(\d+(?:\.\d+)?)",
    r"US\\$ ?(\d+(?:\.\d+)?)",
]

TITLE_STOPWORDS = {
    "for",
    "the",
    "with",
    "and",
    "pack",
    "pcs",
    "piece",
    "pieces",
    "set",
    "sale",
    "new",
    "hot",
    "portable",
    "wireless",
    "home",
}


@dataclass
class FetchResult:
    platform: str
    tool: str
    status: str
    score: int
    text: str
    notes: str = ""


@dataclass
class DemandCandidate:
    candidate_id: str
    title: str
    sell_platform: str
    sell_link: str
    sell_price_cny: float | None
    query: str
    extracted_at: str
    raw_signals: dict[str, Any] = field(default_factory=dict)


@dataclass
class SourceCandidate:
    platform: str
    link: str
    title: str
    price_cny: float | None
    weight_kg: float | None
    weight_grade: str
    fetch_tool: str
    match_score: float
    blocked: bool = False
    notes: str = ""


@dataclass
class ArbitrageDecision:
    product_name: str
    buy_platform: str
    buy_link: str
    sell_platform: str
    sell_link: str
    sell_price_cny: float | None
    purchase_cost_cny: float | None
    weight_kg: float | None
    gross_profit_amount: float | None
    gross_margin_rate: float | None
    conservative_margin_rate: float | None
    confidence_score: float
    weight_grade: str
    qualified: bool
    reasons: list[str] = field(default_factory=list)


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _utc_now_iso() -> str:
    return _utc_now().isoformat()


def _ny_now() -> datetime:
    return _utc_now() + timedelta(hours=REPORT_TZ_OFFSET)


def _slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-") or "item"


def _run(cmd: list[str], *, timeout: int = 45) -> subprocess.CompletedProcess:
    try:
        return subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    except subprocess.TimeoutExpired as exc:
        return subprocess.CompletedProcess(
            cmd,
            124,
            stdout=(exc.stdout or ""),
            stderr=((exc.stderr or "") + f"\nTIMEOUT after {timeout}s").strip(),
        )


def _clean_text(text: str) -> str:
    return re.sub(r"\s+", " ", str(text or "")).strip()


def _normalize_title(text: str) -> str:
    tokens = re.findall(r"[a-z0-9]+", str(text or "").lower())
    return " ".join(token for token in tokens if token not in TITLE_STOPWORDS)


def _load_site_preferences() -> dict[str, Any]:
    if not SITE_PREFS_PATH.exists():
        return {}
    try:
        return json.loads(SITE_PREFS_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _fetch_direct_http(url: str) -> tuple[str, str]:
    code = (
        "import sys,urllib.request; "
        "u=sys.argv[1]; "
        "req=urllib.request.Request(u, headers={'User-Agent':'Mozilla/5.0'}); "
        "resp=urllib.request.urlopen(req, timeout=30); "
        "print(resp.read().decode('utf-8','ignore')[:400000])"
    )
    proc = _run(["python3", "-c", code, url])
    return proc.stdout, proc.stderr


def _fetch_curl_cffi(url: str) -> tuple[str, str]:
    code = (
        "from curl_cffi import requests; import sys; "
        "r=requests.get(sys.argv[1], impersonate='chrome124', timeout=30); "
        "print(r.text[:400000])"
    )
    proc = _run([str(VENV_PY), "-c", code, url])
    return proc.stdout, proc.stderr


def _fetch_playwright(url: str, stealth: bool = False) -> tuple[str, str]:
    preamble = "from playwright_stealth import Stealth;" if stealth else ""
    apply = "Stealth().apply_stealth_sync(page);" if stealth else ""
    code = (
        "from playwright.sync_api import sync_playwright;"
        f"{preamble}"
        "import sys;"
        "u=sys.argv[1];"
        "with sync_playwright() as p:"
        " browser=p.chromium.launch(headless=True);"
        " page=browser.new_page();"
        f" {apply}"
        " page.goto(u, wait_until='load', timeout=45000);"
        " print(page.content()[:400000]);"
        " browser.close()"
    )
    proc = _run([str(VENV_PY), "-c", code, url])
    return proc.stdout, proc.stderr


def _fetch_crawl4ai(url: str) -> tuple[str, str]:
    proc = _run([str(CRAWL4AI), url, "-o", "markdown", "--bypass-cache", "-c", "wait_until=load"])
    return proc.stdout, proc.stderr


def _fetch_agent_browser(url: str) -> tuple[str, str]:
    _run([str(AGENT_BROWSER), "connect", "http://127.0.0.1:18800"], timeout=20)
    _run([str(AGENT_BROWSER), "open", url], timeout=25)
    current_url = _run([str(AGENT_BROWSER), "get", "url"], timeout=10).stdout.strip()
    title = _run([str(AGENT_BROWSER), "get", "title"], timeout=10).stdout.strip()
    snapshot = _run([str(AGENT_BROWSER), "snapshot"], timeout=20).stdout
    return f"opened_url={current_url}\n{title}\n{snapshot}", ""


TOOL_FETCHERS: dict[str, Callable[[str], tuple[str, str]]] = {
    "direct_http": _fetch_direct_http,
    "curl_cffi": _fetch_curl_cffi,
    "playwright": lambda url: _fetch_playwright(url, stealth=False),
    "playwright_stealth": lambda url: _fetch_playwright(url, stealth=True),
    "crawl4ai": _fetch_crawl4ai,
    "agent_browser": _fetch_agent_browser,
}


def _tool_order(platform: str) -> list[str]:
    prefs = (_load_site_preferences().get("sites", {}) or {}).get(platform, {}) or {}
    learned = []
    for raw in prefs.get("preferred_tool_order", []) or []:
        raw = str(raw).strip().lower()
        if raw in {"curl-cffi", "curl_cffi"}:
            learned.append("curl_cffi")
        elif raw in {"crawl4ai-cli", "crawl4ai"}:
            learned.append("crawl4ai")
        elif raw in {"scrapy-cffi", "scrapy_cffi"}:
            learned.append("curl_cffi")
        elif raw in {"local-agent-browser-cli", "agent-browser", "agent_browser"}:
            learned.append("agent_browser")
        elif raw in {"playwright"}:
            learned.append("playwright")
        elif raw in {"playwright-stealth", "playwright_stealth"}:
            learned.append("playwright_stealth")
        elif raw in {"direct-http-html", "direct_http"}:
            learned.append("direct_http")
    defaults = {
        "temu": ["agent_browser", "crawl4ai", "curl_cffi", "playwright_stealth", "direct_http"],
        "amazon": ["curl_cffi", "agent_browser", "playwright", "crawl4ai"],
        "walmart": ["agent_browser", "curl_cffi", "playwright_stealth", "crawl4ai"],
        "1688": ["agent_browser", "playwright_stealth", "playwright", "curl_cffi", "crawl4ai", "direct_http"],
        "yiwugo": ["curl_cffi", "playwright_stealth", "playwright", "crawl4ai", "direct_http"],
        "made_in_china": ["curl_cffi", "direct_http", "crawl4ai", "playwright_stealth"],
    }.get(platform, ["curl_cffi", "crawl4ai", "direct_http"])
    ordered = []
    for item in [*learned, *defaults]:
        if item not in ordered:
            ordered.append(item)
    return ordered


def _score_fetch(platform: str, tool: str, text: str, stderr: str) -> FetchResult:
    lowered = text.lower()
    blocked = sum(len(re.findall(p, lowered, flags=re.I)) for p in BLOCK_PATTERNS.get(platform, []))
    score = 0
    if len(text) > 500:
        score += 20
    if len(text) > 5000:
        score += 15
    if "price" in lowered or "¥" in text or "$" in text:
        score += 15
    if "href" in lowered or "/goods.html" in lowered or "/dp/" in lowered or "/ip/" in lowered or "productdirectory" in lowered or "offer_search" in lowered:
        score += 20
    if blocked:
        score -= min(60, blocked * 12)
    status = "blocked" if blocked else ("usable" if score >= 50 else "partial")
    return FetchResult(platform=platform, tool=tool, status=status, score=max(0, min(100, score)), text=text, notes=stderr[:400])


def fetch_best(platform: str, url: str, *, max_tools: int | None = None) -> FetchResult:
    best: FetchResult | None = None
    ordered_tools = _tool_order(platform)
    if max_tools is not None:
        ordered_tools = ordered_tools[:max_tools]
    for tool in ordered_tools:
        fetcher = TOOL_FETCHERS.get(tool)
        if not fetcher:
            continue
        try:
            text, stderr = fetcher(url)
        except Exception as exc:
            candidate = FetchResult(platform=platform, tool=tool, status="failed", score=0, text="", notes=str(exc))
        else:
            candidate = _score_fetch(platform, tool, text, stderr)
        if best is None or candidate.score > best.score:
            best = candidate
        if candidate.status == "usable":
            return candidate
    return best or FetchResult(platform=platform, tool="none", status="failed", score=0, text="", notes="no fetcher")


def _extract_prices(text: str) -> list[float]:
    prices = []
    for pattern in PRICE_PATTERNS:
        for raw in re.findall(pattern, text, flags=re.I):
            try:
                prices.append(float(raw))
            except Exception:
                pass
    return prices


def _extract_weight(text: str) -> tuple[float | None, str]:
    lowered = text.lower()
    for pattern in WEIGHT_PATTERNS:
        match = re.search(pattern, lowered, flags=re.I)
        if not match:
            continue
        value = float(match.group(1))
        unit = match.group(2).lower()
        if unit in {"g", "克"}:
            value = value / 1000.0
        return value, "A"
    return None, "D"


def _extract_sell_candidates(platform: str, text: str, query: str) -> list[DemandCandidate]:
    rows: list[DemandCandidate] = []
    seen: set[str] = set()
    patterns = {
        "temu": r"(https://www\.temu\.com[^\"'\s<>]+|/goods\.html[^\"'\s<>]+)",
        "amazon": r"(https://www\.amazon\.com/dp/[A-Z0-9]{10}|/dp/[A-Z0-9]{10})",
        "walmart": r"(https://www\.walmart\.com/ip/[^\"'\s<>]+|/ip/[^\"'\s<>]+)",
    }
    for raw_link in re.findall(patterns.get(platform, r"$^"), text, flags=re.I):
        link = raw_link if raw_link.startswith("http") else {
            "temu": "https://www.temu.com",
            "amazon": "https://www.amazon.com",
            "walmart": "https://www.walmart.com",
        }[platform] + raw_link
        if link in seen:
            continue
        seen.add(link)
        title = query.title()
        prices = _extract_prices(text[:12000])
        price = prices[0] if prices else None
        rows.append(
            DemandCandidate(
                candidate_id=f"{platform}-{_slug(link)}",
                title=title,
                sell_platform=platform,
                sell_link=link,
                sell_price_cny=(price or 0.0) * 7.2 if price is not None and platform in {"amazon", "walmart"} else price,
                query=query,
                extracted_at=_utc_now_iso(),
                raw_signals={"fetch_price_count": len(prices)},
            )
        )
        if len(rows) >= 5:
            break
    if not rows:
        fallback_price = (_extract_prices(text[:12000]) or [None])[0]
        rows.append(
            DemandCandidate(
                candidate_id=f"{platform}-{_slug(query)}",
                title=query.title(),
                sell_platform=platform,
                sell_link=url_for_sell(platform, query),
                sell_price_cny=(fallback_price or 0.0) * 7.2 if fallback_price is not None and platform in {"amazon", "walmart"} else fallback_price,
                query=query,
                extracted_at=_utc_now_iso(),
                raw_signals={"fallback_from_search_page": True},
            )
        )
    return rows


def url_for_sell(platform: str, query: str) -> str:
    return SELL_PLATFORM_SEARCH[platform](query)


def _extract_source_candidate(platform: str, text: str, query: str, fetch_tool: str) -> SourceCandidate:
    prices = _extract_prices(text[:60000])
    weight, grade = _extract_weight(text[:60000])
    link_patterns = {
        "1688": r"(https?://[^\s\"']+offer[^\s\"']+|/offer/[^\s\"']+)",
        "yiwugo": r"(https?://en\.yiwugo\.com/[^\s\"']+|/product/detail/[^\s\"']+)",
        "made_in_china": r"(https?://[^\s\"']+made-in-china\.com[^\s\"']+|https?://[^\s\"']+productdirectory\.do[^\s\"']+)",
    }
    raw_link = ""
    pattern = link_patterns.get(platform, "")
    if pattern:
        found = re.search(pattern, text, flags=re.I)
        if found:
            raw_link = found.group(1)
    if raw_link and not raw_link.startswith("http"):
        raw_link = {
            "1688": "https://detail.1688.com",
            "yiwugo": "https://en.yiwugo.com",
            "made_in_china": "https://www.made-in-china.com",
        }[platform] + raw_link
    blocked = any(re.search(p, text, flags=re.I) for p in BLOCK_PATTERNS.get(platform, []))
    match_score = 35.0
    if prices:
        match_score += 20
    if weight is not None:
        match_score += 25
    if raw_link:
        match_score += 10
    normalized_query = _normalize_title(query)
    normalized_text = _normalize_title(text[:4000])
    overlap = len(set(normalized_query.split()) & set(normalized_text.split()))
    match_score += min(10, overlap * 2)
    return SourceCandidate(
        platform=platform,
        link=raw_link or SOURCE_PLATFORM_SEARCH[platform](query),
        title=query.title(),
        price_cny=prices[0] if prices else None,
        weight_kg=weight,
        weight_grade=grade,
        fetch_tool=fetch_tool,
        match_score=min(100.0, match_score),
        blocked=blocked,
        notes="blocked" if blocked else "",
    )


def _is_restricted(text: str) -> tuple[bool, list[str]]:
    lowered = text.lower()
    hits = [pattern for pattern in RESTRICTED_PATTERNS if re.search(pattern, lowered, flags=re.I)]
    return bool(hits), hits


def _compute_decision(candidate: DemandCandidate, sources: list[SourceCandidate]) -> ArbitrageDecision:
    reasons: list[str] = []
    restricted, hits = _is_restricted(candidate.title)
    if restricted:
        reasons.append(f"restricted:{','.join(hits[:4])}")
    best_source = None
    for source in sorted(sources, key=lambda item: item.match_score, reverse=True):
        if source.blocked:
            continue
        if source.price_cny is None:
            continue
        if best_source is None or source.match_score > best_source.match_score:
            best_source = source
    if best_source is None:
        return ArbitrageDecision(
            product_name=candidate.title,
            buy_platform="",
            buy_link="",
            sell_platform=candidate.sell_platform,
            sell_link=candidate.sell_link,
            sell_price_cny=candidate.sell_price_cny,
            purchase_cost_cny=None,
            weight_kg=None,
            gross_profit_amount=None,
            gross_margin_rate=None,
            conservative_margin_rate=None,
            confidence_score=0.0,
            weight_grade="D",
            qualified=False,
            reasons=["no_usable_source_match", *reasons],
        )
    if best_source.weight_kg is None:
        return ArbitrageDecision(
            product_name=candidate.title,
            buy_platform=best_source.platform,
            buy_link=best_source.link,
            sell_platform=candidate.sell_platform,
            sell_link=candidate.sell_link,
            sell_price_cny=candidate.sell_price_cny,
            purchase_cost_cny=best_source.price_cny,
            weight_kg=None,
            gross_profit_amount=None,
            gross_margin_rate=None,
            conservative_margin_rate=None,
            confidence_score=min(79.0, best_source.match_score),
            weight_grade=best_source.weight_grade,
            qualified=False,
            reasons=["missing_trusted_weight", *reasons],
        )
    if candidate.sell_price_cny is None:
        return ArbitrageDecision(
            product_name=candidate.title,
            buy_platform=best_source.platform,
            buy_link=best_source.link,
            sell_platform=candidate.sell_platform,
            sell_link=candidate.sell_link,
            sell_price_cny=None,
            purchase_cost_cny=best_source.price_cny,
            weight_kg=best_source.weight_kg,
            gross_profit_amount=None,
            gross_margin_rate=None,
            conservative_margin_rate=None,
            confidence_score=min(79.0, best_source.match_score),
            weight_grade=best_source.weight_grade,
            qualified=False,
            reasons=["missing_sell_price", *reasons],
        )
    logistics = 59 * best_source.weight_kg + 35 * best_source.weight_kg + 1.4
    gross_profit = candidate.sell_price_cny - best_source.price_cny - logistics
    margin = gross_profit / candidate.sell_price_cny if candidate.sell_price_cny else None
    conservative_sell = candidate.sell_price_cny * 0.95
    conservative_purchase = best_source.price_cny * 1.05
    conservative_weight = best_source.weight_kg * 1.10
    conservative_profit = conservative_sell - conservative_purchase - (59 * conservative_weight) - (35 * conservative_weight) - 1.4
    conservative_margin = conservative_profit / conservative_sell if conservative_sell else None
    confidence = min(
        100.0,
        25.0
        + best_source.match_score * 0.35
        + (20.0 if best_source.weight_grade in {"A", "B"} else 0.0)
        + (10.0 if not restricted else 0.0)
        + (10.0 if margin is not None and margin >= 0.45 else 0.0)
        + (10.0 if conservative_margin is not None and conservative_margin >= 0.45 else 0.0),
    )
    qualified = (
        not restricted
        and margin is not None
        and conservative_margin is not None
        and margin >= 0.45
        and conservative_margin >= 0.45
        and best_source.weight_grade in {"A", "B"}
        and confidence >= 80.0
    )
    if not qualified and not reasons:
        reasons.append("below_threshold_or_low_confidence")
    return ArbitrageDecision(
        product_name=candidate.title,
        buy_platform=best_source.platform,
        buy_link=best_source.link,
        sell_platform=candidate.sell_platform,
        sell_link=candidate.sell_link,
        sell_price_cny=round(candidate.sell_price_cny, 2),
        purchase_cost_cny=round(best_source.price_cny, 2),
        weight_kg=round(best_source.weight_kg, 4),
        gross_profit_amount=round(gross_profit, 2),
        gross_margin_rate=round(margin, 4) if margin is not None else None,
        conservative_margin_rate=round(conservative_margin, 4) if conservative_margin is not None else None,
        confidence_score=round(confidence, 2),
        weight_grade=best_source.weight_grade,
        qualified=qualified,
        reasons=reasons,
    )


def _load_state() -> dict[str, Any]:
    if not STATE_PATH.exists():
        return {"runs": [], "recent_candidates": []}
    try:
        return json.loads(STATE_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {"runs": [], "recent_candidates": []}


def _save_state(payload: dict[str, Any]) -> None:
    STATE_PATH.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def autosize(ws) -> None:
    for col in ws.columns:
        max_len = 0
        col_idx = col[0].column
        for cell in col:
            value = "" if cell.value is None else str(cell.value)
            max_len = max(max_len, min(len(value), 80))
        ws.column_dimensions[get_column_letter(col_idx)].width = min(max_len + 2, 40)


def style_header(ws, row: int = 1) -> None:
    fill = PatternFill("solid", fgColor="1F4E78")
    font = Font(color="FFFFFF", bold=True)
    for cell in ws[row]:
        cell.fill = fill
        cell.font = font


def _write_excel(run_id: str, decisions: list[ArbitrageDecision], summary: dict[str, Any]) -> Path:
    wb = Workbook()
    ws = wb.active
    ws.title = "Qualified"
    ws.append(["产品名称", "目标采购平台", "采购链接", "目标售卖平台", "售卖链接"])
    style_header(ws)
    for item in decisions:
        if not item.qualified:
            continue
        ws.append([item.product_name, item.buy_platform, item.buy_link, item.sell_platform, item.sell_link])
    autosize(ws)

    audit = wb.create_sheet("Audit")
    headers = [
        "产品名称", "采购平台", "采购链接", "售卖平台", "售卖链接", "售价(RMB)", "采购成本(RMB)", "重量(kg)",
        "毛利额", "毛利率", "保守毛利率", "置信度", "重量等级", "是否入选", "原因"
    ]
    audit.append(headers)
    style_header(audit)
    for item in decisions:
        audit.append([
            item.product_name,
            item.buy_platform,
            item.buy_link,
            item.sell_platform,
            item.sell_link,
            item.sell_price_cny,
            item.purchase_cost_cny,
            item.weight_kg,
            item.gross_profit_amount,
            item.gross_margin_rate,
            item.conservative_margin_rate,
            item.confidence_score,
            item.weight_grade,
            "yes" if item.qualified else "no",
            " | ".join(item.reasons),
        ])
    autosize(audit)

    summary_ws = wb.create_sheet("Summary")
    summary_ws.append(["字段", "内容"])
    style_header(summary_ws)
    for key, value in summary.items():
        summary_ws.append([key, json.dumps(value, ensure_ascii=False) if isinstance(value, (dict, list)) else value])
    autosize(summary_ws)

    path = OUT_DIR / f"cross-market-arbitrage-{run_id}.xlsx"
    wb.save(path)
    return path


def _write_markdown(run_id: str, decisions: list[ArbitrageDecision], summary: dict[str, Any]) -> Path:
    lines = [
        "# Cross-market arbitrage run",
        "",
        f"- Run ID: `{run_id}`",
        f"- Generated at: `{summary['generated_at']}`",
        f"- Qualified count: `{summary['qualified_count']}`",
        f"- Discovery candidates: `{summary['discovery_candidate_count']}`",
        "",
        "## Qualified",
        "",
    ]
    qualified = [item for item in decisions if item.qualified]
    if not qualified:
        lines.append("- No candidates passed the current strong thresholds.")
    for item in qualified:
        lines.extend([
            f"### {item.product_name}",
            f"- Buy: `{item.buy_platform}` -> {item.buy_link}",
            f"- Sell: `{item.sell_platform}` -> {item.sell_link}",
            f"- Margin: `{item.gross_margin_rate}`",
            f"- Conservative margin: `{item.conservative_margin_rate}`",
            f"- Confidence: `{item.confidence_score}`",
            "",
        ])
    lines.extend(["## Audit notes", ""])
    lines.extend([
        "- 1688 is still treated as high-risk / often blocked under automated browsing.",
        "- Yiwugo is currently supplementary, not a primary trusted weight source.",
        "- Made-in-China is currently the most stable public source among the tested source-side platforms.",
    ])
    path = OUT_DIR / f"cross-market-arbitrage-{run_id}.md"
    path.write_text("\n".join(lines), encoding="utf-8")
    return path


def _write_json(run_id: str, payload: dict[str, Any]) -> Path:
    path = OUT_DIR / f"cross-market-arbitrage-{run_id}.json"
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def run_once(*, test: bool = False) -> dict[str, Any]:
    run_id = _utc_now().strftime("%Y%m%dT%H%M%SZ")
    queries = DEFAULT_DISCOVERY_QUERIES[:1] if test else DEFAULT_DISCOVERY_QUERIES
    sell_platforms = ["temu", "amazon"] if test else ["temu", "amazon", "walmart"]
    source_platforms = ["made_in_china", "1688"] if test else ["1688", "yiwugo", "made_in_china"]
    max_tools = 2 if test else None

    fetch_log: list[dict[str, Any]] = []
    demand_candidates: list[DemandCandidate] = []

    for query in queries:
        for platform in sell_platforms:
            result = fetch_best(platform, url_for_sell(platform, query), max_tools=max_tools)
            fetch_log.append({"platform": platform, "query": query, "tool": result.tool, "status": result.status, "score": result.score})
            demand_candidates.extend(_extract_sell_candidates(platform, result.text, query))

    deduped: dict[tuple[str, str], DemandCandidate] = {}
    for item in demand_candidates:
        key = (item.sell_platform, _normalize_title(item.title))
        if key not in deduped:
            deduped[key] = item
    demand_candidates = list(deduped.values())
    if test:
        demand_candidates = demand_candidates[:3]

    source_matches: dict[str, list[SourceCandidate]] = {}
    for candidate in demand_candidates:
        source_rows: list[SourceCandidate] = []
        normalized_query = _normalize_title(candidate.title) or candidate.query
        for platform in source_platforms:
            url = SOURCE_PLATFORM_SEARCH[platform](normalized_query)
            result = fetch_best(platform, url, max_tools=max_tools)
            fetch_log.append({"platform": platform, "query": normalized_query, "tool": result.tool, "status": result.status, "score": result.score})
            source_rows.append(_extract_source_candidate(platform, result.text, normalized_query, result.tool))
        source_matches[candidate.candidate_id] = source_rows

    decisions = [_compute_decision(item, source_matches.get(item.candidate_id, [])) for item in demand_candidates]
    summary = {
        "generated_at": _utc_now_iso(),
        "mode": "test" if test else "normal",
        "discovery_candidate_count": len(demand_candidates),
        "qualified_count": sum(1 for item in decisions if item.qualified),
        "queries": queries,
        "timing": {
            "discovery_interval_seconds": DISCOVERY_INTERVAL_SECONDS,
            "matching_interval_seconds": MATCH_INTERVAL_SECONDS,
            "report_hour_new_york": REPORT_HOUR,
        },
    }
    excel_path = _write_excel(run_id, decisions, summary)
    md_path = _write_markdown(run_id, decisions, summary)
    json_path = _write_json(
        run_id,
        {
            "summary": summary,
            "fetch_log": fetch_log,
            "decisions": [asdict(item) for item in decisions],
            "source_matches": {key: [asdict(row) for row in rows] for key, rows in source_matches.items()},
        },
    )

    state = _load_state()
    state.setdefault("runs", []).append(
        {
            "run_id": run_id,
            "generated_at": summary["generated_at"],
            "qualified_count": summary["qualified_count"],
            "excel_path": str(excel_path),
            "markdown_path": str(md_path),
            "json_path": str(json_path),
        }
    )
    state["runs"] = state["runs"][-40:]
    _save_state(state)

    return {
        "run_id": run_id,
        "summary": summary,
        "excel_path": str(excel_path),
        "markdown_path": str(md_path),
        "json_path": str(json_path),
    }


def _seconds_until_next_discovery() -> int:
    state = _load_state()
    runs = state.get("runs", []) or []
    if not runs:
        return 0
    try:
        last = datetime.fromisoformat(runs[-1]["generated_at"])
    except Exception:
        return 0
    elapsed = (_utc_now() - last).total_seconds()
    return max(0, int(DISCOVERY_INTERVAL_SECONDS - elapsed))


def run_daemon() -> int:
    while True:
        run_once(test=False)
        time.sleep(max(60, _seconds_until_next_discovery()))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=["once", "daemon"], default="once")
    parser.add_argument("--test", action="store_true")
    args = parser.parse_args()
    if args.mode == "daemon":
        return run_daemon()
    payload = run_once(test=args.test)
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
