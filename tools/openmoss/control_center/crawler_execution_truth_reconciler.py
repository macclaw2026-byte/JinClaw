#!/usr/bin/env python3
# RULES-FIRST NOTICE:
# Before modifying this file, first read:
# - `JINCLAW_CONSTITUTION.md`
# - `AI_OPTIMIZATION_FRAMEWORK.md`
# Follow the constitution and framework:
# brain-first, one-doctor, fail-closed, evidence-over-narration,
# validate locally, then use the required PR workflow.
"""
中文说明：
- 文件路径：`tools/openmoss/control_center/crawler_execution_truth_reconciler.py`
- 文件作用：把 crawler 的 latest-run / contract / site-profile 三层证据做一次受控对账，并在安全可解释时落盘修正。
- 顶层函数：list_execution_truth_drift_sites、reconcile_site_execution_truth、reconcile_execution_truth_batch。
- 顶层类：无顶层类。
"""
from __future__ import annotations

import json
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

from paths import CRAWLER_CAPABILITY_PROFILE_PATH

WORKSPACE_ROOT = Path("/Users/mac_claw/.openclaw/workspace")
REPORTS_ROOT = WORKSPACE_ROOT / "crawler/reports"
SITE_PROFILES_ROOT = WORKSPACE_ROOT / "crawler/site-profiles"
LEGACY_SITE_PROFILES_PATH = WORKSPACE_ROOT / "crawler/logic/site_profiles.json"

import sys

if str(WORKSPACE_ROOT) not in sys.path:
    sys.path.insert(0, str(WORKSPACE_ROOT))

from crawler.logic.crawler_contract import build_contract


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _read_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return default


