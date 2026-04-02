#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import time
import xml.etree.ElementTree as ET
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable
from urllib.parse import quote_plus
from urllib.request import urlopen
from zoneinfo import ZoneInfo

from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill
from openpyxl.utils import get_column_letter


ROOT = Path("/Users/mac_claw/.openclaw/workspace")
CONTROL_CENTER_ROOT = ROOT / "tools/openmoss/control_center"
STATE_DIR = ROOT / ".state"
STATE_DIR.mkdir(parents=True, exist_ok=True)
STATE_PATH = STATE_DIR / "cross-market-arbitrage-engine.json"
OUT_DIR = ROOT / "output" / "cross-market-arbitrage-engine"
OUT_DIR.mkdir(parents=True, exist_ok=True)
LATEST_REPORT_PATH = OUT_DIR / "latest-report.json"
FX_CACHE_PATH = STATE_DIR / "usd_cny_midrate.json"

TOOLS_ROOT = ROOT / "tools"
CRAWL4AI = TOOLS_ROOT / "bin" / "crawl4ai"
AGENT_BROWSER = TOOLS_ROOT / "agent-browser-local" / "node_modules" / "agent-browser" / "bin" / "agent-browser-darwin-arm64"
VENV_PY = TOOLS_ROOT / "matrix-venv" / "bin" / "python"
SITE_PREFS_PATH = ROOT / "tools/openmoss/runtime/autonomy/learning/crawler_site_preferences.json"
OPENCLAW_BIN = "/opt/homebrew/bin/openclaw"

import sys

if str(CONTROL_CENTER_ROOT) not in sys.path:
    sys.path.insert(0, str(CONTROL_CENTER_ROOT))

from control_plane_builder import build_control_plane
from memory_writeback_runtime import record_memory_writeback
from paths import CROSS_MARKET_ARBITRAGE_SCHEDULER_STATE_PATH

DISCOVERY_INTERVAL_SECONDS = 30 * 60
MATCH_INTERVAL_SECONDS = 60 * 60
REPORT_WINDOW_HOURS = 24
REPORT_TIMEZONE = ZoneInfo("America/New_York")
REPORT_HOUR = 18
DEFAULT_TELEGRAM_TARGET = "8528973600"
USD_TO_CNY_FALLBACK = 7.2
_USD_TO_CNY_CACHE: dict[str, Any] | None = None
DEFAULT_PLATFORM_FEE = 0.15

PLATFORM_FEE_TABLE = {
    "amazon": 0.15,
    "walmart": 0.15,
    "temu": 0.15,
}

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
    "yiwugo": lambda q: f"https://en.yiwugo.com/search/s.html?queryKey={quote_plus(q)}",
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

PAIN_POINT_PATTERNS = [
    r"broke",
    r"broken",
    r"cheap",
    r"flimsy",
    r"too small",
    r"too thin",
    r"doesn't fit",
    r"poor quality",
    r"fell apart",
    r"leak",
    r"damaged",
    r"not sturdy",
    r"坏了",
    r"太小",
    r"太薄",
    r"质量差",
    r"不结实",
    r"容易坏",
]

MONTHLY_ORDER_PATTERNS = [
    r"(\d[\d,]*)\+?\s+bought in past month",
    r"(\d[\d,]*)\+?\s+purchased in the last month",
    r"(\d[\d,]*)\+?\s+sold in past month",
    r"(\d[\d,]*(?:\.\d+)?)\s*k\+?\s+(?:bought|purchased|sold)(?:\s+in\s+(?:the\s+)?)?(?:past|last)?\s*month",
    r"(\d[\d,]*)\+?\s+(?:bought|purchased|sold)(?:\s+in\s+(?:the\s+)?)?(?:past|last)?\s*(?:month|30 days)",
    r'"(?:monthlySold|unitsSold|monthly_orders|monthlySales)"\s*[:=]\s*"?(\\d[\d,]*)\+?"?',
]

SOLD_PATTERNS = [
    r"(\d+(?:\.\d+)?)k\+?\s+sold",
    r"(\d[\d,]*)\+?\s+sold",
]

RATING_PATTERNS = [
    r"(\d(?:\.\d)?)\s+out of 5 stars",
    r"(\d(?:\.\d)?)\s*\/\s*5",
]

REVIEW_COUNT_PATTERNS = [
    r"(\d[\d,]*)\s+ratings",
    r"(\d[\d,]*)\s+reviews",
]

AMAZON_TOP_CATEGORIES = {
    "home & kitchen",
    "kitchen & dining",
    "tools & home improvement",
    "patio, lawn & garden",
    "office products",
    "industrial & scientific",
    "sports & outdoors",
    "arts, crafts & sewing",
    "home improvement",
    "pet supplies",
}

LISTING_AGE_PATTERNS = [
    r"Date First Available[^A-Za-z0-9]{0,20}([A-Za-z]+ \d{1,2}, \d{4})",
    r"First available[^A-Za-z0-9]{0,20}([A-Za-z]+ \d{1,2}, \d{4})",
    r"Available on[^A-Za-z0-9]{0,20}([A-Za-z]+ \d{1,2}, \d{4})",
    r"Date First Available[^0-9]{0,20}(\d{1,2}/\d{1,2}/\d{4})",
    r"First available[^0-9]{0,20}(\d{1,2}/\d{1,2}/\d{4})",
    r"Available on[^0-9]{0,20}(\d{1,2}/\d{1,2}/\d{4})",
    r'"(?:dateFirstAvailable|firstAvailableDate|datePublished|releaseDate)"\s*[:=]\s*"(\d{4}-\d{2}-\d{2})"',
    r'"(?:dateFirstAvailable|firstAvailableDate|datePublished|releaseDate)"\s*[:=]\s*"(\d{4}/\d{2}/\d{2})"',
]

WEIGHT_PATTERNS = [
    r"(\d+(?:\.\d+)?)\s*(kg|公斤)",
    r"(\d+(?:\.\d+)?)\s*(g|克)",
    r"weight[^\\d]{0,10}(\d+(?:\.\d+)?)\s*(kg|g)",
    r"净重[^\\d]{0,10}(\d+(?:\.\d+)?)\s*(kg|g|公斤|克)",
    r"毛重[^\\d]{0,10}(\d+(?:\.\d+)?)\s*(kg|g|公斤|克)",
]

