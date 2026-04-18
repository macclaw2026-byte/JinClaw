#!/usr/bin/env python3

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path

NON_COMPANY_DOMAINS = {
    "gmail.com",
    "aol.com",
    "hotmail.com",
    "outlook.com",
    "yahoo.com",
    "comcast.net",
    "duckduckgo.com",
}

REVIEW_TOLERANT_SOURCE_FAMILIES = {
    "google_business_profile",
    "linkedin_company_pages",
    "trade_directories",
}
NEOSGO_FIT_APPROVED_CATEGORY_KEYWORDS = {
    "interior designer",
    "interior decorator",
    "architectural interiors",
}
NEOSGO_FIT_APPROVED_CONTRACTOR_CATEGORY_KEYWORDS = {
    "general contractor",
    "general contracting",
    "construction company",
    "design-build",
    "design build",
    "remodeler",
    "custom home builder",
    "home builder",
}
NEOSGO_FIT_REVIEW_CATEGORY_KEYWORDS = {
    "home staging",
    "lighting consultant",
    "lighting store",
    "architect",
}
NEOSGO_FIT_REVIEW_CONTRACTOR_CATEGORY_KEYWORDS = {
    "kitchen remodeler",
    "bathroom remodeler",
    "builder",
    "contractor",
    "construction management",
}
NEOSGO_FIT_REJECT_CATEGORY_KEYWORDS = {
    "business center",
    "paint store",
    "painter",
    "landscape designer",
    "landscaper",
    "garden center",
    "florist",
    "publisher",
    "magazine",
    "media company",
}
NEOSGO_FIT_REJECT_CONTRACTOR_CATEGORY_KEYWORDS = {
    "roofing contractor",
    "painting contractor",
    "paving contractor",
    "hvac contractor",
    "plumbing contractor",
    "electrical contractor",
    "landscape contractor",
}
NEOSGO_FIT_REJECT_NAME_KEYWORDS = {
    "paint",
    "painting",
    "tropical",
    "landscape",
    "landscaping",
    "garden",
    "magazine",
    "media",
    "publisher",
    "florist",
}


def _read_json(path: Path) -> dict | list:
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _slugify(value: str) -> str:
    return "".join(ch.lower() if ch.isalnum() else "-" for ch in value).strip("-")


def _normalize_url(value: str) -> str:
    text = (value or "").strip().lower()
    text = text.removeprefix("https://").removeprefix("http://")
    text = text.removeprefix("www.")
    return text.rstrip("/")


def _normalize_host(value: str) -> str:
    text = _normalize_url(value)
    return text.split("/")[0]


def _utc_marker() -> str:
    from datetime import datetime, timezone

    return datetime.now(timezone.utc).isoformat()


def _normalize_signals(value: object) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    text = str(value).strip()
    if not text:
        return []
    delimiter = "|" if "|" in text else ","
    return [item.strip() for item in text.split(delimiter) if item.strip()]


def _first_nonempty(raw: dict, keys: list[str]) -> str:
    for key in keys:
        value = raw.get(key)
        if value is not None and str(value).strip():
            return str(value).strip()
    return ""


def _infer_domain(raw: dict) -> str:
    domain = _first_nonempty(raw, ["website_root_domain", "domain"])
    if domain:
        return domain.lower()
    website = _first_nonempty(raw, ["website", "website_url", "site"])
    if not website:
        return ""
    website = website.strip().lower()
    website = website.removeprefix("https://").removeprefix("http://")
    website = website.removeprefix("www.")
    return website.split("/")[0]


def _infer_account_type(raw: dict) -> str:
    direct = _first_nonempty(raw, ["account_type", "segment_primary"])
    if direct:
        return direct.lower()
    industry = _first_nonempty(raw, ["industry", "industry_name"]).lower()
    title = _first_nonempty(raw, ["title"]).lower()
    if "electric" in industry or "electric" in title:
        return "electrician"
    if "design" in industry or "architect" in industry:
        return "designer"
    if "contractor" in industry or "builder" in industry or "construction" in industry:
        return "contractor"
    if "wholesale" in industry or "manufacturer" in industry or "lighting" in industry:
        return "distributor"
    return ""


