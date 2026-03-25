#!/usr/bin/env python3

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Dict, Iterable, List

from paths import BROWSER_SIGNALS_ROOT, OPENCLAW_SESSIONS_ROOT


IMAGE_COUNT_PATTERNS = [
    re.compile(r"产品图片区图片数(?:仍然)?是\s*\*{0,2}(\d+)\*{0,2}"),
    re.compile(r'"productImgs":\s*(\d+)'),
    re.compile(r'"count":\s*(\d+)'),
]
FILE_COUNT_PATTERNS = [
    re.compile(r"文件 input .*?文件数(?:还是|为)?\s*\*{0,2}(\d+)\*{0,2}"),
    re.compile(r'"files":\s*(\d+)'),
]


def _write_json(path: Path, payload: Dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _load_link(task_id: str) -> Dict[str, object]:
    links_root = Path("/Users/mac_claw/.openclaw/workspace/tools/openmoss/runtime/autonomy/links")
    for link_path in links_root.glob("*.json"):
        try:
            payload = json.loads(link_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            continue
        if str(payload.get("task_id", "")) == task_id:
            payload["_path"] = str(link_path)
            return payload
    return {}


def _candidate_session_files(last_message_id: str) -> List[Path]:
    if not last_message_id or not OPENCLAW_SESSIONS_ROOT.exists():
        return []
    matches: List[Path] = []
    for session_path in OPENCLAW_SESSIONS_ROOT.glob("*.jsonl"):
        try:
            text = session_path.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        if last_message_id in text:
            matches.append(session_path)
    return sorted(matches, key=lambda path: path.stat().st_mtime, reverse=True)


def _extract_int(patterns: Iterable[re.Pattern[str]], text: str) -> int | None:
    for pattern in patterns:
        match = pattern.search(text)
        if match:
            return int(match.group(1))
    return None


def _analyze_lines(lines: List[str]) -> Dict[str, object]:
    evidence: List[str] = []
    product_image_count = None
    file_input_count = None
    upload_attempted = False
    upload_not_received = False
    upload_path_invalid = False
    needs_network_debug = False

    for line in lines:
        lower = line.lower()
        product_image_count = _extract_int(IMAGE_COUNT_PATTERNS, line) if product_image_count is None else product_image_count
        file_input_count = _extract_int(FILE_COUNT_PATTERNS, line) if file_input_count is None else file_input_count
        if any(token in lower for token in ["upload", "上传动作", "upload 路径", "文件注入"]):
            upload_attempted = True
        if "没有被页面真正接收" in line or "根本没有被这个产品图片区的上传链接收进去" in line:
            upload_not_received = True
            evidence.append("page rejected the upload injection path")
        if "上传控件" in line and "没有生效" in line:
            upload_path_invalid = True
            evidence.append("upload control path did not react to injected file")
        if "查它真实上传请求" in line or "查它的前端绑定事件" in line or "找它的接口链路" in line:
            needs_network_debug = True
            evidence.append("deeper request-chain or frontend-binding inspection explicitly required")

    diagnosis = "none"
    recommended_action = "continue_current_plan"
    if upload_attempted and file_input_count == 0 and upload_not_received:
        diagnosis = "upload_control_path_invalid"
        recommended_action = "needs_network_request_level_debugging"
    elif upload_path_invalid:
        diagnosis = "frontend_binding_not_triggered"
        recommended_action = "investigate_frontend_binding_and_network_request_chain"
    elif needs_network_debug:
        diagnosis = "needs_network_request_level_debugging"
        recommended_action = "needs_network_request_level_debugging"

    return {
        "product_image_count": product_image_count,
        "file_input_count": file_input_count,
        "upload_attempted": upload_attempted,
        "upload_not_received": upload_not_received,
        "upload_path_invalid": upload_path_invalid,
        "needs_network_debug": needs_network_debug,
        "diagnosis": diagnosis,
        "recommended_action": recommended_action,
        "evidence": sorted(set(evidence)),
    }


def collect_browser_task_signals(task_id: str) -> Dict[str, object]:
    link = _load_link(task_id)
    last_message_id = str(link.get("last_message_id", "")).strip()
    session_files = _candidate_session_files(last_message_id)
    payload: Dict[str, object] = {
        "task_id": task_id,
        "link_path": link.get("_path", ""),
        "last_message_id": last_message_id,
        "session_path": "",
        "analysis_window_lines": 0,
        "diagnosis": "none",
        "recommended_action": "continue_current_plan",
        "product_image_count": None,
        "file_input_count": None,
        "evidence": [],
    }

    if not session_files:
        _write_json(BROWSER_SIGNALS_ROOT / f"{task_id}.json", payload)
        return payload

    session_path = session_files[0]
    payload["session_path"] = str(session_path)
    lines = session_path.read_text(encoding="utf-8", errors="ignore").splitlines()

    start_index = max(0, len(lines) - 220)
    if last_message_id:
        for idx, line in enumerate(lines):
            if last_message_id in line:
                start_index = max(0, idx - 120)
                break
    window = lines[start_index:]
    analysis = _analyze_lines(window)
    payload.update(analysis)
    payload["analysis_window_lines"] = len(window)
    _write_json(BROWSER_SIGNALS_ROOT / f"{task_id}.json", payload)
    return payload


def main() -> int:
    import argparse

    parser = argparse.ArgumentParser(description="Collect browser-observed task signals from the linked OpenClaw session")
    parser.add_argument("--task-id", required=True)
    args = parser.parse_args()
    print(json.dumps(collect_browser_task_signals(args.task_id), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
