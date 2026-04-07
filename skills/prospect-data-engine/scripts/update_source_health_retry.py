#!/usr/bin/env python3

from __future__ import annotations

import argparse
import json
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path


def _read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _load_items(path: Path) -> list[dict]:
    if not path.exists():
        return []
    payload = _read_json(path)
    if isinstance(payload, list):
        return payload
    return payload.get("items", [])


def _read_json_safe(path: Path) -> dict:
    if not path.exists():
        return {}
    return _read_json(path)


def main() -> int:
    parser = argparse.ArgumentParser(description="Build provider/source health and retry targets from discovery outputs.")
    parser.add_argument("--project-root", required=True)
    args = parser.parse_args()

    project_root = Path(args.project_root).expanduser().resolve()
    output_root = project_root / "output" / "prospect-data-engine"
    runtime_root = project_root / "runtime" / "prospect-data-engine"

    search_report = _read_json(output_root / "search-discovery-report.json") if (output_root / "search-discovery-report.json").exists() else {}
    discovery_report = _read_json(output_root / "discovery-report.json") if (output_root / "discovery-report.json").exists() else {}
    source_registry = _load_items(output_root / "source-registry.json")
    manual_targets = _load_items(project_root / "data" / "discovery-targets.json")
    generated_targets = _load_items(project_root / "data" / "discovery-targets.generated.json")

    provider_failures = Counter()
    existing_provider_health = _read_json_safe(runtime_root / "provider-health.json")
    provider_scores = existing_provider_health.get("provider_scores", {"duckduckgo": 0.55, "bing_rss": 0.9})
    for item in search_report.get("failures", []):
        provider = item.get("provider")
        if provider:
            provider_failures[provider] += 1
    for provider, count in provider_failures.items():
        provider_scores[provider] = max(0.1, round(provider_scores.get(provider, 0.75) - count * 0.08, 3))
    if search_report.get("generated_target_count", 0) > 0:
        if provider_failures.get("duckduckgo", 0) == 0:
            provider_scores["duckduckgo"] = min(0.75, round(provider_scores.get("duckduckgo", 0.55) + 0.02, 3))
        if provider_failures.get("bing_rss", 0) == 0:
            provider_scores["bing_rss"] = min(1.0, round(provider_scores.get("bing_rss", 0.9) + 0.01, 3))

    source_health = []
    for item in source_registry:
        quality = item.get("quality_rating")
        score = 0.9
        if quality == "review":
            score = 0.63
        elif quality == "low":
            score = 0.35
        elif quality == "empty":
            score = 0.5
        source_health.append(
            {
                "source_label": item.get("source_label"),
                "source_family": item.get("source_family"),
                "quality_rating": quality,
                "health_score": score,
                "duplicate_rate": item.get("duplicate_rate"),
                "average_source_confidence": item.get("average_source_confidence"),
            }
        )

    target_lookup = {item.get("target_url"): item for item in [*manual_targets, *generated_targets] if item.get("target_url")}
    retry_items = []
    target_failures = defaultdict(list)
    for failure in discovery_report.get("failures", []):
        url = failure.get("target_url")
        if url:
            target_failures[url].append(failure.get("error", ""))
    retry_until = (_utc_now() + timedelta(hours=6)).isoformat()
    for url, failures in target_failures.items():
        target = target_lookup.get(url, {})
        retry_items.append(
            {
                **target,
                "target_url": url,
                "enabled": True,
                "retry_attempts": len(failures),
                "retry_reason": failures[-1],
                "retry_not_before": retry_until,
            }
        )

    provider_health_path = runtime_root / "provider-health.json"
    source_health_path = runtime_root / "source-health.json"
    retry_targets_path = runtime_root / "retry-targets.generated.json"

    _write_json(
        provider_health_path,
        {
            "updated_at": _utc_now().isoformat(),
            "provider_scores": provider_scores,
            "provider_failures": dict(provider_failures),
        },
    )
    _write_json(
        source_health_path,
        {
            "updated_at": _utc_now().isoformat(),
            "items": source_health,
        },
    )
    _write_json(
        retry_targets_path,
        {
            "generated_at": _utc_now().isoformat(),
            "items": retry_items,
        },
    )

    print(
        json.dumps(
            {
                "status": "ok",
                "provider_health_path": str(provider_health_path),
                "source_health_path": str(source_health_path),
                "retry_target_count": len(retry_items),
                "retry_targets_path": str(retry_targets_path),
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
