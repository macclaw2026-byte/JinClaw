#!/usr/bin/env python3

from __future__ import annotations

import argparse
import json
import re
import urllib.request
from collections import defaultdict
from html import unescape
from pathlib import Path


PRIORITY_STATES = ["RI", "MA", "CT", "NH", "ME", "VT", "NY", "CA", "TX", "FL"]
EXCLUDE_DOMAINS = {"msn.com", "google.com"}
NEGATIVE_PATTERNS = [
    "paint",
    "tropical",
    "nursery",
    "landscape",
    "landscaping",
    "garden",
    "botanical",
    "florist",
    "flowers",
    "pest",
    "lawn",
    "irrigation",
]
GLOBAL_POSITIVE_PATTERNS = [
    "lighting",
    "light fixture",
    "showroom",
    "electrical",
    "electric",
    "interior design",
    "interiors",
    "architect",
    "architecture",
    "builder",
    "construction",
    "contractor",
    "design studio",
    "trade program",
]
TYPE_POSITIVE_PATTERNS = {
    "designer": ["interior", "interiors", "design", "architect", "architecture", "studio"],
    "lighting": ["lighting", "light", "controls", "fixture", "electrical supply", "showroom"],
    "electrician": ["electric", "electrical", "electrician", "supply", "power", "controls"],
    "contractor": ["contractor", "construction", "build", "remodel", "commercial", "residential"],
    "builder": ["builder", "custom home", "construction", "build", "remodel"],
    "showroom": ["showroom", "lighting", "home decor", "design center"],
    "dealer": ["dealer", "lighting", "showroom", "home decor"],
    "distributor": ["distributor", "wholesale", "lighting", "electrical supply", "dealer"],
}


def _read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _normalize_text(*parts: str) -> str:
    text = " ".join(part for part in parts if part).lower()
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def _extract_state(geo: str) -> str:
    match = re.search(r"\b([A-Z]{2})\b", geo or "")
    return match.group(1) if match else ""


def _fetch_page_summary(url: str) -> dict:
    request = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(request, timeout=10) as response:
        html = response.read(50000).decode("utf-8", "ignore")
    title_match = re.search(r"<title[^>]*>(.*?)</title>", html, re.I | re.S)
    desc_match = re.search(
        r"<meta[^>]+name=[\"']description[\"'][^>]+content=[\"'](.*?)[\"']",
        html,
        re.I | re.S,
    )
    return {
        "title": unescape(title_match.group(1).strip()) if title_match else "",
        "description": unescape(desc_match.group(1).strip()) if desc_match else "",
    }


def _relevance_verdict(account_type: str, company_name: str, domain: str, title: str, description: str) -> dict:
    text = _normalize_text(company_name, domain, title, description)
    negatives = [pattern for pattern in NEGATIVE_PATTERNS if pattern in text]
    global_hits = [pattern for pattern in GLOBAL_POSITIVE_PATTERNS if pattern in text]
    type_hits = [pattern for pattern in TYPE_POSITIVE_PATTERNS.get(account_type, []) if pattern in text]

    verdict = "review"
    if negatives and not global_hits and not type_hits:
        verdict = "exclude"
    elif type_hits or len(global_hits) >= 2:
        verdict = "accept"
    elif global_hits:
        verdict = "review"

    return {
        "verdict": verdict,
        "negative_hits": negatives,
        "global_positive_hits": global_hits,
        "type_positive_hits": type_hits,
    }


def _candidate_rank(item: dict) -> float:
    state = item.get("state", "")
    state_rank = PRIORITY_STATES.index(state) if state in PRIORITY_STATES else 99
    confidence = float(item.get("source_confidence", 0))
    total_score = float(item.get("total_score", 0))
    return total_score - state_rank * 1.5 + confidence * 4


