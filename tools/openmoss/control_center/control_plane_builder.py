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
- 文件路径：`tools/openmoss/control_center/control_plane_builder.py`
- 文件作用：负责统一控制平面的快照构建与多源状态汇总。
- 顶层函数：_utc_now_iso、_read_json、_write_json、_launchctl_status、build_process_registry、_load_task_state、_load_task_contract、_conversation_links_for_task、build_task_registry、build_control_plane、main。
- 顶层类：无顶层类。
- 阅读建议：先看模块说明，再按函数/类 docstring 顺着主流程理解调用关系。
"""
from __future__ import annotations

import json
import os
import plistlib
import subprocess
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

from canonical_active_task import resolve_canonical_active_task
from crawler_capability_profile import build_crawler_capability_profile
from crawler_remediation_planner import build_crawler_remediation_plan
from execution_governor import classify_blocked_runtime_state
from generate_task_dashboard import build_task_dashboard
from governance_runtime import _build_doctor_coverage_bundle
from memory_writeback_runtime import summarize_project_memory_writebacks
from project_scheduler_policy import build_project_scheduler_policy
from task_alias_registry import build_task_alias_registry
from task_retention_runtime import load_archived_task_registry, run_task_retention
from paths import (
    ALERTS_PATH,
    ARCHIVED_TASK_REGISTRY_PATH,
    CONVERSATION_REGISTRY_PATH,
    DOCTOR_LAST_RUN_PATH,
    CROSS_MARKET_ARBITRAGE_SCHEDULER_STATE_PATH,
    CRAWLER_CAPABILITY_PROFILE_PATH,
    CRAWLER_REMEDIATION_EXECUTION_PATH,
    CRAWLER_REMEDIATION_PLAN_PATH,
    CRAWLER_REMEDIATION_QUEUE_PATH,
    CRAWLER_REMEDIATION_SCHEDULER_STATE_PATH,
    DOCTOR_QUEUE_PATH,
    PROCESS_REGISTRY_PATH,
    PROCESS_INCIDENTS_PATH,
    PROJECT_REPAIR_VALUE_HISTORY_PATH,
    PROJECT_RESULT_FEEDBACK_HISTORY_PATH,
    RUNTIME_JOBS_REGISTRY_PATH,
    SELLER_BULK_SCHEDULER_STATE_PATH,
    SYSTEM_SNAPSHOT_PATH,
    TASK_RETENTION_LAST_RUN_PATH,
    TASK_ALIAS_REGISTRY_PATH,
    TASK_REGISTRY_PATH,
    WAITING_REGISTRY_PATH,
)
from progress_evidence import build_progress_evidence


AUTONOMY_TASKS_ROOT = Path("/Users/mac_claw/.openclaw/workspace/tools/openmoss/runtime/autonomy/tasks")
LINKS_ROOT = Path("/Users/mac_claw/.openclaw/workspace/tools/openmoss/runtime/autonomy/links")
LAUNCH_AGENTS_ROOT = Path.home() / "Library/LaunchAgents"
OPENCLAW_LAUNCHD_PREFIXES = ("ai.openclaw.", "ai.jinclaw.")

PROCESS_TARGETS = [
    {"label": "brain_enforcer", "launchd_label": "ai.openclaw.brain-enforcer"},
    {"label": "autonomy_runtime", "launchd_label": "ai.jinclaw.autonomy-runtime"},
    {"label": "cross_market_arbitrage", "launchd_label": "ai.jinclaw.cross-market-arbitrage"},
    {"label": "crawler_remediation", "launchd_label": "ai.jinclaw.crawler-remediation"},
]

RUNTIME_JOB_OVERRIDES: Dict[str, Dict[str, str]] = {
    "ai.jinclaw.autonomy-runtime": {
        "name": "Autonomy Runtime",
        "description": "持续轮询 autonomy 任务，推进执行、恢复、验证和学习写回。",
    },
    "ai.jinclaw.crawler-remediation": {
        "name": "Crawler Remediation",
        "description": "定时跑 crawler 修复、站点回归和能力恢复循环。",
    },
    "ai.jinclaw.cross-market-arbitrage": {
        "name": "Cross-Market Arbitrage",
        "description": "持续监控跨市场套利机会并驱动套利引擎。",
    },
    "ai.jinclaw.cross-market-daily-report": {
        "name": "Cross-Market Daily Report",
        "description": "每天发送跨市场套利日报到指定 Telegram 会话。",
    },
    "ai.jinclaw.neosgo-admin-ops-daily-report": {
        "name": "NEOSGO Admin Ops Daily Report",
        "description": "每天汇总并发送 NEOSGO admin ops 日报。",
    },
    "ai.jinclaw.neosgo-admin-ops-watcher": {
        "name": "NEOSGO Admin Ops Watcher",
        "description": "高频巡检 NEOSGO admin ops 健康、指标和异常信号。",
    },
    "ai.jinclaw.neosgo-growth-radar": {
        "name": "NEOSGO Growth Radar",
        "description": "周期运行 marketing suite，跟踪增长机会、内容与线索变化。",
    },
    "ai.jinclaw.neosgo-lead-collection-daily": {
        "name": "NEOSGO Lead Collection Daily",
        "description": "每天发送 Google Maps 潜客采集进度汇总。",
    },
    "ai.jinclaw.neosgo-outreach-cycle-hourly": {
        "name": "NEOSGO Outreach Cycle",
        "description": "周期推进潜客触达，包括 contact form 和 email 外联循环。",
    },
    "ai.jinclaw.neosgo-outreach-summary-3h": {
        "name": "NEOSGO Outreach Summary",
        "description": "每 3 小时发送一次 outreach 进度摘要。",
    },
    "ai.jinclaw.neosgo-seller-maintenance-daily": {
        "name": "NEOSGO Seller Maintenance",
        "description": "每天跑 seller 持续维护、素材修补和状态校验。",
    },
    "ai.jinclaw.neosgo-seo-geo-daily": {
        "name": "NEOSGO SEO Geo Daily",
        "description": "每天执行 NEOSGO SEO/GEO 运营循环与内容更新。",
    },
    "ai.jinclaw.upstream-watch": {
        "name": "Upstream Watch",
        "description": "定时检查上游依赖、外部源和同步链路是否变化。",
    },
    "ai.openclaw.brain-enforcer": {
        "name": "Brain Enforcer",
        "description": "常驻守护控制平面，纠正会话焦点、任务路由和约束执行。",
    },
    "ai.openclaw.gateway": {
        "name": "OpenClaw Gateway",
        "description": "OpenClaw 网关常驻服务，负责入口通信和服务接入。",
    },
    "ai.openclaw.selfheal": {
        "name": "OpenClaw Selfheal",
        "description": "定时自愈巡检，尝试恢复 OpenClaw 关键链路。",
    },
}


def _utc_now_iso() -> str:
    """
    中文注解：
    - 功能：实现 `_utc_now_iso` 对应的处理逻辑。
    - 角色：属于本模块中的内部辅助逻辑；私有函数通常服务同文件主流程，公共函数通常作为跨模块入口或能力接口。
    - 调用关系：建议结合本文件的模块说明、调用方以及同名相关辅助函数一起阅读。
    """
    return datetime.now(timezone.utc).isoformat()


def _read_json(path: Path, default: Any) -> Any:
    """
    中文注解：
    - 功能：实现 `_read_json` 对应的处理逻辑。
    - 角色：属于本模块中的内部辅助逻辑；私有函数通常服务同文件主流程，公共函数通常作为跨模块入口或能力接口。
    - 调用关系：建议结合本文件的模块说明、调用方以及同名相关辅助函数一起阅读。
    """
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return default


def _write_json(path: Path, payload: Any) -> str:
    """
    中文注解：
    - 功能：实现 `_write_json` 对应的处理逻辑。
    - 角色：属于本模块中的内部辅助逻辑；私有函数通常服务同文件主流程，公共函数通常作为跨模块入口或能力接口。
    - 调用关系：建议结合本文件的模块说明、调用方以及同名相关辅助函数一起阅读。
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = path.with_name(f"{path.name}.{os.getpid()}.{uuid.uuid4().hex}.tmp")
    temp_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    temp_path.replace(path)
    return str(path)


def _launchctl_status(launchd_label: str) -> Dict[str, Any]:
    """
    中文注解：
    - 功能：实现 `_launchctl_status` 对应的处理逻辑。
    - 角色：属于本模块中的内部辅助逻辑；私有函数通常服务同文件主流程，公共函数通常作为跨模块入口或能力接口。
    - 调用关系：建议结合本文件的模块说明、调用方以及同名相关辅助函数一起阅读。
    """
    domain = f"gui/{os.getuid()}/{launchd_label}"
    proc = subprocess.run(
        ["launchctl", "print", domain],
        capture_output=True,
        text=True,
        timeout=10,
    )
    output = (proc.stdout or "") + "\n" + (proc.stderr or "")
    state = "unknown"
    pid = 0
    runs = 0
    last_exit_code: int | None = None
    active_count = 0
    plist_path = ""
    for line in output.splitlines():
        stripped = line.strip()
        if stripped.startswith("state = "):
            state = stripped.split("=", 1)[1].strip()
        elif stripped.startswith("pid = "):
            try:
                pid = int(stripped.split("=", 1)[1].strip())
            except ValueError:
                pid = 0
        elif stripped.startswith("runs = "):
            try:
                runs = int(stripped.split("=", 1)[1].strip())
            except ValueError:
                runs = 0
        elif stripped.startswith("last exit code = "):
            raw = stripped.split("=", 1)[1].strip()
            try:
                last_exit_code = int(raw)
            except ValueError:
                last_exit_code = None
        elif stripped.startswith("active count = "):
            try:
                active_count = int(stripped.split("=", 1)[1].strip())
            except ValueError:
                active_count = 0
        elif stripped.startswith("path = "):
            plist_path = stripped.split("=", 1)[1].strip()
    return {
        "launchd_label": launchd_label,
        "ok": proc.returncode == 0,
        "state": state,
        "pid": pid,
        "runs": runs,
        "last_exit_code": last_exit_code,
        "active_count": active_count,
        "plist_path": plist_path,
        "raw_excerpt": "\n".join(output.splitlines()[:20]),
    }


