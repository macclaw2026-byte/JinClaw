#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import subprocess
import time
from pathlib import Path
from typing import Any


ROOT = Path("/Users/mac_claw/.openclaw/workspace")
AGENT_BROWSER = ROOT / "tools/agent-browser-local/node_modules/agent-browser/bin/agent-browser-darwin-arm64"
DEFAULT_CDP = "http://127.0.0.1:18800"


def _run(cmd: list[str], timeout: int = 30) -> subprocess.CompletedProcess[str]:
    return subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)


def _connect(cdp_url: str) -> dict[str, Any]:
    proc = _run([str(AGENT_BROWSER), "connect", cdp_url], timeout=20)
    return {"ok": proc.returncode == 0, "stdout": proc.stdout.strip(), "stderr": proc.stderr.strip()}


def _get(name: str) -> str:
    proc = _run([str(AGENT_BROWSER), "get", name], timeout=20)
    return proc.stdout.strip()


def _open(url: str) -> dict[str, Any]:
    proc = _run([str(AGENT_BROWSER), "open", url], timeout=30)
    return {"ok": proc.returncode == 0, "stdout": proc.stdout.strip(), "stderr": proc.stderr.strip()}


def _snapshot() -> str:
    proc = _run([str(AGENT_BROWSER), "snapshot"], timeout=40)
    return proc.stdout


def _signal_summary(text: str) -> dict[str, Any]:
    lowered = text.lower()
    keywords = {
        "sellersprite": "sellersprite" in lowered,
        "amazon": "amazon" in lowered,
        "keyword": "keyword" in lowered,
        "search_volume": "search volume" in lowered,
        "opportunity_score": "opportunity score" in lowered,
        "bsr": "bsr" in lowered,
        "monthly_sales_cn": "月销量" in text,
        "seller_sprite_cn": "卖家精灵" in text,
    }
    return {
        "signals": keywords,
        "matched": [key for key, value in keywords.items() if value],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Probe SellerSprite or related authorized browser pages via the current logged-in Chrome session")
    parser.add_argument("--cdp", default=DEFAULT_CDP)
    parser.add_argument("--url", help="Optional URL to open in the already logged-in browser session")
    parser.add_argument("--wait-seconds", type=float, default=4.0)
    parser.add_argument("--max-chars", type=int, default=12000)
    args = parser.parse_args()

    result: dict[str, Any] = {
        "cdp": args.cdp,
        "connect": _connect(args.cdp),
    }
    if not result["connect"]["ok"]:
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 1

    if args.url:
        result["open"] = _open(args.url)
        time.sleep(max(0.0, args.wait_seconds))

    current_url = _get("url")
    current_title = _get("title")
    snap = _snapshot()
    result["page"] = {
        "url": current_url,
        "title": current_title,
    }
    result["signals"] = _signal_summary(snap)
    result["snapshot_head"] = snap[: args.max_chars]
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
