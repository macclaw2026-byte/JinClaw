#!/usr/bin/env python3

"""
中文说明：
- 文件路径：`tools/openmoss/autonomy/verifier_registry.py`
- 文件作用：负责任务验证器注册与校验执行。
- 顶层函数：verify_not_configured、verify_file_exists、verify_text_contains、verify_json_field_equals、_resolve_field、_load_task_state_payload、verify_task_state_metadata_equals、verify_task_state_metadata_nonempty、verify_command_exit_zero、verify_all、run_verifier。
- 顶层类：无顶层类。
- 阅读建议：先看模块说明，再按函数/类 docstring 顺着主流程理解调用关系。
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict


TASKS_ROOT = Path("/Users/mac_claw/.openclaw/workspace/tools/openmoss/runtime/autonomy/tasks")
CONTROL_CENTER_DIR = Path("/Users/mac_claw/.openclaw/workspace/tools/openmoss/control_center")
if str(CONTROL_CENTER_DIR) not in sys.path:
    sys.path.insert(0, str(CONTROL_CENTER_DIR))

from progress_evidence import build_progress_evidence


def verify_not_configured(spec: Dict[str, Any]) -> Dict[str, Any]:
    """
    中文注解：
    - 功能：实现 `verify_not_configured` 对应的处理逻辑。
    - 角色：属于本模块中的对外可见逻辑；私有函数通常服务同文件主流程，公共函数通常作为跨模块入口或能力接口。
    - 调用关系：建议结合本文件的模块说明、调用方以及同名相关辅助函数一起阅读。
    """
    return {
        "ok": False,
        "status": "not_configured",
        "reason": "no verifier configured",
    }


def verify_file_exists(spec: Dict[str, Any]) -> Dict[str, Any]:
    """
    中文注解：
    - 功能：实现 `verify_file_exists` 对应的处理逻辑。
    - 角色：属于本模块中的对外可见逻辑；私有函数通常服务同文件主流程，公共函数通常作为跨模块入口或能力接口。
    - 调用关系：建议结合本文件的模块说明、调用方以及同名相关辅助函数一起阅读。
    """
    path = Path(str(spec.get("path", ""))).expanduser()
    return {
        "ok": path.exists(),
        "status": "ok" if path.exists() else "missing",
        "path": str(path),
    }


def verify_text_contains(spec: Dict[str, Any]) -> Dict[str, Any]:
    """
    中文注解：
    - 功能：实现 `verify_text_contains` 对应的处理逻辑。
    - 角色：属于本模块中的对外可见逻辑；私有函数通常服务同文件主流程，公共函数通常作为跨模块入口或能力接口。
    - 调用关系：建议结合本文件的模块说明、调用方以及同名相关辅助函数一起阅读。
    """
    path = Path(str(spec.get("path", ""))).expanduser()
    needle = str(spec.get("contains", ""))
    if not path.exists():
        return {"ok": False, "status": "missing", "path": str(path)}
    text = path.read_text(encoding="utf-8")
    return {
        "ok": needle in text,
        "status": "ok" if needle in text else "not_found",
        "path": str(path),
        "needle": needle,
    }


def verify_json_field_equals(spec: Dict[str, Any]) -> Dict[str, Any]:
    """
    中文注解：
    - 功能：实现 `verify_json_field_equals` 对应的处理逻辑。
    - 角色：属于本模块中的对外可见逻辑；私有函数通常服务同文件主流程，公共函数通常作为跨模块入口或能力接口。
    - 调用关系：建议结合本文件的模块说明、调用方以及同名相关辅助函数一起阅读。
    """
    path = Path(str(spec.get("path", ""))).expanduser()
    field = str(spec.get("field", ""))
    expected = spec.get("equals")
    if not path.exists():
        return {"ok": False, "status": "missing", "path": str(path)}
    payload = json.loads(path.read_text(encoding="utf-8"))
    current = payload
    for part in [p for p in field.split(".") if p]:
        if not isinstance(current, dict) or part not in current:
            return {"ok": False, "status": "field_missing", "path": str(path), "field": field}
        current = current[part]
    return {
        "ok": current == expected,
        "status": "ok" if current == expected else "mismatch",
        "path": str(path),
        "field": field,
        "current": current,
        "expected": expected,
    }


def _resolve_field(payload: Dict[str, Any], field: str) -> tuple[bool, Any]:
    """
    中文注解：
    - 功能：实现 `_resolve_field` 对应的处理逻辑。
    - 角色：属于本模块中的内部辅助逻辑；私有函数通常服务同文件主流程，公共函数通常作为跨模块入口或能力接口。
    - 调用关系：建议结合本文件的模块说明、调用方以及同名相关辅助函数一起阅读。
    """
    parts = [p for p in field.split(".") if p]
    candidates = [payload]
    metadata = payload.get("metadata")
    if isinstance(metadata, dict):
        candidates.append(metadata)
    for candidate in candidates:
        current: Any = candidate
        found = True
        for part in parts:
            if not isinstance(current, dict) or part not in current:
                found = False
                break
            current = current[part]
        if found:
            return True, current
    return False, None


def _load_task_state_payload(task_id: str) -> tuple[Path, Dict[str, Any] | None]:
    """
    中文注解：
    - 功能：实现 `_load_task_state_payload` 对应的处理逻辑。
    - 角色：属于本模块中的内部辅助逻辑；私有函数通常服务同文件主流程，公共函数通常作为跨模块入口或能力接口。
    - 调用关系：建议结合本文件的模块说明、调用方以及同名相关辅助函数一起阅读。
    """
    path = TASKS_ROOT / task_id / "state.json"
    if not path.exists():
        return path, None
    return path, json.loads(path.read_text(encoding="utf-8"))


def verify_task_state_metadata_equals(spec: Dict[str, Any]) -> Dict[str, Any]:
    """
    中文注解：
    - 功能：实现 `verify_task_state_metadata_equals` 对应的处理逻辑。
    - 角色：属于本模块中的对外可见逻辑；私有函数通常服务同文件主流程，公共函数通常作为跨模块入口或能力接口。
    - 调用关系：建议结合本文件的模块说明、调用方以及同名相关辅助函数一起阅读。
    """
    task_id = str(spec.get("task_id", "")).strip()
    field = str(spec.get("field", "")).strip()
    expected = spec.get("equals")
    path, payload = _load_task_state_payload(task_id)
    if payload is None:
        return {"ok": False, "status": "task_state_missing", "task_id": task_id, "path": str(path)}
    found, current = _resolve_field(payload, field)
    if not found:
        return {"ok": False, "status": "field_missing", "task_id": task_id, "path": str(path), "field": field}
    return {
        "ok": current == expected,
        "status": "ok" if current == expected else "mismatch",
        "task_id": task_id,
        "path": str(path),
        "field": field,
        "current": current,
        "expected": expected,
    }


def verify_task_state_metadata_nonempty(spec: Dict[str, Any]) -> Dict[str, Any]:
    """
    中文注解：
    - 功能：实现 `verify_task_state_metadata_nonempty` 对应的处理逻辑。
    - 角色：属于本模块中的对外可见逻辑；私有函数通常服务同文件主流程，公共函数通常作为跨模块入口或能力接口。
    - 调用关系：建议结合本文件的模块说明、调用方以及同名相关辅助函数一起阅读。
    """
    task_id = str(spec.get("task_id", "")).strip()
    field = str(spec.get("field", "")).strip()
    path, payload = _load_task_state_payload(task_id)
    if payload is None:
        return {"ok": False, "status": "task_state_missing", "task_id": task_id, "path": str(path)}
    found, current = _resolve_field(payload, field)
    if not found:
        return {"ok": False, "status": "field_missing", "task_id": task_id, "path": str(path), "field": field}
    if current is None:
        is_nonempty = False
    elif isinstance(current, str):
        is_nonempty = current.strip() != ""
    elif isinstance(current, (list, tuple, set, dict)):
        is_nonempty = len(current) > 0
    else:
        is_nonempty = True
    return {
        "ok": bool(is_nonempty),
        "status": "ok" if is_nonempty else "empty",
        "task_id": task_id,
        "path": str(path),
        "field": field,
        "current": current,
    }


def verify_command_exit_zero(spec: Dict[str, Any]) -> Dict[str, Any]:
    """
    中文注解：
    - 功能：实现 `verify_command_exit_zero` 对应的处理逻辑。
    - 角色：属于本模块中的对外可见逻辑；私有函数通常服务同文件主流程，公共函数通常作为跨模块入口或能力接口。
    - 调用关系：建议结合本文件的模块说明、调用方以及同名相关辅助函数一起阅读。
    """
    command = spec.get("command") or []
    if not isinstance(command, list) or not command:
        return {"ok": False, "status": "invalid_command"}
    timeout = int(spec.get("timeout_seconds", 30))
    completed = subprocess.run(command, capture_output=True, text=True, check=False, timeout=timeout)
    return {
        "ok": completed.returncode == 0,
        "status": "ok" if completed.returncode == 0 else "command_failed",
        "command": command,
        "returncode": completed.returncode,
        "stdout": completed.stdout[-1000:],
        "stderr": completed.stderr[-1000:],
    }


def verify_task_milestones_complete(spec: Dict[str, Any]) -> Dict[str, Any]:
    """
    中文注解：
    - 功能：验证任务的必需 milestones 是否都已完成。
    - 说明：milestones 来自 contract.metadata.control_center.task_milestones，进度来自 state.metadata.milestone_progress。
    """
    task_id = str(spec.get("task_id", "")).strip()
    contract_path = TASKS_ROOT / task_id / "contract.json"
    state_path = TASKS_ROOT / task_id / "state.json"
    if not contract_path.exists() or not state_path.exists():
        return {"ok": False, "status": "task_artifact_missing", "task_id": task_id}
    contract = json.loads(contract_path.read_text(encoding="utf-8"))
    state = json.loads(state_path.read_text(encoding="utf-8"))
    milestones = (contract.get("metadata", {}) or {}).get("control_center", {}).get("task_milestones", []) or []
    progress = (state.get("metadata", {}) or {}).get("milestone_progress", {}) or {}
    missing = []
    for item in milestones:
        if not isinstance(item, dict) or item.get("required", True) is False:
            continue
        stage_name = str(item.get("stage", "")).strip()
        if stage_name in {"verify", "learn"}:
            continue
        milestone_id = str(item.get("id", "")).strip()
        if not milestone_id:
            continue
        if (progress.get(milestone_id, {}) or {}).get("status") != "completed":
            missing.append(milestone_id)
    return {
        "ok": not missing,
        "status": "ok" if not missing else "milestones_incomplete",
        "task_id": task_id,
        "missing_milestones": missing,
    }


def verify_task_liveness_ok(spec: Dict[str, Any]) -> Dict[str, Any]:
    """
    中文注解：
    - 功能：验证任务当前不存在明显的假等待、假忙或停滞。
    """
    task_id = str(spec.get("task_id", "")).strip()
    stale_after_seconds = int(spec.get("stale_after_seconds", 300) or 300)
    evidence = build_progress_evidence(task_id, stale_after_seconds=stale_after_seconds)
    bad_states = {
        "waiting_external_without_execution",
        "stalled_waiting_external",
        "idle_without_execution",
        "blocked",
        "stalled_verification",
    }
    progress_state = str(evidence.get("progress_state", "")).strip()
    ok = progress_state not in bad_states
    return {
        "ok": ok,
        "status": "ok" if ok else "liveness_violation",
        "task_id": task_id,
        "progress_state": progress_state,
        "reason": evidence.get("reason", ""),
    }


def verify_task_conformance_ok(spec: Dict[str, Any]) -> Dict[str, Any]:
    """
    中文注解：
    - 功能：验证任务实际状态是否仍然符合其阶段顺序与严格推进约束。
    """
    task_id = str(spec.get("task_id", "")).strip()
    contract_path = TASKS_ROOT / task_id / "contract.json"
    state_path = TASKS_ROOT / task_id / "state.json"
    if not contract_path.exists() or not state_path.exists():
        return {"ok": False, "status": "task_artifact_missing", "task_id": task_id}
    contract = json.loads(contract_path.read_text(encoding="utf-8"))
    state = json.loads(state_path.read_text(encoding="utf-8"))
    strict = bool((contract.get("metadata", {}) or {}).get("control_center", {}).get("strict_continuation_required"))
    order = list(state.get("stage_order", []) or [])
    stages = state.get("stages", {}) or {}
    violations = []
    completed_seen = False
    for stage_name in order:
        stage_status = str((stages.get(stage_name, {}) or {}).get("status", "")).strip()
        if stage_status == "completed":
            completed_seen = True
            continue
        if completed_seen and stage_status in {"running", "pending", "blocked", "failed"}:
            # 阶段顺序允许前面 completed、后面未完成；这里只记录越级完成的异常情况。
            continue
    if strict:
        milestones = (contract.get("metadata", {}) or {}).get("control_center", {}).get("task_milestones", []) or []
        progress = (state.get("metadata", {}) or {}).get("milestone_progress", {}) or {}
        execute_required = [
            item for item in milestones
            if isinstance(item, dict) and str(item.get("stage", "")).strip() == "execute" and item.get("required", True) is not False
        ]
        incomplete_execute = [
            str(item.get("id", "")).strip()
            for item in execute_required
            if (progress.get(str(item.get("id", "")).strip(), {}) or {}).get("status") != "completed"
        ]
        execute_status = str((stages.get("execute", {}) or {}).get("status", "")).strip()
        if execute_status == "completed" and incomplete_execute:
            violations.append("execute_completed_before_required_milestones")
    return {
        "ok": not violations,
        "status": "ok" if not violations else "conformance_violation",
        "task_id": task_id,
        "violations": violations,
    }


def verify_crawler_report_complete(spec: Dict[str, Any]) -> Dict[str, Any]:
    """
    中文注解：
    - 功能：验证 crawler 任务是否真的产出了完整的结构化测试报告，并覆盖请求中的站点/工具。
    """
    task_id = str(spec.get("task_id", "")).strip()
    contract_path = TASKS_ROOT / task_id / "contract.json"
    state_path = TASKS_ROOT / task_id / "state.json"
    if not contract_path.exists() or not state_path.exists():
        return {"ok": False, "status": "task_artifact_missing", "task_id": task_id}
    contract = json.loads(contract_path.read_text(encoding="utf-8"))
    state = json.loads(state_path.read_text(encoding="utf-8"))
    crawler = (contract.get("metadata", {}) or {}).get("control_center", {}).get("crawler", {}) or {}
    execution = (state.get("metadata", {}) or {}).get("crawler_execution", {}) or {}
    report_raw = str(execution.get("report_json_path", "")).strip()
    if not report_raw:
        return {"ok": False, "status": "crawler_report_missing", "task_id": task_id, "path": ""}
    report_path = Path(report_raw).expanduser()
    if not report_path.exists() or not report_path.is_file():
        return {"ok": False, "status": "crawler_report_missing", "task_id": task_id, "path": str(report_path)}
    payload = json.loads(report_path.read_text(encoding="utf-8"))
    required_sites = [str(item).strip() for item in crawler.get("requested_sites", []) if str(item).strip()]
    required_tools = [str(item).strip() for item in crawler.get("requested_tools", []) if str(item).strip()]
    if not required_sites:
        required_sites = [str(item).strip() for item in payload.get("required_sites", []) if str(item).strip()]
    if not required_tools:
        required_tools = [str(item).strip() for item in payload.get("required_tools", []) if str(item).strip()]
    site_rows = payload.get("sites", []) or []
    seen_sites = {str(item.get("site", "")).strip() for item in site_rows if str(item.get("site", "")).strip()}
    missing_sites = [site for site in required_sites if site not in seen_sites]
    tool_label_map = {
        "crawl4ai": {"crawl4ai-cli"},
        "direct_http": {"direct-http-html"},
        "curl_cffi": {"curl-cffi"},
        "playwright": {"playwright"},
        "playwright_stealth": {"playwright-stealth"},
        "scrapy_cffi": {"scrapy-cffi"},
        "agent_browser": {"local-agent-browser-cli"},
        "crawlee": {"crawlee"},
    }
    missing_tools_by_site: Dict[str, Any] = {}
    for site in site_rows:
        site_id = str(site.get("site", "")).strip()
        labels = {str(row.get("tool", "")).strip() for row in site.get("tool_results", []) or [] if str(row.get("tool", "")).strip()}
        missing = []
        for tool in required_tools:
            accepted = tool_label_map.get(tool, {tool})
            if labels.isdisjoint(accepted):
                missing.append(tool)
        if missing:
            missing_tools_by_site[site_id] = missing
    ok = not missing_sites and not missing_tools_by_site
    return {
        "ok": ok,
        "status": "ok" if ok else "crawler_report_incomplete",
        "task_id": task_id,
        "path": str(report_path),
        "missing_sites": missing_sites,
        "missing_tools_by_site": missing_tools_by_site,
    }


def verify_crawler_retro_complete(spec: Dict[str, Any]) -> Dict[str, Any]:
    """
    中文注解：
    - 功能：验证 crawler 的复盘、演化与学习沉淀是否已经真正完成。
    """
    task_id = str(spec.get("task_id", "")).strip()
    state_path = TASKS_ROOT / task_id / "state.json"
    if not state_path.exists():
        return {"ok": False, "status": "task_state_missing", "task_id": task_id}
    state = json.loads(state_path.read_text(encoding="utf-8"))
    execution = (state.get("metadata", {}) or {}).get("crawler_execution", {}) or {}
    retro_raw = str(execution.get("retro_json_path", "")).strip()
    evolution_raw = str(execution.get("evolution_json_path", "")).strip()
    learning_raw = str(execution.get("learning_store_path", "")).strip()
    missing = []
    resolved = []
    for raw in [retro_raw, evolution_raw, learning_raw]:
        if not raw:
            missing.append(raw)
            continue
        path = Path(raw).expanduser()
        if not path.exists() or not path.is_file():
            missing.append(str(path))
            continue
        resolved.append(path)
    if missing:
        return {"ok": False, "status": "crawler_retro_missing", "task_id": task_id, "missing_paths": missing}
    retro_path, evolution_path, learning_path = resolved
    retro = json.loads(retro_path.read_text(encoding="utf-8"))
    learning = json.loads(learning_path.read_text(encoding="utf-8"))
    best_tool_by_site = retro.get("best_tool_by_site", {}) or {}
    lessons = retro.get("lessons", []) or []
    task_seen = any(
        str(item.get("last_task_id", "")).strip() == task_id
        for item in (learning.get("sites", {}) or {}).values()
        if isinstance(item, dict)
    )
    ok = bool(best_tool_by_site) and bool(lessons) and task_seen
    return {
        "ok": ok,
        "status": "ok" if ok else "crawler_retro_incomplete",
        "task_id": task_id,
        "retro_path": str(retro_path),
        "evolution_path": str(evolution_path),
        "learning_path": str(learning_path),
        "best_tool_sites": sorted(best_tool_by_site.keys()),
        "lesson_count": len(lessons),
        "task_seen_in_learning": task_seen,
    }


def verify_all(spec: Dict[str, Any]) -> Dict[str, Any]:
    """
    中文注解：
    - 功能：实现 `verify_all` 对应的处理逻辑。
    - 角色：属于本模块中的对外可见逻辑；私有函数通常服务同文件主流程，公共函数通常作为跨模块入口或能力接口。
    - 调用关系：建议结合本文件的模块说明、调用方以及同名相关辅助函数一起阅读。
    """
    checks = spec.get("checks") or []
    if not isinstance(checks, list) or not checks:
        return {"ok": False, "status": "invalid_checks"}
    results = []
    all_ok = True
    for check in checks:
        if not isinstance(check, dict):
            results.append({"ok": False, "status": "invalid_check"})
            all_ok = False
            continue
        verifier_type = str(check.get("type") or "none")
        verifier = VERIFIERS.get(verifier_type, verify_not_configured)
        result = verifier(check)
        result["verifier_type"] = verifier_type
        results.append(result)
        if not result.get("ok"):
            all_ok = False
    return {
        "ok": all_ok,
        "status": "ok" if all_ok else "check_failed",
        "results": results,
    }


VERIFIERS = {
    "none": verify_not_configured,
    "file_exists": verify_file_exists,
    "text_contains": verify_text_contains,
    "json_field_equals": verify_json_field_equals,
    "task_state_metadata_equals": verify_task_state_metadata_equals,
    "task_state_metadata_nonempty": verify_task_state_metadata_nonempty,
    "task_milestones_complete": verify_task_milestones_complete,
    "task_liveness_ok": verify_task_liveness_ok,
    "task_conformance_ok": verify_task_conformance_ok,
    "crawler_report_complete": verify_crawler_report_complete,
    "crawler_retro_complete": verify_crawler_retro_complete,
    "command_exit_zero": verify_command_exit_zero,
    "all": verify_all,
}


def run_verifier(spec: Dict[str, Any]) -> Dict[str, Any]:
    """
    中文注解：
    - 功能：实现 `run_verifier` 对应的处理逻辑。
    - 角色：属于本模块中的对外可见逻辑；私有函数通常服务同文件主流程，公共函数通常作为跨模块入口或能力接口。
    - 调用关系：建议结合本文件的模块说明、调用方以及同名相关辅助函数一起阅读。
    """
    verifier_type = str(spec.get("type") or "none")
    verifier = VERIFIERS.get(verifier_type, verify_not_configured)
    result = verifier(spec)
    result["verifier_type"] = verifier_type
    return result