PRICE_PATTERNS = [
    r"(?:US\$|USD\s*)(\d+(?:\.\d+)?)",
    r"\$(\d+(?:\.\d+)?)",
    r"(?:¥|RMB\s*|￥)(\d+(?:\.\d+)?)",
    r"(\d+(?:\.\d+)?)\s*元",
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

SOURCE_QUERY_STOPWORDS = {
    "organizer",
    "storage",
    "household",
    "home",
    "kitchen",
    "portable",
    "adjustable",
    "multifunction",
    "multi",
    "tool",
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
    estimated_daily_orders: float | None = None
    listing_age_days: int | None = None
    rating_value: float | None = None
    review_count: int | None = None
    demand_confidence: float = 0.0
    demand_refresh_priority: float = 0.0
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
    platform_fee_rate: float | None
    estimated_daily_orders: float | None
    listing_age_days: int | None
    demand_score: float
    competition_score: float
    differentiation_score: float
    price_stability_score: float
    launchability_score: float
    confidence_score: float
    weight_grade: str
    qualified: bool
    reasons: list[str] = field(default_factory=list)


DECISION_DEFAULTS: dict[str, Any] = {
    "platform_fee_rate": None,
    "estimated_daily_orders": None,
    "listing_age_days": None,
    "demand_score": 0.0,
    "competition_score": 0.0,
    "differentiation_score": 0.0,
    "price_stability_score": 0.0,
    "launchability_score": 0.0,
    "confidence_score": 0.0,
    "weight_grade": "D",
    "qualified": False,
    "reasons": [],
}


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _utc_now_iso() -> str:
    return _utc_now().isoformat()


def _load_fx_cache() -> dict[str, Any] | None:
    if not FX_CACHE_PATH.exists():
        return None
    try:
        payload = json.loads(FX_CACHE_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return payload if isinstance(payload, dict) else None


def _save_fx_cache(payload: dict[str, Any]) -> None:
    FX_CACHE_PATH.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _fetch_usd_to_cny_midrate() -> dict[str, Any] | None:
    try:
        with urlopen("https://www.ecb.europa.eu/stats/eurofxref/eurofxref-daily.xml", timeout=20) as resp:
            raw = resp.read()
    except Exception:
        return None
    try:
        root = ET.fromstring(raw)
    except ET.ParseError:
        return None
    ns = {"e": "http://www.ecb.int/vocabulary/2002-08-01/eurofxref"}
    time_node = root.find(".//e:Cube[@time]", ns)
    if time_node is None:
        return None
    as_of = time_node.attrib.get("time")
    eur_usd = None
    eur_cny = None
    for cube in time_node.findall("e:Cube", ns):
        currency = (cube.attrib.get("currency") or "").upper()
        rate_raw = cube.attrib.get("rate")
        try:
            rate = float(rate_raw)
        except Exception:
            continue
        if currency == "USD":
            eur_usd = rate
        elif currency == "CNY":
            eur_cny = rate
    if not eur_usd or not eur_cny or eur_usd <= 0:
        return None
    return {
        "source": "ECB euro foreign exchange reference rates",
        "as_of": as_of,
        "eur_usd": eur_usd,
        "eur_cny": eur_cny,
        "usd_cny_midrate": round(eur_cny / eur_usd, 6),
        "fetched_at": _utc_now_iso(),
    }


def _usd_to_cny_rate() -> float:
    global _USD_TO_CNY_CACHE
    today = _utc_now().date().isoformat()
    if _USD_TO_CNY_CACHE and _USD_TO_CNY_CACHE.get("as_of") == today:
        return float(_USD_TO_CNY_CACHE.get("usd_cny_midrate") or USD_TO_CNY_FALLBACK)
    cached = _load_fx_cache()
    if cached and cached.get("as_of") == today:
        _USD_TO_CNY_CACHE = cached
        return float(cached.get("usd_cny_midrate") or USD_TO_CNY_FALLBACK)
    fresh = _fetch_usd_to_cny_midrate()
    if fresh:
        _USD_TO_CNY_CACHE = fresh
        try:
            _save_fx_cache(fresh)
        except OSError:
            pass
        return float(fresh.get("usd_cny_midrate") or USD_TO_CNY_FALLBACK)
    if cached and cached.get("usd_cny_midrate") is not None:
        _USD_TO_CNY_CACHE = cached
        return float(cached["usd_cny_midrate"])
    return USD_TO_CNY_FALLBACK


def _ny_now() -> datetime:
    return _utc_now().astimezone(REPORT_TIMEZONE)


def _read_json(path: Path, default: dict[str, Any]) -> dict[str, Any]:
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return default


def _write_json_file(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _parse_iso(value: str) -> datetime | None:
    raw = str(value or "").strip()
    if not raw:
        return None
    try:
        return datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        return None


def _seconds_since(value: str) -> int | None:
    dt = _parse_iso(value)
    if not dt:
        return None
    return max(0, int((_utc_now() - dt).total_seconds()))


def _load_scheduler_policy() -> dict[str, Any]:
    try:
        control_plane = build_control_plane()
    except Exception:
        return {}
    return (control_plane.get("project_scheduler_policy", {}) or {}).get("cross_market_arbitrage", {}) or {}


def _load_scheduler_state() -> dict[str, Any]:
    return _read_json(CROSS_MARKET_ARBITRAGE_SCHEDULER_STATE_PATH, {})


def _write_scheduler_state(payload: dict[str, Any]) -> None:
    _write_json_file(CROSS_MARKET_ARBITRAGE_SCHEDULER_STATE_PATH, payload)


def _execution_flags_from_scheduler_policy(scheduler_policy: dict[str, Any] | None) -> dict[str, bool]:
    scheduler_policy = scheduler_policy or {}
    repair_mode = str(scheduler_policy.get("repair_mode", "")).strip()
    start_tasks = bool(scheduler_policy.get("start_tasks", True))
    flags = {
        "allow_discovery": start_tasks,
        "allow_match": start_tasks,
        "allow_report": True,
    }
    if not start_tasks:
        flags["allow_discovery"] = False
        flags["allow_match"] = False
        return flags
    if repair_mode == "crawler_hold":
        flags["allow_discovery"] = False
        flags["allow_match"] = False
    elif repair_mode == "repair_backpressure":
        flags["allow_discovery"] = False
        flags["allow_match"] = True
    elif repair_mode == "repair_observe":
        flags["allow_discovery"] = False
        flags["allow_match"] = True
    return flags


def _slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-") or "item"


def _run(cmd: list[str], *, timeout: int = 45) -> subprocess.CompletedProcess:
    timeout_cap = os.environ.get("CROSS_MARKET_TIMEOUT_CAP", "").strip()
    if timeout_cap.isdigit():
        timeout = min(timeout, max(3, int(timeout_cap)))
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


def _title_from_link(link: str, fallback: str) -> str:
    text = str(link or "")
    if "temu.com" in text:
        match = re.search(r"/([a-z0-9-]+)-s\.html", text, flags=re.I)
        if match:
            return match.group(1).replace("-", " ").strip().title()
    if "amazon.com" in text:
        return fallback
    if "walmart.com" in text:
        match = re.search(r"/ip/([^/?]+)", text, flags=re.I)
        if match:
            return match.group(1).replace("-", " ").strip().title()
    return fallback


def _extract_page_title(text: str) -> str | None:
    match = re.search(r"<title>([^<]+)</title>", text, flags=re.I)
    if match:
        title = _clean_text(match.group(1))
        if title:
            return re.sub(r"\s*[|\-]\s*(Amazon|Temu|Walmart).*$", "", title, flags=re.I).strip()
    snapshot_title = re.search(r"^([^\n]{10,160})$", text.strip(), flags=re.M)
    if snapshot_title:
        title = _clean_text(snapshot_title.group(1))
        if title and "http" not in title.lower():
            return title
    return None


def _source_query_variants(candidate: DemandCandidate) -> list[str]:
    base = _normalize_title(candidate.title) or _normalize_title(candidate.query) or candidate.query.strip().lower()
    tokens = [token for token in base.split() if token not in SOURCE_QUERY_STOPWORDS]
    variants: list[str] = []
    if len(tokens) >= 2:
        pair = " ".join(tokens[:2]).strip()
        if pair:
            variants.append(pair)
    if len(tokens) >= 3:
        trio = " ".join(tokens[:3]).strip()
        if trio:
            variants.append(trio)
    for text in [
        " ".join(tokens[:6]).strip(),
        " ".join(tokens[:4]).strip(),
        candidate.query.strip().lower(),
        candidate.title.strip().lower(),
    ]:
        text = re.sub(r"\s+", " ", text).strip()
        if text and text not in variants:
            variants.append(text)
    return variants[:4]


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
    preamble = "from playwright_stealth import Stealth\n" if stealth else ""
    apply = "    Stealth().apply_stealth_sync(page)\n" if stealth else ""
    code = (
        "from playwright.sync_api import sync_playwright\n"
        f"{preamble}"
        "import sys\n"
        "u = sys.argv[1]\n"
        "with sync_playwright() as p:\n"
        "    browser = p.chromium.launch(headless=True)\n"
        "    page = browser.new_page()\n"
        f"{apply}"
        "    page.goto(u, wait_until='load', timeout=45000)\n"
        "    html = page.content()[:400000]\n"
        "    body_text = ''\n"
        "    try:\n"
        "        body_text = page.locator('body').inner_text(timeout=10000)[:200000]\n"
        "    except Exception:\n"
        "        body_text = ''\n"
        "    print(html)\n"
        "    if body_text:\n"
        "        print('\\n\\n__VISIBLE_TEXT__\\n')\n"
        "        print(body_text)\n"
        "    browser.close()\n"
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


def _extract_prices_detailed(text: str) -> list[tuple[float, str]]:
    rows: list[tuple[float, str]] = []
    for raw in re.findall(r"(?:US\$|USD\s*)(\d+(?:\.\d+)?)", text, flags=re.I):
        try:
            rows.append((float(raw), "USD"))
        except Exception:
            pass
    for raw in re.findall(r"\$(\d+(?:\.\d+)?)", text, flags=re.I):
        try:
            rows.append((float(raw), "USD"))
        except Exception:
            pass
    for raw in re.findall(r"(?:¥|RMB\s*|￥)(\d+(?:\.\d+)?)", text, flags=re.I):
        try:
            rows.append((float(raw), "CNY"))
        except Exception:
            pass
    for raw in re.findall(r"(\d+(?:\.\d+)?)\s*元", text, flags=re.I):
        try:
            rows.append((float(raw), "CNY"))
        except Exception:
            pass
    return rows


def _extract_amazon_price_usd(text: str) -> float | None:
    patterns = [
        r'id="apex-pricetopay-accessibility-label"[^>]*>\s*\$?(\d+(?:\.\d+)?)',
        r'class="[^"]*priceToPay[^"]*"[^>]*>\s*<span class="a-offscreen">\s*\$?(\d+(?:\.\d+)?)',
        r'class="[^"]*apex-pricetopay-value[^"]*"[^>]*>.*?<span class="a-offscreen">\s*\$?(\d+(?:\.\d+)?)',
        r'id="corePriceDisplay_desktop_feature_div".*?<span class="a-offscreen">\s*\$?(\d+(?:\.\d+)?)',
    ]
    for pattern in patterns:
        found = re.search(pattern, text, flags=re.I | re.S)
        if not found:
            continue
        try:
            value = float(found.group(1))
        except Exception:
            continue
        if value > 1.0:
            return value
    return None


def _price_to_cny(value: float, currency: str, platform: str) -> float:
    usd_to_cny = _usd_to_cny_rate()
    if currency == "USD":
        return value * usd_to_cny
    if platform in {"amazon", "walmart", "temu"}:
        return value * usd_to_cny
    if platform == "made_in_china" and currency != "CNY":
        return value * usd_to_cny
    return value


def _best_price_cny(text: str, platform: str) -> float | None:
    detailed = _extract_prices_detailed(text[:120000])
    if detailed:
        converted = [_price_to_cny(value, currency, platform) for value, currency in detailed if value > 0]
        if converted:
            return round(min(converted), 2)
    simple = _extract_prices(text[:120000])
    if not simple:
        return None
    inferred = min(simple)
    if platform in {"amazon", "walmart", "temu", "made_in_china"}:
        inferred *= _usd_to_cny_rate()
    return round(inferred, 2)


def _extract_platform_price_cny(text: str, platform: str) -> float | None:
    if platform == "amazon":
        amazon_price = _extract_amazon_price_usd(text)
        if amazon_price is not None:
            return round(amazon_price * _usd_to_cny_rate(), 2)
    if platform == "yiwugo":
        prices: list[float] = []
        for raw in re.findall(r'sellprice="(\d+(?:\.\d+)?)"', text, flags=re.I):
            try:
                value = float(raw)
            except Exception:
                continue
            if value > 0:
                prices.append(value)
        if prices:
            return round(min(prices), 2)
    if platform == "made_in_china":
        usd_hits: list[float] = []
        for raw in re.findall(r"US\$\s*(\d+(?:\.\d+)?)", text, flags=re.I):
            try:
                value = float(raw)
            except Exception:
                continue
            if value > 0:
                usd_hits.append(value)
        if usd_hits:
            return round(min(usd_hits) * _usd_to_cny_rate(), 2)
    return _best_price_cny(text, platform)


def _extract_rating_value(text: str) -> float | None:
    for pattern in RATING_PATTERNS:
        found = re.search(pattern, text, flags=re.I)
        if found:
            try:
                value = float(found.group(1))
            except Exception:
                continue
            if 0.0 < value <= 5.0:
                return value
    return None


def _extract_review_count(text: str) -> int | None:
    for pattern in REVIEW_COUNT_PATTERNS:
        found = re.search(pattern, text, flags=re.I)
        if found:
            try:
                return int(found.group(1).replace(",", ""))
            except Exception:
                continue
    return None


def _normalize_category_name(raw: str) -> str:
    cleaned = _clean_text(raw)
    cleaned = re.sub(r"\s+", " ", cleaned).strip(" >-")
    return cleaned


def _extract_amazon_best_seller_rank(text: str) -> tuple[int | None, str | None]:
    section_patterns = [
        r"Best Sellers Rank.*?#([\d,]+)\s+in\s+([^<\n\r]+)",
        r"#([\d,]+)\s+in\s+([^<\n\r]+).*?Best Sellers Rank",
    ]
    for pattern in section_patterns:
        found = re.search(pattern, text, flags=re.I | re.S)
        if not found:
            continue
        try:
            rank = int(found.group(1).replace(",", ""))
        except Exception:
            continue
        category = _normalize_category_name(found.group(2))
        if rank > 0 and category:
            return rank, category
    return None, None


def _estimate_amazon_daily_orders_from_rank(rank: int | None, category: str | None) -> float | None:
    if not rank or rank <= 0:
        return None
    lowered = (category or "").lower()
    is_top_category = any(token in lowered for token in AMAZON_TOP_CATEGORIES)
    if is_top_category:
        if rank <= 100:
            return 120.0
        if rank <= 250:
            return 80.0
        if rank <= 500:
            return 50.0
        if rank <= 1000:
            return 30.0
        if rank <= 3000:
            return 15.0
        if rank <= 10000:
            return 5.0
        return 1.0
    if rank <= 10:
        return 20.0
    if rank <= 50:
        return 10.0
    if rank <= 200:
        return 5.0
    if rank <= 1000:
        return 2.0
    return 0.5


def _extract_monthly_orders(text: str) -> float | None:
    lowered = text.lower()
    values: list[float] = []
    for pattern in MONTHLY_ORDER_PATTERNS:
        for found in re.finditer(pattern, lowered, flags=re.I):
            try:
                raw = found.group(1).replace(",", "").strip().lower()
                whole = found.group(0).lower()
                base = float(raw[:-1]) if raw.endswith("k") else float(raw)
                if raw.endswith("k") or re.search(r"\d\s*k\+?", whole):
                    values.append(base * 1000.0)
                else:
                    values.append(base)
            except Exception:
                continue
    if values:
        return max(values)
    for pattern in SOLD_PATTERNS:
        for found in re.finditer(pattern, lowered, flags=re.I):
            raw = found.group(1).replace(",", "").lower()
            try:
                value = float(raw[:-1]) * 1000 if raw.endswith("k") else float(raw)
            except Exception:
                continue
            # Treat "sold" as lower-confidence rolling demand proxy over roughly 90 days.
            values.append(value / 3.0)
    if values:
        return max(values)
    return None


def _extract_temu_sold_count(text: str) -> float | None:
    matches = re.findall(r"(\d+(?:\.\d+)?)\s*sold", text, flags=re.I)
    values: list[float] = []
    for raw in matches:
        try:
            values.append(float(raw))
        except Exception:
            continue
    return max(values) if values else None


def _extract_listing_age_days(text: str) -> int | None:
    for pattern in LISTING_AGE_PATTERNS:
        found = re.search(pattern, text, flags=re.I)
        if not found:
            continue
        try:
            raw = found.group(1).strip()
            if "/" in raw:
                if len(raw.split("/", 1)[0]) == 4:
                    dt = datetime.strptime(raw, "%Y/%m/%d").replace(tzinfo=timezone.utc)
                else:
                    dt = datetime.strptime(raw, "%m/%d/%Y").replace(tzinfo=timezone.utc)
            elif "-" in raw and raw[:4].isdigit():
                dt = datetime.strptime(raw, "%Y-%m-%d").replace(tzinfo=timezone.utc)
            else:
                dt = datetime.strptime(raw, "%B %d, %Y").replace(tzinfo=timezone.utc)
        except Exception:
            continue
        return max(0, int((_utc_now() - dt).total_seconds() // 86400))
    return None


def _pain_point_score(text: str) -> float:
    lowered = text.lower()
    hits = sum(1 for pattern in PAIN_POINT_PATTERNS if re.search(pattern, lowered, flags=re.I))
    return min(100.0, hits * 12.5)


def _competition_score(text: str) -> float:
    lowered = text.lower()
    ad_hits = len(re.findall(r"sponsored", lowered))
    top_brand_hits = len(re.findall(r"brand", lowered))
    duplicate_hits = len(re.findall(r"best seller", lowered))
    penalty = min(60, ad_hits * 8 + top_brand_hits * 4 + duplicate_hits * 6)
    return max(20.0, 100.0 - penalty)


def _price_stability_from_history(history: list[float]) -> float:
    cleaned = [float(x) for x in history if x is not None]
    if len(cleaned) < 3:
        return 50.0
    avg = sum(cleaned) / len(cleaned)
    if avg <= 0:
        return 0.0
    variance = sum((x - avg) ** 2 for x in cleaned) / len(cleaned)
    cv = (variance ** 0.5) / avg
    return max(0.0, min(100.0, 100.0 - cv * 200.0))


def _unit_to_kg(value: float, unit: str) -> float:
    unit = unit.lower()
    if unit in {"g", "克"}:
        return value / 1000.0
    return value


def _extract_weight(text: str, platform: str = "") -> tuple[float | None, str]:
    lowered = text.lower()
    if platform == "made_in_china":
        contextual = re.search(
            r"(?:package gross weight|gross weight|net weight)[^0-9]{0,80}(\d+(?:\.\d+)?)\s*(kg|g|公斤|克)",
            lowered,
            flags=re.I,
        )
        if contextual:
            return _unit_to_kg(float(contextual.group(1)), contextual.group(2)), "A"
    if platform == "yiwugo":
        gross = re.search(r"g\.w\./ctn[^0-9]{0,40}(\d+(?:\.\d+)?)\s*(kg|g|公斤|克)", lowered, flags=re.I)
        qty = re.search(r"qty/ctn[^0-9]{0,40}(\d+(?:\.\d+)?)\s*piece", lowered, flags=re.I)
        if gross and qty:
            gross_kg = _unit_to_kg(float(gross.group(1)), gross.group(2))
            qty_value = float(qty.group(1))
            if qty_value > 0:
                return round(gross_kg / qty_value, 4), "B"
    for pattern in WEIGHT_PATTERNS:
        match = re.search(pattern, lowered, flags=re.I)
        if not match:
            continue
        value = _unit_to_kg(float(match.group(1)), match.group(2))
        if 0.01 <= value <= 30:
            return value, "C"
    return None, "D"


def _extract_sell_candidates(platform: str, text: str, query: str) -> list[DemandCandidate]:
    rows: list[DemandCandidate] = []
    seen: set[str] = set()
    if platform == "amazon":
        matches = list(re.finditer(r'data-asin="([A-Z0-9]{10})"', text, flags=re.I))
        for idx_match, match in enumerate(matches):
            asin = match.group(1)
            link = f"https://www.amazon.com/dp/{asin}"
            if link in seen:
                continue
            seen.add(link)
            start = match.start()
            end = matches[idx_match + 1].start() if idx_match + 1 < len(matches) else min(len(text), start + 25000)
            snippet = text[start:end]
            title_match = re.search(r'<span[^>]*>([^<]{20,240})</span>', snippet, flags=re.I)
            title = _clean_text(title_match.group(1)) if title_match else query.title()
            if title.lower() in {"amazon", "prime", "limited time deal"}:
                title = query.title()
            price = _best_price_cny(snippet, platform)
            monthly_orders = _extract_monthly_orders(snippet)
            amazon_rank, amazon_category = _extract_amazon_best_seller_rank(snippet)
            amazon_rank_daily_proxy = _estimate_amazon_daily_orders_from_rank(amazon_rank, amazon_category)
            estimated_daily_orders = (monthly_orders / 30.0) if monthly_orders else amazon_rank_daily_proxy
            rating_value = _extract_rating_value(snippet)
            review_count = _extract_review_count(snippet)
            rows.append(
                DemandCandidate(
                    candidate_id=f"{platform}-{asin.lower()}",
                    title=title,
                    sell_platform=platform,
                    sell_link=link,
                    sell_price_cny=price,
                    query=query,
                    extracted_at=_utc_now_iso(),
                    estimated_daily_orders=estimated_daily_orders,
                    rating_value=rating_value,
                    review_count=review_count,
                    demand_confidence=65.0 if monthly_orders else (45.0 if amazon_rank_daily_proxy else 35.0),
                    raw_signals={
                        "price_extracted": price is not None,
                        "monthly_orders": monthly_orders,
                        "amazon_best_seller_rank": amazon_rank,
                        "amazon_best_seller_category": amazon_category,
                        "amazon_rank_daily_proxy": amazon_rank_daily_proxy,
                        "source": "amazon_search",
                    },
                )
            )
            if len(rows) >= 8:
                break
        if rows:
            return rows
    patterns = {
        "temu": r"(https://www\.temu\.com/[^\s\"'<>]+-s\.html(?:\?[^\s\"'<>]+)?|/[^\s\"'<>]+-s\.html(?:\?[^\s\"'<>]+)?)",
        "amazon": r"(https://www\.amazon\.com/dp/[A-Z0-9]{10}|/dp/[A-Z0-9]{10})",
        "walmart": r"(https://www\.walmart\.com/ip/[^\s\"'<>]+|/ip/[^\s\"'<>]+)",
    }
    for raw_link in re.findall(patterns.get(platform, r"$^"), text, flags=re.I):
        link = raw_link if raw_link.startswith("http") else {
            "temu": "https://www.temu.com",
            "amazon": "https://www.amazon.com",
            "walmart": "https://www.walmart.com",
        }[platform] + raw_link
        if platform == "temu" and link.rstrip("/") == "https://www.temu.com":
            continue
        if platform == "walmart" and "/search?" in link:
            continue
        if link in seen:
            continue
        seen.add(link)
        title = _title_from_link(link, query.title())
        price = _best_price_cny(text, platform)
        monthly_orders = _extract_monthly_orders(text)
        rating_value = _extract_rating_value(text)
        review_count = _extract_review_count(text)
        rows.append(
            DemandCandidate(
                candidate_id=f"{platform}-{_slug(link)}",
                title=title,
                sell_platform=platform,
                sell_link=link,
                sell_price_cny=price,
                query=query,
                extracted_at=_utc_now_iso(),
                estimated_daily_orders=(monthly_orders / 30.0) if monthly_orders else None,
                rating_value=rating_value,
                review_count=review_count,
                demand_confidence=55.0 if monthly_orders else 20.0,
                raw_signals={"price_extracted": price is not None, "monthly_orders": monthly_orders},
            )
        )
        if len(rows) >= 5:
            break
    if not rows:
        fallback_price = _best_price_cny(text, platform)
        rows.append(
            DemandCandidate(
                candidate_id=f"{platform}-{_slug(query)}",
                title=query.title(),
                sell_platform=platform,
                sell_link=url_for_sell(platform, query),
                sell_price_cny=fallback_price,
                query=query,
                extracted_at=_utc_now_iso(),
                estimated_daily_orders=None,
                rating_value=_extract_rating_value(text),
                review_count=_extract_review_count(text),
                demand_confidence=10.0,
                raw_signals={"fallback_from_search_page": True},
            )
        )
    return rows


def url_for_sell(platform: str, query: str) -> str:
    return SELL_PLATFORM_SEARCH[platform](query)


def _extract_source_candidate(platform: str, text: str, query: str, fetch_tool: str) -> SourceCandidate:
    price_cny = _extract_platform_price_cny(text, platform)
    weight, grade = _extract_weight(text[:120000], platform)
    raw_link = ""
    if platform == "1688":
        for candidate_link in re.findall(r"(https?://[^\s\"']+offer[^\s\"']+|/offer/[^\s\"']+)", text, flags=re.I):
            raw_link = candidate_link
            break
    elif platform == "yiwugo":
        for candidate_link in re.findall(r"(https?://en\.yiwugo\.com/product/detail/[^\s\"']+|/product/detail/[^\s\"']+)", text, flags=re.I):
            raw_link = candidate_link
            break
    elif platform == "made_in_china":
        candidates = re.findall(r"https?://[^\s\"']+made-in-china\.com/product/[^\s\"']+", text, flags=re.I)
        if not candidates:
            candidates = re.findall(r"/product/[^\s\"']+", text, flags=re.I)
        for candidate_link in candidates:
            if any(skip in candidate_link for skip in ("productdirectory.do", "/products-search/", "/search/product", "/suggest/")):
                continue
            raw_link = candidate_link
            break
    if raw_link and not raw_link.startswith("http"):
        raw_link = {
            "1688": "https://detail.1688.com",
            "yiwugo": "https://en.yiwugo.com",
            "made_in_china": "https://www.made-in-china.com",
        }[platform] + raw_link
    blocked = any(re.search(p, text, flags=re.I) for p in BLOCK_PATTERNS.get(platform, []))
    match_score = 35.0
    if price_cny is not None:
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
        price_cny=price_cny,
        weight_kg=weight,
        weight_grade=grade,
        fetch_tool=fetch_tool,
        match_score=min(100.0, match_score),
        blocked=blocked,
        notes="blocked" if blocked else "",
    )


def _extract_source_links(platform: str, text: str) -> list[str]:
    raw_links: list[str] = []
    if platform == "1688":
        raw_links.extend(re.findall(r"(https?://[^\s\"']+offer[^\s\"']+|/offer/[^\s\"']+)", text, flags=re.I))
    elif platform == "yiwugo":
        raw_links.extend(re.findall(r"(https?://en\.yiwugo\.com/product/detail/[^\s\"']+|/product/detail/[^\s\"']+)", text, flags=re.I))
    elif platform == "made_in_china":
        raw_links.extend(re.findall(r"https?://[^\s\"']+made-in-china\.com/product/[^\s\"']+", text, flags=re.I))
        raw_links.extend(re.findall(r"/product/[^\s\"']+", text, flags=re.I))
    resolved: list[str] = []
    for raw_link in raw_links:
        if any(skip in raw_link for skip in ("productdirectory.do", "/products-search/", "/search/product", "/suggest/")):
            continue
        link = raw_link
        if not link.startswith("http"):
            link = {
                "1688": "https://detail.1688.com",
                "yiwugo": "https://en.yiwugo.com",
                "made_in_china": "https://www.made-in-china.com",
            }[platform] + link
        if link not in resolved:
            resolved.append(link)
    return resolved[:5]


def _source_title_from_link(link: str) -> str:
    cleaned = re.sub(r"https?://", "", str(link or ""), flags=re.I)
    cleaned = re.sub(r"[?#].*$", "", cleaned)
    slug = cleaned.rstrip("/").split("/")[-1]
    slug = re.sub(r"\.html?$", "", slug, flags=re.I)
    slug = re.sub(r"[-_]+", " ", slug)
    return _clean_text(slug)


def _candidate_overlap_score(query: str, text: str) -> float:
    query_tokens = set(_normalize_title(query).split())
    text_tokens = set(_normalize_title(text).split())
    if not query_tokens or not text_tokens:
        return 0.0
    overlap = len(query_tokens & text_tokens)
    coverage = overlap / max(1, len(query_tokens))
    return min(20.0, coverage * 20.0)


def _enrich_source_candidate(platform: str, candidate: SourceCandidate) -> SourceCandidate:
    if not candidate.link or (candidate.weight_kg is not None and candidate.price_cny is not None):
        return candidate
    if platform not in {"made_in_china", "yiwugo", "1688"}:
        return candidate
    detail = fetch_best(platform, candidate.link, max_tools=2)
    detail_weight, detail_grade = _extract_weight(detail.text[:120000], platform)
    detail_price = _extract_platform_price_cny(detail.text, platform)
    notes = candidate.notes
    if detail.status == "blocked":
        notes = (notes + " | detail_blocked").strip(" |")
    return SourceCandidate(
        platform=candidate.platform,
        link=candidate.link,
        title=candidate.title,
        price_cny=detail_price if detail_price is not None else candidate.price_cny,
        weight_kg=detail_weight if detail_weight is not None else candidate.weight_kg,
        weight_grade=detail_grade if detail_weight is not None else candidate.weight_grade,
        fetch_tool=f"{candidate.fetch_tool}+detail:{detail.tool}",
        match_score=min(100.0, candidate.match_score + (12.0 if detail_weight is not None else 0.0)),
        blocked=candidate.blocked and detail.status == "blocked",
        notes=notes,
    )


def _best_source_for_platform(platform: str, candidate: DemandCandidate, *, max_tools: int | None = None) -> tuple[SourceCandidate, list[dict[str, Any]]]:
    fetch_log: list[dict[str, Any]] = []
    best: SourceCandidate | None = None
    for query_variant in _source_query_variants(candidate):
        url = SOURCE_PLATFORM_SEARCH[platform](query_variant)
        result = fetch_best(platform, url, max_tools=max_tools)
        fetch_log.append(
            {"stage": "match", "platform": platform, "query": query_variant, "tool": result.tool, "status": result.status, "score": result.score}
        )
        row = _extract_source_candidate(platform, result.text, query_variant, result.tool)
        row = _enrich_source_candidate(platform, row)
        if best is None or row.match_score > best.match_score:
            best = row
        extra_links = _extract_source_links(platform, result.text)
        for detail_link in extra_links[:2]:
            detail_result = fetch_best(platform, detail_link, max_tools=2 if max_tools is None else max_tools)
            fetch_log.append(
                {
                    "stage": "match_detail",
                    "platform": platform,
                    "query": query_variant,
                    "link": detail_link,
                    "tool": detail_result.tool,
                    "status": detail_result.status,
                    "score": detail_result.score,
                }
            )
            detail_row = SourceCandidate(
                platform=platform,
                link=detail_link,
                title=_source_title_from_link(detail_link) or query_variant.title(),
                price_cny=_extract_platform_price_cny(detail_result.text, platform),
                weight_kg=_extract_weight(detail_result.text[:120000], platform)[0],
                weight_grade=_extract_weight(detail_result.text[:120000], platform)[1],
                fetch_tool=f"detail:{detail_result.tool}",
                match_score=min(
                    100.0,
                    35.0
                    + (20.0 if _extract_platform_price_cny(detail_result.text, platform) is not None else 0.0)
                    + (25.0 if _extract_weight(detail_result.text[:120000], platform)[0] is not None else 0.0)
                    + _candidate_overlap_score(query_variant, _source_title_from_link(detail_link) + " " + detail_result.text[:4000]),
                ),
                blocked=detail_result.status == "blocked",
                notes="detail_probe",
            )
            if best is None or detail_row.match_score > best.match_score:
                best = detail_row
        if row.match_score >= 75 and row.weight_grade in {"A", "B"} and not row.blocked:
            break
    return best or SourceCandidate(platform=platform, link=SOURCE_PLATFORM_SEARCH[platform](candidate.query), title=candidate.title, price_cny=None, weight_kg=None, weight_grade="D", fetch_tool="none", match_score=0.0, blocked=True, notes="no_source_probe"), fetch_log


def _enrich_sell_candidate(candidate: DemandCandidate, *, max_tools: int | None = None) -> tuple[DemandCandidate, dict[str, Any]]:
    tool_plan = {
        "temu": ["agent_browser", "playwright_stealth", "curl_cffi", "crawl4ai"],
        "amazon": ["curl_cffi", "agent_browser", "playwright_stealth", "direct_http", "crawl4ai"],
        "walmart": ["agent_browser", "playwright_stealth", "curl_cffi", "direct_http", "crawl4ai"],
    }.get(candidate.sell_platform, [fetch_best(candidate.sell_platform, candidate.sell_link, max_tools=max_tools).tool])
    if max_tools is not None:
        tool_plan = tool_plan[:max_tools]
    best_price = candidate.sell_price_cny
    best_monthly_orders = candidate.estimated_daily_orders * 30.0 if candidate.estimated_daily_orders else None
    best_listing_age = candidate.listing_age_days
    best_rating = candidate.rating_value
    best_reviews = candidate.review_count
    best_title = candidate.title
    best_confidence = candidate.demand_confidence
    best_status = "unknown"
    best_tool = "none"
    best_amazon_rank = (candidate.raw_signals or {}).get("amazon_best_seller_rank")
    best_amazon_category = (candidate.raw_signals or {}).get("amazon_best_seller_category")
    best_amazon_rank_daily_proxy = (candidate.raw_signals or {}).get("amazon_rank_daily_proxy")
    for tool in tool_plan:
        fetcher = TOOL_FETCHERS.get(tool)
        if not fetcher:
            continue
        try:
            text, err = fetcher(candidate.sell_link)
        except Exception:
            continue
        detail = _score_fetch(candidate.sell_platform, tool, text, err)
        best_status = detail.status
        best_tool = detail.tool
        price = _best_price_cny(detail.text, candidate.sell_platform)
        if price is not None:
            best_price = price
        monthly_orders = _extract_monthly_orders(detail.text)
        if monthly_orders is None and candidate.sell_platform == "temu":
            sold_proxy = _extract_temu_sold_count(detail.text)
            if sold_proxy:
                monthly_orders = sold_proxy
        if monthly_orders is not None:
            best_monthly_orders = max(best_monthly_orders or 0.0, monthly_orders)
            best_confidence = max(best_confidence, 70.0 if candidate.sell_platform == "temu" else 65.0)
        elif candidate.sell_platform == "amazon":
            amazon_rank, amazon_category = _extract_amazon_best_seller_rank(detail.text)
            amazon_rank_daily_proxy = _estimate_amazon_daily_orders_from_rank(amazon_rank, amazon_category)
            if amazon_rank_daily_proxy is not None:
                inferred_monthly_orders = amazon_rank_daily_proxy * 30.0
                best_monthly_orders = max(best_monthly_orders or 0.0, inferred_monthly_orders)
                best_confidence = max(best_confidence, 48.0)
                best_amazon_rank = amazon_rank
                best_amazon_category = amazon_category
                best_amazon_rank_daily_proxy = amazon_rank_daily_proxy
        listing_age_days = _extract_listing_age_days(detail.text)
        if listing_age_days is not None:
            best_listing_age = listing_age_days
            best_confidence = max(best_confidence, 70.0)
        rating_value = _extract_rating_value(detail.text)
        if rating_value is not None:
            best_rating = rating_value
        review_count = _extract_review_count(detail.text)
        if review_count is not None:
            best_reviews = review_count
        title = _extract_page_title(detail.text)
        if title:
            best_title = title
        if best_monthly_orders is not None and best_listing_age is not None:
            break
    updated = DemandCandidate(
        candidate_id=candidate.candidate_id,
        title=best_title,
        sell_platform=candidate.sell_platform,
        sell_link=candidate.sell_link,
        sell_price_cny=best_price,
        query=candidate.query,
        extracted_at=candidate.extracted_at,
        estimated_daily_orders=(best_monthly_orders / 30.0) if best_monthly_orders else candidate.estimated_daily_orders,
        listing_age_days=best_listing_age,
        rating_value=best_rating,
        review_count=best_reviews,
        demand_confidence=max(candidate.demand_confidence, best_confidence),
        demand_refresh_priority=candidate.demand_refresh_priority,
        raw_signals={
            **candidate.raw_signals,
            "detail_tool": best_tool,
            "detail_status": best_status,
            "detail_monthly_orders": best_monthly_orders,
            "amazon_best_seller_rank": best_amazon_rank,
            "amazon_best_seller_category": best_amazon_category,
            "amazon_rank_daily_proxy": best_amazon_rank_daily_proxy,
        },
    )
    return updated, {"stage": "sell_detail", "platform": candidate.sell_platform, "query": candidate.query, "tool": best_tool, "status": best_status, "score": 0}


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
            platform_fee_rate=None,
            estimated_daily_orders=candidate.estimated_daily_orders,
            listing_age_days=candidate.listing_age_days,
            demand_score=0.0,
            competition_score=0.0,
            differentiation_score=0.0,
            price_stability_score=0.0,
            launchability_score=0.0,
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
            platform_fee_rate=PLATFORM_FEE_TABLE.get(candidate.sell_platform, DEFAULT_PLATFORM_FEE),
            estimated_daily_orders=candidate.estimated_daily_orders,
            listing_age_days=candidate.listing_age_days,
            demand_score=0.0,
            competition_score=0.0,
            differentiation_score=0.0,
            price_stability_score=0.0,
            launchability_score=0.0,
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
            platform_fee_rate=PLATFORM_FEE_TABLE.get(candidate.sell_platform, DEFAULT_PLATFORM_FEE),
            estimated_daily_orders=candidate.estimated_daily_orders,
            listing_age_days=candidate.listing_age_days,
            demand_score=0.0,
            competition_score=0.0,
            differentiation_score=0.0,
            price_stability_score=0.0,
            launchability_score=0.0,
            confidence_score=min(79.0, best_source.match_score),
            weight_grade=best_source.weight_grade,
            qualified=False,
            reasons=["missing_sell_price", *reasons],
        )
    platform_fee_rate = PLATFORM_FEE_TABLE.get(candidate.sell_platform, DEFAULT_PLATFORM_FEE)
    platform_fee_amount = candidate.sell_price_cny * platform_fee_rate
    logistics = 59 * best_source.weight_kg + 35 * best_source.weight_kg + 1.4
    gross_profit = candidate.sell_price_cny - best_source.price_cny - logistics - platform_fee_amount
    margin = gross_profit / candidate.sell_price_cny if candidate.sell_price_cny else None
    conservative_sell = candidate.sell_price_cny * 0.95
    conservative_purchase = best_source.price_cny * 1.05
    conservative_weight = best_source.weight_kg * 1.10
    conservative_fee = conservative_sell * platform_fee_rate
    conservative_profit = conservative_sell - conservative_purchase - (59 * conservative_weight) - (35 * conservative_weight) - conservative_fee - 1.4
    conservative_margin = conservative_profit / conservative_sell if conservative_sell else None
    estimated_daily_orders = candidate.estimated_daily_orders or 0.0
    listing_age_days = candidate.listing_age_days
    demand_score = min(100.0, estimated_daily_orders * 2.0) if estimated_daily_orders else min(60.0, candidate.demand_confidence)
    if estimated_daily_orders < 30:
        reasons.append("estimated_daily_orders_below_threshold")
    if listing_age_days is None:
        reasons.append("listing_age_unknown")
    elif listing_age_days > 730:
        reasons.append("listing_age_above_two_years")
    competition_score = _competition_score(candidate.title)
    differentiation_score = _pain_point_score(candidate.title)
    price_history = (candidate.raw_signals or {}).get("observed_sell_prices", []) or []
    if candidate.sell_price_cny is not None:
        price_history = [*price_history, candidate.sell_price_cny]
    price_stability_score = _price_stability_from_history(price_history)
    launchability_score = round(
        demand_score * 0.25
        + (min(100.0, max(0.0, (margin or 0.0) * 100.0 * 1.5)) if margin is not None else 0.0) * 0.25
        + competition_score * 0.20
        + differentiation_score * 0.15
        + price_stability_score * 0.15,
        2,
    )
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
        and estimated_daily_orders >= 30
        and listing_age_days is not None
        and listing_age_days <= 730
        and margin is not None
        and conservative_margin is not None
        and margin >= 0.45
        and conservative_margin >= 0.45
        and best_source.weight_grade in {"A", "B"}
        and launchability_score >= 70.0
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
        platform_fee_rate=platform_fee_rate,
        estimated_daily_orders=round(estimated_daily_orders, 2) if estimated_daily_orders else None,
        listing_age_days=listing_age_days,
        demand_score=round(demand_score, 2),
        competition_score=round(competition_score, 2),
        differentiation_score=round(differentiation_score, 2),
        price_stability_score=round(price_stability_score, 2),
        launchability_score=launchability_score,
        confidence_score=round(confidence, 2),
        weight_grade=best_source.weight_grade,
        qualified=qualified,
        reasons=reasons,
    )


def _refresh_priority(row: dict[str, Any]) -> float:
    monthly_orders = float(((row.get("raw_signals", {}) or {}).get("monthly_orders", 0) or 0) or 0)
    detail_monthly_orders = float(((row.get("raw_signals", {}) or {}).get("detail_monthly_orders", 0) or 0) or 0)
    best_monthly_orders = max(monthly_orders, detail_monthly_orders)
    estimated_daily_orders = float(row.get("estimated_daily_orders", 0) or 0)
    review_count = float(row.get("review_count", 0) or 0)
    listing_age_days = row.get("listing_age_days")
    amazon_rank_daily_proxy = float(((row.get("raw_signals", {}) or {}).get("amazon_rank_daily_proxy", 0) or 0) or 0)
    score = 0.0
    if best_monthly_orders:
        score += min(60.0, best_monthly_orders / 20.0)
    elif estimated_daily_orders:
        score += min(50.0, estimated_daily_orders * 1.5)
    elif amazon_rank_daily_proxy:
        score += min(45.0, amazon_rank_daily_proxy * 1.5)
    score += min(20.0, review_count / 5000.0)
    if listing_age_days is None:
        score += 15.0
    elif listing_age_days <= 730:
        score += 10.0
    return round(score, 2)


def _ensure_refresh_priority(row: dict[str, Any]) -> float:
    priority = row.get("demand_refresh_priority")
    if priority is None:
        priority = _refresh_priority(row)
        row["demand_refresh_priority"] = priority
    return float(priority or 0.0)


def _load_state() -> dict[str, Any]:
    default = {"runs": [], "candidates": {}, "last_discovery_at": "", "last_match_at": "", "last_report_date": ""}
    if not STATE_PATH.exists():
        return default
    try:
        payload = json.loads(STATE_PATH.read_text(encoding="utf-8"))
    except Exception:
        return default
    if not isinstance(payload, dict):
        return default
    if "candidates" not in payload:
        payload["candidates"] = {}
    payload.setdefault("runs", [])
    payload.setdefault("last_discovery_at", "")
    payload.setdefault("last_match_at", "")
    payload.setdefault("last_report_date", "")
    payload.pop("recent_candidates", None)
    for row in (payload.get("candidates") or {}).values():
        if not isinstance(row, dict):
            continue
        row.setdefault("raw_signals", {})
        row["demand_refresh_priority"] = _ensure_refresh_priority(row)
        decision = row.get("decision")
        if isinstance(decision, dict):
            row["decision"] = _decision_payload(decision)
    return payload


def _save_state(payload: dict[str, Any]) -> None:
    STATE_PATH.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _decision_payload(payload: dict[str, Any]) -> dict[str, Any]:
    merged = dict(payload)
    for key, value in DECISION_DEFAULTS.items():
        merged.setdefault(key, value)
    merged.setdefault("reasons", [])
    return {key: merged.get(key) for key in ArbitrageDecision.__dataclass_fields__.keys()}


def _decision_from_payload(payload: dict[str, Any]) -> ArbitrageDecision:
    return ArbitrageDecision(**_decision_payload(payload))


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
        "毛利额", "毛利率", "保守毛利率", "平台佣金率", "估算日单量", "上架天数", "需求分", "竞争分",
        "差异化分", "价格稳定分", "综合可做分", "置信度", "重量等级", "是否入选", "原因"
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
            item.platform_fee_rate,
            item.estimated_daily_orders,
            item.listing_age_days,
            item.demand_score,
            item.competition_score,
            item.differentiation_score,
            item.price_stability_score,
            item.launchability_score,
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
    governance = summary.get("governance") or {}
    lines = [
        "# Cross-market arbitrage run",
        "",
        f"- Run ID: `{run_id}`",
        f"- Generated at: `{summary['generated_at']}`",
        f"- Qualified count: `{summary['qualified_count']}`",
        f"- Discovery candidates: `{summary['discovery_candidate_count']}`",
        f"- Governance status: `{governance.get('status', 'unknown')}`",
        "",
        "## Governance",
        "",
        f"- Primary blocker: `{governance.get('primary_blocker', 'none')}`",
        f"- Next actions: `{', '.join(governance.get('next_actions', []) or ['none'])}`",
        f"- Failure categories: `{json.dumps(governance.get('failure_categories', {}), ensure_ascii=False)}`",
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
            f"- Estimated daily orders: `{item.estimated_daily_orders}`",
            f"- Listing age days: `{item.listing_age_days}`",
            f"- Margin: `{item.gross_margin_rate}`",
            f"- Conservative margin: `{item.conservative_margin_rate}`",
            f"- Launchability: `{item.launchability_score}`",
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


def _state_candidate_window(state: dict[str, Any], *, hours: int = REPORT_WINDOW_HOURS) -> list[dict[str, Any]]:
    cutoff = _utc_now() - timedelta(hours=hours)
    rows: list[dict[str, Any]] = []
    for payload in (state.get("candidates") or {}).values():
        discovered_at = payload.get("discovered_at") or payload.get("updated_at") or ""
        dt = parse_dt(discovered_at)
        if dt and dt >= cutoff:
            rows.append(payload)
    return rows


def parse_dt(value: str) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(timezone.utc)
    except Exception:
        return None


def _needs_rematch(row: dict[str, Any]) -> bool:
    last_matched = parse_dt(str(row.get("last_matched_at", "")))
    if last_matched is None:
        return True
    updated_at = parse_dt(str(row.get("updated_at", "")))
    if updated_at and updated_at > last_matched:
        return True
    return not bool(row.get("decision"))


def _send_to_telegram(*, chat_id: str, text: str, media_paths: list[Path]) -> list[dict[str, Any]]:
    deliveries: list[dict[str, Any]] = []
    text_cmd = [OPENCLAW_BIN, "message", "send", "--channel", "telegram", "--target", chat_id, "--message", text, "--json"]
    text_proc = _run(text_cmd, timeout=60)
    deliveries.append({"kind": "text", "returncode": text_proc.returncode, "stdout": text_proc.stdout.strip(), "stderr": text_proc.stderr.strip()})
    for media_path in media_paths:
        cmd = [OPENCLAW_BIN, "message", "send", "--channel", "telegram", "--target", chat_id, "--media", str(media_path), "--force-document", "--json"]
        proc = _run(cmd, timeout=120)
        deliveries.append({"kind": "media", "path": str(media_path), "returncode": proc.returncode, "stdout": proc.stdout.strip(), "stderr": proc.stderr.strip()})
    return deliveries


def _summary_text(summary: dict[str, Any], decisions: list[ArbitrageDecision]) -> str:
    governance = summary.get("governance") or {}
    qualified = [item for item in decisions if item.qualified]
    lines = [
        f"Cross-market arbitrage run completed.",
        f"Run ID: {summary['run_id']}",
        f"过去24小时候选数: {summary['discovery_candidate_count']}",
        f"通过强规则候选数: {summary['qualified_count']}",
        f"治理状态: {governance.get('status', 'unknown')}",
    ]
    primary_blocker = governance.get("primary_blocker")
    if primary_blocker and primary_blocker != "none":
        lines.append(f"主阻塞: {primary_blocker}")
    next_actions = governance.get("next_actions", []) or []
    if next_actions:
        lines.append(f"下一步: {', '.join(next_actions[:3])}")
    if qualified:
        top = qualified[:3]
        for item in top:
            lines.append(
                f"- {item.product_name}: 买 {item.buy_platform} / 卖 {item.sell_platform} / 毛利率 {item.gross_margin_rate:.2%}"
            )
    else:
        lines.append("- 本轮没有候选通过强阈值；请看附件里的审计和证据。")
    return "\n".join(lines)


def _decision_failure_categories(decisions: list[ArbitrageDecision]) -> dict[str, int]:
    categories: dict[str, int] = {}
    for item in decisions:
        if item.qualified:
            continue
        reason = "unknown_failure"
        for candidate in item.reasons or []:
            normalized = str(candidate or "").strip()
            if normalized:
                reason = normalized
                break
        categories[reason] = categories.get(reason, 0) + 1
    return dict(sorted(categories.items(), key=lambda row: (-row[1], row[0])))


def _build_governance_summary(rows: list[dict[str, Any]], decisions: list[ArbitrageDecision]) -> dict[str, Any]:
    failure_categories = _decision_failure_categories(decisions)
    primary_blocker = next(iter(failure_categories.keys()), "none")
    if any(item.qualified for item in decisions):
        status = "healthy"
        next_actions = ["continue_discovery_cadence", "continue_matching_cadence"]
    elif rows and primary_blocker == "no_usable_source_match":
        status = "attention_required"
        next_actions = ["strengthen_source_matching", "increase_source_detail_extraction", "review_source_site_health"]
    elif rows and primary_blocker in {"listing_age_unknown", "estimated_daily_orders_below_threshold"}:
        status = "attention_required"
        next_actions = ["strengthen_demand_signal_extraction", "improve_listing_age_capture", "improve_order_estimation"]
    else:
        status = "watching"
        next_actions = ["continue_discovery_cadence", "continue_matching_cadence", "inspect_recent_failures"]
    return {
        "status": status,
        "primary_blocker": primary_blocker,
        "failure_categories": failure_categories,
        "next_actions": next_actions,
    }


def run_once(*, test: bool = False) -> dict[str, Any]:
    run_id = _utc_now().strftime("%Y%m%dT%H%M%SZ")
    queries = DEFAULT_DISCOVERY_QUERIES[:1] if test else DEFAULT_DISCOVERY_QUERIES
    sell_platforms = ["temu", "amazon"] if test else ["temu", "amazon", "walmart"]
    source_platforms = ["1688", "yiwugo", "made_in_china"] if test else ["1688", "yiwugo", "made_in_china"]
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


def _discover_cycle(state: dict[str, Any], *, test: bool = False) -> tuple[dict[str, Any], list[DemandCandidate], list[dict[str, Any]]]:
    queries = DEFAULT_DISCOVERY_QUERIES[:1] if test else DEFAULT_DISCOVERY_QUERIES
    sell_platforms = ["temu", "amazon"] if test else ["temu", "amazon", "walmart"]
    max_tools = 2 if test else None
    fetch_log: list[dict[str, Any]] = []
    candidates: list[DemandCandidate] = []
    for query in queries:
        for platform in sell_platforms:
            result = fetch_best(platform, url_for_sell(platform, query), max_tools=max_tools)
            fetch_log.append({"stage": "discover", "platform": platform, "query": query, "tool": result.tool, "status": result.status, "score": result.score})
            candidates.extend(_extract_sell_candidates(platform, result.text, query))
    enriched: list[DemandCandidate] = []
    for item in candidates:
        updated, detail_log = _enrich_sell_candidate(item, max_tools=max_tools)
        fetch_log.append(detail_log)
        enriched.append(updated)
    candidates = enriched
    bucket = state.setdefault("candidates", {})
    for item in candidates:
        row = bucket.get(item.candidate_id, {})
        previous_snapshot = {
            "title": row.get("title"),
            "sell_price_cny": row.get("sell_price_cny"),
            "estimated_daily_orders": row.get("estimated_daily_orders"),
            "listing_age_days": row.get("listing_age_days"),
            "rating_value": row.get("rating_value"),
            "review_count": row.get("review_count"),
        }
        price_history = list(row.get("observed_sell_prices", []) or [])
        if item.sell_price_cny is not None:
            price_history.append(item.sell_price_cny)
            price_history = price_history[-20:]
        row.update(asdict(item))
        row["updated_at"] = _utc_now_iso()
        row["discovered_at"] = row.get("discovered_at") or item.extracted_at
        row["observed_sell_prices"] = price_history
        row.setdefault("source_matches", [])
        current_snapshot = {
            "title": row.get("title"),
            "sell_price_cny": row.get("sell_price_cny"),
            "estimated_daily_orders": row.get("estimated_daily_orders"),
            "listing_age_days": row.get("listing_age_days"),
            "rating_value": row.get("rating_value"),
            "review_count": row.get("review_count"),
        }
        if previous_snapshot != current_snapshot:
            row.pop("last_matched_at", None)
            row.pop("decision", None)
            row["source_matches"] = []
        row["demand_refresh_priority"] = _refresh_priority(row)
        bucket[item.candidate_id] = row
    state["last_discovery_at"] = _utc_now_iso()
    return state, candidates, fetch_log


def _match_cycle(state: dict[str, Any], *, test: bool = False) -> tuple[dict[str, Any], list[ArbitrageDecision], list[dict[str, Any]]]:
    source_platforms = ["1688", "yiwugo", "made_in_china"] if test else ["1688", "yiwugo", "made_in_china"]
    max_tools = 2 if test else None
    fetch_log: list[dict[str, Any]] = []
    decisions: list[ArbitrageDecision] = []
    ordered_candidates = sorted(
        (state.get("candidates") or {}).items(),
        key=lambda item: (-_ensure_refresh_priority(item[1] or {}), str(item[0])),
    )
    for candidate_id, payload in ordered_candidates:
        if not _needs_rematch(payload):
            continue
        candidate = DemandCandidate(**{k: payload[k] for k in DemandCandidate.__dataclass_fields__.keys() if k in payload})
        rows: list[SourceCandidate] = []
        for platform in source_platforms:
            best_row, best_log = _best_source_for_platform(platform, candidate, max_tools=max_tools)
            fetch_log.extend(best_log)
            rows.append(best_row)
        payload["source_matches"] = [asdict(row) for row in rows]
        payload["last_matched_at"] = _utc_now_iso()
        decision = _compute_decision(candidate, rows)
        payload["decision"] = asdict(decision)
        decisions.append(decision)
    state["last_match_at"] = _utc_now_iso()
    return state, decisions, fetch_log


def _report_cycle(
    state: dict[str, Any],
    *,
    chat_id: str | None,
    force_send: bool = False,
    scheduler_policy: dict[str, Any] | None = None,
) -> dict[str, Any]:
    run_id = _utc_now().strftime("%Y%m%dT%H%M%SZ")
    scheduler_policy = scheduler_policy or {}
    rows = _state_candidate_window(state, hours=REPORT_WINDOW_HOURS)
    decisions: list[ArbitrageDecision] = []
    fetch_log: list[dict[str, Any]] = []
    for payload in rows:
        decision = payload.get("decision")
        if decision:
            decisions.append(_decision_from_payload(decision))
    summary = {
        "run_id": run_id,
        "generated_at": _utc_now_iso(),
        "mode": "scheduled",
        "discovery_candidate_count": len(rows),
        "qualified_count": sum(1 for item in decisions if item.qualified),
        "timing": {
            "discovery_interval_seconds": int(scheduler_policy.get("discovery_interval_seconds", DISCOVERY_INTERVAL_SECONDS) or DISCOVERY_INTERVAL_SECONDS),
            "matching_interval_seconds": int(scheduler_policy.get("matching_interval_seconds", MATCH_INTERVAL_SECONDS) or MATCH_INTERVAL_SECONDS),
            "report_hour_new_york": int(scheduler_policy.get("report_hour_new_york", REPORT_HOUR) or REPORT_HOUR),
        },
        "governance": _build_governance_summary(rows, decisions),
        "scheduler_policy": scheduler_policy,
    }
    excel_path = _write_excel(run_id, decisions, summary)
    md_path = _write_markdown(run_id, decisions, summary)
    payload = {
        "summary": summary,
        "decisions": [asdict(item) for item in decisions],
        "fetch_log": fetch_log,
        "deliveries": [],
    }
    json_path = _write_json(run_id, payload)
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
    state["last_report_date"] = _ny_now().date().isoformat()
    deliveries = []
    if chat_id and force_send:
        deliveries = _send_to_telegram(chat_id=chat_id, text=_summary_text(summary, decisions), media_paths=[md_path, json_path, excel_path])
    summary["memory_writeback"] = record_memory_writeback(
        "project-cross-market-arbitrage",
        source="cross_market_arbitrage_cycle",
        summary={
            "attention_required": bool((summary.get("governance", {}) or {}).get("primary_blocker")),
            "state_patch": {},
            "governance_patch": {},
            "next_actions": [
                str(item).strip()
                for item in ((summary.get("governance", {}) or {}).get("next_actions", []) or [])
                if str(item).strip()
            ],
            "warnings": [str((summary.get("governance", {}) or {}).get("primary_blocker", "")).strip()] if str((summary.get("governance", {}) or {}).get("primary_blocker", "")).strip() else [],
            "errors": [],
            "decisions": ["cross_market_arbitrage_cycle_completed"],
            "memory_targets": ["project", "runtime"],
            "memory_reasons": ["cross_market_arbitrage_cycle", "project_arbitrage_feedback"],
        },
    )
    payload["summary"] = summary
    payload["deliveries"] = deliveries
    _write_json(run_id, payload)
    _write_json_file(
        LATEST_REPORT_PATH,
        {
            "run_id": run_id,
            "generated_at": summary["generated_at"],
            "qualified_count": summary["qualified_count"],
            "governance": summary.get("governance", {}) or {},
            "deliveries": deliveries,
            "excel_path": str(excel_path),
            "markdown_path": str(md_path),
            "json_path": str(json_path),
        },
    )
    _save_state(state)
    return {"run_id": run_id, "summary": summary, "excel_path": str(excel_path), "markdown_path": str(md_path), "json_path": str(json_path), "deliveries": deliveries}


def _discovery_due(state: dict[str, Any], interval_seconds: int = DISCOVERY_INTERVAL_SECONDS) -> bool:
    last = parse_dt(state.get("last_discovery_at", ""))
    return last is None or (_utc_now() - last).total_seconds() >= interval_seconds


def _match_due(state: dict[str, Any], interval_seconds: int = MATCH_INTERVAL_SECONDS) -> bool:
    last = parse_dt(state.get("last_match_at", ""))
    has_unmatched = any(_needs_rematch(row) for row in (state.get("candidates") or {}).values())
    return has_unmatched and (last is None or (_utc_now() - last).total_seconds() >= interval_seconds)


def _report_due(state: dict[str, Any], report_hour: int = REPORT_HOUR) -> bool:
    ny_now = _ny_now()
    if ny_now.hour < report_hour:
        return False
    return state.get("last_report_date") != ny_now.date().isoformat()


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
        state = _load_state()
        scheduler_policy = _load_scheduler_policy()
        scheduler_state = _load_scheduler_state()
        execution_flags = _execution_flags_from_scheduler_policy(scheduler_policy)
        discovery_interval = int(scheduler_policy.get("discovery_interval_seconds", DISCOVERY_INTERVAL_SECONDS) or DISCOVERY_INTERVAL_SECONDS)
        matching_interval = int(scheduler_policy.get("matching_interval_seconds", MATCH_INTERVAL_SECONDS) or MATCH_INTERVAL_SECONDS)
        report_hour = int(scheduler_policy.get("report_hour_new_york", REPORT_HOUR) or REPORT_HOUR)
        loop_sleep_seconds = int(scheduler_policy.get("loop_sleep_seconds", 300) or 300)
        changed = False
        effective_discovery = False
        effective_match = False
        effective_report = False
        if execution_flags["allow_discovery"] and _discovery_due(state, interval_seconds=discovery_interval):
            state, _, _ = _discover_cycle(state, test=False)
            changed = True
            effective_discovery = True
        if execution_flags["allow_match"] and _match_due(state, interval_seconds=matching_interval):
            state, _, _ = _match_cycle(state, test=False)
            changed = True
            effective_match = True
        if changed:
            _save_state(state)
        if execution_flags["allow_report"] and _report_due(state, report_hour=report_hour):
            _report_cycle(
                state,
                chat_id=os.environ.get("CROSS_MARKET_TELEGRAM_CHAT", DEFAULT_TELEGRAM_TARGET),
                force_send=True,
                scheduler_policy=scheduler_policy,
            )
            effective_report = True
        scheduler_state_after = {
            "updated_at": _utc_now_iso(),
            "last_mode": scheduler_policy.get("recommended_mode", ""),
            "last_repair_focus": str(scheduler_policy.get("repair_focus", "")).strip(),
            "last_repair_mode": str(scheduler_policy.get("repair_mode", "")).strip(),
            "loop_sleep_seconds": loop_sleep_seconds,
            "discovery_interval_seconds": discovery_interval,
            "matching_interval_seconds": matching_interval,
            "report_hour_new_york": report_hour,
            "last_allow_discovery": execution_flags["allow_discovery"],
            "last_allow_match": execution_flags["allow_match"],
            "last_allow_report": execution_flags["allow_report"],
            "last_effective_discovery": effective_discovery,
            "last_effective_match": effective_match,
            "last_effective_report": effective_report,
            "last_discovery_started_at": _utc_now_iso() if effective_discovery else scheduler_state.get("last_discovery_started_at", ""),
            "last_match_started_at": _utc_now_iso() if effective_match else scheduler_state.get("last_match_started_at", ""),
            "last_report_started_at": _utc_now_iso() if effective_report else scheduler_state.get("last_report_started_at", ""),
        }
        _write_scheduler_state(scheduler_state_after)
        time.sleep(loop_sleep_seconds)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=["once", "daemon"], default="once")
    parser.add_argument("--test", action="store_true")
    parser.add_argument("--send-telegram", action="store_true")
    parser.add_argument("--telegram-chat", default=DEFAULT_TELEGRAM_TARGET)
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()
    if args.mode == "daemon":
        return run_daemon()
    scheduler_policy = _load_scheduler_policy()
    scheduler_state_before = _load_scheduler_state()
    execution_flags = _execution_flags_from_scheduler_policy(scheduler_policy)
    if not args.force and scheduler_policy and not bool(scheduler_policy.get("start_tasks", True)):
        payload = {
            "ran": False,
            "reason": "scheduler_policy_start_tasks_false",
            "scheduler_policy": scheduler_policy,
            "execution_flags": execution_flags,
            "scheduler_state_before": scheduler_state_before,
        }
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return 0
    state = _load_state()
    discover_log = []
    match_log = []
    decisions = []
    if execution_flags["allow_discovery"]:
        state, _, discover_log = _discover_cycle(state, test=args.test)
    if execution_flags["allow_match"]:
        state, decisions, match_log = _match_cycle(state, test=args.test)
    _save_state(state)
    payload = _report_cycle(
        state,
        chat_id=args.telegram_chat if args.send_telegram else None,
        force_send=args.send_telegram,
        scheduler_policy=scheduler_policy,
    )
    payload["fetch_log_count"] = len(discover_log) + len(match_log)
    payload["qualified_preview"] = [asdict(item) for item in decisions if item.qualified][:3]
    payload["scheduler_policy"] = scheduler_policy
    payload["execution_flags"] = execution_flags
    payload["scheduler_state_before"] = scheduler_state_before
    scheduler_state_after = {
        "updated_at": _utc_now_iso(),
        "last_mode": scheduler_policy.get("recommended_mode", ""),
        "last_repair_focus": str(scheduler_policy.get("repair_focus", "")).strip(),
        "last_repair_mode": str(scheduler_policy.get("repair_mode", "")).strip(),
        "loop_sleep_seconds": int(scheduler_policy.get("loop_sleep_seconds", 300) or 300),
        "discovery_interval_seconds": int(scheduler_policy.get("discovery_interval_seconds", DISCOVERY_INTERVAL_SECONDS) or DISCOVERY_INTERVAL_SECONDS),
        "matching_interval_seconds": int(scheduler_policy.get("matching_interval_seconds", MATCH_INTERVAL_SECONDS) or MATCH_INTERVAL_SECONDS),
        "report_hour_new_york": int(scheduler_policy.get("report_hour_new_york", REPORT_HOUR) or REPORT_HOUR),
        "last_allow_discovery": execution_flags["allow_discovery"],
        "last_allow_match": execution_flags["allow_match"],
        "last_allow_report": execution_flags["allow_report"],
        "last_effective_discovery": execution_flags["allow_discovery"],
        "last_effective_match": execution_flags["allow_match"],
        "last_effective_report": True,
        "last_discovery_started_at": _utc_now_iso() if execution_flags["allow_discovery"] else scheduler_state_before.get("last_discovery_started_at", ""),
        "last_match_started_at": _utc_now_iso() if execution_flags["allow_match"] else scheduler_state_before.get("last_match_started_at", ""),
        "last_report_started_at": _utc_now_iso(),
    }
    payload["scheduler_state_after"] = scheduler_state_after
    _write_scheduler_state(scheduler_state_after)
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
