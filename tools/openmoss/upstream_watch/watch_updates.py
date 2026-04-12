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
- 文件路径：`tools/openmoss/upstream_watch/watch_updates.py`
- 文件作用：负责`watch_updates` 相关的一方系统逻辑。
- 顶层函数：utc_now_iso、read_json、write_json、github_json、fetch_repo_snapshot、classify_change、build_intake_note、render_markdown_report、run_once、main。
- 顶层类：无顶层类。
- 阅读建议：先看模块说明，再按函数/类 docstring 顺着主流程理解调用关系。
"""
from __future__ import annotations

import argparse
import json
import os
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List


ROOT = Path(__file__).resolve().parents[1]
WATCH_ROOT = ROOT / "upstream_watch"
RUNTIME_ROOT = ROOT / "runtime/upstream_watch"
REPORTS_ROOT = RUNTIME_ROOT / "reports"
STATE_PATH = RUNTIME_ROOT / "state.json"
UPSTREAMS_PATH = RUNTIME_ROOT / "upstreams.json"
CONFIG_PATH = WATCH_ROOT / "repos.json"


def utc_now_iso() -> str:
    """
    中文注解：
    - 功能：实现 `utc_now_iso` 对应的处理逻辑。
    - 角色：属于本模块中的对外可见逻辑；私有函数通常服务同文件主流程，公共函数通常作为跨模块入口或能力接口。
    - 调用关系：建议结合本文件的模块说明、调用方以及同名相关辅助函数一起阅读。
    """
    return datetime.now(timezone.utc).isoformat()


def read_json(path: Path, default):
    """
    中文注解：
    - 功能：实现 `read_json` 对应的处理逻辑。
    - 角色：属于本模块中的对外可见逻辑；私有函数通常服务同文件主流程，公共函数通常作为跨模块入口或能力接口。
    - 调用关系：建议结合本文件的模块说明、调用方以及同名相关辅助函数一起阅读。
    """
    if not path.exists():
        return default
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, payload: object) -> None:
    """
    中文注解：
    - 功能：实现 `write_json` 对应的处理逻辑。
    - 角色：属于本模块中的对外可见逻辑；私有函数通常服务同文件主流程，公共函数通常作为跨模块入口或能力接口。
    - 调用关系：建议结合本文件的模块说明、调用方以及同名相关辅助函数一起阅读。
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def github_json(path: str) -> Dict[str, object] | List[Dict[str, object]]:
    """
    中文注解：
    - 功能：实现 `github_json` 对应的处理逻辑。
    - 角色：属于本模块中的对外可见逻辑；私有函数通常服务同文件主流程，公共函数通常作为跨模块入口或能力接口。
    - 调用关系：建议结合本文件的模块说明、调用方以及同名相关辅助函数一起阅读。
    """
    url = f"https://api.github.com{path}"
    token = os.environ.get("GITHUB_TOKEN", "").strip()
    headers = {"Accept": "application/vnd.github+json", "User-Agent": "JinClaw-Upstream-Watch"}

    def _request_json(use_token: bool) -> Dict[str, object] | List[Dict[str, object]]:
        """
        中文注解：
        - 功能：实现 `_request_json` 对应的处理逻辑。
        - 角色：属于本模块中的内部辅助逻辑；私有函数通常服务同文件主流程，公共函数通常作为跨模块入口或能力接口。
        - 调用关系：建议结合本文件的模块说明、调用方以及同名相关辅助函数一起阅读。
        """
        req = urllib.request.Request(url, headers=headers)
        if use_token and token:
            req.add_header("Authorization", f"Bearer {token}")
        with urllib.request.urlopen(req, timeout=20) as resp:
            return json.loads(resp.read().decode("utf-8"))

    try:
        return _request_json(use_token=bool(token))
    except urllib.error.HTTPError as exc:
        if token and exc.code in {401, 403}:
            return _request_json(use_token=False)
        raise