def build_process_registry() -> Dict[str, Any]:
    """
    中文注解：
    - 功能：实现 `build_process_registry` 对应的处理逻辑。
    - 角色：属于本模块中的对外可见逻辑；私有函数通常服务同文件主流程，公共函数通常作为跨模块入口或能力接口。
    - 调用关系：建议结合本文件的模块说明、调用方以及同名相关辅助函数一起阅读。
    """
    items = []
    for target in PROCESS_TARGETS:
        status = _launchctl_status(target["launchd_label"])
        status["label"] = target["label"]
        items.append(status)
    registry = {
        "generated_at": _utc_now_iso(),
        "items": items,
        "all_running": all(item.get("state") == "running" for item in items),
    }
    registry["path"] = _write_json(PROCESS_REGISTRY_PATH, registry)
    return registry


def _read_plist(path: Path) -> Dict[str, Any]:
    if not path.exists():
        return {}
    try:
        return plistlib.loads(path.read_bytes())
    except (OSError, plistlib.InvalidFileException):
        return {}


def _humanize_interval(seconds: int) -> str:
    if seconds <= 0:
        return "按间隔触发"
    if seconds % 86400 == 0:
        days = seconds // 86400
        return f"每 {days} 天"
    if seconds % 3600 == 0:
        hours = seconds // 3600
        return f"每 {hours} 小时"
    if seconds % 60 == 0:
        minutes = seconds // 60
        return f"每 {minutes} 分钟"
    return f"每 {seconds} 秒"


def _format_calendar_entry(entry: Dict[str, Any]) -> str:
    if not isinstance(entry, dict):
        return "按日历触发"
    hour = int(entry.get("Hour", 0) or 0)
    minute = int(entry.get("Minute", 0) or 0)
    month = entry.get("Month")
    day = entry.get("Day")
    weekday = entry.get("Weekday")
    clock = f"{hour:02d}:{minute:02d}"
    if month is not None and day is not None:
        return f"每年 {int(month):02d}-{int(day):02d} {clock}"
    if weekday is not None:
        weekday_names = {
            0: "周日",
            1: "周一",
            2: "周二",
            3: "周三",
            4: "周四",
            5: "周五",
            6: "周六",
            7: "周日",
        }
        return f"{weekday_names.get(int(weekday), f'每周{weekday}')} {clock}"
    if day is not None:
        return f"每月 {int(day):02d} 日 {clock}"
    return f"每天 {clock}"


def _format_calendar_schedule(value: Any) -> str:
    if isinstance(value, list):
        parts = [_format_calendar_entry(item) for item in value if isinstance(item, dict)]
        return "；".join(parts) if parts else "按日历触发"
    if isinstance(value, dict):
        return _format_calendar_entry(value)
    return "按日历触发"


def _program_summary(arguments: List[Any]) -> str:
    parts = [str(arg).strip() for arg in (arguments or []) if str(arg).strip()]
    if not parts:
        return "-"
    for part in reversed(parts):
        if "/" in part or part.endswith((".py", ".sh", ".js")):
            return Path(part).name
    return " ".join(parts[:3])


def _runtime_job_name(label: str, payload: Dict[str, Any]) -> str:
    override = (RUNTIME_JOB_OVERRIDES.get(label, {}) or {}).get("name")
    if override:
        return override
    comment = str(payload.get("Comment", "")).strip()
    if comment:
        return comment
    return label.replace("ai.openclaw.", "").replace("ai.jinclaw.", "").replace("-", " ").title()


def _runtime_job_description(label: str, payload: Dict[str, Any]) -> str:
    override = (RUNTIME_JOB_OVERRIDES.get(label, {}) or {}).get("description")
    if override:
        return override
    comment = str(payload.get("Comment", "")).strip()
    if comment:
        return comment
    return f"由 { _program_summary(payload.get('ProgramArguments', []) or []) } 驱动的运行任务。"


def _runtime_trigger_summary(payload: Dict[str, Any], category: str) -> Dict[str, Any]:
    keep_alive = bool(payload.get("KeepAlive"))
    run_at_load = bool(payload.get("RunAtLoad"))
    start_interval = int(payload.get("StartInterval", 0) or 0)
    start_calendar = payload.get("StartCalendarInterval")
    if category == "continuous" and keep_alive:
        return {
            "schedule_kind": "keepalive",
            "trigger_summary": "启动时拉起；退出后自动重启",
            "trigger_sort_value": "0000-keepalive",
        }
    parts: List[str] = []
    if run_at_load:
        parts.append("启动时先跑一次")
    sort_value = "9999-unscheduled"
    if start_calendar:
        parts.append(_format_calendar_schedule(start_calendar))
        if isinstance(start_calendar, dict):
            sort_value = f"{int(start_calendar.get('Hour', 99) or 99):02d}:{int(start_calendar.get('Minute', 99) or 99):02d}"
    if start_interval > 0:
        parts.append(_humanize_interval(start_interval))
        sort_value = f"{start_interval:08d}"
    return {
        "schedule_kind": "scheduled",
        "trigger_summary": "；".join(parts) if parts else "按计划触发",
        "trigger_sort_value": sort_value,
    }


def _runtime_status_summary(category: str, launch_status: Dict[str, Any]) -> Dict[str, str]:
    ok = bool(launch_status.get("ok"))
    state = str(launch_status.get("state", "")).strip() or "unknown"
    pid = int(launch_status.get("pid", 0) or 0)
    last_exit_code = launch_status.get("last_exit_code")
    if pid > 0 or state == "running":
        return {"state_family": "running", "status_text": f"running · pid {pid}" if pid > 0 else "running"}
    if not ok:
        return {"state_family": "not_loaded", "status_text": "not loaded"}
    if last_exit_code not in {None, 0}:
        if category == "continuous":
            return {"state_family": "crashed", "status_text": f"crashed · last exit {last_exit_code}"}
        return {"state_family": "failing", "status_text": f"last run failed · exit {last_exit_code}"}
    if category == "continuous":
        if state == "spawn scheduled":
            return {"state_family": "attention", "status_text": "spawn scheduled"}
        if state == "not running":
            return {"state_family": "attention", "status_text": "not running"}
        return {"state_family": "attention", "status_text": state}
    return {"state_family": "idle", "status_text": "waiting next trigger"}


def _runtime_job_doctor_attention(item: Dict[str, Any]) -> Dict[str, Any]:
    category = str(item.get("category", "")).strip()
    state_family = str(item.get("state_family", "")).strip()
    last_exit_code = item.get("last_exit_code")
    launchctl_ok = bool(item.get("launchctl_ok"))
    state = str(item.get("state", "")).strip()
    if state_family == "running":
        return {"needs_attention": False, "severity": "none", "reason": ""}
    if not launchctl_ok:
        return {"needs_attention": True, "severity": "critical", "reason": "launchctl_unavailable"}
    if category == "continuous" and state_family in {"crashed", "attention"}:
        reason = "continuous_process_not_running"
        if last_exit_code not in {None, 0}:
            reason = "continuous_process_crashed"
        elif state == "spawn scheduled":
            reason = "continuous_process_spawn_scheduled"
        return {"needs_attention": True, "severity": "critical", "reason": reason}
    if last_exit_code not in {None, 0}:
        severity = "high" if category == "continuous" else "medium"
        reason = "scheduled_job_last_run_failed" if category == "scheduled" else "continuous_process_crashed"
        return {"needs_attention": True, "severity": severity, "reason": reason}
    return {"needs_attention": False, "severity": "none", "reason": ""}


