#!/usr/bin/env python3

"""
中文说明：
- 文件路径：`tools/openmoss/control_center/browser_channel_recovery.py`
- 文件作用：负责控制中心中与 `browser_channel_recovery` 相关的编排、分析或决策逻辑。
- 顶层函数：_write_json、_resolve_openclaw_bin、_openclaw_browser_json、_open_relay_tab、list_relay_tabs、prune_relay_tabs、_url_matches_target、_select_best_matching_tab、load_gateway_token、browser_control_get、browser_control_post、_normalize_expected_domains、get_current_relay_context、recover_browser_channel、navigate_relay_to_url。
- 顶层类：无顶层类。
- 阅读建议：先看模块说明，再按函数/类 docstring 顺着主流程理解调用关系。
"""
from __future__ import annotations

import json
import shutil
import subprocess
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Dict, Iterable, List

from paths import BROWSER_CHANNELS_ROOT, OPENCLAW_ROOT


def _write_json(path: Path, payload: Dict[str, object]) -> None:
    """
    中文注解：
    - 功能：实现 `_write_json` 对应的处理逻辑。
    - 角色：属于本模块中的内部辅助逻辑；私有函数通常服务同文件主流程，公共函数通常作为跨模块入口或能力接口。
    - 调用关系：建议结合本文件的模块说明、调用方以及同名相关辅助函数一起阅读。
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _resolve_openclaw_bin() -> str:
    """
    中文注解：
    - 功能：实现 `_resolve_openclaw_bin` 对应的处理逻辑。
    - 角色：属于本模块中的内部辅助逻辑；私有函数通常服务同文件主流程，公共函数通常作为跨模块入口或能力接口。
    - 调用关系：建议结合本文件的模块说明、调用方以及同名相关辅助函数一起阅读。
    """
    return shutil.which("openclaw") or "/opt/homebrew/bin/openclaw"


def _openclaw_browser_json(*args: str, timeout: int = 20) -> Dict[str, object]:
    """
    中文注解：
    - 功能：实现 `_openclaw_browser_json` 对应的处理逻辑。
    - 角色：属于本模块中的内部辅助逻辑；私有函数通常服务同文件主流程，公共函数通常作为跨模块入口或能力接口。
    - 调用关系：建议结合本文件的模块说明、调用方以及同名相关辅助函数一起阅读。
    """
    proc = subprocess.run(
        [_resolve_openclaw_bin(), "browser", *args, "--json"],
        capture_output=True,
        text=True,
        check=False,
        timeout=timeout,
    )
    if proc.returncode != 0:
        raise RuntimeError(proc.stderr.strip() or proc.stdout.strip() or f"openclaw browser {' '.join(args)} failed")
    return json.loads(proc.stdout or "{}")


def _open_relay_tab(url: str, timeout: int = 20) -> Dict[str, object]:
    """
    中文注解：
    - 功能：实现 `_open_relay_tab` 对应的处理逻辑。
    - 角色：属于本模块中的内部辅助逻辑；私有函数通常服务同文件主流程，公共函数通常作为跨模块入口或能力接口。
    - 调用关系：建议结合本文件的模块说明、调用方以及同名相关辅助函数一起阅读。
    """
    return _openclaw_browser_json("open", "--browser-profile", "chrome-relay", url, timeout=timeout)


def list_relay_tabs(profile: str = "chrome-relay", timeout: int = 15) -> List[Dict[str, object]]:
    """
    中文注解：
    - 功能：实现 `list_relay_tabs` 对应的处理逻辑。
    - 角色：属于本模块中的对外可见逻辑；私有函数通常服务同文件主流程，公共函数通常作为跨模块入口或能力接口。
    - 调用关系：建议结合本文件的模块说明、调用方以及同名相关辅助函数一起阅读。
    """
    payload = _openclaw_browser_json("tabs", "--browser-profile", profile, timeout=timeout)
    tabs = payload.get("tabs", [])
    if not isinstance(tabs, list):
        return []
    return [tab for tab in tabs if isinstance(tab, dict)]


def prune_relay_tabs(
    task_id: str,
    *,
    keep_target_id: str = "",
    preferred_url: str = "",
    last_known_url: str = "",
    expected_domains: Iterable[str] | None = None,
    max_tabs: int = 1,
) -> Dict[str, object]:
    """
    中文注解：
    - 功能：实现 `prune_relay_tabs` 对应的处理逻辑。
    - 角色：属于本模块中的对外可见逻辑；私有函数通常服务同文件主流程，公共函数通常作为跨模块入口或能力接口。
    - 调用关系：建议结合本文件的模块说明、调用方以及同名相关辅助函数一起阅读。
    """
    expected = _normalize_expected_domains(expected_domains, last_known_url or preferred_url)
    tabs = list_relay_tabs("chrome-relay", timeout=15)
    relevant_tabs: List[Dict[str, object]] = []
    for tab in tabs:
        tab_url = str(tab.get("url", "")).strip().lower()
        if not expected or any(domain in tab_url for domain in expected):
            relevant_tabs.append(tab)
    if not relevant_tabs:
        result = {
            "task_id": task_id,
            "ok": True,
            "status": "no_matching_tabs_to_prune",
            "expected_domains": expected,
            "tabs_before": len(tabs),
            "relevant_tabs_before": 0,
            "tabs_after": len(tabs),
            "closed_target_ids": [],
        }
        _write_json(BROWSER_CHANNELS_ROOT / f"{task_id}.json", result)
        return result

    keep_ids: List[str] = []
    normalized_keep = str(keep_target_id or "").strip()
    if normalized_keep:
        keep_ids.append(normalized_keep)
    primary_tab = _select_best_matching_tab(
        relevant_tabs,
        preferred_url=preferred_url,
        last_known_url=last_known_url,
        expected_domains=expected,
    )
    primary_id = str(primary_tab.get("targetId", "")).strip()
    if primary_id and primary_id not in keep_ids:
        keep_ids.append(primary_id)
    keep_ids = [item for item in keep_ids if item][:max(1, int(max_tabs or 1))]

    closed_target_ids: List[str] = []
    close_errors: List[Dict[str, str]] = []
    for tab in relevant_tabs:
        target_id = str(tab.get("targetId", "")).strip()
        if not target_id or target_id in keep_ids:
            continue
        try:
            _openclaw_browser_json("close", "--browser-profile", "chrome-relay", target_id, timeout=15)
            closed_target_ids.append(target_id)
        except Exception as exc:  # pragma: no cover - best-effort cleanup
            close_errors.append({"target_id": target_id, "error": str(exc)})

    remaining_tabs = list_relay_tabs("chrome-relay", timeout=15)
    result = {
        "task_id": task_id,
        "ok": not close_errors,
        "status": "relay_tabs_pruned" if closed_target_ids else "relay_tabs_already_within_budget",
        "expected_domains": expected,
        "keep_target_ids": keep_ids,
        "tabs_before": len(tabs),
        "relevant_tabs_before": len(relevant_tabs),
        "tabs_after": len(remaining_tabs),
        "closed_target_ids": closed_target_ids,
        "close_errors": close_errors,
    }
    _write_json(BROWSER_CHANNELS_ROOT / f"{task_id}.json", result)
    return result


def _url_matches_target(current_url: str, target_url: str) -> bool:
    """
    中文注解：
    - 功能：实现 `_url_matches_target` 对应的处理逻辑。
    - 角色：属于本模块中的内部辅助逻辑；私有函数通常服务同文件主流程，公共函数通常作为跨模块入口或能力接口。
    - 调用关系：建议结合本文件的模块说明、调用方以及同名相关辅助函数一起阅读。
    """
    current = urllib.parse.urlparse((current_url or "").strip())
    target = urllib.parse.urlparse((target_url or "").strip())
    if not current.scheme or not current.netloc or not target.scheme or not target.netloc:
        return False
    if current.scheme != target.scheme or current.netloc != target.netloc:
        return False
    current_path = (current.path or "").rstrip("/") or "/"
    target_path = (target.path or "").rstrip("/") or "/"
    current_query = current.query or ""
    target_query = target.query or ""
    return current_path == target_path and current_query == target_query


def _select_best_matching_tab(
    tabs: List[Dict[str, object]],
    *,
    preferred_url: str = "",
    last_known_url: str = "",
    expected_domains: Iterable[str] | None = None,
) -> Dict[str, object]:
    """
    中文注解：
    - 功能：实现 `_select_best_matching_tab` 对应的处理逻辑。
    - 角色：属于本模块中的内部辅助逻辑；私有函数通常服务同文件主流程，公共函数通常作为跨模块入口或能力接口。
    - 调用关系：建议结合本文件的模块说明、调用方以及同名相关辅助函数一起阅读。
    """
    expected = _normalize_expected_domains(expected_domains, last_known_url)
    normalized_preferred = str(preferred_url or "").strip()
    normalized_last_known = str(last_known_url or "").strip()

    for target_url in (normalized_preferred, normalized_last_known):
        if not target_url:
            continue
        for tab in tabs:
            tab_url = str(tab.get("url", "")).strip()
            if _url_matches_target(tab_url, target_url):
                return tab

    for tab in tabs:
        tab_url = str(tab.get("url", "")).strip().lower()
        if any(domain in tab_url for domain in expected):
            return tab

    return tabs[0] if tabs else {}


def load_gateway_token() -> str:
    """
    中文注解：
    - 功能：实现 `load_gateway_token` 对应的处理逻辑。
    - 角色：属于本模块中的对外可见逻辑；私有函数通常服务同文件主流程，公共函数通常作为跨模块入口或能力接口。
    - 调用关系：建议结合本文件的模块说明、调用方以及同名相关辅助函数一起阅读。
    """
    config_path = OPENCLAW_ROOT / "openclaw.json"
    try:
        payload = json.loads(config_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return ""
    return str(payload.get("gateway", {}).get("auth", {}).get("token", "")).strip()


def browser_control_get(token: str, path: str, timeout: int = 10) -> Dict[str, object]:
    """
    中文注解：
    - 功能：实现 `browser_control_get` 对应的处理逻辑。
    - 角色：属于本模块中的对外可见逻辑；私有函数通常服务同文件主流程，公共函数通常作为跨模块入口或能力接口。
    - 调用关系：建议结合本文件的模块说明、调用方以及同名相关辅助函数一起阅读。
    """
    req = urllib.request.Request(
        f"http://127.0.0.1:18791{path}",
        headers={"Authorization": f"Bearer {token}"},
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode(errors="ignore"))


def browser_control_post(token: str, path: str, body: Dict[str, object], timeout: int = 20) -> Dict[str, object]:
    """
    中文注解：
    - 功能：实现 `browser_control_post` 对应的处理逻辑。
    - 角色：属于本模块中的对外可见逻辑；私有函数通常服务同文件主流程，公共函数通常作为跨模块入口或能力接口。
    - 调用关系：建议结合本文件的模块说明、调用方以及同名相关辅助函数一起阅读。
    """
    req = urllib.request.Request(
        f"http://127.0.0.1:18791{path}",
        data=json.dumps(body).encode(),
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode(errors="ignore"))


def _normalize_expected_domains(expected_domains: Iterable[str] | None, last_known_url: str) -> List[str]:
    """
    中文注解：
    - 功能：实现 `_normalize_expected_domains` 对应的处理逻辑。
    - 角色：属于本模块中的内部辅助逻辑；私有函数通常服务同文件主流程，公共函数通常作为跨模块入口或能力接口。
    - 调用关系：建议结合本文件的模块说明、调用方以及同名相关辅助函数一起阅读。
    """
    domains = [str(item).strip().lower() for item in (expected_domains or []) if str(item).strip()]
    if last_known_url:
        parsed = urllib.parse.urlparse(last_known_url)
        hostname = (parsed.hostname or "").strip().lower()
        if hostname:
            domains.append(hostname)
    deduped: List[str] = []
    seen = set()
    for item in domains:
        if item in seen:
            continue
        seen.add(item)
        deduped.append(item)
    return deduped


def get_current_relay_context(expected_domains: Iterable[str] | None = None, last_known_url: str = "", preferred_url: str = "") -> Dict[str, object]:
    """
    中文注解：
    - 功能：实现 `get_current_relay_context` 对应的处理逻辑。
    - 角色：属于本模块中的对外可见逻辑；私有函数通常服务同文件主流程，公共函数通常作为跨模块入口或能力接口。
    - 调用关系：建议结合本文件的模块说明、调用方以及同名相关辅助函数一起阅读。
    """
    token = load_gateway_token()
    expected = _normalize_expected_domains(expected_domains, last_known_url)
    if not token:
        return {
            "ok": False,
            "status": "missing_gateway_token",
            "expected_domains": expected,
            "last_known_url": last_known_url,
        }

    body = {
        "profile": "chrome-relay",
        "kind": "evaluate",
        "fn": """() => ({
  href: location.href,
  title: document.title || '',
  readyState: document.readyState || '',
})""",
    }
    try:
        response = browser_control_post(token, "/act", body, timeout=15)
    except (urllib.error.URLError, urllib.error.HTTPError, json.JSONDecodeError) as exc:
        try:
            tabs = _openclaw_browser_json("tabs", "--browser-profile", "chrome-relay", timeout=15).get("tabs", [])
        except Exception as cli_exc:  # pragma: no cover - fallback path
            return {
                "ok": False,
                "status": "relay_context_probe_failed",
                "error": str(exc),
                "cli_error": str(cli_exc),
                "expected_domains": expected,
                "last_known_url": last_known_url,
            }
        matched_tab = _select_best_matching_tab(
            tabs,
            preferred_url=preferred_url,
            last_known_url=last_known_url,
            expected_domains=expected,
        )
        page_url = str(matched_tab.get("url", "")).strip()
        target_id = str(matched_tab.get("targetId", "")).strip()
        matched_domain = ""
        lowered_url = page_url.lower()
        for domain in expected:
            if domain and domain in lowered_url:
                matched_domain = domain
                break
        matched = bool(matched_domain or not expected)
        return {
            "ok": bool(target_id and page_url and matched),
            "status": "browser_channel_recovered" if target_id and page_url and matched else "relay_context_mismatch",
            "target_id": target_id,
            "page_url": page_url,
            "title": str(matched_tab.get("title", "")).strip(),
            "ready_state": "",
            "expected_domains": expected,
            "matched_domain": matched_domain,
            "last_known_url": last_known_url,
            "preferred_url": preferred_url,
            "fallback": "openclaw_browser_cli",
            "tabs_count": len(tabs),
        }

    result = response.get("result", {}) if isinstance(response, dict) else {}
    page_url = ""
    if isinstance(result, dict):
        page_url = str(result.get("href", "") or result.get("url", "")).strip()
    if not page_url:
        page_url = str(response.get("url", "")).strip() if isinstance(response, dict) else ""
    target_id = str(response.get("targetId", "")).strip() if isinstance(response, dict) else ""
    matched_domain = ""
    lowered_url = page_url.lower()
    for domain in expected:
        if domain and domain in lowered_url:
            matched_domain = domain
            break
    matched = bool(matched_domain or not expected)
    result = {
        "ok": bool(target_id and page_url and matched),
        "status": "browser_channel_recovered" if target_id and page_url and matched else "relay_context_mismatch",
        "target_id": target_id,
        "page_url": page_url,
        "title": str(result.get("title", "")).strip() if isinstance(result, dict) else "",
        "ready_state": str(result.get("readyState", "")).strip() if isinstance(result, dict) else "",
        "expected_domains": expected,
        "matched_domain": matched_domain,
        "last_known_url": last_known_url,
        "preferred_url": preferred_url,
    }
    if preferred_url and not _url_matches_target(page_url, preferred_url):
        try:
            tabs = _openclaw_browser_json("tabs", "--browser-profile", "chrome-relay", timeout=15).get("tabs", [])
        except Exception:  # pragma: no cover - fallback path
            return result
        matched_tab = _select_best_matching_tab(
            tabs,
            preferred_url=preferred_url,
            last_known_url=last_known_url,
            expected_domains=expected,
        )
        matched_url = str(matched_tab.get("url", "")).strip()
        matched_target_id = str(matched_tab.get("targetId", "")).strip()
        if matched_target_id and matched_url and _url_matches_target(matched_url, preferred_url):
            lowered_url = matched_url.lower()
            matched_domain = ""
            for domain in expected:
                if domain and domain in lowered_url:
                    matched_domain = domain
                    break
            result.update(
                {
                    "ok": True,
                    "status": "browser_channel_recovered",
                    "target_id": matched_target_id,
                    "page_url": matched_url,
                    "title": str(matched_tab.get("title", "")).strip(),
                    "ready_state": "",
                    "matched_domain": matched_domain,
                    "fallback": "openclaw_browser_cli",
                    "tabs_count": len(tabs),
                }
            )
    return result


def recover_browser_channel(task_id: str, expected_domains: Iterable[str] | None = None, last_known_url: str = "", preferred_url: str = "") -> Dict[str, object]:
    """
    中文注解：
    - 功能：实现 `recover_browser_channel` 对应的处理逻辑。
    - 角色：属于本模块中的对外可见逻辑；私有函数通常服务同文件主流程，公共函数通常作为跨模块入口或能力接口。
    - 调用关系：建议结合本文件的模块说明、调用方以及同名相关辅助函数一起阅读。
    """
    context = get_current_relay_context(expected_domains=expected_domains, last_known_url=last_known_url, preferred_url=preferred_url)
    retry_count = 0
    while (
        not context.get("ok")
        and str(context.get("status", "")) == "relay_context_mismatch"
        and int(context.get("tabs_count", 0) or 0) == 0
        and retry_count < 3
    ):
        retry_count += 1
        time.sleep(0.75)
        context = get_current_relay_context(expected_domains=expected_domains, last_known_url=last_known_url, preferred_url=preferred_url)

    reopened = None
    target_url = str(preferred_url or last_known_url or "").strip()
    if (
        not context.get("ok")
        and target_url
        and (
            str(context.get("status", "")) in {"relay_context_mismatch", "relay_context_probe_failed"}
            or int(context.get("tabs_count", 0) or 0) == 0
        )
    ):
        try:
            reopened = _open_relay_tab(target_url, timeout=20)
            time.sleep(1.0)
            context = get_current_relay_context(expected_domains=expected_domains, last_known_url=last_known_url or target_url, preferred_url=preferred_url or target_url)
        except Exception as exc:  # pragma: no cover - best-effort recovery
            reopened = {"ok": False, "status": "relay_open_failed", "error": str(exc), "url": target_url}

    result = {
        "task_id": task_id,
        **context,
    }
    if retry_count:
        result["retry_count"] = retry_count
    if reopened is not None:
        result["reopened_tab"] = reopened
    if result.get("ok"):
        prune_result = prune_relay_tabs(
            task_id,
            keep_target_id=str(result.get("target_id", "")).strip(),
            preferred_url=preferred_url,
            last_known_url=last_known_url,
            expected_domains=expected_domains,
            max_tabs=1,
        )
        result["tab_pruning"] = prune_result
    _write_json(BROWSER_CHANNELS_ROOT / f"{task_id}.json", result)
    return result


def navigate_relay_to_url(task_id: str, url: str, expected_domains: Iterable[str] | None = None) -> Dict[str, object]:
    """
    中文注解：
    - 功能：实现 `navigate_relay_to_url` 对应的处理逻辑。
    - 角色：属于本模块中的对外可见逻辑；私有函数通常服务同文件主流程，公共函数通常作为跨模块入口或能力接口。
    - 调用关系：建议结合本文件的模块说明、调用方以及同名相关辅助函数一起阅读。
    """
    token = load_gateway_token()
    expected = _normalize_expected_domains(expected_domains, url)
    if not token:
        result = {
            "task_id": task_id,
            "ok": False,
            "status": "missing_gateway_token",
            "url": url,
            "expected_domains": expected,
        }
        _write_json(BROWSER_CHANNELS_ROOT / f"{task_id}.json", result)
        return result

    context = recover_browser_channel(task_id, expected_domains=expected, last_known_url=url, preferred_url=url)
    target_id = str(context.get("target_id", "")).strip()
    current_url = str(context.get("page_url", "")).strip()
    if _url_matches_target(current_url, url):
        result = {
            "task_id": task_id,
            "ok": True,
            "status": "already_at_target_url",
            "url": url,
            "expected_domains": expected,
            "context": context,
        }
        _write_json(BROWSER_CHANNELS_ROOT / f"{task_id}.json", result)
        return result
    if not target_id:
        try:
            reopened = _open_relay_tab(url, timeout=20)
            time.sleep(1.0)
            context = recover_browser_channel(task_id, expected_domains=expected, last_known_url=url, preferred_url=url)
            target_id = str(context.get("target_id", "")).strip()
            current_url = str(context.get("page_url", "")).strip()
            if _url_matches_target(current_url, url):
                result = {
                    "task_id": task_id,
                    "ok": True,
                    "status": "relay_tab_reopened_at_target_url",
                    "url": url,
                    "expected_domains": expected,
                    "context": context,
                    "reopened_tab": reopened,
                }
                _write_json(BROWSER_CHANNELS_ROOT / f"{task_id}.json", result)
                return result
        except Exception as exc:  # pragma: no cover - best-effort recovery
            reopened = {"ok": False, "status": "relay_open_failed", "error": str(exc), "url": url}
        if not target_id:
            result = {
                "task_id": task_id,
                "ok": False,
                "status": "missing_relay_target",
                "url": url,
                "expected_domains": expected,
                "context": context,
                "reopened_tab": reopened,
            }
            _write_json(BROWSER_CHANNELS_ROOT / f"{task_id}.json", result)
            return result

    try:
        browser_control_post(
            token,
            "/act",
            {
                "profile": "chrome-relay",
                "targetId": target_id,
                "kind": "evaluate",
                "fn": f"() => {{ window.location.href = {json.dumps(url)}; return {{ href: location.href }}; }}",
            },
            timeout=15,
        )
    except (urllib.error.URLError, urllib.error.HTTPError, json.JSONDecodeError):
        try:
            subprocess.run(
                [_resolve_openclaw_bin(), "browser", "--browser-profile", "chrome-relay", "focus", target_id],
                capture_output=True,
                text=True,
                check=False,
                timeout=15,
            )
            _openclaw_browser_json("navigate", "--browser-profile", "chrome-relay", "--target-id", target_id, url, timeout=20)
        except Exception as cli_exc:
            result = {
                "task_id": task_id,
                "ok": False,
                "status": "relay_navigation_failed",
                "url": url,
                "expected_domains": expected,
                "error": str(cli_exc),
                "context": context,
            }
            _write_json(BROWSER_CHANNELS_ROOT / f"{task_id}.json", result)
            return result

    latest = context
    for _ in range(8):
        time.sleep(0.5)
        latest = get_current_relay_context(expected_domains=expected, last_known_url=url, preferred_url=url)
        current_url = str(latest.get("page_url", "")).strip()
        if current_url.startswith(url):
            result = {
                "task_id": task_id,
                "ok": True,
                "status": "relay_navigation_succeeded",
                "url": url,
                "expected_domains": expected,
                "target_id": latest.get("target_id", ""),
                "page_url": current_url,
                "context": latest,
            }
            result["tab_pruning"] = prune_relay_tabs(
                task_id,
                keep_target_id=str(latest.get("target_id", "")).strip(),
                preferred_url=url,
                last_known_url=url,
                expected_domains=expected,
                max_tabs=1,
            )
            _write_json(BROWSER_CHANNELS_ROOT / f"{task_id}.json", result)
            return result

    result = {
        "task_id": task_id,
        "ok": False,
        "status": "relay_navigation_unconfirmed",
        "url": url,
        "expected_domains": expected,
        "context": latest,
    }
    _write_json(BROWSER_CHANNELS_ROOT / f"{task_id}.json", result)
    return result