def fetch_repo_snapshot(source: Dict[str, object]) -> Dict[str, object]:
    """
    中文注解：
    - 功能：实现 `fetch_repo_snapshot` 对应的处理逻辑。
    - 角色：属于本模块中的对外可见逻辑；私有函数通常服务同文件主流程，公共函数通常作为跨模块入口或能力接口。
    - 调用关系：建议结合本文件的模块说明、调用方以及同名相关辅助函数一起阅读。
    """
    repo = str(source["repo"])
    repo_meta = github_json(f"/repos/{repo}")
    try:
        latest_release = github_json(f"/repos/{repo}/releases/latest")
        release_payload = {
            "tag_name": latest_release.get("tag_name", ""),
            "name": latest_release.get("name", ""),
            "published_at": latest_release.get("published_at", ""),
            "html_url": latest_release.get("html_url", ""),
        }
    except urllib.error.HTTPError as exc:
        if exc.code == 404:
            release_payload = {}
        else:
            raise
    tags = github_json(f"/repos/{repo}/tags?per_page=5")
    return {
        "id": source["id"],
        "name": source["name"],
        "repo": repo,
        "category": source["category"],
        "priority": source["priority"],
        "adoption_policy": source["adoption_policy"],
        "why_it_matters": source["why_it_matters"],
        "fetched_at": utc_now_iso(),
        "default_branch": repo_meta.get("default_branch", ""),
        "pushed_at": repo_meta.get("pushed_at", ""),
        "updated_at": repo_meta.get("updated_at", ""),
        "stargazers_count": repo_meta.get("stargazers_count", 0),
        "open_issues_count": repo_meta.get("open_issues_count", 0),
        "latest_release": release_payload,
        "recent_tags": [
            {
                "name": tag.get("name", ""),
                "sha": ((tag.get("commit") or {}).get("sha", "")),
            }
            for tag in tags[:5]
        ],
        "html_url": repo_meta.get("html_url", ""),
    }


def classify_change(previous: Dict[str, object], current: Dict[str, object]) -> Dict[str, object]:
    """
    中文注解：
    - 功能：实现 `classify_change` 对应的处理逻辑。
    - 角色：属于本模块中的对外可见逻辑；私有函数通常服务同文件主流程，公共函数通常作为跨模块入口或能力接口。
    - 调用关系：建议结合本文件的模块说明、调用方以及同名相关辅助函数一起阅读。
    """
    changed_fields: List[str] = []
    if previous.get("pushed_at") != current.get("pushed_at"):
        changed_fields.append("pushed_at")
    if (previous.get("latest_release") or {}).get("tag_name") != (current.get("latest_release") or {}).get("tag_name"):
        changed_fields.append("latest_release")
    if (previous.get("recent_tags") or [])[:1] != (current.get("recent_tags") or [])[:1]:
        changed_fields.append("recent_tags")
    changed = bool(changed_fields)
    if not changed:
        status = "no_change"
    elif current.get("priority") == "critical":
        status = "review_immediately"
    elif "latest_release" in changed_fields:
        status = "review_today"
    else:
        status = "review_soon"
    return {"changed": changed, "changed_fields": changed_fields, "status": status}


def build_intake_note(source: Dict[str, object], change: Dict[str, object]) -> Dict[str, object]:
    """
    中文注解：
    - 功能：实现 `build_intake_note` 对应的处理逻辑。
    - 角色：属于本模块中的对外可见逻辑；私有函数通常服务同文件主流程，公共函数通常作为跨模块入口或能力接口。
    - 调用关系：建议结合本文件的模块说明、调用方以及同名相关辅助函数一起阅读。
    """
    action = "borrow_and_localize"
    if source["category"] == "upstream-core" and source["priority"] == "critical":
        action = "evaluate_for_real_sync"
    elif source["category"] == "runtime-dependency":
        action = "compare_with_current_usage_then_selectively_absorb"
    return {
        "repo": source["repo"],
        "status": change["status"],
        "changed_fields": change["changed_fields"],
        "recommended_action": action,
        "why_it_matters": source["why_it_matters"],
        "adoption_policy": source["adoption_policy"],
    }