def _infer_persona_type(raw: dict) -> str | None:
    direct = _first_nonempty(raw, ["persona_type"])
    if direct:
        return direct.lower()
    title = _first_nonempty(raw, ["title"]).lower()
    if any(token in title for token in ["owner", "founder", "president", "principal"]):
        return "founder"
    if any(token in title for token in ["buyer", "purchasing", "procurement", "sourcing"]):
        return "buyer"
    if any(token in title for token in ["operations", "project", "manager", "vice president"]):
        return "operations_manager"
    return None


def _infer_geo(raw: dict) -> str | None:
    direct = _first_nonempty(raw, ["geo"])
    if direct:
        return direct
    city = _first_nonempty(raw, ["city"])
    state = _first_nonempty(raw, ["state"])
    if city and state:
        return f"{city}, {state}"
    if state:
        return state
    return None


def _infer_signals(raw: dict) -> list[str]:
    direct = _normalize_signals(raw.get("signals"))
    if direct:
        return direct
    signals: list[str] = []
    fit_tier = _first_nonempty(raw, ["fit_tier"])
    if fit_tier:
        signals.append(f"fit_tier_{fit_tier.lower()}")
    priority = _first_nonempty(raw, ["outreach_priority_score"])
    if priority:
        signals.append("prior_scored_lead")
    industry = _first_nonempty(raw, ["industry"]).lower()
    if "lighting" in industry:
        signals.append("lighting_industry_match")
    if "wholesale" in industry or "manufacturer" in industry:
        signals.append("channel_supply_signal")
    if "design" in industry:
        signals.append("design_led_projects")
    if "contractor" in industry or "construction" in industry:
        signals.append("active_project_pipeline")
    if "electric" in industry:
        signals.append("installation_trade_fit")
    website = _first_nonempty(raw, ["website", "website_url", "site"])
    if website:
        signals.append("website_present")
    email = _first_nonempty(raw, ["email"])
    if email:
        signals.append("contactable_email_present")
    return signals


def _infer_reachability(raw: dict) -> str:
    direct = _first_nonempty(raw, ["reachability_status"])
    if direct:
        return direct
    email = _first_nonempty(raw, ["email"])
    website = _first_nonempty(raw, ["website", "website_url", "site"])
    contact_form_detected = bool(raw.get("contact_form_detected", False))
    if email and contact_form_detected:
        return "form_and_email_available"
    if email:
        return "email_verified"
    if contact_form_detected:
        return "form_available"
    if website:
        return "form_available"
    return "unknown"


def _normalize_seed(raw: dict, index: int, source_label: str = "") -> dict:
    company_name = _first_nonempty(raw, ["company_name", "company", "Company Name"]).strip()
    domain = _infer_domain(raw)
    full_name = _first_nonempty(raw, ["full_name", "contact_name", "contact_full_name", "Contact"]).strip()
    contact_id = str(raw.get("contact_id", "")).strip() or f"contact-{_slugify(company_name or domain or str(index))}"
    return {
        "source_url": _first_nonempty(raw, ["source_url", "website", "website_url", "site"]),
        "company_name": company_name,
        "website_root_domain": domain,
        "account_type": _infer_account_type(raw),
        "persona_type": _infer_persona_type(raw),
        "geo": _infer_geo(raw),
        "signals": _infer_signals(raw),
        "contact": {
            "contact_id": contact_id,
            "full_name": full_name,
            "email": _first_nonempty(raw, ["email", "Email"]),
            "reachability_status": _infer_reachability(raw),
        },
        "source_confidence": float(raw.get("source_confidence", raw.get("fit_score", 70)) or 0.7) / (100.0 if str(raw.get("fit_score", "")).strip() else 1.0),
        "source_label": source_label,
        "source_family": _first_nonempty(raw, ["source_family"]),
        "category": _first_nonempty(raw, ["category", "primary_type"]),
        "formatted_address": _first_nonempty(raw, ["formatted_address"]),
        "phone": _first_nonempty(raw, ["phone"]),
        "website_fit_status": _first_nonempty(raw, ["website_fit_status"]),
        "website_fit_reasons": raw.get("website_fit_reasons", []),
        "contact_form_detected": bool(raw.get("contact_form_detected", False)),
        "contact_form_url": _first_nonempty(raw, ["contact_form_url"]),
        "contact_form_signals": raw.get("contact_form_signals", []),
        "query_id": _first_nonempty(raw, ["query_id"]),
        "discovery_query": _first_nonempty(raw, ["discovery_query", "generated_from_query"]),
        "query_family": _first_nonempty(raw, ["query_family"]),
        "generated_from_provider": _first_nonempty(raw, ["generated_from_provider"]),
    }


