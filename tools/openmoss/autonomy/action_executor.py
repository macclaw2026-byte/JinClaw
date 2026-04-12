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
- 文件路径：`tools/openmoss/autonomy/action_executor.py`
- 文件作用：负责把当前 stage 真正派发给外部执行链，并持续轮询 run 状态再写回任务状态。
- 顶层函数：_resolve_openclaw_bin、_execution_records_dir、_derive_execution_session_key、_write_json、_record_execution、_set_waiting_external_metadata、_batch_execution_should_continue、_summarize_preflight_block、_gateway_call、_dispatch_prompt、_finalize_stage_wait_result、dispatch_stage、poll_active_execution。
- 顶层类：无顶层类。
- 主流程定位：
  1. dispatch_stage：执行前检查、构造执行 prompt、调用 gateway 派发。
  2. poll_active_execution：轮询 run 是否结束、是否 timeout、是否要继续等待。
  3. finalize：在 wait 返回成功后自动推进 stage、运行 verifier，或重新拉回执行。
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import uuid
from pathlib import Path
from typing import Dict

from manager import advance_execute_milestone, apply_hook_effects, build_args, complete_execute_milestones, complete_stage_internal, find_link_by_task_id, infer_link_session_key, load_contract, load_state, log_event, save_state, task_dir, utc_now_iso, verify_task, write_business_outcome
from preflight_engine import run_stage_preflight
from verifier_registry import run_verifier

CONTROL_CENTER_DIR = Path("/Users/mac_claw/.openclaw/workspace/tools/openmoss/control_center")
if str(CONTROL_CENTER_DIR) not in sys.path:
    sys.path.insert(0, str(CONTROL_CENTER_DIR))

from context_builder import build_stage_context
from acp_dispatch_builder import build_acp_dispatch_request
from browser_task_signals import collect_browser_task_signals
from crawler_probe_runner import run_crawler_probe, run_crawler_retro
from task_receipt_engine import emit_route_receipt
from task_status_snapshot import build_task_status_snapshot


def _resolve_openclaw_bin() -> str:
    """
    中文注解：
    - 功能：实现 `_resolve_openclaw_bin` 对应的处理逻辑。
    - 角色：属于本模块中的内部辅助逻辑；私有函数通常服务同文件主流程，公共函数通常作为跨模块入口或能力接口。
    - 调用关系：建议结合本文件的模块说明、调用方以及同名相关辅助函数一起阅读。
    """
    candidates = []
    env_value = (os.environ.get("OPENCLAW_BIN") or "").strip()
    if env_value:
        candidates.append(env_value)
        if "/" not in env_value:
            resolved_env = shutil.which(env_value)
            if resolved_env:
                candidates.append(resolved_env)
    discovered = shutil.which("openclaw")
    if discovered:
        candidates.append(discovered)
    candidates.extend(
        [
            "/opt/homebrew/bin/openclaw",
            "/usr/local/bin/openclaw",
        ]
    )
    for candidate in candidates:
        if candidate and Path(candidate).exists():
            return candidate
    return env_value or "openclaw"


def _execution_records_dir(task_id: str) -> Path:
    """
    中文注解：
    - 功能：实现 `_execution_records_dir` 对应的处理逻辑。
    - 角色：属于本模块中的内部辅助逻辑；私有函数通常服务同文件主流程，公共函数通常作为跨模块入口或能力接口。
    - 调用关系：建议结合本文件的模块说明、调用方以及同名相关辅助函数一起阅读。
    """
    return task_dir(task_id) / "executions"


def _derive_execution_session_key(session_key: str, task_id: str) -> str:
    """
    中文注解：
    - 功能：实现 `_derive_execution_session_key` 对应的处理逻辑。
    - 角色：属于本模块中的内部辅助逻辑；私有函数通常服务同文件主流程，公共函数通常作为跨模块入口或能力接口。
    - 调用关系：建议结合本文件的模块说明、调用方以及同名相关辅助函数一起阅读。
    """
    normalized = str(session_key or "").strip()
    if not normalized:
        return normalized
    return f"{normalized}:autonomy:{task_id}"