def render_markdown_report(items: List[Dict[str, object]]) -> str:
    """
    中文注解：
    - 功能：实现 `render_markdown_report` 对应的处理逻辑。
    - 角色：属于本模块中的对外可见逻辑；私有函数通常服务同文件主流程，公共函数通常作为跨模块入口或能力接口。
    - 调用关系：建议结合本文件的模块说明、调用方以及同名相关辅助函数一起阅读。
    """
    lines = ["# JinClaw Upstream Watch Report", "", f"Generated at: `{utc_now_iso()}`", ""]
    for item in items:
        snapshot = item["snapshot"]
        change = item["change"]
        intake = item["intake"]
        lines.extend(
            [
                f"## {snapshot['name']}",
                f"- Repo: `{snapshot['repo']}`",
                f"- Priority: `{snapshot['priority']}`",
                f"- Status: `{change['status']}`",
                f"- Changed: `{change['changed']}`",
                f"- Changed fields: `{', '.join(change['changed_fields']) or 'none'}`",
                f"- Latest release: `{(snapshot.get('latest_release') or {}).get('tag_name', 'n/a')}`",
                f"- Last push: `{snapshot.get('pushed_at', '')}`",
                f"- Recommended action: `{intake['recommended_action']}`",
                f"- Why it matters: {snapshot['why_it_matters']}",
                "",
            ]
        )
    return "\n".join(lines).strip() + "\n"


def run_once() -> Dict[str, object]:
    """
    中文注解：
    - 功能：实现 `run_once` 对应的处理逻辑。
    - 角色：属于本模块中的对外可见逻辑；私有函数通常服务同文件主流程，公共函数通常作为跨模块入口或能力接口。
    - 调用关系：建议结合本文件的模块说明、调用方以及同名相关辅助函数一起阅读。
    """
    config = read_json(CONFIG_PATH, {"sources": []})
    previous_state = read_json(STATE_PATH, {"repos": {}})
    items = []
    next_state = {"checked_at": utc_now_iso(), "repos": {}}
    for source in config.get("sources", []):
        snapshot = fetch_repo_snapshot(source)
        previous = previous_state.get("repos", {}).get(source["id"], {})
        change = classify_change(previous, snapshot)
        intake = build_intake_note(source, change)
        items.append({"source": source, "snapshot": snapshot, "change": change, "intake": intake})
        next_state["repos"][source["id"]] = snapshot

    report_md = render_markdown_report(items)
    write_json(UPSTREAMS_PATH, {"checked_at": utc_now_iso(), "items": items})
    write_json(STATE_PATH, next_state)
    REPORTS_ROOT.mkdir(parents=True, exist_ok=True)
    (REPORTS_ROOT / "latest-report.md").write_text(report_md, encoding="utf-8")
    return {
        "checked_at": next_state["checked_at"],
        "repo_count": len(items),
        "changed": [item["snapshot"]["repo"] for item in items if item["change"]["changed"]],
        "report_path": str(REPORTS_ROOT / "latest-report.md"),
        "state_path": str(STATE_PATH),
    }


def main() -> int:
    """
    中文注解：
    - 功能：实现 `main` 对应的处理逻辑。
    - 角色：属于本模块中的对外可见逻辑；私有函数通常服务同文件主流程，公共函数通常作为跨模块入口或能力接口。
    - 调用关系：建议结合本文件的模块说明、调用方以及同名相关辅助函数一起阅读。
    """
    parser = argparse.ArgumentParser(description="Watch upstream OSS projects that JinClaw depends on or borrows from")
    parser.add_argument("--once", action="store_true", help="Run one check now")
    args = parser.parse_args()
    result = run_once()
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
