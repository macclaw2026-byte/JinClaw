#!/usr/bin/env python3

from __future__ import annotations

import argparse
import json
from pathlib import Path


SCRIPT_DIR = Path(__file__).resolve().parent
SUITE_ROOT = SCRIPT_DIR.parent


def _write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Initialize a reusable marketing automation project workspace.")
    parser.add_argument("--project-root", required=True)
    parser.add_argument("--project-id", required=True)
    parser.add_argument("--project-name", default="")
    args = parser.parse_args()

    project_root = Path(args.project_root).expanduser().resolve()
    project_name = args.project_name.strip() or args.project_id

    config_template = json.loads((SUITE_ROOT / "project-config-template.json").read_text(encoding="utf-8"))
    config_template["project"]["id"] = args.project_id
    config_template["project"]["name"] = project_name

    _write_json(project_root / "config" / "project-config.json", config_template)
    _write_text(project_root / "README.md", f"# {project_name}\n\nInitialized marketing automation project workspace.\n")
    _write_text(project_root / "data" / ".gitkeep", "")
    _write_text(project_root / "data" / "raw-imports" / ".gitkeep", "")
    _write_text(
        project_root / "data" / "raw-imports" / "sample-public-leads.csv",
        "\n".join(
            [
                "source_url,company_name,website_root_domain,account_type,persona_type,geo,signals,email,full_name,reachability_status,source_confidence",
                "https://exampledealer.com/partners,Example Dealer,exampledealer.com,distributor,buyer,US,dealer_program_fit|regional_distribution,trade@exampledealer.com,Taylor Brooks,email_verified,0.86",
                "https://demo-contractor.com/contact,Demo Contractor,demo-contractor.com,contractor,operations_manager,US,quote_request_path|active_install_work,,Jamie Stone,form_available,0.79",
            ]
        )
        + "\n",
    )
    _write_json(
        project_root / "data" / "prospect-seeds.json",
        {
            "items": [
                {
                    "source_url": "https://exampledesignstudio.com/contact",
                    "company_name": "Example Design Studio",
                    "website_root_domain": "exampledesignstudio.com",
                    "account_type": "designer",
                    "persona_type": "buyer",
                    "geo": "US",
                    "signals": ["trade_program_fit", "design_led_projects"],
                    "contact": {
                        "contact_id": "contact-example-design-studio-buyer",
                        "full_name": "Alex Carter",
                        "email": "trade@exampledesignstudio.com",
                        "reachability_status": "email_verified"
                    },
                    "source_confidence": 0.88
                },
                {
                    "source_url": "https://samplebuildco.com/quote",
                    "company_name": "Sample Build Co",
                    "website_root_domain": "samplebuildco.com",
                    "account_type": "contractor",
                    "persona_type": "operations_manager",
                    "geo": "US",
                    "signals": ["quote_request_path", "active_project_pipeline"],
                    "contact": {
                        "contact_id": "contact-sample-build-co-ops",
                        "full_name": "Jordan Lee",
                        "email": "",
                        "reachability_status": "form_available"
                    },
                    "source_confidence": 0.84
                },
                {
                    "source_url": "https://regionaldistributor.example/partner",
                    "company_name": "Regional Distributor Group",
                    "website_root_domain": "regionaldistributor.example",
                    "account_type": "distributor",
                    "persona_type": "founder",
                    "geo": "US",
                    "signals": ["dealer_program_fit", "multi_region_coverage"],
                    "contact": {
                        "contact_id": "contact-regional-distributor-founder",
                        "full_name": "Morgan Price",
                        "email": "partnerships@regionaldistributor.example",
                        "reachability_status": "email_unverified"
                    },
                    "source_confidence": 0.81
                }
            ]
        },
    )
    _write_json(project_root / "data" / "feedback-events.json", {"items": []})
    _write_json(
        project_root / "data" / "discovery-targets.json",
        {
            "items": [
                {
                    "target_url": "https://example.com",
                    "account_type": "distributor",
                    "persona_type": "buyer",
                    "geo": "US",
                    "signal_hints": ["public_website_discovery"],
                    "enabled": False
                }
            ]
        },
    )
    _write_json(
        project_root / "data" / "discovery-queries.json",
        {
            "items": [
                {
                    "query": "lighting distributor united states",
                    "account_type": "distributor",
                    "persona_type": "buyer",
                    "geo": "US",
                    "signal_hints": ["search_discovery"],
                    "max_results": 5,
                    "enabled": False
                }
            ]
        },
    )
    _write_text(project_root / "output" / ".gitkeep", "")
    _write_text(project_root / "runtime" / ".gitkeep", "")
    _write_text(project_root / "reports" / ".gitkeep", "")
    _write_text(project_root / "logs" / ".gitkeep", "")
    _write_json(
        project_root / "runtime" / "state.json",
        {
            "project_id": args.project_id,
            "status": "initialized",
            "last_completed_cycle": "",
            "last_feedback_sync_at": "",
            "notes": [],
        },
    )

    print(
        json.dumps(
            {
                "project_root": str(project_root),
                "config_path": str(project_root / "config" / "project-config.json"),
                "status_path": str(project_root / "runtime" / "state.json"),
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
