#!/usr/bin/env python3

from __future__ import annotations

from pathlib import Path
from typing import Dict


LEAD_ENGINE_PLAN_PATH = Path("/Users/mac_claw/.openclaw/workspace/output/neosgo-lead-engine-ideal-plan-2026-03-25.md")


def _normalized(text: str) -> str:
    return " ".join(str(text or "").strip().lower().split())


def detect_root_mission_profile(goal: str, *, task_id: str = "", intent: Dict[str, object] | None = None) -> Dict[str, object]:
    normalized_goal = _normalized(goal)
    normalized_task_id = _normalized(task_id)
    task_types = {str(item).strip().lower() for item in (intent or {}).get("task_types", []) if str(item).strip()}

    lead_keywords = (
        "lead",
        "leads",
        "prospect",
        "prospects",
        "database",
        "duckdb",
        "marketing",
        "outreach",
        "campaign",
        "daily report",
        "daily reports",
        "daily reporting",
        "客户数据",
        "潜客",
        "数据库",
        "营销",
        "客户开发",
        "开发方案",
        "每日汇报",
        "导入",
        "压缩包",
    )
    keyword_hits = sum(1 for token in lead_keywords if token in normalized_goal)
    looks_like_lead_engine = (
        normalized_task_id == "neosgo-lead-engine"
        or (
            "neosgo" in normalized_goal
            and (
                keyword_hits >= 2
                or (
                    {"data", "code"} & task_types
                    and any(token in normalized_goal for token in ("潜客", "lead", "marketing", "outreach", "daily"))
                )
            )
        )
    )
    if not looks_like_lead_engine:
        return {"matched": False}

    canonical_goal = (
        "搭建并持续运行 Neosgo lead engine：把本机数据库与 Downloads 压缩包中的客户数据导入统一 DuckDB，"
        "完成清洗标准化、潜客筛选与打分、客户画像、营销策略、客户开发方案、可持续自动执行，以及每日进展汇报。"
    )
    return {
        "matched": True,
        "profile_id": "neosgo_lead_engine",
        "root_task_id": "neosgo-lead-engine",
        "canonical_goal": canonical_goal,
        "done_definition": (
            "Neosgo lead engine 已按理想方案落成可持续 root mission：数据导入、标准化、潜客识别、营销策略、"
            "客户开发与每日汇报都有真实产出或被精确阻塞并持续报告。"
        ),
        "ideal_plan_path": str(LEAD_ENGINE_PLAN_PATH),
        "phase_names": [
            "data_ingress",
            "normalization",
            "prospect_scoring",
            "marketing_strategy",
            "outreach_execution",
            "daily_reporting",
        ],
        "summary": "A stable Neosgo lead-engine root mission with phased execution and daily reporting.",
    }
