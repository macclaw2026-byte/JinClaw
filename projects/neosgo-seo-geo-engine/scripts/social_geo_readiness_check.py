#!/usr/bin/env python3
# RULES-FIRST NOTICE:
# Before modifying this file, first read:
# - `JINCLAW_CONSTITUTION.md`
# - `AI_OPTIMIZATION_FRAMEWORK.md`
# Follow the constitution and framework:
# brain-first, one-doctor, fail-closed, evidence-over-narration,
# validate locally, then use the required PR workflow.
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path("/Users/mac_claw/.openclaw/workspace/projects/neosgo-seo-geo-engine")
CONFIG_PATH = ROOT / "config" / "social_geo_program.json"
OUTPUT_DIR = ROOT / "output" / "social-geo-readiness"
MARKETING_ENV_PATH = Path("/Users/mac_claw/.openclaw/secrets/neosgo-marketing.env")
ADMIN_OPS_ENV_PATH = Path("/Users/mac_claw/.config/openclaw/env/neosgo-admin-ops.env")


def _now_compact() -> str:
    """返回 UTC 紧凑时间戳，供报告文件名使用。"""
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def _load_json(path: Path) -> Any:
    """安全读取 JSON；缺失或损坏时返回空结构。"""
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _load_env(path: Path) -> dict[str, str]:
    """从简单 env 文件读取键值对。"""
    data: dict[str, str] = {}
    if not path.exists():
        return data
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        data[key.strip()] = value.strip()
    return data


def _secret_status() -> dict[str, Any]:
    """检查 SEO+GEO 与 admin-ops 两条线的 token 配置是否齐备。"""
    marketing_env = _load_env(MARKETING_ENV_PATH)
    admin_ops_env = _load_env(ADMIN_OPS_ENV_PATH)
    return {
        "marketing_env_path": str(MARKETING_ENV_PATH),
        "admin_ops_env_path": str(ADMIN_OPS_ENV_PATH),
        "marketing_token_present": bool(marketing_env.get("NEOSGO_ADMIN_MARKETING_KEY", "").strip()),
        "marketing_base_url": marketing_env.get("NEOSGO_ADMIN_MARKETING_API_BASE", "https://mc.neosgo.com"),
        "admin_ops_token_present": bool(
            (admin_ops_env.get("NEOSGO_ADMIN_API_TOKEN") or admin_ops_env.get("NEOSGO_ADMIN_AUTOMATION_KEY") or "").strip()
        ),
        "admin_ops_base_url": admin_ops_env.get("NEOSGO_ADMIN_BASE_URL", "https://mc.neosgo.com"),
        "gsc_enabled": str(marketing_env.get("NEOSGO_GSC_ENABLED", "false")).strip().lower() in {"1", "true", "yes", "on"},
        "gsc_credentials_present": all(
            bool(marketing_env.get(key, "").strip())
            for key in ("NEOSGO_GSC_CLIENT_ID", "NEOSGO_GSC_CLIENT_SECRET", "NEOSGO_GSC_REFRESH_TOKEN", "NEOSGO_GSC_SITE_URL")
        ),
    }


def _operator_input_status(config: dict[str, Any]) -> list[dict[str, Any]]:
    """检查操作方需要提供的资料是否已经落位。"""
    rows: list[dict[str, Any]] = []
    for item in list(config.get("operator_inputs") or []):
        path = Path(str(item.get("path") or "").strip())
        exists = path.exists() if path else False
        rows.append(
            {
                "key": str(item.get("key") or "").strip(),
                "required": bool(item.get("required", False)),
                "path": str(path),
                "exists": exists,
                "description": str(item.get("description") or "").strip(),
            }
        )
    return rows


def _channel_status(config: dict[str, Any], operator_inputs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """把资料齐备情况映射成各渠道 readiness。"""
    ready_lookup = {row["key"]: row["exists"] for row in operator_inputs}
    channels: list[dict[str, Any]] = []
    for item in list(config.get("channels") or []):
        required_inputs = [str(value).strip() for value in list(item.get("required_inputs") or []) if str(value).strip()]
        missing = [key for key in required_inputs if not ready_lookup.get(key, False)]
        channels.append(
            {
                "key": str(item.get("key") or "").strip(),
                "priority": item.get("priority"),
                "role": str(item.get("role") or "").strip(),
                "required_inputs": required_inputs,
                "missing_inputs": missing,
                "ready": not missing,
            }
        )
    return channels


def build_readiness_report(config: dict[str, Any]) -> dict[str, Any]:
    """组合完整 readiness 报告。"""
    secret_status = _secret_status()
    operator_inputs = _operator_input_status(config)
    channels = _channel_status(config, operator_inputs)
    required_missing = [row["key"] for row in operator_inputs if row["required"] and not row["exists"]]
    blocked_channels = [row["key"] for row in channels if not row["ready"]]
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "program": dict(config.get("program") or {}),
        "secret_status": secret_status,
        "operator_inputs": operator_inputs,
        "channels": channels,
        "blocked": bool(required_missing or blocked_channels or not secret_status["marketing_token_present"] or not secret_status["admin_ops_token_present"]),
        "required_missing_inputs": required_missing,
        "blocked_channels": blocked_channels,
        "recommended_next_actions": [
            "Provide all required operator input files under runtime/operator-inputs.",
            "Enable Bing AI Performance and record access evidence.",
            "If GSC automation is desired, populate Google Search Console OAuth credentials.",
            "Only move channel status to ready after explicit access evidence is stored."
        ],
    }


def main() -> int:
    ap = argparse.ArgumentParser(description="Build a NEOSGO social+GEO readiness report.")
    ap.add_argument("--write", action="store_true", help="Write the report to output/social-geo-readiness.")
    args = ap.parse_args()

    config = _load_json(CONFIG_PATH)
    if not config:
        print(json.dumps({"ok": False, "error": f"missing_or_invalid_config:{CONFIG_PATH}"}, ensure_ascii=False))
        return 1

    report = build_readiness_report(config)
    if args.write:
        OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
        target = OUTPUT_DIR / f"social-geo-readiness-{_now_compact()}.json"
        target.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        report["report_path"] = str(target)

    print(json.dumps(report, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