def build_runtime_jobs_registry() -> Dict[str, Any]:
    items: List[Dict[str, Any]] = []
    if LAUNCH_AGENTS_ROOT.exists():
        for path in sorted(LAUNCH_AGENTS_ROOT.glob("*.plist")):
            payload = _read_plist(path)
            label = str(payload.get("Label", "")).strip()
            if not label or not label.startswith(OPENCLAW_LAUNCHD_PREFIXES):
                continue
            keep_alive = bool(payload.get("KeepAlive"))
            start_interval = int(payload.get("StartInterval", 0) or 0)
            start_calendar = payload.get("StartCalendarInterval")
            run_at_load = bool(payload.get("RunAtLoad"))
            category = "continuous" if keep_alive else "scheduled"
            if category == "scheduled" and not any([start_interval, start_calendar, run_at_load]):
                continue
            launch_status = _launchctl_status(label)
            trigger = _runtime_trigger_summary(payload, category)
            runtime = _runtime_status_summary(category, launch_status)
            doctor_attention = _runtime_job_doctor_attention(
                {
                    "category": category,
                    "state_family": runtime.get("state_family", ""),
                    "last_exit_code": launch_status.get("last_exit_code"),
                    "launchctl_ok": launch_status.get("ok"),
                    "state": launch_status.get("state", ""),
                }
            )
            arguments = [str(arg).strip() for arg in (payload.get("ProgramArguments", []) or []) if str(arg).strip()]
            items.append(
                {
                    "label": label,
                    "name": _runtime_job_name(label, payload),
                    "category": category,
                    "description": _runtime_job_description(label, payload),
                    "trigger_summary": trigger.get("trigger_summary", ""),
                    "trigger_sort_value": trigger.get("trigger_sort_value", ""),
                    "schedule_kind": trigger.get("schedule_kind", ""),
                    "run_at_load": run_at_load,
                    "keep_alive": keep_alive,
                    "start_interval_seconds": start_interval,
                    "program_arguments": arguments,
                    "program_summary": _program_summary(arguments),
                    "state": str(launch_status.get("state", "")).strip() or "unknown",
                    "state_family": runtime.get("state_family", "idle"),
                    "status_text": runtime.get("status_text", "unknown"),
                    "is_running": bool(int(launch_status.get("pid", 0) or 0) > 0 or str(launch_status.get("state", "")).strip() == "running"),
                    "pid": int(launch_status.get("pid", 0) or 0),
                    "runs": int(launch_status.get("runs", 0) or 0),
                    "last_exit_code": launch_status.get("last_exit_code"),
                    "active_count": int(launch_status.get("active_count", 0) or 0),
                    "launchctl_ok": bool(launch_status.get("ok")),
                    "launchctl_excerpt": str(launch_status.get("raw_excerpt", "")).strip(),
                    "doctor_attention": bool(doctor_attention.get("needs_attention")),
                    "doctor_attention_reason": str(doctor_attention.get("reason", "")).strip(),
                    "doctor_attention_severity": str(doctor_attention.get("severity", "")).strip(),
                    "source_plist": str(path),
                    "stdout_path": str(payload.get("StandardOutPath", "")).strip(),
                    "stderr_path": str(payload.get("StandardErrorPath", "")).strip(),
                }
            )

    scheduled_items = [item for item in items if item.get("category") == "scheduled"]
    continuous_items = [item for item in items if item.get("category") == "continuous"]
    scheduled_items.sort(key=lambda item: (0 if item.get("is_running") else 1, str(item.get("trigger_sort_value", "")), str(item.get("label", ""))))
    continuous_items.sort(key=lambda item: (0 if item.get("is_running") else 1, str(item.get("label", ""))))
    incidents = [
        {
            "label": str(item.get("label", "")).strip(),
            "name": str(item.get("name", "")).strip(),
            "category": str(item.get("category", "")).strip(),
            "description": str(item.get("description", "")).strip(),
            "trigger_summary": str(item.get("trigger_summary", "")).strip(),
            "state": str(item.get("state", "")).strip(),
            "state_family": str(item.get("state_family", "")).strip(),
            "status_text": str(item.get("status_text", "")).strip(),
            "last_exit_code": item.get("last_exit_code"),
            "runs": int(item.get("runs", 0) or 0),
            "doctor_attention_reason": str(item.get("doctor_attention_reason", "")).strip(),
            "doctor_attention_severity": str(item.get("doctor_attention_severity", "")).strip(),
            "program_summary": str(item.get("program_summary", "")).strip(),
            "program_arguments": list(item.get("program_arguments", []) or []),
            "source_plist": str(item.get("source_plist", "")).strip(),
            "stdout_path": str(item.get("stdout_path", "")).strip(),
            "stderr_path": str(item.get("stderr_path", "")).strip(),
            "launchctl_excerpt": str(item.get("launchctl_excerpt", "")).strip(),
        }
        for item in (scheduled_items + continuous_items)
        if item.get("doctor_attention")
    ]
    incidents.sort(
        key=lambda item: (
            0 if str(item.get("doctor_attention_severity", "")).strip() == "critical" else 1,
            str(item.get("category", "")),
            str(item.get("label", "")),
        )
    )
    registry = {
        "generated_at": _utc_now_iso(),
        "items": scheduled_items + continuous_items,
        "scheduled_items": scheduled_items,
        "continuous_items": continuous_items,
        "incidents": incidents,
        "summary": {
            "scheduled_total": len(scheduled_items),
            "scheduled_running_total": sum(1 for item in scheduled_items if item.get("is_running")),
            "continuous_total": len(continuous_items),
            "continuous_running_total": sum(1 for item in continuous_items if item.get("is_running")),
            "incident_total": len(incidents),
            "critical_incident_total": sum(1 for item in incidents if item.get("doctor_attention_severity") == "critical"),
        },
    }
    registry["path"] = _write_json(RUNTIME_JOBS_REGISTRY_PATH, registry)
    _write_json(PROCESS_INCIDENTS_PATH, {"generated_at": registry["generated_at"], "items": incidents})
    return registry


def _load_task_state(task_id: str) -> Dict[str, Any]:
    """
    中文注解：
    - 功能：实现 `_load_task_state` 对应的处理逻辑。
    - 角色：属于本模块中的内部辅助逻辑；私有函数通常服务同文件主流程，公共函数通常作为跨模块入口或能力接口。
    - 调用关系：建议结合本文件的模块说明、调用方以及同名相关辅助函数一起阅读。
    """
    return _read_json(AUTONOMY_TASKS_ROOT / task_id / "state.json", {})


def _load_task_contract(task_id: str) -> Dict[str, Any]:
    """
    中文注解：
    - 功能：实现 `_load_task_contract` 对应的处理逻辑。
    - 角色：属于本模块中的内部辅助逻辑；私有函数通常服务同文件主流程，公共函数通常作为跨模块入口或能力接口。
    - 调用关系：建议结合本文件的模块说明、调用方以及同名相关辅助函数一起阅读。
    """
    return _read_json(AUTONOMY_TASKS_ROOT / task_id / "contract.json", {})


def _conversation_links_for_task(task_id: str, canonical_task_id: str) -> List[Dict[str, Any]]:
    """
    中文注解：
    - 功能：实现 `_conversation_links_for_task` 对应的处理逻辑。
    - 角色：属于本模块中的内部辅助逻辑；私有函数通常服务同文件主流程，公共函数通常作为跨模块入口或能力接口。
    - 调用关系：建议结合本文件的模块说明、调用方以及同名相关辅助函数一起阅读。
    """
    rows: List[Dict[str, Any]] = []
    if not LINKS_ROOT.exists():
        return rows
    for path in sorted(LINKS_ROOT.glob("*.json")):
        payload = _read_json(path, {})
        if not payload:
            continue
        if canonical_task_id not in {
            str(payload.get("task_id", "")).strip(),
            str(payload.get("lineage_root_task_id", "")).strip(),
            str(payload.get("predecessor_task_id", "")).strip(),
        } and task_id not in {
            str(payload.get("task_id", "")).strip(),
            str(payload.get("lineage_root_task_id", "")).strip(),
            str(payload.get("predecessor_task_id", "")).strip(),
        }:
            continue
        rows.append(
            {
                "path": str(path),
                "provider": payload.get("provider", ""),
                "conversation_id": payload.get("conversation_id", ""),
                "task_id": payload.get("task_id", ""),
                "lineage_root_task_id": payload.get("lineage_root_task_id", ""),
                "session_key": payload.get("session_key", ""),
                "updated_at": payload.get("updated_at", ""),
            }
        )
    return rows


def _normalized_blocked_runtime_state(state: Dict[str, Any]) -> Dict[str, Any]:
    metadata = (state.get("metadata", {}) or {}) if isinstance(state, dict) else {}
    if str(state.get("status", "")).strip() != "blocked":
        return {}
    inferred = classify_blocked_runtime_state(
        next_action=str(state.get("next_action", "")).strip(),
        blockers=[str(item).strip() for item in (state.get("blockers", []) or []) if str(item).strip()],
        governance_attention={},
    )
    blocked = dict(metadata.get("blocked_runtime_state", {}) or {})
    normalized = inferred if str(inferred.get("category", "")).strip() else blocked
    if not str(normalized.get("attention_reason", "")).strip():
        normalized["attention_reason"] = str(state.get("next_action", "")).strip() or "blocked_without_runtime_metadata"
    return normalized


def _doctor_priority_for_entry(entry: Dict[str, Any]) -> Dict[str, Any]:
    blocked = (entry.get("blocked_runtime_state", {}) or {}) if isinstance(entry, dict) else {}
    category = str(blocked.get("category", "")).strip() or "unknown"
    reason = str(entry.get("reason", "")).strip()
    status = str(entry.get("status", "")).strip()
    idle_seconds = float(entry.get("idle_seconds", 0) or 0)
    base_scores = {
        "project_crawler_remediation": 100,
        "approval_or_contract": 95,
        "authorized_session": 90,
        "human_checkpoint": 88,
        "runtime_or_contract_fix": 82,
        "runtime_failure": 80,
        "targeted_fix": 72,
        "necessity_proof": 66,
        "relay_attach": 60,
        "session_binding": 42,
        "unknown": 50,
    }
    score = int(base_scores.get(category, 50))
    if reason == "terminal_failure_requires_takeover":
        score = max(score, 110)
    elif reason == "latest_user_goal_mismatch_with_bound_task":
        score = max(score, 105)
    elif status == "failed":
        score = max(score, 108)
    elif status == "blocked" and category in {"project_crawler_remediation", "approval_or_contract"}:
        score += 6
    if idle_seconds >= 3600:
        score += 8
    elif idle_seconds >= 900:
        score += 4
    bucket = "low"
    if score >= 95:
        bucket = "critical"
    elif score >= 80:
        bucket = "high"
    elif score >= 60:
        bucket = "medium"
    priority_reason = category
    if category == "unknown" and reason:
        if reason == "latest_user_goal_mismatch_with_bound_task":
            priority_reason = "goal_mismatch"
        elif reason == "terminal_failure_requires_takeover":
            priority_reason = "terminal_failure"
        else:
            priority_reason = reason
    return {
        "priority_score": score,
        "priority_bucket": bucket,
        "priority_reason": priority_reason or "unknown",
    }