def _assess_neosgo_fit(seed: dict) -> tuple[str, list[str]]:
    source_family = (seed.get("source_family") or "").strip()
    company_name = (seed.get("company_name") or "").strip().lower()
    category = (seed.get("category") or "").strip().lower()
    website = (seed.get("website_root_domain") or "").strip().lower()
    website_fit_status = (seed.get("website_fit_status") or "").strip().lower()
    website_fit_reasons = list(seed.get("website_fit_reasons", []) or [])

    reasons: list[str] = []

    if source_family == "google_maps_places":
        account_type = (seed.get("account_type") or "").strip().lower()
        if website_fit_status == "approved":
            return "approved", ["approved_website_fit", *website_fit_reasons[:4]]
        if website_fit_status == "reject":
            return "reject", ["rejected_website_fit", *website_fit_reasons[:4]]
        if website_fit_status == "review":
            return "review", ["review_website_fit", *website_fit_reasons[:4]]
        reject_keywords = (
            NEOSGO_FIT_REJECT_CONTRACTOR_CATEGORY_KEYWORDS
            if account_type == "contractor"
            else NEOSGO_FIT_REJECT_CATEGORY_KEYWORDS
        )
        approved_keywords = (
            NEOSGO_FIT_APPROVED_CONTRACTOR_CATEGORY_KEYWORDS
            if account_type == "contractor"
            else NEOSGO_FIT_APPROVED_CATEGORY_KEYWORDS
        )
        review_keywords = (
            NEOSGO_FIT_REVIEW_CONTRACTOR_CATEGORY_KEYWORDS
            if account_type == "contractor"
            else NEOSGO_FIT_REVIEW_CATEGORY_KEYWORDS
        )
        if any(keyword in category for keyword in reject_keywords):
            return "reject", [f"reject_category:{category or 'unknown'}"]
        if any(keyword in company_name for keyword in NEOSGO_FIT_REJECT_NAME_KEYWORDS):
            return "reject", [f"reject_name_keyword:{company_name}"]
        if any(keyword in category for keyword in approved_keywords):
            reasons.append("approved_google_maps_category")
            return "approved", reasons
        if account_type == "contractor" and any(
            keyword in company_name
            for keyword in ("contractor", "contracting", "construction", "builders", "builder", "remodel")
        ):
            reasons.append("approved_contractor_company_name_match")
            return "approved", reasons
        if "interior" in company_name or "design" in company_name or "interiors" in company_name:
            reasons.append("approved_company_name_match")
            return "approved", reasons
        if any(keyword in category for keyword in review_keywords):
            return "review", [f"review_category:{category or 'unknown'}"]
        return "review", ["google_maps_uncertain_fit"]

    if source_family in {"seed_registry", "curated_public_source"}:
        return "approved", ["trusted_seed_or_curated_source"]

    if "lighting" in company_name or "lighting" in website:
        return "approved", ["lighting_company_match"]

    return "approved", ["default_allow"]


