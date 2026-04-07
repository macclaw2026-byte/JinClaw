#!/usr/bin/env python3

"""
中文说明：
- 文件路径：`tools/openmoss/ops/openclaw_selfheal.py`
- 文件作用：负责运维脚本中与 `openclaw_selfheal` 相关的诊断、启动或修复逻辑。
- 顶层函数：utc_now_iso、run_cmd、read_json、write_json、parse_json_output、capture_diagnostics、classify_issues、classify_warnings、write_snapshot、restart_gateway、main。
- 顶层类：无顶层类。
- 阅读建议：先看模块说明，再按函数/类 docstring 顺着主流程理解调用关系。
"""
from __future__ import annotations

import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List


RUNTIME_ROOT = Path("/Users/mac_claw/.openclaw/workspace/tools/openmoss/runtime/selfheal")
SNAPSHOT_ROOT = RUNTIME_ROOT / "snapshots"
STATE_PATH = RUNTIME_ROOT / "state.json"
CONFIG_PATH = Path("/Users/mac_claw/.openclaw/openclaw.json")
GATEWAY_LOG_PATH = Path("/Users/mac_claw/.openclaw/logs/gateway.log")


def utc_now_iso() -> str:
    """
    中文注解：
    - 功能：实现 `utc_now_iso` 对应的处理逻辑。
    - 角色：属于本模块中的对外可见逻辑；私有函数通常服务同文件主流程，公共函数通常作为跨模块入口或能力接口。
    - 调用关系：建议结合本文件的模块说明、调用方以及同名相关辅助函数一起阅读。
    """
    return datetime.now(timezone.utc).isoformat()


def run_cmd(command: List[str], timeout: int = 20) -> Dict[str, Any]:
    """
    中文注解：
    - 功能：实现 `run_cmd` 对应的处理逻辑。
    - 角色：属于本模块中的对外可见逻辑；私有函数通常服务同文件主流程，公共函数通常作为跨模块入口或能力接口。
    - 调用关系：建议结合本文件的模块说明、调用方以及同名相关辅助函数一起阅读。
    """
    try:
        proc = subprocess.run(command, capture_output=True, text=True, check=False, timeout=timeout)
    except subprocess.TimeoutExpired as exc:
        return {
            "ok": False,
            "returncode": None,
            "stdout": (exc.stdout or "")[-2000:],
            "stderr": f"timeout after {timeout}s",
        }
    return {
        "ok": proc.returncode == 0,
        "returncode": proc.returncode,
        "stdout": (proc.stdout or "")[-20000:],
        "stderr": (proc.stderr or "")[-5000:],
    }


