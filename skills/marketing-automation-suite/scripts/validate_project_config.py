#!/usr/bin/env python3

from __future__ import annotations

import argparse
import json
from pathlib import Path


REQUIRED_TOP_LEVEL = [
    "project",
    "icp",
    "channels",
    "prospect_data_engine",
    "marketing_strategy_engine",
    "outreach_feedback_engine",
]


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate a marketing automation project config.")
    parser.add_argument("--config", required=True)
    args = parser.parse_args()

    path = Path(args.config).expanduser().resolve()
    payload = json.loads(path.read_text(encoding="utf-8"))
    missing = [key for key in REQUIRED_TOP_LEVEL if key not in payload]
    warnings = []
    if not payload.get("channels", {}).get("priority"):
        warnings.append("channels.priority is empty")
    if not payload.get("icp", {}).get("account_types"):
        warnings.append("icp.account_types is empty")
    if not payload.get("project", {}).get("conversion_target"):
        warnings.append("project.conversion_target is empty")

    print(
        json.dumps(
            {
                "config": str(path),
                "ok": not missing,
                "missing": missing,
                "warnings": warnings,
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0 if not missing else 1


if __name__ == "__main__":
    raise SystemExit(main())