def _load_csv(path: Path) -> list[dict]:
    with path.open("r", encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def _load_raw_records(path: Path) -> list[dict]:
    if path.suffix.lower() == ".csv":
        return _load_csv(path)
    if path.suffix.lower() == ".jsonl":
        records = []
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line:
                records.append(json.loads(line))
        return records
    payload = _read_json(path)
    if isinstance(payload, list):
        return payload
    return payload.get("items", [])


def _dedupe_key(seed: dict) -> str:
    domain = seed.get("website_root_domain", "")
    company = _slugify(seed.get("company_name", ""))
    source = seed.get("source_url", "")
    if domain and domain not in NON_COMPANY_DOMAINS:
        return f"domain:{domain}"
    if company:
        return f"company:{company}"
    return f"source:{source}"


def _infer_source_family(path: Path) -> str:
    name = path.name.lower()
    if "curated-top-" in name:
        return "curated_public_source"
    if "linkedin" in name:
        return "linkedin_company_pages"
    if "google" in name or "business-profile" in name or "gbp" in name:
        return "google_business_profile"
    if "directory" in name or "dealer" in name or "partner" in name:
        return "trade_directories"
    if "association" in name:
        return "association_lists"
    if "exhibitor" in name or "expo" in name or "show" in name:
        return "exhibitor_lists"
    if "website" in name or "public-leads" in name or "official" in name:
        return "official_websites"
    return "unclassified_public_source"


def _source_tier(source_family: str) -> int:
    if source_family in {"official_websites", "google_business_profile", "linkedin_company_pages", "curated_public_source"}:
        return 1
    if source_family in {"trade_directories"}:
        return 2
    return 3


def _build_source_registry_entry(path: Path, raw_records: list[dict], deduped_count: int) -> dict:
    source_family = _infer_source_family(path)
    raw_count = len(raw_records)
    duplicate_count = max(0, raw_count - deduped_count)
    dedupe_rate = round(duplicate_count / raw_count, 4) if raw_count else 0.0
    avg_confidence = round(
        sum(float(record.get("source_confidence", 0.7) or 0.7) for record in raw_records) / raw_count,
        4,
    ) if raw_count else 0.0
    if raw_count == 0:
        quality_rating = "empty"
    else:
        quality_rating = "high"
        if source_family == "curated_public_source" and dedupe_rate <= 0.2 and avg_confidence >= 0.9:
            quality_rating = "high"
        if source_family in REVIEW_TOLERANT_SOURCE_FAMILIES and dedupe_rate <= 0.1 and avg_confidence >= 0.66:
            quality_rating = "high"
        elif avg_confidence < 0.78 or dedupe_rate > 0.35:
            quality_rating = "review"
        if avg_confidence < 0.65 or dedupe_rate > 0.55:
            quality_rating = "low"
        if source_family == "unclassified_public_source" and deduped_count >= 5 and avg_confidence >= 0.74 and quality_rating == "low":
            quality_rating = "review"
    return {
        "source_id": f"source-{_slugify(path.stem)}",
        "source_label": path.name,
        "source_path": str(path),
        "source_family": source_family,
        "source_tier": _source_tier(source_family),
        "raw_record_count": raw_count,
        "deduped_record_count": deduped_count,
        "duplicate_count": duplicate_count,
        "duplicate_rate": dedupe_rate,
        "average_source_confidence": avg_confidence,
        "quality_rating": quality_rating,
        "captured_at": _utc_marker(),
    }


def _quality_gate(source_registry: list[dict], deduped: list[dict], strategy_ready_count: int) -> dict:
    active_sources = [item for item in source_registry if item.get("quality_rating") != "empty"]
    strategy_eligible_sources = [item for item in active_sources if item.get("quality_rating") != "low"]
    duplicate_rates = [item["duplicate_rate"] for item in active_sources]
    avg_duplicate_rate = round(sum(duplicate_rates) / len(duplicate_rates), 4) if duplicate_rates else 0.0
    low_quality_sources = [item["source_label"] for item in active_sources if item["quality_rating"] == "low"]
    review_sources = [item["source_label"] for item in active_sources if item["quality_rating"] == "review"]
    empty_sources = [item["source_label"] for item in source_registry if item["quality_rating"] == "empty"]
    missing_domain_count = len([item for item in deduped if not item.get("website_root_domain")])
    missing_source_url_count = len([item for item in deduped if not item.get("source_url")])
    rejected_fit_count = len([item for item in deduped if item.get("fit_precheck_status") == "reject"])
    allowed = True
    blockers: list[str] = []
    warnings: list[str] = []
    if avg_duplicate_rate > 0.45:
        allowed = False
        blockers.append("duplicate_rate_too_high")
    if strategy_ready_count < 25:
        allowed = False
        blockers.append("not_enough_strategy_ready_records")
    if missing_domain_count > max(1, len(deduped) // 3):
        allowed = False
        blockers.append("too_many_missing_domains")
    if review_sources:
        warnings.append("review_quality_sources_present")
    if low_quality_sources:
        warnings.append("low_quality_sources_quarantined")
    if missing_source_url_count:
        warnings.append("records_missing_source_url")
    return {
        "status": "pass" if allowed else "review_required",
        "allowed_for_strategy": allowed,
        "average_duplicate_rate": avg_duplicate_rate,
        "strategy_eligible_source_count": len(strategy_eligible_sources),
        "strategy_ready_count": strategy_ready_count,
        "missing_domain_count": missing_domain_count,
        "missing_source_url_count": missing_source_url_count,
        "rejected_fit_count": rejected_fit_count,
        "review_sources": review_sources,
        "low_quality_sources": low_quality_sources,
        "empty_sources": empty_sources,
        "blockers": blockers,
        "warnings": warnings,
    }


def _company_variant_equivalent(left: str, right: str) -> bool:
    left_slug = _slugify(left)
    right_slug = _slugify(right)
    if not left_slug or not right_slug:
        return False
    if left_slug == right_slug:
        return True
    left_tokens = {token for token in left_slug.split("-") if token}
    right_tokens = {token for token in right_slug.split("-") if token}
    if not left_tokens or not right_tokens:
        return False
    overlap = len(left_tokens & right_tokens)
    return overlap >= min(len(left_tokens), len(right_tokens))


def _is_trivial_duplicate_conflict(conflict: dict) -> bool:
    kept_company = conflict.get("kept_company_name", "")
    dropped_company = conflict.get("dropped_company_name", "")
    kept_source = conflict.get("kept_source_url", "")
    dropped_source = conflict.get("dropped_source_url", "")
    if _normalize_url(kept_source) == _normalize_url(dropped_source):
        return True
    if _normalize_host(kept_source) and _normalize_host(kept_source) == _normalize_host(dropped_source):
        return True
    if _company_variant_equivalent(kept_company, dropped_company):
        return True
    return False


def _missing_fields_require_review(seed: dict, missing_fields: list[str]) -> bool:
    if not missing_fields:
        return False
    source_family = (seed.get("source_family") or "").strip()
    source_url = (seed.get("source_url") or "").strip()
    company_name = (seed.get("company_name") or "").strip()
    if (
        source_family in REVIEW_TOLERANT_SOURCE_FAMILIES
        and missing_fields == ["website_root_domain"]
        and source_url
        and company_name
    ):
        return False
    if missing_fields == ["website_root_domain"] and source_url and company_name and "google.com/search" in source_url:
        return False
    return True


def _build_review_queue(source_registry: list[dict], deduped: list[dict], duplicate_conflicts: list[dict]) -> list[dict]:
    review_items: list[dict] = []
    low_quality_source_labels = {item.get("source_label") for item in source_registry if item.get("quality_rating") == "low"}
    for source in source_registry:
        if source.get("quality_rating") in {"review", "low"}:
            review_items.append(
                {
                    "review_id": f"review-source-{source['source_id']}",
                    "review_type": "source_quality_review",
                    "severity": "high" if source.get("quality_rating") == "low" else "medium",
                    "status": "open",
                    "source_id": source.get("source_id"),
                    "source_label": source.get("source_label"),
                    "reason": f"quality_rating={source.get('quality_rating')}",
                    "evidence": {
                        "duplicate_rate": source.get("duplicate_rate"),
                        "average_source_confidence": source.get("average_source_confidence"),
                    },
                }
            )
    seen_conflict_keys = set()
    for conflict in duplicate_conflicts:
        dedupe_key = conflict.get("dedupe_key")
        kept_company = (conflict.get("kept_company_name") or "").strip().lower()
        dropped_company = (conflict.get("dropped_company_name") or "").strip().lower()
        kept_source = (conflict.get("kept_source_url") or "").strip().lower()
        dropped_source = (conflict.get("dropped_source_url") or "").strip().lower()
        if kept_company == dropped_company and kept_source == dropped_source:
            continue
        if _is_trivial_duplicate_conflict(conflict):
            continue
        if dedupe_key in seen_conflict_keys:
            continue
        seen_conflict_keys.add(dedupe_key)
        index = len(seen_conflict_keys)
        review_items.append(
            {
                "review_id": f"review-duplicate-{index}",
                "review_type": "duplicate_conflict_review",
                "severity": "medium",
                "status": "open",
                "dedupe_key": dedupe_key,
                "reason": conflict.get("conflict_type"),
                "evidence": conflict,
            }
        )
    for index, seed in enumerate(deduped, start=1):
        if seed.get("source_label") in low_quality_source_labels:
            continue
        missing_fields = []
        if not seed.get("company_name"):
            missing_fields.append("company_name")
        if not seed.get("website_root_domain"):
            missing_fields.append("website_root_domain")
        if not seed.get("source_url"):
            missing_fields.append("source_url")
        if _missing_fields_require_review(seed, missing_fields):
            review_items.append(
                {
                    "review_id": f"review-missing-fields-{index}",
                    "review_type": "missing_key_fields_review",
                    "severity": "high" if "website_root_domain" in missing_fields else "medium",
                    "status": "open",
                    "account_hint": seed.get("company_name") or seed.get("website_root_domain") or f"seed-{index}",
                    "reason": "missing_key_fields",
                    "evidence": {
                        "missing_fields": missing_fields,
                        "source_url": seed.get("source_url"),
                    },
                }
            )
        if seed.get("fit_precheck_status") == "review":
            review_items.append(
                {
                    "review_id": f"review-fit-{index}",
                    "review_type": "neosgo_fit_review",
                    "severity": "medium",
                    "status": "open",
                    "account_hint": seed.get("company_name") or seed.get("website_root_domain") or f"seed-{index}",
                    "reason": "uncertain_neosgo_fit",
                    "evidence": {
                        "source_family": seed.get("source_family"),
                        "category": seed.get("category"),
                        "fit_precheck_reasons": seed.get("fit_precheck_reasons", []),
                        "source_url": seed.get("source_url"),
                    },
                }
            )
    return review_items


def main() -> int:
    parser = argparse.ArgumentParser(description="Import public prospect data files and normalize them into seed records.")
    parser.add_argument("--project-root", required=True)
    args = parser.parse_args()

    root = Path(args.project_root).expanduser().resolve()
    data_root = root / "data"
    raw_root = data_root / "raw-imports"
    base_seed_path = data_root / "prospect-seeds.json"
    output_root = root / "output" / "prospect-data-engine"
    runtime_root = root / "runtime" / "prospect-data-engine"

    merged: list[dict] = []
    sources_seen: list[str] = []
    source_registry: list[dict] = []
    duplicate_conflicts: list[dict] = []

    if base_seed_path.exists():
        base_records = _read_json(base_seed_path).get("items", [])
        for idx, seed in enumerate(base_records, start=1):
            merged.append(_normalize_seed(seed, idx, source_label=base_seed_path.name))
        sources_seen.append(str(base_seed_path))
        source_registry.append(
            {
                "source_id": "source-prospect-seeds",
                "source_label": base_seed_path.name,
                "source_path": str(base_seed_path),
                "source_family": "seed_registry",
                "source_tier": 0,
                "raw_record_count": len(base_records),
                "deduped_record_count": len(base_records),
                "duplicate_count": 0,
                "duplicate_rate": 0.0,
                "average_source_confidence": round(
                    sum(float(item.get("source_confidence", 0.7) or 0.7) for item in base_records) / len(base_records),
                    4,
                ) if base_records else 0.0,
                "quality_rating": "high",
                "captured_at": _utc_marker(),
            }
        )

    import_files = sorted(
        [
            path
            for path in raw_root.glob("*")
            if path.is_file() and path.suffix.lower() in {".csv", ".json", ".jsonl"}
        ]
    )

    next_index = len(merged) + 1
    for path in import_files:
        raw_records = _load_raw_records(path)
        normalized_batch = []
        for raw in raw_records:
            normalized = _normalize_seed(raw, next_index, source_label=path.name)
            merged.append(normalized)
            normalized_batch.append(normalized)
            next_index += 1
        sources_seen.append(str(path))
        batch_unique = len({_dedupe_key(item) for item in normalized_batch})
        source_registry.append(_build_source_registry_entry(path, normalized_batch, batch_unique))

    deduped: list[dict] = []
    seen_by_key: dict[str, dict] = {}
    duplicate_count = 0
    for seed in merged:
        key = _dedupe_key(seed)
        if key in seen_by_key:
            duplicate_count += 1
            first = seen_by_key[key]
            duplicate_conflicts.append(
                {
                    "dedupe_key": key,
                    "kept_company_name": first.get("company_name", ""),
                    "dropped_company_name": seed.get("company_name", ""),
                    "kept_source_url": first.get("source_url", ""),
                    "dropped_source_url": seed.get("source_url", ""),
                    "conflict_type": "duplicate_domain_or_company",
                }
            )
            continue
        seen_by_key[key] = seed
        fit_precheck_status, fit_precheck_reasons = _assess_neosgo_fit(seed)
        seed["fit_precheck_status"] = fit_precheck_status
        seed["fit_precheck_reasons"] = fit_precheck_reasons
        deduped.append(seed)

    merged_path = output_root / "merged-prospect-seeds.json"
    strategy_ready_seed_path = output_root / "strategy-ready-seeds.json"
    source_registry_path = output_root / "source-registry.json"
    duplicate_conflicts_path = output_root / "duplicate-conflicts.json"
    low_quality_source_labels = {item["source_label"] for item in source_registry if item.get("quality_rating") == "low"}
    strategy_ready_seeds = [
        item
        for item in deduped
        if item.get("source_label") not in low_quality_source_labels and item.get("fit_precheck_status") != "reject"
    ]
    quality_gate = _quality_gate(source_registry, deduped, len(strategy_ready_seeds))
    review_queue = _build_review_queue(source_registry, deduped, duplicate_conflicts)
    review_queue_path = output_root / "review-queue.json"
    _write_json(merged_path, {"items": deduped})
    _write_json(strategy_ready_seed_path, {"items": strategy_ready_seeds})
    _write_json(source_registry_path, {"items": source_registry})
    _write_json(duplicate_conflicts_path, {"items": duplicate_conflicts})
    _write_json(review_queue_path, {"items": review_queue})
    _write_json(
        output_root / "import-report.json",
        {
            "source_count": len(sources_seen),
            "sources": sources_seen,
            "raw_record_count": len(merged),
            "deduped_record_count": len(deduped),
            "duplicate_count": duplicate_count,
            "quality_gate_status": quality_gate["status"],
            "review_queue_count": len(review_queue),
        },
    )
    _write_json(output_root / "import-quality-gate.json", quality_gate)
    _write_json(
        runtime_root / "import-state.json",
        {
            "status": "ok",
            "last_import_source_count": len(sources_seen),
            "last_raw_record_count": len(merged),
            "last_deduped_record_count": len(deduped),
            "last_duplicate_count": duplicate_count,
            "merged_seed_path": str(merged_path),
            "strategy_ready_seed_path": str(strategy_ready_seed_path),
            "source_registry_path": str(source_registry_path),
            "duplicate_conflicts_path": str(duplicate_conflicts_path),
            "review_queue_path": str(review_queue_path),
            "quality_gate_status": quality_gate["status"],
            "quality_gate_allowed_for_strategy": quality_gate["allowed_for_strategy"],
            "review_queue_count": len(review_queue),
        },
    )

    print(
        json.dumps(
            {
                "status": "ok",
                "source_count": len(sources_seen),
                "raw_record_count": len(merged),
                "deduped_record_count": len(deduped),
                "merged_seed_path": str(merged_path),
                "strategy_ready_seed_path": str(strategy_ready_seed_path),
                "quality_gate_status": quality_gate["status"],
                "allowed_for_strategy": quality_gate["allowed_for_strategy"],
                "source_registry_path": str(source_registry_path),
                "duplicate_conflicts_path": str(duplicate_conflicts_path),
                "review_queue_path": str(review_queue_path),
                "review_queue_count": len(review_queue),
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