def read_json(path: Path, default: Any) -> Any:
    """
    中文注解：
    - 功能：实现 `read_json` 对应的处理逻辑。
    - 角色：属于本模块中的对外可见逻辑；私有函数通常服务同文件主流程，公共函数通常作为跨模块入口或能力接口。
    - 调用关系：建议结合本文件的模块说明、调用方以及同名相关辅助函数一起阅读。
    """
    if not path.exists():
        return default
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, payload: Any) -> None:
    """
    中文注解：
    - 功能：实现 `write_json` 对应的处理逻辑。
    - 角色：属于本模块中的对外可见逻辑；私有函数通常服务同文件主流程，公共函数通常作为跨模块入口或能力接口。
    - 调用关系：建议结合本文件的模块说明、调用方以及同名相关辅助函数一起阅读。
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def parse_json_output(result: Dict[str, Any]) -> Dict[str, Any]:
    """
    中文注解：
    - 功能：实现 `parse_json_output` 对应的处理逻辑。
    - 角色：属于本模块中的对外可见逻辑；私有函数通常服务同文件主流程，公共函数通常作为跨模块入口或能力接口。
    - 调用关系：建议结合本文件的模块说明、调用方以及同名相关辅助函数一起阅读。
    """
    if not result.get("ok"):
        return {}
    try:
        return json.loads(result.get("stdout") or "{}")
    except json.JSONDecodeError:
        return {}


def capture_diagnostics() -> Dict[str, Any]:
    """
    中文注解：
    - 功能：实现 `capture_diagnostics` 对应的处理逻辑。
    - 角色：属于本模块中的对外可见逻辑；私有函数通常服务同文件主流程，公共函数通常作为跨模块入口或能力接口。
    - 调用关系：建议结合本文件的模块说明、调用方以及同名相关辅助函数一起阅读。
    """
    status_result = run_cmd(["openclaw", "gateway", "status", "--json"])
    health_result = run_cmd(["openclaw", "gateway", "health", "--json"])
    status = parse_json_output(status_result)
    health = parse_json_output(health_result)
    service_runtime = status.get("service", {}).get("runtime", {})
    rpc = status.get("rpc", {})
    telegram = health.get("channels", {}).get("telegram", {})
    cfg = read_json(CONFIG_PATH, {})
    telegram_cfg = ((cfg or {}).get("channels") or {}).get("telegram") or {}
    probe = telegram.get("probe") or {}
    probe_bot = probe.get("bot") or {}
    gateway_log_tail = ""
    if GATEWAY_LOG_PATH.exists():
        gateway_log_tail = GATEWAY_LOG_PATH.read_text(encoding="utf-8", errors="replace")[-20000:]
    telegram_token_configured = bool((telegram_cfg.get("botToken") or "").strip()) or bool(
        (telegram_cfg.get("tokenFile") or "").strip()
    )
    telegram_provider_started_recently = "[telegram] [default] starting provider" in gateway_log_tail
    telegram_probe_ok = bool(probe.get("ok")) and bool(probe_bot.get("username"))
    telegram_effective_ok = bool(
        telegram.get("configured")
        and telegram_token_configured
        and telegram_probe_ok
        and telegram_provider_started_recently
    )
    return {
        "checked_at": utc_now_iso(),
        "status_result": status_result,
        "health_result": health_result,
        "status": status,
        "health": health,
        "service_running": service_runtime.get("status") == "running",
        "rpc_ok": bool(rpc.get("ok")),
        "telegram_configured": bool(telegram.get("configured")),
        "telegram_running": bool(telegram.get("running")),
        "telegram_token_source": telegram.get("tokenSource"),
        "telegram_token_configured": telegram_token_configured,
        "telegram_probe_ok": telegram_probe_ok,
        "telegram_provider_started_recently": telegram_provider_started_recently,
        "telegram_effective_ok": telegram_effective_ok,
    }


def classify_issues(snapshot: Dict[str, Any]) -> List[str]:
    """
    中文注解：
    - 功能：实现 `classify_issues` 对应的处理逻辑。
    - 角色：属于本模块中的对外可见逻辑；私有函数通常服务同文件主流程，公共函数通常作为跨模块入口或能力接口。
    - 调用关系：建议结合本文件的模块说明、调用方以及同名相关辅助函数一起阅读。
    """
    issues: List[str] = []
    if not snapshot.get("service_running"):
        issues.append("gateway_service_not_running")
    if not snapshot.get("rpc_ok"):
        issues.append("gateway_rpc_unhealthy")
    if not snapshot.get("status_result", {}).get("ok"):
        issues.append("gateway_status_command_failed")
    if not snapshot.get("health_result", {}).get("ok"):
        issues.append("gateway_health_command_failed")
    return issues


def classify_warnings(snapshot: Dict[str, Any]) -> List[str]:
    """
    中文注解：
    - 功能：实现 `classify_warnings` 对应的处理逻辑。
    - 角色：属于本模块中的对外可见逻辑；私有函数通常服务同文件主流程，公共函数通常作为跨模块入口或能力接口。
    - 调用关系：建议结合本文件的模块说明、调用方以及同名相关辅助函数一起阅读。
    """
    warnings: List[str] = []
    if snapshot.get("telegram_effective_ok") and (
        not snapshot.get("telegram_running") or snapshot.get("telegram_token_source") == "none"
    ):
        warnings.append("telegram_health_snapshot_mismatch")
        return warnings
    if snapshot.get("telegram_configured") and not snapshot.get("telegram_running"):
        warnings.append("telegram_configured_but_not_running")
    if snapshot.get("telegram_token_source") == "none" and snapshot.get("telegram_configured"):
        warnings.append("telegram_token_source_none")
    return warnings


def write_snapshot(snapshot: Dict[str, Any]) -> str:
    """
    中文注解：
    - 功能：实现 `write_snapshot` 对应的处理逻辑。
    - 角色：属于本模块中的对外可见逻辑；私有函数通常服务同文件主流程，公共函数通常作为跨模块入口或能力接口。
    - 调用关系：建议结合本文件的模块说明、调用方以及同名相关辅助函数一起阅读。
    """
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    path = SNAPSHOT_ROOT / f"{stamp}.json"
    write_json(path, snapshot)
    return str(path)


def restart_gateway() -> Dict[str, Any]:
    """
    中文注解：
    - 功能：实现 `restart_gateway` 对应的处理逻辑。
    - 角色：属于本模块中的对外可见逻辑；私有函数通常服务同文件主流程，公共函数通常作为跨模块入口或能力接口。
    - 调用关系：建议结合本文件的模块说明、调用方以及同名相关辅助函数一起阅读。
    """
    return run_cmd(["openclaw", "gateway", "restart"], timeout=30)


def main() -> int:
    """
    中文注解：
    - 功能：实现 `main` 对应的处理逻辑。
    - 角色：属于本模块中的对外可见逻辑；私有函数通常服务同文件主流程，公共函数通常作为跨模块入口或能力接口。
    - 调用关系：建议结合本文件的模块说明、调用方以及同名相关辅助函数一起阅读。
    """
    snapshot = capture_diagnostics()
    issues = classify_issues(snapshot)
    warnings = classify_warnings(snapshot)
    snapshot["issues"] = issues
    snapshot["warnings"] = warnings
    snapshot["snapshot_path"] = write_snapshot(snapshot)

    state = read_json(
        STATE_PATH,
        {
            "last_check_at": "",
            "last_snapshot_path": "",
            "last_status": "unknown",
            "restart_count": 0,
            "last_restart_at": "",
            "last_restart_reason": "",
            "last_restart_result": {},
            "consecutive_failures": 0,
            "last_warnings": [],
        },
    )
    state["last_check_at"] = snapshot["checked_at"]
    state["last_snapshot_path"] = snapshot["snapshot_path"]
    state["last_warnings"] = warnings

    if issues:
        state["last_status"] = "restart_triggered"
        state["consecutive_failures"] = int(state.get("consecutive_failures", 0)) + 1
        restart_result = restart_gateway()
        state["restart_count"] = int(state.get("restart_count", 0)) + 1
        state["last_restart_at"] = utc_now_iso()
        state["last_restart_reason"] = ", ".join(issues)
        state["last_restart_result"] = restart_result
        snapshot["restart_result"] = restart_result
        write_json(Path(snapshot["snapshot_path"]), snapshot)
    else:
        state["last_status"] = "healthy"
        state["consecutive_failures"] = 0

    write_json(STATE_PATH, state)
    print(json.dumps({"snapshot": snapshot, "state": state}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
