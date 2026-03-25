#!/usr/bin/env python3

from __future__ import annotations

import json
import re
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Dict, Iterable, List

from paths import BROWSER_SIGNALS_ROOT, OPENCLAW_ROOT, OPENCLAW_SESSIONS_ROOT


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


def _load_contract_payload(task_id: str) -> Dict[str, object]:
    contract_path = Path("/Users/mac_claw/.openclaw/workspace/tools/openmoss/runtime/autonomy/tasks") / task_id / "contract.json"
    try:
        return json.loads(contract_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def _load_business_verification_requirements(task_id: str) -> Dict[str, object]:
    contract = _load_contract_payload(task_id)
    metadata = contract.get("metadata", {}) or {}
    control_center = metadata.get("control_center", {}) or {}
    requirements = control_center.get("business_verification_requirements", {}) or {}
    return requirements if isinstance(requirements, dict) else {}


def _load_sessions_registry() -> Dict[str, object]:
    registry_path = OPENCLAW_SESSIONS_ROOT / "sessions.json"
    try:
        return json.loads(registry_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def _is_browser_gallery_task(task_id: str) -> bool:
    contract_path = Path("/Users/mac_claw/.openclaw/workspace/tools/openmoss/runtime/autonomy/tasks") / task_id / "contract.json"
    try:
        payload = json.loads(contract_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return False
    metadata = payload.get("metadata", {}) or {}
    intent = metadata.get("control_center", {}).get("intent", {}) or {}
    task_types = {str(item).strip().lower() for item in intent.get("task_types", []) if str(item).strip()}
    goal = str(payload.get("user_goal", "") or intent.get("goal", "")).lower()
    return bool(
        intent.get("needs_browser")
        and (
            "marketplace" in task_types
            or "image" in task_types
            or any(token in goal for token in ["upload", "上传", "image", "图片", "seller", "product", "详情页", "gallery", "图区"])
        )
    )


def _candidate_session_files_from_key(session_key: str) -> List[Path]:
    if not session_key:
        return []
    registry = _load_sessions_registry()
    session_info = registry.get(session_key, {}) if isinstance(registry, dict) else {}
    session_file = str(session_info.get("sessionFile") or "").strip()
    session_id = str(session_info.get("sessionId") or "").strip()
    candidates: List[Path] = []
    if session_file:
        candidates.append(Path(session_file))
    if session_id:
        candidates.append(OPENCLAW_SESSIONS_ROOT / f"{session_id}.jsonl")
    deduped: List[Path] = []
    seen = set()
    for candidate in candidates:
        key = str(candidate)
        if key in seen:
            continue
        seen.add(key)
        if candidate.exists():
            deduped.append(candidate)
    return deduped


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


def _load_gateway_token() -> str:
    config_path = OPENCLAW_ROOT / "openclaw.json"
    try:
        payload = json.loads(config_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return ""
    return str(payload.get("gateway", {}).get("auth", {}).get("token", "")).strip()


def _extract_latest_target_context(lines: List[str]) -> Dict[str, str]:
    target_id = ""
    page_url = ""
    for line in lines:
        target_match = re.search(r'"targetId":\s*"([^"]+)"', line)
        if target_match:
            target_id = target_match.group(1)
        url_match = re.search(r'"url":\s*"([^"]+seller\.neosgo\.com[^"]*)"', line)
        if url_match:
            page_url = url_match.group(1)
    return {"target_id": target_id, "page_url": page_url}


def _browser_control_get(token: str, path: str) -> Dict[str, object]:
    req = urllib.request.Request(
        f"http://127.0.0.1:18791{path}",
        headers={"Authorization": f"Bearer {token}"},
    )
    with urllib.request.urlopen(req, timeout=10) as resp:
        return json.loads(resp.read().decode(errors="ignore"))


def _browser_control_post(token: str, path: str, body: Dict[str, object], timeout: int = 20) -> Dict[str, object]:
    req = urllib.request.Request(
        f"http://127.0.0.1:18791{path}",
        data=json.dumps(body).encode(),
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode(errors="ignore"))


def _collect_live_browser_probe(task_id: str, lines: List[str]) -> Dict[str, object]:
    token = _load_gateway_token()
    context = _extract_latest_target_context(lines)
    target_id = context.get("target_id", "")
    page_url = context.get("page_url", "")
    payload: Dict[str, object] = {
        "available": False,
        "target_id": target_id,
        "page_url": page_url,
        "product_image_count": None,
        "file_input_count": None,
        "form_valid": None,
        "invalid_fields": [],
        "save_request_succeeded": False,
        "save_request_url": "",
    }
    if not token or not target_id:
        return payload

    requests_path = f"/requests?{urllib.parse.urlencode({'profile': 'chrome-relay', 'targetId': target_id})}"
    evaluate_body = {
        "profile": "chrome-relay",
        "targetId": target_id,
        "kind": "evaluate",
        "fn": r"""() => {
  const imgs = [...document.querySelectorAll('img')]
    .filter(i => i.alt && /^Image \d+$/.test(i.alt))
    .map(i => i.src);
  const sceneImgs = imgs
    .map((src, idx) => ({src, position: idx + 1}))
    .filter((item) => item.src.includes('neosgo-prod-') || item.src.includes('/products/'));
  const input = document.querySelector("input[type='file'][accept='image/jpeg,image/png,image/gif,image/webp']");
  const form = document.querySelector('form');
  const invalid = form
    ? [...form.querySelectorAll(':invalid')].map((el) => ({
        label: el.previousElementSibling && el.previousElementSibling.tagName === 'LABEL'
          ? (el.previousElementSibling.innerText || '').trim()
          : '',
        type: el.getAttribute('type') || '',
        value: el.value || '',
        min: el.getAttribute('min') || '',
        max: el.getAttribute('max') || '',
        step: el.getAttribute('step') || '',
        stepMismatch: Boolean(el.validity && el.validity.stepMismatch),
      }))
    : [];
  return {
    count: imgs.length,
    sceneImageCount: sceneImgs.length,
    sceneImagePositions: sceneImgs.map((item) => item.position),
    firstScenePosition: sceneImgs.length ? sceneImgs[0].position : null,
    fileCount: input && input.files ? input.files.length : 0,
    formValid: form ? form.checkValidity() : null,
    invalidFields: invalid,
    imgs,
    lastImgs: imgs.slice(-3),
    url: location.href,
  };
}""",
    }
    product_fetch_body = {
        "profile": "chrome-relay",
        "targetId": target_id,
        "kind": "evaluate",
        "fn": r"""async () => {
  const id = location.pathname.split('/').filter(Boolean).pop();
  try {
    const resp = await fetch(`/api/products/${id}`, { credentials: 'include' });
    const data = await resp.json();
    return {
      ok: resp.ok,
      status: resp.status,
      productStatus: data && typeof data.status === 'string' ? data.status : '',
      packingUnitsCount: Array.isArray(data && data.packingUnits) ? data.packingUnits.length : 0,
      packingUnits: Array.isArray(data && data.packingUnits) ? data.packingUnits : [],
    };
  } catch (err) {
    return {
      ok: false,
      status: 0,
      productStatus: '',
      packingUnitsCount: 0,
      packingUnits: [],
      fetchError: String(err && err.message || err),
    };
  }
}""",
    }
    try:
        requests = _browser_control_get(token, requests_path)
        state = _browser_control_post(token, "/act", evaluate_body)
        product_state = _browser_control_post(token, "/act", product_fetch_body)
    except (urllib.error.URLError, urllib.error.HTTPError, json.JSONDecodeError):
        return payload

    request_rows = requests.get("requests", []) if isinstance(requests, dict) else []
    state_result = state.get("result", {}) if isinstance(state, dict) else {}
    product_result = product_state.get("result", {}) if isinstance(product_state, dict) else {}
    save_request = next(
        (
            row
            for row in request_rows
            if row.get("method") == "PATCH"
            and "/api/products/" in str(row.get("url", ""))
            and bool(row.get("ok"))
        ),
        None,
    )
    payload.update(
        {
            "available": True,
            "page_url": str(state_result.get("url", page_url) or page_url),
            "product_image_count": state_result.get("count"),
            "scene_image_count": state_result.get("sceneImageCount"),
            "scene_image_positions": state_result.get("sceneImagePositions", []),
            "first_scene_position": state_result.get("firstScenePosition"),
            "file_input_count": state_result.get("fileCount"),
            "form_valid": state_result.get("formValid"),
            "invalid_fields": state_result.get("invalidFields", []),
            "all_images": state_result.get("imgs", []),
            "last_images": state_result.get("lastImgs", []),
            "save_request_succeeded": bool(save_request),
            "save_request_url": str(save_request.get("url", "")) if save_request else "",
            "product_status": str(product_result.get("productStatus", "") or ""),
            "packing_units_count": product_result.get("packingUnitsCount"),
            "packing_units": product_result.get("packingUnits", []),
        }
    )
    if save_request:
        payload["evidence"] = [
            "live browser probe observed successful product PATCH save request",
            "browser page retained uploaded product image after save path engaged",
        ]
    elif payload["file_input_count"] and payload["form_valid"] is False:
        payload["evidence"] = [
            "file reached the real file input in the page",
            "native form validation blocked submit before the save request was sent",
        ]
    return payload


def _evaluate_business_requirements(requirements: Dict[str, object], payload: Dict[str, object]) -> Dict[str, object]:
    if not requirements:
        return {"ok": True, "status": "no_explicit_requirements", "failures": []}

    live_probe = payload.get("live_probe", {}) if isinstance(payload.get("live_probe"), dict) else {}
    failures: List[Dict[str, object]] = []

    min_scene_count = requirements.get("scene_image_count_at_least")
    if isinstance(min_scene_count, int):
        current = live_probe.get("scene_image_count")
        if not isinstance(current, int) or current < min_scene_count:
            failures.append(
                {
                    "code": "scene_image_count_below_target",
                    "expected_at_least": min_scene_count,
                    "current": current,
                }
            )

    scene_pos_max = requirements.get("scene_image_position_max")
    if isinstance(scene_pos_max, int):
        current = live_probe.get("first_scene_position")
        if not isinstance(current, int) or current > scene_pos_max:
            failures.append(
                {
                    "code": "scene_image_not_far_enough_forward",
                    "expected_position_max": scene_pos_max,
                    "current": current,
                }
            )

    packing_units_at_least = requirements.get("packing_units_at_least")
    if isinstance(packing_units_at_least, int):
        current = live_probe.get("packing_units_count")
        if not isinstance(current, int) or current < packing_units_at_least:
            failures.append(
                {
                    "code": "packing_units_below_target",
                    "expected_at_least": packing_units_at_least,
                    "current": current,
                }
            )

    if requirements.get("form_must_be_valid") is True and live_probe.get("form_valid") is not True:
        failures.append(
            {
                "code": "form_not_valid",
                "current": live_probe.get("form_valid"),
                "invalid_fields": live_probe.get("invalid_fields", []),
            }
        )

    forbidden_statuses = requirements.get("review_status_not_in") or []
    if isinstance(forbidden_statuses, list) and forbidden_statuses:
        current_status = str(live_probe.get("product_status", "") or "").strip()
        if not current_status or current_status in {str(item) for item in forbidden_statuses}:
            failures.append(
                {
                    "code": "review_not_submitted",
                    "forbidden_statuses": forbidden_statuses,
                    "current": current_status,
                }
            )

    status = "ok" if not failures else failures[0]["code"]
    return {"ok": not failures, "status": status, "failures": failures}


def collect_browser_task_signals(task_id: str) -> Dict[str, object]:
    if not _is_browser_gallery_task(task_id):
        payload = {
            "task_id": task_id,
            "diagnosis": "none",
            "recommended_action": "continue_current_plan",
            "evidence": [],
            "reason": "task is not a browser-backed image or marketplace gallery workflow",
        }
        _write_json(BROWSER_SIGNALS_ROOT / f"{task_id}.json", payload)
        return payload

    link = _load_link(task_id)
    last_message_id = str(link.get("last_message_id", "")).strip()
    session_key = str(link.get("session_key", "")).strip()
    session_files = _candidate_session_files_from_key(session_key) or _candidate_session_files(last_message_id)
    payload: Dict[str, object] = {
        "task_id": task_id,
        "link_path": link.get("_path", ""),
        "session_key": session_key,
        "last_message_id": last_message_id,
        "session_path": "",
        "analysis_window_lines": 0,
        "diagnosis": "none",
        "recommended_action": "continue_current_plan",
        "product_image_count": None,
        "file_input_count": None,
        "evidence": [],
    }
    requirements = _load_business_verification_requirements(task_id)
    payload["business_verification_requirements"] = requirements

    if not session_files:
        _write_json(BROWSER_SIGNALS_ROOT / f"{task_id}.json", payload)
        return payload

    session_path = session_files[0]
    payload["session_path"] = str(session_path)
    lines = session_path.read_text(encoding="utf-8", errors="ignore").splitlines()

    start_index = max(0, len(lines) - 220)
    if last_message_id:
        found_message = False
        for idx, line in enumerate(lines):
            if last_message_id in line:
                start_index = max(0, idx - 120)
                found_message = True
                break
        if not found_message:
            # Manual reroutes and successor tasks may point at the correct session but not at a literal
            # transcript message id. In that case, inspect a larger recent window rather than returning
            # no useful browser evidence.
            start_index = max(0, len(lines) - 320)
    window = lines[start_index:]
    analysis = _analyze_lines(window)
    payload.update(analysis)
    payload["analysis_window_lines"] = len(window)

    live_probe = _collect_live_browser_probe(task_id, window)
    payload["live_probe"] = live_probe
    if live_probe.get("available"):
        payload["live_product_image_count"] = live_probe.get("product_image_count")
        payload["live_file_input_count"] = live_probe.get("file_input_count")
        payload["live_form_valid"] = live_probe.get("form_valid")
        payload["live_invalid_fields"] = live_probe.get("invalid_fields", [])
        payload["live_last_images"] = live_probe.get("last_images", [])
        payload["save_request_succeeded"] = live_probe.get("save_request_succeeded", False)
        payload["save_request_url"] = live_probe.get("save_request_url", "")
        payload["scene_image_count"] = live_probe.get("scene_image_count")
        payload["first_scene_position"] = live_probe.get("first_scene_position")
        payload["scene_image_positions"] = live_probe.get("scene_image_positions", [])
        payload["product_status"] = live_probe.get("product_status", "")
        payload["packing_units_count"] = live_probe.get("packing_units_count")
        payload["packing_units"] = live_probe.get("packing_units", [])
        if live_probe.get("save_request_succeeded"):
            payload["diagnosis"] = "upload_saved_successfully"
            payload["recommended_action"] = "confirm_business_outcome_and_finalize"
            payload["evidence"] = sorted(set([*payload.get("evidence", []), *live_probe.get("evidence", [])]))
            payload["business_outcome"] = {
                "goal_satisfied": True,
                "user_visible_result_confirmed": True,
                "proof_summary": (
                    f"Live browser probe observed seller.neosgo product image save success; "
                    f"product image count is {live_probe.get('product_image_count')}, "
                    f"save request succeeded via {live_probe.get('save_request_url', '') or 'product PATCH'}."
                ),
                "evidence": {
                    "diagnosis": "upload_saved_successfully",
                    "live_product_image_count": live_probe.get("product_image_count"),
                    "live_file_input_count": live_probe.get("file_input_count"),
                    "save_request_succeeded": live_probe.get("save_request_succeeded", False),
                    "save_request_url": live_probe.get("save_request_url", ""),
                    "page_url": live_probe.get("page_url", ""),
                    "evidence": live_probe.get("evidence", []),
                },
            }
        elif live_probe.get("product_image_count") and any(
            "neosgo-prod-" in str(src) and "/products/" in str(src) for src in live_probe.get("last_images", [])
        ):
            payload["diagnosis"] = "upload_persisted_in_product_gallery"
            payload["recommended_action"] = "confirm_business_outcome_and_finalize"
            payload["evidence"] = sorted(
                set(
                    [
                        *payload.get("evidence", []),
                        "live browser probe observed persisted product image in the product gallery after reload",
                    ]
                )
            )
            payload["business_outcome"] = {
                "goal_satisfied": True,
                "user_visible_result_confirmed": True,
                "proof_summary": (
                    f"Live browser probe observed persisted product image in seller.neosgo gallery; "
                    f"product image count is {live_probe.get('product_image_count')} and the gallery includes a saved neosgo-prod product image URL."
                ),
                "evidence": {
                    "diagnosis": "upload_persisted_in_product_gallery",
                    "live_product_image_count": live_probe.get("product_image_count"),
                    "live_last_images": live_probe.get("last_images", []),
                    "page_url": live_probe.get("page_url", ""),
                },
            }
        elif live_probe.get("file_input_count") and live_probe.get("form_valid") is False:
            payload["diagnosis"] = "browser_form_validation_blocking_submit"
            payload["recommended_action"] = "normalize_invalid_numeric_fields_then_resubmit"
            payload["evidence"] = sorted(set([*payload.get("evidence", []), *live_probe.get("evidence", [])]))

    requirements_evaluation = _evaluate_business_requirements(requirements, payload)
    payload["requirements_evaluation"] = requirements_evaluation
    if requirements and requirements_evaluation.get("ok"):
        live_probe = payload.get("live_probe", {}) if isinstance(payload.get("live_probe"), dict) else {}
        payload["diagnosis"] = "business_requirements_satisfied"
        payload["recommended_action"] = "confirm_business_outcome_and_finalize"
        payload["business_outcome"] = {
            "goal_satisfied": True,
            "user_visible_result_confirmed": True,
            "proof_summary": (
                "Live browser probe confirmed seller.neosgo follow-up completion: "
                f"{live_probe.get('scene_image_count')} scene images are present, "
                f"the first scene image is at position {live_probe.get('first_scene_position')}, "
                f"packing units count is {live_probe.get('packing_units_count')}, "
                f"form validity is {live_probe.get('form_valid')}, "
                f"and product status is {live_probe.get('product_status') or 'unknown'}."
            ),
            "evidence": {
                "diagnosis": "business_requirements_satisfied",
                "live_product_image_count": live_probe.get("product_image_count"),
                "scene_image_count": live_probe.get("scene_image_count"),
                "scene_image_positions": live_probe.get("scene_image_positions", []),
                "first_scene_position": live_probe.get("first_scene_position"),
                "packing_units_count": live_probe.get("packing_units_count"),
                "product_status": live_probe.get("product_status", ""),
                "form_valid": live_probe.get("form_valid"),
                "save_request_succeeded": live_probe.get("save_request_succeeded", False),
                "save_request_url": live_probe.get("save_request_url", ""),
                "page_url": live_probe.get("page_url", ""),
                "requirements_evaluation": requirements_evaluation,
            },
        }
    elif requirements and not requirements_evaluation.get("ok"):
        payload.pop("business_outcome", None)
        failure_code = str(requirements_evaluation.get("status", "")).strip()
        if failure_code == "scene_image_not_far_enough_forward":
            payload["diagnosis"] = "scene_images_not_reordered"
            payload["recommended_action"] = "reorder_scene_images_and_confirm_persistence"
        elif failure_code == "scene_image_count_below_target":
            payload["diagnosis"] = "scene_image_count_below_target"
            payload["recommended_action"] = "generate_or_upload_additional_scene_images"
        elif failure_code == "packing_units_below_target":
            payload["diagnosis"] = "packing_unit_missing"
            payload["recommended_action"] = "add_packing_unit_and_save"
        elif failure_code == "review_not_submitted":
            payload["diagnosis"] = "review_not_submitted"
            payload["recommended_action"] = "submit_for_review_after_requirements_met"
        elif failure_code == "form_not_valid":
            payload["diagnosis"] = "browser_form_validation_blocking_submit"
            payload["recommended_action"] = "normalize_invalid_numeric_fields_then_resubmit"

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