def main() -> int:
    parser = argparse.ArgumentParser(description="Build priority target batches with website relevance verification.")
    parser.add_argument("--project-root", required=True)
    parser.add_argument("--cycle-id", required=True)
    args = parser.parse_args()

    project_root = Path(args.project_root).expanduser().resolve()
    cycle_id = args.cycle_id

    prospects = {
        item["account_id"]: item
        for item in _read_json(project_root / "output" / "prospect-data-engine" / "prospect-records.json")["items"]
    }
    queue = {
        item["account_id"]: item
        for item in _read_json(project_root / "output" / "marketing-automation-suite" / cycle_id / "execution-queue.json")[
            "items"
        ]
        if item.get("status") == "queued"
    }
    strategy = {
        item["account_id"]: item
        for item in _read_json(project_root / "output" / "marketing-automation-suite" / cycle_id / "strategy-tasks.json")[
            "items"
        ]
    }

    candidates = []
    relevance_log = []
    for account_id, prospect in prospects.items():
        queue_item = queue.get(account_id)
        strategy_item = strategy.get(account_id)
        if not queue_item or not strategy_item:
            continue

        company_name = (prospect.get("company_name") or "").strip()
        domain = (prospect.get("website_root_domain") or "").strip()
        if domain in EXCLUDE_DOMAINS:
            continue
        if len(company_name) <= 2 or company_name.lower() in {"ny", "ri", "ma", "ct", "nh", "me", "vt", "ca", "tx", "fl"}:
            continue

        state = _extract_state(prospect.get("geo") or "")
        source_family = prospect.get("source_family") or "seed_or_curated"
        source_url = prospect.get("source_url") or ""
        candidates.append(
            {
                "account_id": account_id,
                "company_name": company_name,
                "domain": domain,
                "geo": prospect.get("geo") or "",
                "state": state,
                "account_type": prospect.get("account_type"),
                "score_tier": prospect.get("score_tier"),
                "total_score": float(prospect.get("total_score", 0)),
                "source_confidence": float(prospect.get("source_confidence", 0)),
                "source_family": source_family,
                "top_signals": prospect.get("top_signals", []),
                "channel": queue_item.get("channel"),
                "path_type": queue_item.get("path_type"),
                "primary_angle": queue_item.get("primary_angle"),
                "cta": queue_item.get("CTA"),
                "followup_plan": strategy_item.get("followup_plan", []),
                "selection_bucket": "",
                "rank_score": round(_candidate_rank({**prospect, "state": state}), 2),
                "relevance_verdict": "unverified",
                "relevance_hits": {"global_positive_hits": [], "type_positive_hits": [], "negative_hits": []},
                "homepage_title": "",
                "fetch_url": "",
                "source_url": source_url,
            }
        )

    candidates.sort(key=lambda item: (-item["rank_score"], -item["total_score"], -item["source_confidence"]))
    verification_pool = candidates[:28]
    verified_candidates = []
    verification_ids = {item["account_id"] for item in verification_pool}

    for item in candidates:
        if item["account_id"] not in verification_ids:
            if item["source_family"] == "seed_or_curated" and item["score_tier"] == "A":
                item["relevance_verdict"] = "accept"
            else:
                item["relevance_verdict"] = "review"
            verified_candidates.append(item)
            continue

        fetch_url = ""
        if item["domain"] and "." in item["domain"]:
            fetch_url = item["domain"] if item["domain"].startswith("http") else f"https://{item['domain']}"
        elif item.get("source_url", "").startswith("http"):
            fetch_url = item["source_url"]

        title = ""
        description = ""
        fetch_error = ""
        if fetch_url:
            try:
                page = _fetch_page_summary(fetch_url)
                title = page["title"]
                description = page["description"]
            except Exception as exc:  # noqa: BLE001
                fetch_error = str(exc)

        relevance = _relevance_verdict(
            item.get("account_type", ""),
            item["company_name"],
            item["domain"],
            title,
            description,
        )
        item["relevance_verdict"] = relevance["verdict"]
        item["relevance_hits"] = {
            "global_positive_hits": relevance["global_positive_hits"],
            "type_positive_hits": relevance["type_positive_hits"],
            "negative_hits": relevance["negative_hits"],
        }
        item["homepage_title"] = title
        item["fetch_url"] = fetch_url
        relevance_log.append(
            {
                "account_id": item["account_id"],
                "company_name": item["company_name"],
                "domain": item["domain"],
                "account_type": item["account_type"],
                "fetch_url": fetch_url,
                "fetch_error": fetch_error,
                "title": title,
                "description": description,
                **relevance,
            }
        )
        if relevance["verdict"] != "exclude":
            verified_candidates.append(item)

    candidates = verified_candidates

    high_conf = [
        item
        for item in candidates
        if item["score_tier"] == "A"
        and item["source_confidence"] >= 0.95
        and item["state"] in PRIORITY_STATES[:6]
        and item["source_family"] == "seed_or_curated"
        and item["relevance_verdict"] == "accept"
    ]

    grouped = defaultdict(list)
    for item in high_conf:
        grouped[item["account_type"]].append(item)
    for key in grouped:
        grouped[key].sort(key=lambda item: (-item["rank_score"], -item["total_score"], -item["source_confidence"]))

    selected = []
    used = set()
    segment_targets = [("designer", 5), ("lighting", 5), ("electrician", 4), ("contractor", 2)]
    for account_type, count in segment_targets:
        for candidate in grouped.get(account_type, []):
            if len([item for item in selected if item["account_type"] == account_type]) >= count:
                break
            if candidate["account_id"] in used:
                continue
            candidate["selection_bucket"] = "high_confidence_priority"
            selected.append(candidate)
            used.add(candidate["account_id"])

    connector_samples = []
    for account_type in ["showroom", "dealer", "builder", "distributor"]:
        connector_rows = sorted(
            [
                item
                for item in candidates
                if item["account_type"] == account_type
                and item["state"] in {"RI", "MA", "CT", "NH", "ME", "VT"}
                and item["source_family"] in {"linkedin_company_pages", "google_business_profile", "trade_directories", "association_lists"}
                and item["relevance_verdict"] != "exclude"
            ],
            key=lambda item: (-item["rank_score"], -item["total_score"]),
        )
        if connector_rows:
            sample = connector_rows[0]
            sample["selection_bucket"] = "connector_learning_sample"
            connector_samples.append(sample)
            used.add(sample["account_id"])

    for candidate in sorted(high_conf, key=lambda item: (-item["rank_score"], -item["total_score"])):
        if len(selected) >= 16:
            break
        if candidate["account_id"] in used:
            continue
        candidate["selection_bucket"] = "high_confidence_priority"
        selected.append(candidate)
        used.add(candidate["account_id"])

    top20 = selected[:16] + connector_samples[:4]
    today10 = top20[:10]
    observation10 = top20[10:]

    output_root = project_root / "output" / "marketing-automation-suite" / cycle_id
    relevance_log_path = output_root / "priority-target-relevance-log.json"
    top20_json = output_root / "priority-targets-top20.json"
    top20_md = output_root / "priority-targets-top20.md"
    today_json = output_root / "priority-targets-today-10.json"
    today_md = output_root / "priority-targets-today-10.md"
    observation_json = output_root / "priority-targets-observation-10.json"
    observation_md = output_root / "priority-targets-observation-10.md"

    summary = {
        "generated_at": "2026-04-07T11:40:00Z",
        "source_cycle_id": cycle_id,
        "selection_goal": "first_batch_20",
        "selection_logic": {
            "high_confidence_priority": "A-tier, source_confidence>=0.95, New England first, curated/seed-backed, form-ready, homepage relevance accepted",
            "connector_learning_sample": "small sample from LinkedIn/GBP/directory-derived channel-partner accounts to improve future weighting",
        },
        "counts": {
            "total_candidates_considered": len(candidates),
            "total_selected": len(top20),
            "high_confidence_priority": sum(1 for item in top20 if item["selection_bucket"] == "high_confidence_priority"),
            "connector_learning_sample": sum(1 for item in top20 if item["selection_bucket"] == "connector_learning_sample"),
        },
        "items": top20,
    }

    _write_json(relevance_log_path, {"items": relevance_log})
    _write_json(top20_json, summary)
    _write_json(today_json, {"generated_at": summary["generated_at"], "source_cycle_id": cycle_id, "count": len(today10), "items": today10})
    _write_json(observation_json, {"generated_at": summary["generated_at"], "source_cycle_id": cycle_id, "count": len(observation10), "items": observation10})

    def _write_md(path: Path, title: str, rows: list[dict], goal: str) -> None:
        lines = [f"# {title}", "", f"Source cycle: `{cycle_id}`", "", f"Goal: {goal}", ""]
        for index, item in enumerate(rows, start=1):
            lines.append(f"## {index}. {item['company_name']}")
            lines.append(f"- Type: `{item['account_type']}`")
            lines.append(f"- Geo: `{item['geo']}`")
            lines.append(f"- Domain: `{item['domain'] or 'n/a'}`")
            lines.append(f"- Bucket: `{item['selection_bucket']}`")
            lines.append(f"- Score: `{item['total_score']}` ({item['score_tier']})")
            lines.append(f"- Source: `{item['source_family']}`")
            lines.append(f"- Channel: `{item['channel']}` | Path: `{item['path_type']}` | CTA: `{item['cta']}`")
            lines.append(f"- Angle: {item['primary_angle']}")
            lines.append(f"- Relevance: `{item['relevance_verdict']}` | Hits: {', '.join(item['relevance_hits']['type_positive_hits'] or item['relevance_hits']['global_positive_hits']) or 'n/a'}")
            lines.append(f"- Signals: {', '.join(item['top_signals'][:5])}")
            lines.append("")
        path.write_text("\n".join(lines), encoding="utf-8")

    _write_md(top20_md, "NEOSGO First Batch Top 20", top20, "balanced first-batch targets after relevance verification")
    _write_md(today_md, "NEOSGO Today 10", today10, "highest-confidence accounts for immediate form-first outreach")
    _write_md(observation_md, "NEOSGO Observation 10", observation10, "secondary batch for connector learning and next-wave execution")

    print(
        json.dumps(
            {
                "status": "ok",
                "relevance_log_path": str(relevance_log_path),
                "top20_json": str(top20_json),
                "today_json": str(today_json),
                "observation_json": str(observation_json),
                "selected_count": len(top20),
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