def build_task_registry(*, stale_after_seconds: int = 300, escalation_after_seconds: int = 900) -> Dict[str, Any]:
    """
    中文注解：
    - 功能：实现 `build_task_registry` 对应的处理逻辑。
    - 角色：属于本模块中的对外可见逻辑；私有函数通常服务同文件主流程，公共函数通常作为跨模块入口或能力接口。
    - 调用关系：建议结合本文件的模块说明、调用方以及同名相关辅助函数一起阅读。
    """
    tasks: List[Dict[str, Any]] = []
    waiting: List[Dict[str, Any]] = []
    doctor_queue: List[Dict[str, Any]] = []
    alerts: List[Dict[str, Any]] = []
    seen_canonical: set[str] = set()

    if AUTONOMY_TASKS_ROOT.exists():
        for task_root in sorted(AUTONOMY_TASKS_ROOT.iterdir()):
            if not task_root.is_dir():
                continue
            task_id = task_root.name
            state = _load_task_state(task_id)
            contract = _load_task_contract(task_id)
            canonical = resolve_canonical_active_task(task_id)
            canonical_task_id = str(canonical.get("canonical_task_id", task_id)).strip() or task_id
            evidence = build_progress_evidence(canonical_task_id, stale_after_seconds=stale_after_seconds)
            links = _conversation_links_for_task(task_id, canonical_task_id)
            blocked_runtime_state = _normalized_blocked_runtime_state(state)
            entry = {
                "task_id": task_id,
                "canonical_task_id": canonical_task_id,
                "lineage_root_task_id": canonical.get("lineage_root_task_id", task_id),
                "goal": contract.get("user_goal", ""),
                "status": state.get("status", "unknown"),
                "current_stage": state.get("current_stage", ""),
                "next_action": state.get("next_action", ""),
                "blocked_runtime_state": blocked_runtime_state,
                "last_progress_at": state.get("last_progress_at", ""),
                "last_update_at": state.get("last_update_at", ""),
                "progress_state": evidence.get("progress_state", "unknown"),
                "needs_intervention": bool(evidence.get("needs_intervention")),
                "idle_seconds": evidence.get("idle_seconds", 0),
                "active_execution": state.get("metadata", {}).get("active_execution", {}) or {},
                "waiting_external": state.get("metadata", {}).get("waiting_external", {}) or {},
                "run_liveness": evidence.get("run_liveness", {}),
                "goal_conformance": evidence.get("goal_conformance", {}),
                "conversation_links": links,
                "canonical": canonical,
            }
            tasks.append(entry)
            if canonical_task_id == task_id and canonical_task_id not in seen_canonical:
                seen_canonical.add(canonical_task_id)
            if entry["waiting_external"]:
                waiting.append(
                    {
                        "task_id": task_id,
                        "canonical_task_id": canonical_task_id,
                        "current_stage": entry["current_stage"],
                        "next_action": entry["next_action"],
                        "waiting_external": entry["waiting_external"],
                        "run_liveness": entry["run_liveness"],
                    }
                )
            if entry["needs_intervention"]:
                doctor_entry = {
                    "task_id": task_id,
                    "canonical_task_id": canonical_task_id,
                    "reason": evidence.get("reason", "unknown"),
                    "progress_state": entry["progress_state"],
                    "status": entry["status"],
                    "current_stage": entry["current_stage"],
                    "next_action": entry["next_action"],
                    "blocked_runtime_state": entry.get("blocked_runtime_state", {}) or {},
                    "idle_seconds": entry["idle_seconds"],
                    "goal_conformance": entry.get("goal_conformance", {}),
                }
                doctor_entry.update(_doctor_priority_for_entry(doctor_entry))
                doctor_queue.append(doctor_entry)
                if entry["idle_seconds"] >= escalation_after_seconds:
                    alerts.append({**doctor_entry, "severity": "high", "escalated": True})

    doctor_queue.sort(
        key=lambda item: (
            -int(item.get("priority_score", 0) or 0),
            -float(item.get("idle_seconds", 0) or 0),
            str(item.get("task_id", "")),
        )
    )
    alerts.sort(
        key=lambda item: (
            -int(item.get("priority_score", 0) or 0),
            -float(item.get("idle_seconds", 0) or 0),
            str(item.get("task_id", "")),
        )
    )

    task_registry = {
        "generated_at": _utc_now_iso(),
        "items": tasks,
        "canonical_active_tasks": sorted(seen_canonical),
    }
    waiting_registry = {"generated_at": task_registry["generated_at"], "items": waiting}
    doctor_queue_registry = {"generated_at": task_registry["generated_at"], "items": doctor_queue}
    alerts_registry = {"generated_at": task_registry["generated_at"], "items": alerts}
    _write_json(TASK_REGISTRY_PATH, task_registry)
    _write_json(WAITING_REGISTRY_PATH, waiting_registry)
    _write_json(DOCTOR_QUEUE_PATH, doctor_queue_registry)
    _write_json(ALERTS_PATH, alerts_registry)
    return {
        "task_registry": task_registry,
        "waiting_registry": waiting_registry,
        "doctor_queue": doctor_queue_registry,
        "alerts": alerts_registry,
    }