def _write_json(path: Path, payload: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _site_profile_path(site: str) -> Path:
    return SITE_PROFILES_ROOT / f"{site}.json"


def _latest_run_path(site: str) -> Path:
    return REPORTS_ROOT / f"{site}-latest-run.json"


def _contract_path(site: str) -> Path:
    return REPORTS_ROOT / f"{site}-contract.json"


def list_execution_truth_drift_sites() -> List[str]:
    """
    中文注解：
    - 功能：从当前 capability profile 读取 execution-truth drift site 列表。
    - 输出角色：供 remediation executor 在 project-level reconcile 动作里直接批量消费。
    """
    profile = _read_json(CRAWLER_CAPABILITY_PROFILE_PATH, {}) or {}
    sites: List[str] = []
    for item in profile.get("sites", []) or []:
        site = str(item.get("site", "")).strip()
        if not site:
            continue
        alignment = (item.get("evidence_alignment", {}) or {}).get("has_drift")
        if alignment and site not in sites:
            sites.append(site)
    return sites


def _safe_to_apply(fresh_contract: Dict[str, Any], latest_run: Dict[str, Any]) -> tuple[bool, str]:
    comparison = fresh_contract.get("comparison_summary", {}) or {}
    fresh_best_tool = str(comparison.get("best_tool") or "").strip()
    fresh_best_status = str(comparison.get("best_status", "")).strip().lower()
    required_fields_met = bool(comparison.get("required_fields_met"))
    latest_best_status = str(latest_run.get("bestStatus", "")).strip().lower()
    if fresh_best_tool and fresh_best_status == "usable" and required_fields_met:
        return True, "fresh_contract_has_required_fields"
    if not fresh_best_tool and fresh_best_status == "blocked" and latest_best_status in {"", "blocked", "failed"}:
        return True, "fresh_contract_and_latest_run_both_blocked"
    return False, "fresh_contract_requires_richer_evidence_or_revalidation"


def _merge_profile(site: str, current_profile: Dict[str, Any], fresh_contract: Dict[str, Any], safe_reason: str) -> Dict[str, Any]:
    comparison = fresh_contract.get("comparison_summary", {}) or {}
    usable_tools = [str(item.get("tool", "")).strip() for item in (comparison.get("usable_tools", []) or []) if str(item.get("tool", "")).strip()]
    blocked_tools = [str(item).strip() for item in (fresh_contract.get("blocked_tools", []) or []) if str(item).strip()]
    preferred_tool_order = [str(item).strip() for item in (fresh_contract.get("preferred_tool_order", []) or []) if str(item).strip()]
    task_fields = dict(fresh_contract.get("task_ready_fields", {}) or {})
    best_tool = str(comparison.get("best_tool") or "").strip()
    confidence = "high" if best_tool and comparison.get("required_fields_met") else "medium" if best_tool else "low"
    notes = list(current_profile.get("notes", []) or [])
    reconcile_note = (
        f"execution_truth_reconciled:{safe_reason}:selected_tool={best_tool or 'none'}:"
        f"required_fields_met={bool(comparison.get('required_fields_met'))}"
    )
    if reconcile_note not in notes:
        notes.append(reconcile_note)
    merged = dict(current_profile or {})
    merged.update(
        {
            "site": site,
            "mode": str(current_profile.get("mode", "")).strip() or str(fresh_contract.get("mode", "")).strip(),
            "confidence": confidence,
            "selected_tool": best_tool,
            "usable_tools": usable_tools,
            "blocked_tools": blocked_tools,
            "tested_tools": list(fresh_contract.get("tested_tools", []) or current_profile.get("tested_tools", []) or []),
            "preferred_tool_order": preferred_tool_order,
            "fallback_policy": str(current_profile.get("fallback_policy", "")).strip()
            or str(current_profile.get("fallbackPolicy", "")).strip()
            or str(fresh_contract.get("repeat_run_rule", "")).strip(),
            "task_output_fields": task_fields,
            "last_evaluated": str(fresh_contract.get("generated_at", "")).split("T")[0] or _utc_now_iso().split("T")[0],
            "last_reconciled_at": _utc_now_iso(),
            "reconciliation_status": "aligned",
            "reconciliation_reason": safe_reason,
            "notes": notes[-8:],
        }
    )
    return merged


def _sync_legacy_profile(site: str, merged_profile: Dict[str, Any]) -> None:
    legacy = _read_json(LEGACY_SITE_PROFILES_PATH, {}) or {}
    legacy[site] = {
        "site": site,
        "lastEvaluated": merged_profile.get("last_evaluated", ""),
        "confidence": merged_profile.get("confidence", ""),
        "mode": merged_profile.get("mode", ""),
        "preferredTools": list(merged_profile.get("preferred_tool_order", []) or []),
        "fallbackPolicy": merged_profile.get("fallback_policy", ""),
        "notes": list(merged_profile.get("notes", []) or [])[-5:],
    }
    _write_json(LEGACY_SITE_PROFILES_PATH, legacy)


def reconcile_site_execution_truth(site: str) -> Dict[str, Any]:
    """
    中文注解：
    - 功能：对单个站点做 execution-truth 对账。
    - 设计意图：只有在 fresh contract 足够强、不会把弱证据伪装成真相时才自动落盘；否则显式要求 revalidation。
    """
    normalized_site = str(site or "").strip().lower()
    current_profile = _read_json(_site_profile_path(normalized_site), {}) or {}
    latest_run = _read_json(_latest_run_path(normalized_site), {}) or {}
    existing_contract = _read_json(_contract_path(normalized_site), {}) or {}
    fresh_contract = asdict(build_contract(normalized_site))
    safe_to_apply, safe_reason = _safe_to_apply(fresh_contract, latest_run)
    result: Dict[str, Any] = {
        "site": normalized_site,
        "checked_at": _utc_now_iso(),
        "safe_to_apply": safe_to_apply,
        "safe_reason": safe_reason,
        "latest_best_tool": latest_run.get("bestTool"),
        "latest_best_status": latest_run.get("bestStatus"),
        "existing_contract_best_tool": (existing_contract.get("comparison_summary", {}) or {}).get("best_tool"),
        "fresh_contract_best_tool": (fresh_contract.get("comparison_summary", {}) or {}).get("best_tool"),
        "fresh_contract_best_status": (fresh_contract.get("comparison_summary", {}) or {}).get("best_status"),
        "required_fields_met": bool((fresh_contract.get("comparison_summary", {}) or {}).get("required_fields_met")),
        "missing_required_fields": list((fresh_contract.get("comparison_summary", {}) or {}).get("missing_required_fields", []) or []),
        "written_paths": [],
    }
    if not safe_to_apply:
        result["status"] = "needs_revalidation"
        return result
    merged_profile = _merge_profile(normalized_site, current_profile, fresh_contract, safe_reason)
    _write_json(_contract_path(normalized_site), fresh_contract)
    _write_json(_site_profile_path(normalized_site), merged_profile)
    _sync_legacy_profile(normalized_site, merged_profile)
    result["status"] = "applied"
    result["written_paths"] = [
        str(_contract_path(normalized_site)),
        str(_site_profile_path(normalized_site)),
        str(LEGACY_SITE_PROFILES_PATH),
    ]
    return result


def reconcile_execution_truth_batch(sites: List[str] | None = None) -> Dict[str, Any]:
    """
    中文注解：
    - 功能：批量对账 execution-truth drift site。
    - 输入角色：可显式指定 site 列表；若为空则自动读取 capability profile 中的 drift sites。
    - 输出角色：供 remediation executor、doctor、ops 汇总“本轮对账修了多少、还剩多少需要 revalidation”。
    """
    target_sites = [str(site).strip().lower() for site in (sites or list_execution_truth_drift_sites()) if str(site).strip()]
    results = [reconcile_site_execution_truth(site) for site in target_sites]
    return {
        "checked_at": _utc_now_iso(),
        "sites_total": len(target_sites),
        "applied_total": sum(1 for item in results if item.get("status") == "applied"),
        "needs_revalidation_total": sum(1 for item in results if item.get("status") == "needs_revalidation"),
        "sites": results,
    }


def main() -> int:
    print(json.dumps(reconcile_execution_truth_batch(), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
