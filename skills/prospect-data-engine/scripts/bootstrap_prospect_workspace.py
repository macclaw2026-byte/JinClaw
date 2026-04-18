#!/usr/bin/env python3

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


WORKSPACE_ROOT = Path("/Users/mac_claw/.openclaw/workspace")
if str(WORKSPACE_ROOT) not in sys.path:
    sys.path.insert(0, str(WORKSPACE_ROOT))

from tools.openmoss.ops.local_data_platform_bridge import sync_marketing_suite


def _read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _score_tier(total_score: float) -> str:
    if total_score >= 85:
        return "A"
    if total_score >= 70:
        return "B"
    if total_score >= 55:
        return "C"
    return "D"


def _slugify(value: str) -> str:
    return "".join(ch.lower() if ch.isalnum() else "-" for ch in value).strip("-")


def _normalize_reachability(raw: str) -> tuple[str, float]:
    mapping = {
        "email_verified": ("email_ready", 18.0),
        "email_unverified": ("email_review", 12.0),
        "form_available": ("form_ready", 15.0),
        "linkedin_only": ("social_ready", 10.0),
    }
    return mapping.get(raw or "", ("unknown", 6.0))


def _fit_score(account_type: str, persona_type: str, config: dict) -> float:
    icp = config.get("icp", {})
    fit = 0.0
    if account_type in icp.get("account_types", []):
        fit += 24.0
    if persona_type in icp.get("personas", []):
        fit += 10.0
    if persona_type and persona_type in icp.get("exclusions", []):
        fit -= 20.0
    return max(0.0, min(40.0, fit + 6.0))


def _fit_precheck_adjustment(status: str) -> float:
    if status == "approved":
        return 4.0
    if status == "review":
        return -10.0
    if status == "reject":
        return -25.0
    return 0.0


def _intent_score(signals: list[str]) -> float:
    count = len(signals)
    base = min(18.0, count * 7.0)
    freshness_bonus = 6.0 if count >= 2 else 3.0 if count == 1 else 0.0
    specificity_bonus = 4.0 if any("fit" in signal or "project" in signal for signal in signals) else 2.0
    return min(30.0, base + freshness_bonus + specificity_bonus)


def _data_quality_score(seed: dict) -> float:
    score = 0.0
    if seed.get("source_url"):
        score += 3.0
    if seed.get("company_name"):
        score += 2.0
    if seed.get("website_root_domain"):
        score += 2.0
    if seed.get("contact", {}).get("full_name"):
        score += 1.5
    if seed.get("contact", {}).get("contact_id"):
        score += 1.5
    return min(10.0, score)