def build_conversation_registry(task_items: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    中文注解：
    - 功能：把当前会话绑定关系整理成 conversation-centric 注册表。
    - 设计意图：让面板能直接回答“哪个聊天窗口当前在聊哪个任务”，而不是只看任务列表。
    """
    task_by_id: Dict[str, Dict[str, Any]] = {}
    canonical_by_id: Dict[str, Dict[str, Any]] = {}
    for item in task_items:
        task_id = str(item.get("task_id", "")).strip()
        canonical_task_id = str(item.get("canonical_task_id", "")).strip() or task_id
        if task_id:
            task_by_id[task_id] = item
        if canonical_task_id:
            existing = canonical_by_id.get(canonical_task_id)
            if existing is None or str(item.get("task_id", "")).strip() == canonical_task_id:
                canonical_by_id[canonical_task_id] = item

    rows: List[Dict[str, Any]] = []
    provider_counts: Dict[str, int] = {}
    if LINKS_ROOT.exists():
        for path in sorted(LINKS_ROOT.glob("*.json")):
            payload = _read_json(path, {})
            if not payload:
                continue
            provider = str(payload.get("provider", "")).strip()
            conversation_id = str(payload.get("conversation_id", "")).strip()
            if not provider or not conversation_id:
                continue
            bound_task_id = str(payload.get("task_id", "")).strip()
            canonical = resolve_canonical_active_task(bound_task_id) if bound_task_id else {}
            canonical_task_id = str(canonical.get("canonical_task_id", "")).strip() or bound_task_id
            task_entry = (
                task_by_id.get(canonical_task_id)
                or task_by_id.get(bound_task_id)
                or canonical_by_id.get(canonical_task_id)
                or {}
            )
            conversation_type = str(payload.get("conversation_type", "")).strip() or "direct"
            last_goal = str(payload.get("last_goal", "")).strip() or str(payload.get("goal", "")).strip()
            row = {
                "provider": provider,
                "conversation_id": conversation_id,
                "conversation_type": conversation_type,
                "conversation_label": f"{provider}/{conversation_id}",
                "session_key": str(payload.get("session_key", "")).strip(),
                "bound_task_id": bound_task_id,
                "canonical_task_id": canonical_task_id,
                "lineage_root_task_id": str(payload.get("lineage_root_task_id", "")).strip()
                or str(((task_entry.get("canonical", {}) or {}).get("lineage_root_task_id", ""))).strip(),
                "status": str(task_entry.get("status", "unknown")).strip() or "unknown",
                "current_stage": str(task_entry.get("current_stage", "")).strip(),
                "next_action": str(task_entry.get("next_action", "")).strip(),
                "progress_state": str(task_entry.get("progress_state", "unknown")).strip() or "unknown",
                "needs_intervention": bool(task_entry.get("needs_intervention")),
                "goal": str(task_entry.get("goal", "")).strip(),
                "last_goal": last_goal,
                "updated_at": str(payload.get("updated_at", "")).strip(),
                "link_path": str(path),
                "selector_hint": f"[task:{canonical_task_id}] " if canonical_task_id else "",
            }
            rows.append(row)
            provider_counts[provider] = provider_counts.get(provider, 0) + 1

    rows.sort(key=lambda item: (str(item.get("provider", "")), str(item.get("conversation_id", ""))))
    registry = {
        "generated_at": _utc_now_iso(),
        "items": rows,
        "provider_counts": dict(sorted(provider_counts.items(), key=lambda kv: kv[0])),
    }
    _write_json(CONVERSATION_REGISTRY_PATH, registry)
    return registry


def _alias_entry(alias_registry: Dict[str, Any], task_id: str) -> Dict[str, Any]:
    if not task_id:
        return {}
    return dict(((alias_registry.get("by_task_id", {}) or {}).get(task_id, {}) or {}))


def _decorate_task_views_with_aliases(task_views: Dict[str, Any], alias_registry: Dict[str, Any]) -> None:
    for item in task_views.get("task_registry", {}).get("items", []) or []:
        task_entry = _alias_entry(alias_registry, str(item.get("task_id", "")).strip())
        canonical_entry = _alias_entry(alias_registry, str(item.get("canonical_task_id", "")).strip())
        item["task_alias"] = str(task_entry.get("task_alias", "")).strip()
        item["task_group_alias"] = str(task_entry.get("task_group_alias", "")).strip()
        item["canonical_task_alias"] = str(canonical_entry.get("task_alias", "")).strip()
        item["canonical_task_group_alias"] = str(canonical_entry.get("task_group_alias", "")).strip()

    for collection_key in ("waiting_registry", "doctor_queue"):
        for item in task_views.get(collection_key, {}).get("items", []) or []:
            task_entry = _alias_entry(alias_registry, str(item.get("task_id", "")).strip())
            canonical_entry = _alias_entry(alias_registry, str(item.get("canonical_task_id", "")).strip())
            item["task_alias"] = str(task_entry.get("task_alias", "")).strip()
            item["task_group_alias"] = str(task_entry.get("task_group_alias", "")).strip()
            item["canonical_task_alias"] = str(canonical_entry.get("task_alias", "")).strip()
            item["canonical_task_group_alias"] = str(canonical_entry.get("task_group_alias", "")).strip()


def _decorate_conversation_registry_with_aliases(conversation_registry: Dict[str, Any], alias_registry: Dict[str, Any]) -> None:
    for item in conversation_registry.get("items", []) or []:
        bound_entry = _alias_entry(alias_registry, str(item.get("bound_task_id", "")).strip())
        canonical_entry = _alias_entry(alias_registry, str(item.get("canonical_task_id", "")).strip())
        canonical_group_alias = str(canonical_entry.get("task_group_alias", "")).strip()
        canonical_task_alias = str(canonical_entry.get("task_alias", "")).strip()
        item["bound_task_alias"] = str(bound_entry.get("task_alias", "")).strip()
        item["bound_task_group_alias"] = str(bound_entry.get("task_group_alias", "")).strip()
        item["canonical_task_alias"] = canonical_task_alias
        item["canonical_task_group_alias"] = canonical_group_alias
        item["selector_hint"] = f"[task:{canonical_group_alias or canonical_task_alias or item.get('canonical_task_id', '')}] " if (canonical_group_alias or canonical_task_alias or item.get("canonical_task_id")) else ""
        item["exact_selector_hint"] = f"[task:{canonical_task_alias or item.get('canonical_task_id', '')}] " if (canonical_task_alias or item.get("canonical_task_id")) else ""


def _refresh_task_items_after_alias_and_canonical_fix(task_views: Dict[str, Any]) -> None:
    task_index = {
        str(item.get("task_id", "")).strip(): item
        for item in task_views.get("task_registry", {}).get("items", []) or []
        if str(item.get("task_id", "")).strip()
    }
    for collection_key in ("waiting_registry", "doctor_queue"):
        for item in task_views.get(collection_key, {}).get("items", []) or []:
            task_id = str(item.get("task_id", "")).strip()
            source = task_index.get(task_id, {}) or {}
            if source:
                item["canonical_task_id"] = source.get("canonical_task_id", item.get("canonical_task_id", ""))
                item["canonical_task_alias"] = source.get("canonical_task_alias", item.get("canonical_task_alias", ""))
                item["canonical_task_group_alias"] = source.get("canonical_task_group_alias", item.get("canonical_task_group_alias", ""))


def build_crawler_remediation_queue(crawler_capability_profile: Dict[str, Any]) -> Dict[str, Any]:
    """
    中文注解：
    - 功能：把 crawler capability profile 里的优先修复建议整理成 control plane 可消费的项目级待办队列。
    - 设计意图：让系统不只知道“哪里弱”，还知道“下一步应该先修什么”，供医生、监督器和后续调度链共享。
    """
    items: List[Dict[str, Any]] = []
    for index, action in enumerate(crawler_capability_profile.get("priority_actions", []) or [], start=1):
        items.append(
            {
                "id": f"crawler-remediation-{index}",
                "priority": action.get("priority", "medium"),
                "action": action.get("action", ""),
                "site": action.get("site", ""),
                "reason": action.get("reason", ""),
                "status": "pending",
            }
        )
    queue = {
        "generated_at": _utc_now_iso(),
        "items": items,
    }
    _write_json(CRAWLER_REMEDIATION_QUEUE_PATH, queue)
    return queue


def _load_crawler_remediation_execution() -> Dict[str, Any]:
    return _read_json(CRAWLER_REMEDIATION_EXECUTION_PATH, {"items": []}) or {"items": []}


def _load_crawler_remediation_scheduler_state() -> Dict[str, Any]:
    return _read_json(CRAWLER_REMEDIATION_SCHEDULER_STATE_PATH, {}) or {}


def _load_seller_bulk_scheduler_state() -> Dict[str, Any]:
    return _read_json(SELLER_BULK_SCHEDULER_STATE_PATH, {}) or {}


def _load_cross_market_arbitrage_scheduler_state() -> Dict[str, Any]:
    return _read_json(CROSS_MARKET_ARBITRAGE_SCHEDULER_STATE_PATH, {}) or {}


def _blocked_category_counts(task_items: List[Dict[str, Any]]) -> Dict[str, int]:
    counts: Dict[str, int] = {}
    for item in task_items:
        if item.get("status") != "blocked":
            continue
        category = str(((item.get("blocked_runtime_state", {}) or {}).get("category", ""))).strip() or "unknown"
        counts[category] = counts.get(category, 0) + 1
    return dict(sorted(counts.items(), key=lambda kv: (-kv[1], kv[0])))


def _load_doctor_last_run() -> Dict[str, Any]:
    return _read_json(DOCTOR_LAST_RUN_PATH, {}) or {}


def _build_doctor_incident_inbox(
    runtime_jobs_registry: Dict[str, Any],
    doctor_last_run: Dict[str, Any],
) -> Dict[str, Any]:
    doctor_root = DOCTOR_LAST_RUN_PATH.parent
    process_root = doctor_root / "process_incidents"
    task_root = doctor_root / "task_incidents"
    resolution_root = doctor_root / "resolutions"
    process_items: List[Dict[str, Any]] = []
    task_items: List[Dict[str, Any]] = []
    resolution_items: List[Dict[str, Any]] = []

    def _watch_status(task_id: str) -> Dict[str, Any]:
        raw = str(task_id or "").strip()
        if not raw:
            return {}
        state_path = AUTONOMY_TASKS_ROOT / raw / "state.json"
        payload = _read_json(state_path, {}) or {}
        if not isinstance(payload, dict):
            return {}
        return {
            "status": str(payload.get("status", "")).strip(),
            "current_stage": str(payload.get("current_stage", "")).strip(),
            "next_action": str(payload.get("next_action", "")).strip(),
        }

    def _append_active_incident(scope: str, payload: Dict[str, Any], path: Path) -> None:
        dispatch = payload.get("brain_dispatch", {}) or {}
        watch_task_id = str(dispatch.get("task_id", "")).strip()
        diagnosis = payload.get("diagnosis", {}) or {}
        reason = (
            str(diagnosis.get("reason", "")).strip()
            or str(payload.get("doctor_attention_reason", "")).strip()
            or str(payload.get("resolution_reason", "")).strip()
        )
        severity = (
            str(payload.get("doctor_attention_severity", "")).strip()
            or str(((payload.get("priority", {}) or {}).get("bucket", ""))).strip()
            or "unknown"
        )
        row = {
            "scope": scope,
            "generated_at": str(payload.get("generated_at", "")).strip(),
            "last_seen_at": str(payload.get("last_seen_at", "")).strip(),
            "subject_id": str(payload.get("label", "")).strip() or str(payload.get("watched_task_id", "")).strip(),
            "name": str(payload.get("name", "")).strip() or str(payload.get("watched_task_id", "")).strip(),
            "status": str(payload.get("status_text", "")).strip() or str(payload.get("status", "")).strip(),
            "current_stage": str(payload.get("current_stage", "")).strip(),
            "reason": reason,
            "severity": severity,
            "watch_task_id": watch_task_id,
            "watch_task_action": str(dispatch.get("task_action", "")).strip(),
            "watch_link_kind": str(dispatch.get("link_kind", "")).strip(),
            "watch_status": _watch_status(watch_task_id),
            "report_path": str(path),
        }
        if scope == "process_incident":
            process_items.append(row)
        else:
            task_items.append(row)

    if process_root.exists():
        for path in sorted(process_root.glob("*.json")):
            payload = _read_json(path, {}) or {}
            if not isinstance(payload, dict) or not payload.get("active"):
                continue
            _append_active_incident("process_incident", payload, path)

    seen_process_subjects = {str(item.get("subject_id", "")).strip() for item in process_items if str(item.get("subject_id", "")).strip()}
    for incident in runtime_jobs_registry.get("incidents", []) or []:
        subject_id = str(incident.get("label", "")).strip()
        if not subject_id or subject_id in seen_process_subjects:
            continue
        process_items.append(
            {
                "scope": "process_incident",
                "generated_at": str((doctor_last_run.get("checked_at") or doctor_last_run.get("started_at") or "")).strip(),
                "last_seen_at": str((doctor_last_run.get("checked_at") or doctor_last_run.get("started_at") or "")).strip(),
                "subject_id": subject_id,
                "name": str(incident.get("name", "")).strip() or subject_id,
                "status": str(incident.get("status_text", "")).strip() or str(incident.get("state", "")).strip(),
                "current_stage": "",
                "reason": str(incident.get("doctor_attention_reason", "")).strip(),
                "severity": str(incident.get("doctor_attention_severity", "")).strip() or "unknown",
                "watch_task_id": "",
                "watch_task_action": "",
                "watch_link_kind": "",
                "watch_status": {},
                "report_path": "",
            }
        )

    if task_root.exists():
        for path in sorted(task_root.glob("*.json")):
            payload = _read_json(path, {}) or {}
            if not isinstance(payload, dict) or not payload.get("active"):
                continue
            _append_active_incident("task_incident", payload, path)

    if resolution_root.exists():
        for path in sorted(resolution_root.glob("*.json")):
            payload = _read_json(path, {}) or {}
            if not isinstance(payload, dict):
                continue
            resolution_items.append(
                {
                    "written_at": str(payload.get("written_at", "")).strip(),
                    "scope": str(payload.get("scope", "")).strip() or "unknown",
                    "subject_id": str(payload.get("subject_id", "")).strip(),
                    "watch_task_id": str(payload.get("watch_task_id", "")).strip(),
                    "resolution_reason": str(payload.get("resolution_reason", "")).strip(),
                    "reusable_rule": str(payload.get("reusable_rule", "")).strip(),
                    "suggested_runtime_changes": list(payload.get("suggested_runtime_changes", []) or []),
                    "evolution_proposal_path": str(payload.get("evolution_proposal_path", "")).strip(),
                    "path": str(path),
                }
            )

    process_items.sort(key=lambda item: (str(item.get("severity", "")) != "critical", str(item.get("generated_at", ""))), reverse=False)
    task_items.sort(key=lambda item: (str(item.get("severity", "")) != "critical", str(item.get("generated_at", ""))), reverse=False)
    resolution_items.sort(key=lambda item: str(item.get("written_at", "")), reverse=True)
    active_items = sorted(
        [*process_items, *task_items],
        key=lambda item: (
            0 if str(item.get("severity", "")).strip() == "critical" else 1,
            str(item.get("generated_at", "")),
        ),
    )
    return {
        "generated_at": _utc_now_iso(),
        "summary": {
            "active_total": len(active_items),
            "process_total": len(process_items),
            "task_total": len(task_items),
            "with_ai_takeover_total": sum(1 for item in active_items if str(item.get("watch_task_id", "")).strip()),
            "resolutions_total": len(resolution_items),
        },
        "active_items": active_items,
        "process_items": process_items,
        "task_items": task_items,
        "resolution_items": resolution_items[:20],
    }


def _parse_iso(value: str) -> datetime | None:
    raw = str(value or "").strip()
    if not raw:
        return None
    try:
        return datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        return None


def _project_result_feedback_summary(
    memory_writeback_overview: Dict[str, Any],
    crawler_remediation_execution: Dict[str, Any],
    seller_bulk_scheduler_state: Dict[str, Any],
) -> Dict[str, Any]:
    now = datetime.now(timezone.utc)
    recent_items = memory_writeback_overview.get("recent_items", []) or []
    tracked = {
        "crawler_remediation_cycle": {
            "task_id": "project-crawler-remediation-cycle",
            "kind": "project_runtime_loop",
        },
        "seller_bulk_cycle": {
            "task_id": "project-neosgo-seller-bulk",
            "kind": "project_runtime_loop",
        },
    }
    for item in recent_items:
        task_id = str(item.get("task_id", "")).strip()
        last_entry = item.get("last_entry", {}) or {}
        source = str(last_entry.get("source", "")).strip()
        if source not in tracked:
            continue
        at = _parse_iso(last_entry.get("at"))
        age_seconds = int((now - at).total_seconds()) if at else None
        tracked[source].update(
            {
                "seen": True,
                "at": last_entry.get("at", ""),
                "age_seconds": age_seconds,
                "attention_required": bool(last_entry.get("attention_required")),
                "memory_reasons": list(last_entry.get("memory_reasons", []) or []),
                "task_id": task_id or tracked[source]["task_id"],
            }
        )
    remediation_items = crawler_remediation_execution.get("items", []) or []
    tracked["crawler_remediation_cycle"]["active_execution_total"] = sum(
        1
        for item in remediation_items
        if str(((item.get("task_state", {}) or {}).get("status", ""))).strip().lower() in {"running", "planning", "recovering", "blocked"}
    )
    tracked["seller_bulk_cycle"]["last_mode"] = str(seller_bulk_scheduler_state.get("last_mode", "")).strip()
    tracked["seller_bulk_cycle"]["last_batch_bias"] = str(seller_bulk_scheduler_state.get("last_batch_bias", "")).strip()
    tracked["seller_bulk_cycle"]["last_skip_reason"] = str(seller_bulk_scheduler_state.get("last_skip_reason", "")).strip()

    active_total = sum(1 for item in tracked.values() if item.get("seen"))
    recent_total = sum(1 for item in tracked.values() if item.get("seen") and (item.get("age_seconds") is None or item.get("age_seconds", 10**9) <= 6 * 3600))
    attention_total = sum(1 for item in tracked.values() if item.get("attention_required"))
    status = "thin"
    if recent_total >= 2:
        status = "strong"
    elif recent_total == 1:
        status = "partial"
    if attention_total > 0 and status == "strong":
        status = "watch"
    return {
        "status": status,
        "active_total": active_total,
        "recent_total": recent_total,
        "attention_total": attention_total,
        "loops": tracked,
    }


def _score_project_result_feedback(feedback: Dict[str, Any]) -> int:
    status = str(feedback.get("status", "")).strip().lower()
    base = {
        "strong": 100,
        "watch": 75,
        "partial": 55,
        "thin": 30,
    }.get(status, 40)
    recent_total = int(feedback.get("recent_total", 0) or 0)
    attention_total = int(feedback.get("attention_total", 0) or 0)
    score = base + min(10, recent_total * 3) - min(20, attention_total * 10)
    return max(0, min(100, score))


def _update_project_result_feedback_history(feedback: Dict[str, Any]) -> Dict[str, Any]:
    history = _read_json(PROJECT_RESULT_FEEDBACK_HISTORY_PATH, {"items": []}) or {"items": []}
    items = list(history.get("items", []) or [])
    current = {
        "at": _utc_now_iso(),
        "status": str(feedback.get("status", "")).strip() or "unknown",
        "score": _score_project_result_feedback(feedback),
        "recent_total": int(feedback.get("recent_total", 0) or 0),
        "attention_total": int(feedback.get("attention_total", 0) or 0),
    }
    items.append(current)
    items = items[-24:]
    history["items"] = items
    history["updated_at"] = current["at"]
    trend = "stable"
    delta = 0
    if len(items) >= 2:
        delta = int(items[-1].get("score", 0) or 0) - int(items[-2].get("score", 0) or 0)
        if delta >= 8:
            trend = "improving"
        elif delta <= -8:
            trend = "degrading"
    history["trend"] = {
        "direction": trend,
        "delta": delta,
        "latest_score": current["score"],
        "previous_score": int(items[-2].get("score", 0) or 0) if len(items) >= 2 else current["score"],
    }
    _write_json(PROJECT_RESULT_FEEDBACK_HISTORY_PATH, history)
    return history


def _project_repair_value_summary(system_summary: Dict[str, Any], project_result_feedback_history: Dict[str, Any]) -> Dict[str, Any]:
    blocked_targeted_fix_total = int(system_summary.get("blocked_targeted_fix_total", 0) or 0)
    blocked_total = int(system_summary.get("blocked_total", 0) or 0)
    recovery_efficiency_ratio = float(system_summary.get("recovery_efficiency_ratio", 0.0) or 0.0)
    feedback_score = int((project_result_feedback_history.get("trend", {}) or {}).get("latest_score", 0) or 0)
    feedback_trend = str((project_result_feedback_history.get("trend", {}) or {}).get("direction", "unknown")).strip() or "unknown"
    blocked_penalty = min(35, blocked_targeted_fix_total // 3) + min(15, blocked_total // 20)
    score = max(0, min(100, int(feedback_score * 0.45 + recovery_efficiency_ratio * 100 * 0.4 + 25 - blocked_penalty)))
    status = "weak"
    if score >= 75:
        status = "strong"
    elif score >= 50:
        status = "watch"
    return {
        "status": status,
        "score": score,
        "inputs": {
            "feedback_score": feedback_score,
            "feedback_trend": feedback_trend,
            "recovery_efficiency_ratio": recovery_efficiency_ratio,
            "blocked_targeted_fix_total": blocked_targeted_fix_total,
            "blocked_total": blocked_total,
        },
    }


def _update_project_repair_value_history(repair_value: Dict[str, Any]) -> Dict[str, Any]:
    history = _read_json(PROJECT_REPAIR_VALUE_HISTORY_PATH, {"items": []}) or {"items": []}
    items = list(history.get("items", []) or [])
    current = {
        "at": _utc_now_iso(),
        "status": str(repair_value.get("status", "")).strip() or "unknown",
        "score": int(repair_value.get("score", 0) or 0),
    }
    items.append(current)
    items = items[-24:]
    history["items"] = items
    history["updated_at"] = current["at"]
    trend = "stable"
    delta = 0
    if len(items) >= 2:
        delta = int(items[-1].get("score", 0) or 0) - int(items[-2].get("score", 0) or 0)
        if delta >= 8:
            trend = "improving"
        elif delta <= -8:
            trend = "degrading"
    history["trend"] = {
        "direction": trend,
        "delta": delta,
        "latest_score": current["score"],
        "previous_score": int(items[-2].get("score", 0) or 0) if len(items) >= 2 else current["score"],
    }
    _write_json(PROJECT_REPAIR_VALUE_HISTORY_PATH, history)
    return history


def _recommended_project_repair_actions(system_summary: Dict[str, Any]) -> List[Dict[str, Any]]:
    actions: List[Dict[str, Any]] = []
    project_repair_value_status = str(system_summary.get("project_repair_value_status", "")).strip().lower()
    project_repair_value_trend = str(system_summary.get("project_repair_value_trend", "")).strip().lower()
    top_blocked_category = str(system_summary.get("top_blocked_category", "")).strip()
    project_result_feedback_status = str(system_summary.get("project_result_feedback_status", "")).strip().lower()
    feedback_attention_total = int(system_summary.get("project_result_feedback_attention_total", 0) or 0)
    recovery_efficiency_ratio = float(system_summary.get("recovery_efficiency_ratio", 0) or 0)
    blocked_targeted_fix_total = int(system_summary.get("blocked_targeted_fix_total", 0) or 0)

    def _add_action(action_id: str, *, priority: str, action: str, reason: str, value: str) -> None:
        if any(item.get("id") == action_id for item in actions):
            return
        actions.append(
            {
                "id": action_id,
                "priority": priority,
                "action": action,
                "reason": reason,
                "value": value,
            }
        )

    if project_repair_value_status == "weak":
        _add_action(
            "repair-value-rebuild",
            priority="critical",
            action="concentrate_repair_capacity_on_high_value_paths",
            reason="project_repair_value_weak",
            value=f"score={int(system_summary.get('project_repair_value_score', 0) or 0)}",
        )
    elif project_repair_value_trend == "degrading":
        _add_action(
            "repair-value-watch",
            priority="high",
            action="watch_repair_value_trend_and_reduce_expansion_pressure",
            reason="project_repair_value_trend_degrading",
            value=project_repair_value_trend,
        )

    if top_blocked_category in {"targeted_fix", "runtime_failure", "runtime_or_contract_fix"} and blocked_targeted_fix_total > 0:
        _add_action(
            "targeted-fix-hotspot",
            priority="high",
            action="bias_repair_cycles_toward_targeted_fix_hotspots",
            reason="blocked_targeted_fix_pressure",
            value=str(blocked_targeted_fix_total),
        )
    elif top_blocked_category in {"project_crawler_remediation", "authorized_session", "human_checkpoint", "approval_or_contract"}:
        _add_action(
            "governance-unblock",
            priority="high",
            action="unblock_governance_gated_execution_paths",
            reason="top_blocked_category",
            value=top_blocked_category,
        )

    if project_result_feedback_status in {"thin", "partial"} or feedback_attention_total > 0:
        _add_action(
            "feedback-loop-rebuild",
            priority="high" if feedback_attention_total > 0 else "medium",
            action="rebuild_project_result_feedback_loop_health",
            reason="project_result_feedback_pressure",
            value=f"status={project_result_feedback_status},attention={feedback_attention_total}",
        )

    if recovery_efficiency_ratio < 0.3:
        _add_action(
            "recovery-efficiency-improve",
            priority="medium",
            action="reduce_cycle_spread_and_improve_recovery_efficiency",
            reason="recovery_efficiency_low",
            value=f"{recovery_efficiency_ratio:.4f}",
        )

    return actions[:6]


def build_control_plane(*, stale_after_seconds: int = 300, escalation_after_seconds: int = 900) -> Dict[str, Any]:
    """
    中文注解：
    - 功能：实现 `build_control_plane` 对应的处理逻辑。
    - 角色：属于本模块中的对外可见逻辑；私有函数通常服务同文件主流程，公共函数通常作为跨模块入口或能力接口。
    - 调用关系：建议结合本文件的模块说明、调用方以及同名相关辅助函数一起阅读。
    """
    process_registry = build_process_registry()
    runtime_jobs_registry = build_runtime_jobs_registry()
    task_retention = run_task_retention()
    archived_task_registry = load_archived_task_registry()
    crawler_capability_profile = build_crawler_capability_profile()
    memory_writeback_overview = summarize_project_memory_writebacks()
    crawler_remediation_queue = build_crawler_remediation_queue(crawler_capability_profile)
    crawler_remediation_plan = build_crawler_remediation_plan()
    crawler_remediation_execution = _load_crawler_remediation_execution()
    crawler_remediation_scheduler_state = _load_crawler_remediation_scheduler_state()
    seller_bulk_scheduler_state = _load_seller_bulk_scheduler_state()
    cross_market_arbitrage_scheduler_state = _load_cross_market_arbitrage_scheduler_state()
    doctor_last_run = _load_doctor_last_run()
    doctor_incident_inbox = _build_doctor_incident_inbox(runtime_jobs_registry, doctor_last_run)
    project_result_feedback = _project_result_feedback_summary(
        memory_writeback_overview,
        crawler_remediation_execution,
        seller_bulk_scheduler_state,
    )
    project_result_feedback_history = _update_project_result_feedback_history(project_result_feedback)
    task_views = build_task_registry(
        stale_after_seconds=stale_after_seconds,
        escalation_after_seconds=escalation_after_seconds,
    )
    task_items = task_views["task_registry"].get("items", []) or []
    task_alias_registry = build_task_alias_registry(task_items)
    _decorate_task_views_with_aliases(task_views, task_alias_registry)
    _refresh_task_items_after_alias_and_canonical_fix(task_views)
    _write_json(TASK_REGISTRY_PATH, task_views["task_registry"])
    _write_json(WAITING_REGISTRY_PATH, task_views["waiting_registry"])
    _write_json(DOCTOR_QUEUE_PATH, task_views["doctor_queue"])
    conversation_registry = build_conversation_registry(task_items)
    _decorate_conversation_registry_with_aliases(conversation_registry, task_alias_registry)
    _write_json(CONVERSATION_REGISTRY_PATH, conversation_registry)
    blocked_category_counts = _blocked_category_counts(task_items)
    top_blocked_category = next(iter(blocked_category_counts), "")
    doctor_cycle_stats = (doctor_last_run.get("doctor_cycle_stats", {}) or {}) if isinstance(doctor_last_run, dict) else {}
    doctor_strategy = (doctor_last_run.get("doctor_strategy", {}) or {}) if isinstance(doctor_last_run, dict) else {}
    processed_total = int(doctor_cycle_stats.get("processed_total", 0) or 0)
    skipped_total = int(doctor_cycle_stats.get("skipped_total", 0) or 0)
    attempted_total = processed_total + skipped_total
    recovery_efficiency_ratio = round((processed_total / attempted_total), 4) if attempted_total > 0 else 0.0
    blocked_total = sum(1 for item in task_items if item.get("status") == "blocked")
    blocked_targeted_fix_total = blocked_category_counts.get("targeted_fix", 0)
    repair_value_inputs = {
        "blocked_total": blocked_total,
        "blocked_targeted_fix_total": blocked_targeted_fix_total,
        "recovery_efficiency_ratio": recovery_efficiency_ratio,
    }
    repair_value = _project_repair_value_summary(repair_value_inputs, project_result_feedback_history)
    project_repair_value_history = _update_project_repair_value_history(repair_value)
    doctor_coverage = _build_doctor_coverage_bundle()
    snapshot = {
        "generated_at": _utc_now_iso(),
        "process_registry_path": process_registry.get("path"),
        "runtime_jobs_registry_path": str(RUNTIME_JOBS_REGISTRY_PATH),
        "crawler_capability_profile_path": str(CRAWLER_CAPABILITY_PROFILE_PATH),
        "crawler_remediation_queue_path": str(CRAWLER_REMEDIATION_QUEUE_PATH),
        "crawler_remediation_plan_path": str(CRAWLER_REMEDIATION_PLAN_PATH),
        "crawler_remediation_execution_path": str(CRAWLER_REMEDIATION_EXECUTION_PATH),
        "task_registry_path": str(TASK_REGISTRY_PATH),
        "task_alias_registry_path": str(TASK_ALIAS_REGISTRY_PATH),
        "archived_task_registry_path": str(ARCHIVED_TASK_REGISTRY_PATH),
        "task_retention_last_run_path": str(TASK_RETENTION_LAST_RUN_PATH),
        "conversation_registry_path": str(CONVERSATION_REGISTRY_PATH),
        "waiting_registry_path": str(WAITING_REGISTRY_PATH),
        "doctor_queue_path": str(DOCTOR_QUEUE_PATH),
        "alerts_path": str(ALERTS_PATH),
        "doctor_coverage": doctor_coverage,
        "summary": {
            "processes_running": sum(1 for item in process_registry.get("items", []) if item.get("state") == "running"),
            "processes_total": len(process_registry.get("items", [])),
            "scheduled_jobs_total": runtime_jobs_registry.get("summary", {}).get("scheduled_total", 0),
            "scheduled_jobs_running_total": runtime_jobs_registry.get("summary", {}).get("scheduled_running_total", 0),
            "continuous_jobs_total": runtime_jobs_registry.get("summary", {}).get("continuous_total", 0),
            "continuous_jobs_running_total": runtime_jobs_registry.get("summary", {}).get("continuous_running_total", 0),
            "process_incident_total": runtime_jobs_registry.get("summary", {}).get("incident_total", 0),
            "critical_process_incident_total": runtime_jobs_registry.get("summary", {}).get("critical_incident_total", 0),
            "doctor_active_incident_total": (doctor_incident_inbox.get("summary", {}) or {}).get("active_total", 0),
            "doctor_process_incident_total": (doctor_incident_inbox.get("summary", {}) or {}).get("process_total", 0),
            "doctor_task_incident_total": (doctor_incident_inbox.get("summary", {}) or {}).get("task_total", 0),
            "doctor_ai_takeover_total": (doctor_incident_inbox.get("summary", {}) or {}).get("with_ai_takeover_total", 0),
            "doctor_resolution_total": (doctor_incident_inbox.get("summary", {}) or {}).get("resolutions_total", 0),
            "crawler_sites_total": crawler_capability_profile.get("summary", {}).get("sites_total", 0),
            "crawler_sites_ready": crawler_capability_profile.get("summary", {}).get("sites_production_ready", 0),
            "crawler_sites_governed_ready": crawler_capability_profile.get("summary", {}).get("sites_governed_ready", 0),
            "crawler_sites_authorized_session_ready": crawler_capability_profile.get("summary", {}).get("sites_authorized_session_ready", 0),
            "crawler_sites_with_evidence_drift": crawler_capability_profile.get("summary", {}).get("sites_with_evidence_drift", 0),
            "crawler_width_score": crawler_capability_profile.get("summary", {}).get("width_score", 0),
            "crawler_governed_width_score": crawler_capability_profile.get("summary", {}).get("governed_width_score", 0),
            "crawler_evidence_alignment_score": crawler_capability_profile.get("summary", {}).get("evidence_alignment_score", 0),
            "crawler_breadth_score": crawler_capability_profile.get("summary", {}).get("breadth_score", 0),
            "crawler_depth_score": crawler_capability_profile.get("summary", {}).get("depth_score", 0),
            "crawler_stability_score": crawler_capability_profile.get("summary", {}).get("stability_score", 0),
            "crawler_trend_direction": crawler_capability_profile.get("trend", {}).get("direction", "unknown"),
            "crawler_feedback_coverage_status": crawler_capability_profile.get("feedback", {}).get("coverage_status", "unknown"),
            "crawler_remediation_total": len(crawler_remediation_queue.get("items", [])),
            "crawler_remediation_plan_total": len(crawler_remediation_plan.get("items", [])),
            "crawler_remediation_execution_total": len(crawler_remediation_execution.get("items", [])),
            "crawler_remediation_last_mode": crawler_remediation_scheduler_state.get("last_mode", ""),
            "seller_bulk_last_mode": seller_bulk_scheduler_state.get("last_mode", ""),
            "cross_market_arbitrage_last_mode": cross_market_arbitrage_scheduler_state.get("last_mode", ""),
            "memory_writeback_tasks_total": memory_writeback_overview.get("tasks_total", 0),
            "project_result_feedback_status": project_result_feedback.get("status", "unknown"),
            "project_result_feedback_recent_total": project_result_feedback.get("recent_total", 0),
            "project_result_feedback_attention_total": project_result_feedback.get("attention_total", 0),
            "project_result_feedback_trend": ((project_result_feedback_history.get("trend", {}) or {}).get("direction", "unknown")),
            "project_result_feedback_score": ((project_result_feedback_history.get("trend", {}) or {}).get("latest_score", 0)),
            "doctor_priority_focus": str(doctor_strategy.get("priority_focus", "")).strip() or "unknown",
            "doctor_repair_mode": str(doctor_strategy.get("repair_mode", "")).strip() or "unknown",
            "doctor_processed_total": processed_total,
            "doctor_skipped_total": skipped_total,
            "doctor_single_authority": bool(doctor_coverage.get("single_doctor_rule")),
            "doctor_registered_integrations_total": len(doctor_coverage.get("registered_integrations", []) or []),
            "recovery_efficiency_ratio": recovery_efficiency_ratio,
            "project_repair_value_status": repair_value.get("status", "unknown"),
            "project_repair_value_trend": ((project_repair_value_history.get("trend", {}) or {}).get("direction", "unknown")),
            "project_repair_value_score": ((project_repair_value_history.get("trend", {}) or {}).get("latest_score", 0)),
            "tasks_total": len(task_items),
            "task_groups_total": len(task_alias_registry.get("items", []) or []),
            "archived_task_lineages_total": len(archived_task_registry.get("items", []) or []),
            "task_retention_archived_total": int(task_retention.get("archived_total", 0) or 0),
            "task_retention_candidates_total": int(task_retention.get("candidates_total", 0) or 0),
            "conversation_bindings_total": len(conversation_registry.get("items", []) or []),
            "blocked_total": blocked_total,
            "blocked_project_crawler_remediation_total": blocked_category_counts.get("project_crawler_remediation", 0),
            "blocked_approval_or_contract_total": blocked_category_counts.get("approval_or_contract", 0),
            "blocked_authorized_session_total": blocked_category_counts.get("authorized_session", 0),
            "blocked_human_checkpoint_total": blocked_category_counts.get("human_checkpoint", 0),
            "blocked_targeted_fix_total": blocked_targeted_fix_total,
            "blocked_categories": blocked_category_counts,
            "top_blocked_category": top_blocked_category,
            "waiting_total": len(task_views["waiting_registry"].get("items", [])),
            "doctor_queue_total": len(task_views["doctor_queue"].get("items", [])),
            "alerts_total": len(task_views["alerts"].get("items", [])),
        },
    }
    project_scheduler_policy = build_project_scheduler_policy(
        crawler_profile=crawler_capability_profile,
        remediation_execution=crawler_remediation_execution,
        system_summary=snapshot.get("summary", {}) or {},
        project_result_feedback=project_result_feedback,
    )
    project_repair_recommendations = _recommended_project_repair_actions(snapshot.get("summary", {}) or {})
    snapshot["project_scheduler_policy"] = project_scheduler_policy
    snapshot["project_repair_recommendations"] = project_repair_recommendations
    snapshot["doctor_incident_inbox"] = doctor_incident_inbox
    snapshot["scheduler_states"] = {
        "crawler_remediation": crawler_remediation_scheduler_state,
        "seller_bulk": seller_bulk_scheduler_state,
        "cross_market_arbitrage": cross_market_arbitrage_scheduler_state,
    }
    snapshot["task_retention"] = task_retention
    snapshot["archived_task_registry_overview"] = {
        "generated_at": str(archived_task_registry.get("generated_at", "")).strip(),
        "items_total": len(archived_task_registry.get("items", []) or []),
    }
    dashboard_info: Dict[str, Any]
    try:
        dashboard_path = build_task_dashboard(
            system_snapshot=snapshot,
            runtime_jobs_registry=runtime_jobs_registry,
            task_registry=task_views["task_registry"],
            task_alias_registry=task_alias_registry,
            conversation_registry=conversation_registry,
            waiting_registry=task_views["waiting_registry"],
            doctor_queue=task_views["doctor_queue"],
            doctor_incident_inbox=doctor_incident_inbox,
            task_retention=task_retention,
            archived_task_registry=archived_task_registry,
        )
        dashboard_info = {"ok": True, "path": dashboard_path}
    except Exception as exc:
        dashboard_info = {"ok": False, "error": str(exc)}
    snapshot["task_board_dashboard"] = dashboard_info
    snapshot["path"] = _write_json(SYSTEM_SNAPSHOT_PATH, snapshot)
    return {
        "process_registry": process_registry,
        "runtime_jobs_registry": runtime_jobs_registry,
        "task_retention": task_retention,
        "archived_task_registry": archived_task_registry,
        "crawler_capability_profile": crawler_capability_profile,
        "memory_writeback_overview": memory_writeback_overview,
        "project_result_feedback": project_result_feedback,
        "project_result_feedback_history": project_result_feedback_history,
        "project_repair_value": repair_value,
        "project_repair_value_history": project_repair_value_history,
        "project_repair_recommendations": project_repair_recommendations,
        "crawler_remediation_queue": crawler_remediation_queue,
        "crawler_remediation_plan": crawler_remediation_plan,
        "crawler_remediation_execution": crawler_remediation_execution,
        "crawler_remediation_scheduler_state": crawler_remediation_scheduler_state,
        "seller_bulk_scheduler_state": seller_bulk_scheduler_state,
        "cross_market_arbitrage_scheduler_state": cross_market_arbitrage_scheduler_state,
        "doctor_last_run": doctor_last_run,
        "doctor_incident_inbox": doctor_incident_inbox,
        "project_scheduler_policy": project_scheduler_policy,
        "task_alias_registry": task_alias_registry,
        "conversation_registry": conversation_registry,
        **task_views,
        "system_snapshot": snapshot,
    }


def main() -> int:
    """
    中文注解：
    - 功能：实现 `main` 对应的处理逻辑。
    - 角色：属于本模块中的对外可见逻辑；私有函数通常服务同文件主流程，公共函数通常作为跨模块入口或能力接口。
    - 调用关系：建议结合本文件的模块说明、调用方以及同名相关辅助函数一起阅读。
    """
    import argparse

    parser = argparse.ArgumentParser(description="Build the unified control plane snapshot for JinClaw")
    parser.add_argument("--stale-after-seconds", type=int, default=300)
    parser.add_argument("--escalation-after-seconds", type=int, default=900)
    args = parser.parse_args()
    print(
        json.dumps(
            build_control_plane(
                stale_after_seconds=args.stale_after_seconds,
                escalation_after_seconds=args.escalation_after_seconds,
            ),
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