def _write_json(path: Path, payload: Dict) -> None:
    """
    中文注解：
    - 功能：实现 `_write_json` 对应的处理逻辑。
    - 角色：属于本模块中的内部辅助逻辑；私有函数通常服务同文件主流程，公共函数通常作为跨模块入口或能力接口。
    - 调用关系：建议结合本文件的模块说明、调用方以及同名相关辅助函数一起阅读。
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _record_execution(task_id: str, payload: Dict) -> str:
    """
    中文注解：
    - 功能：实现 `_record_execution` 对应的处理逻辑。
    - 角色：属于本模块中的内部辅助逻辑；私有函数通常服务同文件主流程，公共函数通常作为跨模块入口或能力接口。
    - 调用关系：建议结合本文件的模块说明、调用方以及同名相关辅助函数一起阅读。
    """
    record_path = _execution_records_dir(task_id) / f"{uuid.uuid4().hex}.json"
    _write_json(record_path, payload)
    return str(record_path)


def _set_waiting_external_metadata(state, *, run_id: str, stage_name: str, reason: str, wait_status: str = "", wait_error: str = "") -> None:
    """
    中文注解：
    - 功能：实现 `_set_waiting_external_metadata` 对应的处理逻辑。
    - 角色：属于本模块中的内部辅助逻辑；私有函数通常服务同文件主流程，公共函数通常作为跨模块入口或能力接口。
    - 调用关系：建议结合本文件的模块说明、调用方以及同名相关辅助函数一起阅读。
    """
    state.metadata["waiting_external"] = {
        "run_id": str(run_id or "").strip(),
        "stage_name": str(stage_name or "").strip(),
        "reason": str(reason or "").strip(),
        "wait_status": str(wait_status or "").strip(),
        "wait_error": str(wait_error or "").strip(),
        "last_polled_at": utc_now_iso(),
    }


def _batch_execution_should_continue(task_id: str) -> Dict | None:
    """
    中文注解：
    - 功能：实现 `_batch_execution_should_continue` 对应的处理逻辑。
    - 角色：属于本模块中的内部辅助逻辑；私有函数通常服务同文件主流程，公共函数通常作为跨模块入口或能力接口。
    - 调用关系：建议结合本文件的模块说明、调用方以及同名相关辅助函数一起阅读。
    """
    contract = load_contract(task_id)
    requirements = contract.metadata.get("control_center", {}).get("business_verification_requirements", {}) or {}
    if requirements.get("batch_listings_mode") is not True:
        return None
    signals = collect_browser_task_signals(task_id)
    diagnosis = str(signals.get("diagnosis", "")).strip()
    recommended_action = str(signals.get("recommended_action", "")).strip()
    if diagnosis in {"draft_listings_remaining", "batch_not_on_listings_overview", "batch_listings_rows_unreadable"}:
        return {"signals": signals, "diagnosis": diagnosis, "recommended_action": recommended_action}
    if recommended_action in {"process_next_draft_listing", "return_to_listings_overview_and_retry_batch_probe"}:
        return {"signals": signals, "diagnosis": diagnosis or "batch_continuation_required", "recommended_action": recommended_action}
    return None


def _summarize_preflight_block(preflight: Dict) -> list[str]:
    """
    中文注解：
    - 功能：实现 `_summarize_preflight_block` 对应的处理逻辑。
    - 角色：属于本模块中的内部辅助逻辑；私有函数通常服务同文件主流程，公共函数通常作为跨模块入口或能力接口。
    - 调用关系：建议结合本文件的模块说明、调用方以及同名相关辅助函数一起阅读。
    """
    result = preflight.get("result", {}) or {}
    entries = list(result.get("results", []) or [])
    blockers: list[str] = []
    for entry in entries:
        status = str(entry.get("status", "")).strip()
        if status == "required_commands_missing":
            missing = ", ".join(entry.get("missing_commands", []) or [])
            blockers.append(f"preflight_missing_commands:{missing or 'unknown'}")
        elif status == "required_paths_missing":
            missing = ", ".join(entry.get("missing_paths", []) or [])
            blockers.append(f"preflight_missing_paths:{missing or 'unknown'}")
        elif status == "writable_paths_blocked":
            blocked = ", ".join(entry.get("blocked_paths", []) or [])
            blockers.append(f"preflight_unwritable_paths:{blocked or 'unknown'}")
        elif status in {"approval_required", "approval_pending"}:
            pending = ", ".join(entry.get("pending_ids", []) or entry.get("declared_pending_ids", []) or [])
            blockers.append(f"preflight_approval_pending:{pending or 'unknown'}")
        elif status:
            blockers.append(f"preflight_{status}")
    if not blockers:
        blockers.append(f"preflight_blocked:{preflight.get('guard_type', 'unknown')}")
    return blockers


def _gateway_call(method: str, params: Dict, timeout_seconds: int = 15) -> Dict:
    """
    中文注解：
    - 功能：实现 `_gateway_call` 对应的处理逻辑。
    - 角色：属于本模块中的内部辅助逻辑；私有函数通常服务同文件主流程，公共函数通常作为跨模块入口或能力接口。
    - 调用关系：建议结合本文件的模块说明、调用方以及同名相关辅助函数一起阅读。
    """
    openclaw_bin = _resolve_openclaw_bin()
    try:
        proc = subprocess.run(
            [
                openclaw_bin,
                "gateway",
                "call",
                method,
                "--params",
                json.dumps(params, ensure_ascii=False),
                "--json",
            ],
            capture_output=True,
            text=True,
            check=False,
            timeout=timeout_seconds,
        )
    except subprocess.TimeoutExpired as exc:
        return {
            "ok": False,
            "method": method,
            "openclaw_bin": openclaw_bin,
            "stderr": f"subprocess timeout after {timeout_seconds}s",
            "stdout": (exc.stdout or "")[-1000:],
        }
    if proc.returncode != 0:
        return {
            "ok": False,
            "method": method,
            "openclaw_bin": openclaw_bin,
            "stderr": proc.stderr[-1000:],
            "stdout": proc.stdout[-1000:],
        }
    return {
        "ok": True,
        "method": method,
        "openclaw_bin": openclaw_bin,
        "response": json.loads(proc.stdout.strip() or "{}"),
    }


def _dispatch_prompt(task_id: str, stage_name: str) -> str:
    """
    中文注解：
    - 功能：把 contract/state/context_builder 的结构化信息拼成真正发给 AI agent 的执行请求。
    - 输入：task_id、stage_name。
    - 输出：一段完整 prompt 文本。
    - 调用关系：dispatch_stage 在真正发消息给 gateway.chat.send 之前必经这里；这一步决定 AI agent 看到的是“结构化执行工单”，而不是原始聊天消息。
    - 集成说明：对于 coding task，这里会消费 control-center -> coding session adapter -> acp dispatch builder，确保 gstack-lite discipline 真正进入 runtime 主执行链。
    """
    contract = load_contract(task_id)
    state = load_state(task_id)
    contract_dict = contract.to_dict()
    stage_context = build_stage_context(task_id, stage_name, contract_dict, state.to_dict())
    stage_contract = next((stage for stage in contract.stages if stage.name == stage_name), None)
    verifier_requirements = stage_contract.verifier if stage_contract and stage_contract.verifier else {}
    prompt_lines = [
        "[Autonomy runtime execution request]",
        f"task_id: {stage_context.get('task_id', task_id)}",
        f"stage: {stage_context.get('stage_name', stage_name)}",
        f"user_goal: {stage_context.get('goal', contract.user_goal)}",
        f"done_definition: {stage_context.get('done_definition', contract.done_definition)}",
        f"stage_goal: {stage_context.get('stage_goal', '')}",
        f"selected_plan: {json.dumps(stage_context.get('selected_plan', {}), ensure_ascii=False)}",
        f"topology_focus: {json.dumps(stage_context.get('topology_focus', {}), ensure_ascii=False)}",
        f"fractal_focus: {json.dumps(stage_context.get('fractal_focus', {}), ensure_ascii=False)}",
        f"htn_focus: {json.dumps(stage_context.get('htn_focus', {}), ensure_ascii=False)}",
        f"subtask_progress: {json.dumps(stage_context.get('subtask_progress', {}), ensure_ascii=False)}",
        f"batch_focus: {json.dumps(stage_context.get('batch_focus', {}), ensure_ascii=False)}",
        f"browser_target_hint: {json.dumps(stage_context.get('browser_target_hint', {}), ensure_ascii=False)}",
        f"crawler: {json.dumps(stage_context.get('crawler', {}), ensure_ascii=False)}",
        f"project_control: {json.dumps(((stage_context.get('governance', {}) or {}).get('project_control', {})), ensure_ascii=False)}",
        f"permission_decision: {json.dumps(((stage_context.get('governance', {}) or {}).get('permission_decision', {})), ensure_ascii=False)}",
        f"governance: {json.dumps(stage_context.get('governance', {}), ensure_ascii=False)}",
        f"execution_summary: {json.dumps(stage_context.get('summary', {}), ensure_ascii=False)}",
        f"allowed_tools: {json.dumps(stage_context.get('allowed_tools', []), ensure_ascii=False)}",
        f"business_verification_requirements: {json.dumps(verifier_requirements, ensure_ascii=False)}",
        "Instruction: this is a background runtime execution request, not a user-facing status conversation.",
        "Instruction: do not reply with a status-only summary before acting. Use approved tools, make the next concrete move, and then report concise verification evidence.",
        "Browser execution rule: do not exceed the global JinClaw browser budget of 3 open tabs for the active task/session.",
        "Browser execution rule: reuse the current working tab whenever possible, and close finished or duplicate tabs before opening more.",
        "Browser execution rule: stability comes before speed when working against live third-party sites.",
        "Browser execution rule: if the target site starts returning robot checks, 'Something went wrong' pages, or suspicious empty states, stop the batch, cool down, and recover a clean browser session instead of forcing progress.",
        "Browser execution rule: if repeated browser recovery attempts keep failing on the same live-site step, stop repeating the same browser-only tactic and switch to another available technical route such as direct HTTP, a verified API, or a hybrid collector.",
    ]
    batch_focus = stage_context.get("batch_focus", {}) or {}
    normalized_goal = str(stage_context.get("goal", contract.user_goal) or "").lower()
    # 下面这些附加规则不是通用提示词噪音，而是 runtime 在已知高风险业务域上
    # 给 agent 增加的“硬约束补丁”，用于压住会重复出现的错误行为。
    if "seller.neosgo" in normalized_goal or "neosgo" in normalized_goal or "seller" in normalized_goal:
        prompt_lines.extend(
            [
                "Browser execution rule: use the existing seller.neosgo host browser chain, not a fresh local browser profile.",
                "Browser execution rule: prefer browser tool calls with target=host and profile=chrome-relay for seller.neosgo work.",
                "Browser execution rule: if the previous target id is stale, reacquire a current chrome-relay tab for seller.neosgo before continuing.",
                "Do not switch to a generic local Chrome profile when the task depends on the already logged-in seller.neosgo session.",
            ]
        )
    if batch_focus.get("force_listings_overview"):
        prompt_lines.extend(
            [
                "Mandatory batch step: before any per-product work, return to the Listings overview page and confirm the page URL is the overview, not a single-product edit page.",
                f"Listings overview URL: {batch_focus.get('expected_listings_url', 'https://seller.neosgo.com/seller/products')}",
                "If you are still on a single-product page, navigate back to Listings overview first, re-read the visible Draft rows, and only then continue with the next Draft listing.",
                "Do not claim batch progress or completion from a single-product edit page.",
            ]
        )
    next_draft = batch_focus.get("next_draft", {}) or {}
    if next_draft:
        prompt_lines.extend(
            [
                f"Next draft listing sku: {next_draft.get('sku', '')}",
                f"Next draft listing edit URL: {next_draft.get('editHref', '')}",
                "After confirming you are on Listings overview, open exactly this next draft listing before doing any other seller action.",
            ]
        )
    if batch_focus and ("seller.neosgo" in normalized_goal or "neosgo" in normalized_goal):
        prompt_lines.extend(
            [
                "Seller workflow browser rule: prefer keeping seller.neosgo work inside one working tab whenever possible.",
                "Seller workflow browser rule: do not intentionally open a new tab for each Draft listing edit page.",
                "Seller workflow browser rule: prefer navigate(current tab, editHref) over clicking a link that may open target=_blank.",
                "Seller workflow browser rule: stay within the global 3-tab browser budget, and close older or duplicate seller.neosgo tabs after each listing is processed.",
                "After finishing a listing, return the surviving working tab to Listings overview before selecting the next Draft.",
            ]
        )
    browser_target_hint = stage_context.get("browser_target_hint", {}) or {}
    last_nav = browser_target_hint.get("last_listings_overview_navigation", {}) or {}
    last_nav_context = last_nav.get("context", {}) or {}
    hinted_target = str(last_nav_context.get("target_id", "") or browser_target_hint.get("last_browser_channel_recovery", {}).get("target_id", "") or "").strip()
    hinted_url = str(last_nav_context.get("page_url", "") or browser_target_hint.get("last_browser_channel_recovery", {}).get("page_url", "") or "").strip()
    if hinted_target or hinted_url:
        prompt_lines.extend(
            [
                f"Recovered browser target hint: {hinted_target or 'unknown'}",
                f"Recovered browser page hint: {hinted_url or 'unknown'}",
                "Prefer this recovered target/page hint first when reattaching browser control, instead of relying on stale prior tab focus.",
            ]
        )
    if batch_focus and ("seller.neosgo" in normalized_goal or "neosgo" in normalized_goal):
        prompt_lines.extend(
            [
                "Batch seller workflow for each Draft listing:",
                "1. Open the next Draft listing edit page.",
                "2. Ensure at least 3 scene images exist and the first 3 image positions are scene images.",
                "3. Ensure Packing Unit is valid and saved (at minimum one unit with valid numeric dimensions/quantity).",
                "4. Submit the listing for review and confirm the status is no longer DRAFT.",
                "5. Return to Listings overview and continue with the next visible Draft listing.",
                "Do not stop because 'previous task requirements are unclear' — use the workflow above as the authoritative per-listing checklist.",
                "If a browser act/evaluate/snapshot call returns 'tab not found', immediately reacquire the current seller.neosgo tab via tabs and retry the same step instead of replying with a blocker summary.",
                "Prefer DOM evaluate/act on the Listings page over aria snapshot when chrome-relay snapshot is unstable.",
            ]
        )
    base_prompt = "\n".join(prompt_lines)
    dispatch_request = build_acp_dispatch_request(
        {
            'user_goal': contract.user_goal,
            'done_definition': contract.done_definition,
            'allowed_tools': contract.allowed_tools,
            'stages': contract_dict.get('stages', []),
            'metadata': contract_dict.get('metadata', {}),
        },
        stage_context,
    )
    if dispatch_request.get('prompt_components', {}).get('methodology_prompt_included'):
        final_prompt = dispatch_request.get('prompt', '').strip()
        if final_prompt:
            return final_prompt
    return base_prompt


def _finalize_stage_wait_result(task_id: str, stage_name: str, result: Dict, record_path: str) -> Dict:
    """
    中文注解：
    - 功能：实现 `_finalize_stage_wait_result` 对应的处理逻辑。
    - 角色：属于本模块中的内部辅助逻辑；私有函数通常服务同文件主流程，公共函数通常作为跨模块入口或能力接口。
    - 调用关系：建议结合本文件的模块说明、调用方以及同名相关辅助函数一起阅读。
    """
    state = load_state(task_id)
    stage = state.stages.get(stage_name)
    if stage:
        stage.last_execution_status = result["status"]
    state.metadata.pop("active_execution", None)
    save_state(state)

    contract = load_contract(task_id)
    stage_contract = next((stage for stage in contract.stages if stage.name == stage_name), None)
    if (
        result.get("ok")
        and result.get("status") == "completed"
        and stage_contract
    ):
        strict_continuation = bool(contract.metadata.get("control_center", {}).get("strict_continuation_required"))
        if stage_name == "execute" and strict_continuation:
            milestone_progress = advance_execute_milestone(
                task_id,
                summary=f"execute cycle completed for stage {stage_name}",
            )
            result["milestone_progress"] = milestone_progress
            if _should_emit_milestone_progress_notice(task_id, milestone_progress):
                _emit_milestone_progress_notice(task_id, milestone_progress)
            if not milestone_progress.get("stage_complete"):
                state = load_state(task_id)
                stage = state.stages.get(stage_name)
                stage.status = "running"
                stage.blocker = ""
                stage.updated_at = utc_now_iso()
                state.status = "planning"
                state.current_stage = stage_name
                state.next_action = f"start_stage:{stage_name}"
                state.blockers = []
                state.last_update_at = utc_now_iso()
                save_state(state)
                log_event(task_id, "stage_continues_via_milestone_progress", stage=stage_name, milestone_progress=milestone_progress, record_path=record_path)
                return result
            completion = complete_stage_internal(
                task_id=task_id,
                stage_name=stage_name,
                summary=f"All execute milestones completed for stage {stage_name}",
                evidence_ref=record_path,
            )
            result["auto_completed"] = completion
            return result
        if bool(stage_contract.execution_policy.get("require_verifier_before_complete", False)) and stage_contract.verifier:
            verification = run_verifier(stage_contract.verifier)
            result["completion_verifier"] = verification
            if not verification.get("ok"):
                continuation = _batch_execution_should_continue(task_id)
                if continuation:
                    stage.verification_status = verification["status"]
                    stage.status = "running"
                    stage.blocker = ""
                    stage.updated_at = utc_now_iso()
                    state.status = "planning"
                    state.current_stage = stage_name
                    state.next_action = f"start_stage:{stage_name}"
                    state.blockers = []
                    state.last_update_at = utc_now_iso()
                    save_state(state)
                    log_event(
                        task_id,
                        "batch_execution_continues_after_partial_progress",
                        stage=stage_name,
                        verifier=verification,
                        diagnosis=continuation["diagnosis"],
                        recommended_action=continuation["recommended_action"],
                        record_path=record_path,
                    )
                    result["continuation"] = continuation
                    return result
                stage.verification_status = verification["status"]
                stage.status = "failed"
                stage.blocker = f"business verification failed: {verification['status']}"
                stage.updated_at = utc_now_iso()
                state.status = "recovering"
                state.current_stage = stage_name
                state.next_action = "repair_verification_failure"
                state.blockers = [f"business_verification_failed:{verification['status']}"]
                state.last_update_at = utc_now_iso()
                save_state(state)
                log_event(task_id, "stage_completion_blocked_by_verifier", stage=stage_name, verifier=verification, record_path=record_path)
                return result
        if bool(stage_contract.execution_policy.get("auto_complete_on_wait_ok", False)):
            completion = complete_stage_internal(
                task_id=task_id,
                stage_name=stage_name,
                summary=f"OpenClaw run completed successfully for stage {stage_name}",
                evidence_ref=record_path,
            )
            result["auto_completed"] = completion
            refreshed_contract = load_contract(task_id)
            next_stage_name = completion.get("next_action", "").replace("start_stage:", "")
            next_stage = next((stage for stage in refreshed_contract.stages if stage.name == next_stage_name), None)
            if next_stage and next_stage.name == "verify" and next_stage.verifier:
                verify_result = verify_task(build_args(task_id=task_id))
                result["post_completion_verify"] = {"exit_code": verify_result}
            return result

        state.status = "running"
        state.current_stage = stage_name
        state.next_action = f"execute_stage:{stage_name}"
        state.last_update_at = utc_now_iso()
        save_state(state)
        return result
    return result


def _should_emit_milestone_progress_notice(task_id: str, milestone_progress: Dict) -> bool:
    """
    中文注解：
    - 功能：判断当前 milestone 推进是否属于“关键节点”，只有关键节点才主动播报。
    - 设计意图：降低长任务的通知密度，避免每个小步都刷消息。
    - 当前规则：
      - 第一个 execute milestone 完成时播报；
      - 最后一个 execute milestone 完成时播报；
      - required 里程碑跨过 25% / 50% / 75% / 100% 档位时播报。
    """
    if not milestone_progress.get("advanced"):
        return False
    state = load_state(task_id)
    stats = state.metadata.get("milestone_stats", {}) or milestone_progress.get("milestone_stats", {}) or {}
    required_total = int(stats.get("required_total", 0) or 0)
    required_completed = int(stats.get("required_completed", 0) or 0)
    remaining_execute = int(milestone_progress.get("remaining_execute_milestones", 0) or 0)
    if required_total <= 0:
        return True
    if required_completed <= 1:
        return True
    if remaining_execute == 0 or bool(milestone_progress.get("stage_complete")):
        return True
    current_bucket = min(4, (required_completed * 4) // max(required_total, 1))
    last_bucket = int(state.metadata.get("last_notified_milestone_bucket", -1) or -1)
    return current_bucket > last_bucket and current_bucket >= 1


def _emit_milestone_progress_notice(task_id: str, milestone_progress: Dict) -> Dict:
    """
    中文注解：
    - 功能：在 execute 里程碑真实前进时，向当前绑定聊天渠道发一条主动进展通知。
    - 设计意图：只在 milestone 真正完成时播报一次，避免 poll/wait 周期反复刷屏。
    """
    milestone_id = str(milestone_progress.get("milestone_id", "")).strip()
    if not milestone_id:
        return {"delivered": False, "reason": "missing_milestone_id"}
    state = load_state(task_id)
    if str(state.metadata.get("last_notified_milestone_id", "")).strip() == milestone_id:
        return {"delivered": False, "reason": "already_notified", "milestone_id": milestone_id}
    stats = state.metadata.get("milestone_stats", {}) or milestone_progress.get("milestone_stats", {}) or {}
    required_total = int(stats.get("required_total", 0) or 0)
    required_completed = int(stats.get("required_completed", 0) or 0)
    current_bucket = min(4, (required_completed * 4) // max(required_total, 1)) if required_total > 0 else -1
    link = find_link_by_task_id(task_id)
    if not link:
        return {"delivered": False, "reason": "link_not_found", "milestone_id": milestone_id}
    provider = str(link.get("provider", "")).strip() or "openclaw-main"
    conversation_id = str(link.get("conversation_id", "")).strip()
    if not conversation_id:
        return {"delivered": False, "reason": "conversation_id_missing", "milestone_id": milestone_id}
    snapshot = build_task_status_snapshot(task_id)
    route = {
        "mode": "milestone_progress_notice",
        "task_id": task_id,
        "goal": str(link.get("goal", "")).strip(),
        "authoritative_task_status": snapshot,
        "milestone_notice": {
            "milestone_id": milestone_id,
            "title": str(milestone_progress.get("title", "")).strip(),
            "remaining_execute_milestones": milestone_progress.get("remaining_execute_milestones"),
        },
    }
    receipt = emit_route_receipt(
        route,
        provider=provider,
        conversation_id=conversation_id,
        session_key=str(link.get("session_key", "") or infer_link_session_key(link)).strip(),
    )
    state = load_state(task_id)
    state.metadata["last_notified_milestone_id"] = milestone_id
    state.metadata["last_notified_milestone_at"] = utc_now_iso()
    state.metadata["last_notified_milestone_bucket"] = current_bucket
    state.last_update_at = utc_now_iso()
    save_state(state)
    log_event(task_id, "milestone_progress_notice_sent", milestone_id=milestone_id, delivered=bool(receipt.get("delivery", {}).get("delivered")))
    return receipt


def _build_crawler_business_outcome(task_id: str, artifacts: Dict[str, Dict], summary: str) -> Dict:
    """
    中文注解：
    - 功能：把 crawler 执行结果同步成业务层证据和可交付附件。
    """
    coverage = artifacts.get("coverage", {}) or {}
    goal_satisfied = bool(coverage.get("all_sites_attempted"))
    evidence = {
        "crawler_report_path": artifacts.get("report_json_path", ""),
        "crawler_report_markdown_path": artifacts.get("report_md_path", ""),
        "crawler_required_sites": artifacts.get("required_sites", []),
        "crawler_required_tools": artifacts.get("required_tools", []),
        "crawler_coverage": coverage,
        "attachments": [artifacts.get("report_md_path", ""), artifacts.get("report_json_path", "")],
    }
    return write_business_outcome(
        task_id,
        goal_satisfied=goal_satisfied,
        user_visible_result_confirmed=goal_satisfied,
        proof_summary=summary,
        evidence=evidence,
    )


def _persist_crawler_execution_metadata(task_id: str, payload: Dict) -> None:
    state = load_state(task_id)
    execution = state.metadata.get("crawler_execution", {}) or {}
    execution.update(payload)
    state.metadata["crawler_execution"] = execution
    artifacts = [
        str(item)
        for item in [
            execution.get("report_md_path", ""),
            execution.get("report_json_path", ""),
            execution.get("retro_md_path", ""),
            execution.get("retro_json_path", ""),
            execution.get("evolution_json_path", ""),
        ]
        if str(item).strip()
    ]
    if artifacts:
        state.metadata["output_artifacts"] = sorted(dict.fromkeys(artifacts))
        state.metadata["delivery_artifacts"] = sorted(dict.fromkeys(artifacts))
    state.last_update_at = utc_now_iso()
    save_state(state)


def _run_local_crawler_stage(task_id: str, stage_name: str) -> Dict | None:
    """
    中文注解：
    - 功能：对特定 crawler 任务直接在本地执行，而不是仅仅把请求发给外部 agent。
    - 当前覆盖：多站点矩阵测试和单站点自适应抓取验证；统一产出 crawler 报告、retro 与学习工件。
    """
    contract = load_contract(task_id)
    crawler = contract.metadata.get("control_center", {}).get("crawler", {}) or {}
    if not bool(crawler.get("enabled")):
        return None
    if str(crawler.get("execution_mode", "")).strip() not in {"site_tool_matrix_probe", "adaptive_fetch", "adaptive_research_crawl"}:
        return None

    if stage_name == "execute":
        artifacts = run_crawler_probe(task_id, contract.user_goal, crawler)
        _persist_crawler_execution_metadata(task_id, artifacts)
        complete_execute_milestones(task_id, summary="crawler matrix probe completed")
        business_outcome = _build_crawler_business_outcome(
            task_id,
            artifacts,
            summary=(
                f"Completed crawler matrix probe for sites {', '.join(artifacts.get('required_sites', []))} "
                f"with tools {', '.join(artifacts.get('required_tools', []))}."
            ),
        )
        completion = complete_stage_internal(
            task_id=task_id,
            stage_name=stage_name,
            summary="Crawler matrix probe completed with structured report artifacts.",
            evidence_ref=str(artifacts.get("report_json_path", "")),
        )
        result = {
            "ok": True,
            "status": "completed",
            "stage": stage_name,
            "local_crawler": True,
            "artifacts": artifacts,
            "business_outcome": business_outcome,
            "auto_completed": completion,
        }
        log_event(task_id, "local_crawler_execute_completed", stage=stage_name, artifacts=artifacts, business_outcome=business_outcome)
        next_stage_name = str(completion.get("next_action", "")).replace("start_stage:", "")
        refreshed_contract = load_contract(task_id)
        next_stage = next((stage for stage in refreshed_contract.stages if stage.name == next_stage_name), None)
        if next_stage and next_stage.name == "verify" and next_stage.verifier:
            result["post_completion_verify"] = {"exit_code": verify_task(build_args(task_id=task_id))}
        return result

    if stage_name == "learn":
        state = load_state(task_id)
        execution = state.metadata.get("crawler_execution", {}) or {}
        retro = run_crawler_retro(task_id, contract.user_goal, crawler, execution)
        _persist_crawler_execution_metadata(task_id, retro)
        completion = complete_stage_internal(
            task_id=task_id,
            stage_name=stage_name,
            summary="Crawler retro, site preference learning, and evolution artifacts were persisted.",
            evidence_ref=str(retro.get("retro_json_path", "")),
        )
        result = {
            "ok": True,
            "status": "completed",
            "stage": stage_name,
            "local_crawler": True,
            "retro": retro,
            "auto_completed": completion,
            "post_completion_verify": {"exit_code": verify_task(build_args(task_id=task_id))},
        }
        log_event(task_id, "local_crawler_learn_completed", stage=stage_name, retro=retro)
        return result

    return None


def dispatch_stage(task_id: str) -> Dict:
    """
    中文注解：
    - 功能：真正执行“派发当前 stage”这件事。
    - 子步骤：
      1. 找到 task 当前 stage 和绑定会话；
      2. 运行 preflight；
      3. 构造 prompt 并通过 gateway.chat.send 发给 AI agent；
      4. 写入 active_execution / waiting_external；
      5. 先做一次短 wait，尽量快速拿到结果。
    - 调用关系：runtime_service 在 `execute_stage:*` 状态下会调用这里。
    """
    state = load_state(task_id)
    stage_name = state.current_stage
    if not stage_name:
        return {"ok": False, "status": "no_current_stage"}

    local_crawler_result = _run_local_crawler_stage(task_id, stage_name)
    if local_crawler_result is not None:
        return local_crawler_result

    link = find_link_by_task_id(task_id)
    linked_session_key = str(link.get("session_key", "")).strip() or infer_link_session_key(link)
    if not linked_session_key:
        return {"ok": False, "status": "no_bound_session"}
    session_key = _derive_execution_session_key(linked_session_key, task_id)

    active = state.metadata.get("active_execution", {})
    if active.get("stage_name") == stage_name and active.get("run_id"):
        return {"ok": True, "status": "already_waiting", "session_key": session_key, "run_id": active.get("run_id")}

    dispatch_marker = f"{task_id}:{stage_name}"
    if state.metadata.get("last_dispatched_marker") == dispatch_marker and not active:
        return {"ok": True, "status": "already_dispatched", "session_key": session_key}

    # preflight 是执行前的总闸门：
    # 这里会综合审批、命令、路径、promoted rule 等信息，判断“现在这一步能不能安全开工”。
    preflight = run_stage_preflight(task_id, stage_name)
    hook_events = preflight.get("hook_event", {}) or {}
    hook_effects = {}
    for hook_source, event_payload in hook_events.items():
        hook_effects[hook_source] = apply_hook_effects(task_id, event_payload, source=f"preflight:{hook_source}")
    if preflight.get("status") != "no_preflight_needed" and preflight.get("status") != "no_promoted_rule":
        state = load_state(task_id)
        hook_attention = ((state.metadata.get("last_hook_effects", {}) or {}).get("preflight:pre_execute", {}) or {})
        state.metadata["last_preflight"] = {
            "stage_name": stage_name,
            "ran_at": utc_now_iso(),
            "status": preflight.get("status"),
            "action": preflight.get("action", ""),
            "result": preflight.get("result", {}),
            "hook_attention": hook_attention,
            "hook_effects": hook_effects,
        }
        stage = state.stages.get(stage_name)
        if stage:
            stage.updated_at = utc_now_iso()
        state.last_update_at = utc_now_iso()
        save_state(state)
        log_event(task_id, "stage_preflight_ran", stage=stage_name, preflight=preflight)
    if not preflight.get("ok", True):
        state = load_state(task_id)
        hook_attention = ((state.metadata.get("last_hook_effects", {}) or {}).get("preflight:pre_execute", {}) or {})
        state.status = "recovering"
        state.next_action = str((hook_attention.get("next_actions", []) or [preflight.get("action") or "run_root_cause_review_before_retry"])[0])
        state.blockers = _summarize_preflight_block(preflight)
        state.blockers.extend([f"hook_warning:{item}" for item in hook_attention.get("warnings", []) if item])
        state.blockers = list(dict.fromkeys(state.blockers))
        state.last_update_at = utc_now_iso()
        current_stage = state.stages.get(stage_name)
        if current_stage:
            current_stage.blocker = "; ".join(state.blockers)
            current_stage.updated_at = utc_now_iso()
        save_state(state)
        result = {
            "ok": False,
            "status": "preflight_blocked",
            "session_key": session_key,
            "preflight": preflight,
        }
        record_path = _record_execution(task_id, result)
        result["record_path"] = record_path
        log_event(task_id, "stage_dispatch_blocked_by_preflight", stage=stage_name, result=result, link_path=link.get("_path"))
        return result

    # 真正把执行请求送给外部 AI agent 的时刻在这里。
    # 从这一行开始，任务会进入 active_execution / waiting_external 生命周期。
    send_result = _gateway_call(
        "chat.send",
        {
            "idempotencyKey": uuid.uuid4().hex,
            "sessionKey": session_key,
            "message": _dispatch_prompt(task_id, stage_name),
            "timeoutMs": 30000,
        },
    )
    if not send_result.get("ok"):
        result = {
            "ok": False,
            "status": "dispatch_failed",
            "session_key": session_key,
            "stderr": send_result.get("stderr", ""),
            "stdout": send_result.get("stdout", ""),
        }
        record_path = _record_execution(task_id, result)
        result["record_path"] = record_path
        log_event(task_id, "stage_dispatch_attempted", stage=stage_name, result=result, link_path=link.get("_path"))
        return result

    response = send_result.get("response", {})
    run_id = response.get("runId", "")
    result = {
        "ok": True,
        "status": "dispatched",
        "session_key": session_key,
        "response": response,
        "preflight": preflight,
    }

    state.metadata["last_dispatched_marker"] = dispatch_marker
    state.metadata["last_dispatch_at"] = utc_now_iso()
    state.metadata["last_execution_session_key"] = session_key
    state.metadata["active_execution"] = {
        "run_id": run_id,
        "stage_name": stage_name,
        "session_key": session_key,
        "linked_session_key": linked_session_key,
        "dispatched_at": utc_now_iso(),
    }
    state.status = "waiting_external"
    state.next_action = f"poll_run:{run_id}" if run_id else f"poll_stage:{stage_name}"
    _set_waiting_external_metadata(
        state,
        run_id=run_id,
        stage_name=stage_name,
        reason="dispatched_waiting_for_agent_completion",
    )
    state.last_update_at = utc_now_iso()
    stage = state.stages.get(stage_name)
    if stage:
        stage.last_execution_status = "dispatched"
        stage.updated_at = utc_now_iso()
    save_state(state)

    wait_result = _gateway_call("agent.wait", {"runId": run_id, "timeoutMs": 1000}, timeout_seconds=8) if run_id else {"ok": False}
    if wait_result.get("ok"):
        wait_response = wait_result.get("response", {})
        result["wait"] = wait_response
        if wait_response.get("status") == "ok":
            result["status"] = "completed"
        else:
            result["status"] = "waiting_external"
    else:
        result["wait_error"] = wait_result.get("stderr", "") or wait_result.get("stdout", "")
        result["status"] = "waiting_external"

    record_path = _record_execution(task_id, result)
    result["record_path"] = record_path
    log_event(task_id, "stage_dispatch_attempted", stage=stage_name, result=result, link_path=link.get("_path"))
    if result.get("status") == "completed":
        return _finalize_stage_wait_result(task_id, stage_name, result, record_path)
    return result


def poll_active_execution(task_id: str) -> Dict:
    """
    中文注解：
    - 功能：轮询一个已经派发出去的 run，并把“还在等 / 已完成 / 需要切换 verifier”这些结果写回 state。
    - 关键点：
      - `waiting_external` 不是空闲，而是这里持续维护的等待态。
      - 只有 run 真正结束或被判定为 stale，runtime 才会离开这条轮询链。
    - 调用关系：runtime_service 在看到 `waiting_external` 或 `poll_run:*` 时会调用这里。
    """
    state = load_state(task_id)
    active = state.metadata.get("active_execution", {})
    run_id = active.get("run_id", "")
    stage_name = active.get("stage_name", state.current_stage)
    if not run_id or not stage_name:
        return {"ok": False, "status": "no_active_execution"}

    contract = load_contract(task_id)
    current_stage_contract = next((stage for stage in contract.stages if stage.name == stage_name), None)
    if stage_name == "verify" and current_stage_contract and current_stage_contract.verifier:
        state.metadata.pop("active_execution", None)
        state.status = "running"
        state.next_action = f"execute_stage:{stage_name}"
        state.last_update_at = utc_now_iso()
        save_state(state)
        result = {
            "ok": True,
            "status": "verify_handoff_to_structured_verifier",
            "run_id": run_id,
            "stage": stage_name,
        }
        record_path = _record_execution(task_id, result)
        result["record_path"] = record_path
        log_event(task_id, "verify_handoff_to_structured_verifier", stage=stage_name, result=result)
        return result

    tracked_stage = state.stages.get(stage_name)
    if tracked_stage and tracked_stage.status == "completed" and state.current_stage != stage_name:
        state.metadata.pop("active_execution", None)
        if state.current_stage:
            state.status = "running"
            state.next_action = f"execute_stage:{state.current_stage}"
        else:
            state.status = "verifying"
            state.next_action = "verify_done_definition"
        state.last_update_at = utc_now_iso()
        save_state(state)
        result = {
            "ok": True,
            "status": "stale_execution_cleared",
            "run_id": run_id,
            "stage": stage_name,
            "advanced_to": state.current_stage,
        }
        record_path = _record_execution(task_id, result)
        result["record_path"] = record_path
        log_event(task_id, "stale_execution_cleared", stage=stage_name, result=result)
        return result

    # agent.wait 是 runtime 判定“外部执行还活着还是已经结束”的唯一事实来源之一。
    # 如果这里一直 timeout，但又没有新的真实进展，doctor / progress_evidence 就会把它识别成假等待。
    wait_result = _gateway_call("agent.wait", {"runId": run_id, "timeoutMs": 1000}, timeout_seconds=8)
    if not wait_result.get("ok"):
        result = {
            "ok": True,
            "status": "waiting_external",
            "run_id": run_id,
            "stage": stage_name,
            "wait_error": wait_result.get("stderr", "") or wait_result.get("stdout", ""),
        }
    else:
        wait_response = wait_result.get("response", {})
        if wait_response.get("status") == "ok":
            result = {
                "ok": True,
                "status": "completed",
                "run_id": run_id,
                "stage": stage_name,
                "wait": wait_response,
            }
        else:
            result = {
                "ok": True,
                "status": "waiting_external",
                "run_id": run_id,
                "stage": stage_name,
                "wait": wait_response,
            }

    stage = state.stages.get(stage_name)
    if stage:
        stage.last_execution_status = result["status"]
        stage.updated_at = utc_now_iso()
    if result["status"] == "waiting_external":
        state.status = "waiting_external"
        state.next_action = f"poll_run:{run_id}"
        _set_waiting_external_metadata(
            state,
            run_id=run_id,
            stage_name=stage_name,
            reason="agent_wait_timeout" if str((result.get("wait", {}) or {}).get("status", "")).strip() == "timeout" else "waiting_for_agent_completion",
            wait_status=str((result.get("wait", {}) or {}).get("status", "")).strip(),
            wait_error=str(result.get("wait_error", "")).strip(),
        )
        state.last_update_at = utc_now_iso()
        save_state(state)
        record_path = _record_execution(task_id, result)
        result["record_path"] = record_path
        log_event(task_id, "stage_execution_polled", stage=stage_name, result=result)
        return result

    record_path = _record_execution(task_id, result)
    result["record_path"] = record_path
    log_event(task_id, "stage_execution_polled", stage=stage_name, result=result)
    state.metadata.pop("waiting_external", None)
    save_state(state)
    return _finalize_stage_wait_result(task_id, stage_name, result, record_path)