def main() -> int:
    parser = argparse.ArgumentParser(description="Bootstrap Prospect Data Engine runtime files for a project.")
    parser.add_argument("--project-root", required=True)
    parser.add_argument("--config", required=True)
    parser.add_argument("--seeds")
    args = parser.parse_args()

    root = Path(args.project_root).expanduser().resolve()
    config = _read_json(Path(args.config).expanduser().resolve())
    output_root = root / "output" / "prospect-data-engine"
    runtime_root = root / "runtime" / "prospect-data-engine"
    seed_path = Path(args.seeds).expanduser().resolve() if args.seeds else root / "data" / "prospect-seeds.json"
    seeds = _read_json(seed_path).get("items", []) if seed_path.exists() else []

    prospect_records = []
    accounts = []
    contacts = []
    lead_scores = []
    source_attribution = []

    for index, seed in enumerate(seeds, start=1):
        contact = seed.get("contact", {})
        fit_precheck_status = str(seed.get("fit_precheck_status", "") or "")
        fit_score = _fit_score(seed.get("account_type", ""), seed.get("persona_type", ""), config) + _fit_precheck_adjustment(fit_precheck_status)
        fit_score = max(0.0, min(40.0, fit_score))
        intent_score = _intent_score(seed.get("signals", []))
        reachability_status, reachability_score = _normalize_reachability(contact.get("reachability_status", ""))
        data_quality_score = _data_quality_score(seed)
        total_score = round(fit_score + intent_score + reachability_score + data_quality_score, 2)
        account_anchor = seed.get("website_root_domain") or seed.get("company_name") or seed.get("source_url") or f"seed-{index}"
        record = {
            "account_id": f"account-{_slugify(account_anchor) or f'seed-{index}'}",
            "contact_id": contact.get("contact_id"),
            "company_name": seed.get("company_name", ""),
            "website_root_domain": seed.get("website_root_domain", ""),
            "account_type": seed.get("account_type", ""),
            "persona_type": seed.get("persona_type"),
            "geo": seed.get("geo"),
            "fit_score": round(fit_score, 2),
            "intent_score": round(intent_score, 2),
            "reachability_score": round(reachability_score, 2),
            "data_quality_score": round(data_quality_score, 2),
            "total_score": total_score,
            "reachability_status": reachability_status,
            "top_signals": seed.get("signals", []),
            "score_tier": _score_tier(total_score),
            "source_confidence": seed.get("source_confidence", 0.5),
            "source_url": seed.get("source_url", ""),
            "source_label": seed.get("source_label", ""),
            "source_family": seed.get("source_family", ""),
            "fit_precheck_status": fit_precheck_status,
            "fit_precheck_reasons": seed.get("fit_precheck_reasons", []),
            "category": seed.get("category", ""),
            "query_id": seed.get("query_id", ""),
            "discovery_query": seed.get("discovery_query", ""),
            "query_family": seed.get("query_family", ""),
            "generated_from_provider": seed.get("generated_from_provider", ""),
        }
        prospect_records.append(record)
        accounts.append(
            {
                "account_id": record["account_id"],
                "company_name": record["company_name"],
                "website_root_domain": record["website_root_domain"],
                "account_type": record["account_type"],
                "geo": record["geo"],
            }
        )
        contacts.append(
            {
                "contact_id": contact.get("contact_id"),
                "account_id": record["account_id"],
                "full_name": contact.get("full_name", ""),
                "email": contact.get("email", ""),
                "reachability_status": reachability_status,
            }
        )
        lead_scores.append(
            {
                "account_id": record["account_id"],
                "contact_id": record["contact_id"],
                "fit_score": record["fit_score"],
                "intent_score": record["intent_score"],
                "reachability_score": record["reachability_score"],
                "data_quality_score": record["data_quality_score"],
                "total_score": total_score,
                "score_tier": record["score_tier"],
            }
        )
        source_attribution.append(
            {
                "source_id": f"source-{index}",
                "account_id": record["account_id"],
                "source_url": record["source_url"],
                "source_family": record.get("source_family") or "seed_fixture",
                "source_confidence": record["source_confidence"],
                "source_label": record.get("source_label", ""),
                "query_id": record.get("query_id", ""),
                "discovery_query": record.get("discovery_query", ""),
                "query_family": record.get("query_family", ""),
                "generated_from_provider": record.get("generated_from_provider", ""),
            }
        )

    _write_json(
        runtime_root / "state.json",
        {
            "status": "ready",
            "source_registry_version": 1,
            "score_version": 1,
            "last_discovery_run_at": "seeded" if prospect_records else "",
            "last_quality_report_at": "seeded" if prospect_records else "",
            "prospect_count": len(prospect_records),
        },
    )
    _write_json(
        output_root / "database-manifest.json",
        {
            "tables": [
                "accounts",
                "contacts",
                "opportunity_signals",
                "reachability",
                "lead_scores",
                "source_registry",
                "lifecycle_events",
            ],
            "status": "initialized" if not prospect_records else "seeded",
        },
    )
    _write_json(output_root / "prospect-records.json", {"items": prospect_records})
    _write_json(output_root / "accounts.json", {"items": accounts})
    _write_json(output_root / "contacts.json", {"items": contacts})
    _write_json(output_root / "lead-scores.json", {"items": lead_scores})
    _write_json(output_root / "source-attribution.json", {"items": source_attribution})
    _write_json(
        output_root / "quality-report.json",
        {
            "prospect_count": len(prospect_records),
            "high_value_count": len([item for item in prospect_records if item["score_tier"] in {"A", "B"}]),
            "email_ready_count": len([item for item in prospect_records if item["reachability_status"] == "email_ready"]),
            "form_ready_count": len([item for item in prospect_records if item["reachability_status"] == "form_ready"]),
            "fit_review_count": len([item for item in prospect_records if item.get("fit_precheck_status") == "review"]),
            "fit_reject_count": len([item for item in prospect_records if item.get("fit_precheck_status") == "reject"]),
            "average_total_score": round(sum(item["total_score"] for item in prospect_records) / len(prospect_records), 2)
            if prospect_records
            else 0.0,
        },
    )
    print(
        json.dumps(
            {
                "project_root": str(root),
                "status": "seeded" if prospect_records else "initialized",
                "prospect_count": len(prospect_records),
                "prospect_records_path": str(output_root / "prospect-records.json"),
                "data_platform_sync": sync_marketing_suite(project_root=root),
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
