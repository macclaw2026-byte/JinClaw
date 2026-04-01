#!/usr/bin/env python3

"""
中文说明：
- 文件路径：`tools/openmoss/control_center/brain_router.py`
- 文件作用：负责把聊天入口收到的自然语言指令，翻译成“应该挂到哪个任务、是否要切根、是否只返回状态”的路由结果。
- 顶层函数：_is_internal_runtime_request_text、_write_json、_strip_transport_wrapper、_looks_actionable、_looks_like_status_query、_looks_like_followup_goal、_safe_load_contract、_safe_load_state、_task_predecessor、_lineage_root_task_id、_task_created_at、_lineage_task_ids、_find_active_lineage_task、_next_successor_task_id、_mark_task_superseded、_clear_task_superseded、_resolve_linked_active_task_id、_normalize_goal_text、_should_branch_from_active_task、_build_task、_task_matches_root_mission_profile、route_instruction、main。
- 顶层类：无顶层类。
- 主流程定位：
  1. 先清洗聊天文本，去掉 transport wrapper 和运行时提示包装。
  2. 再做意图分析，判断这是“动作型任务”还是“状态查询”。
  3. 结合当前会话 link、mission profile、lineage 状态决定是：
     - 挂到已有任务
     - 创建新的 root mission
     - 创建 successor
     - 仅返回权威状态
  4. 最后把路由结果和 link 一起写回，让后续 runtime 能接着跑。
"""
from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List

from intent_analyzer import analyze_intent
from mission_profiles import detect_root_mission_profile
from orchestrator import build_control_center_package
from paths import BRAIN_ROUTES_ROOT
from task_status_snapshot import build_task_status_snapshot

AUTONOMY_DIR = Path("/Users/mac_claw/.openclaw/workspace/tools/openmoss/autonomy")
import sys

if str(AUTONOMY_DIR) not in sys.path:
    sys.path.insert(0, str(AUTONOMY_DIR))

from manager import TASKS_ROOT, build_args, contract_path, create_task, load_contract, load_state, log_event, read_link, save_state, state_path, utc_now_iso, write_link
from task_ingress import slugify


ACTION_PATTERNS = (
    "请",
    "帮我",
    "需要",
    "生成",
    "制作",
    "上传",
    "分析",
    "抓取",
    "研究",
    "登录",
    "打开",
    "继续",
    "自动",
    "修复",
    "搭建",
    "install",
    "build",
    "generate",
    "upload",
    "analyze",
    "scrape",
    "research",
    "continue",
    "fix",
)

STATUS_QUERY_PATTERNS = (
    "进展",
    "进度",
    "状态",
    "结果",
    "做得怎么样",
    "做的怎么样",
    "怎么样了",
    "如何了",
    "搞定没",
    "搞定了吗",
    "完成了吗",
    "完成没有",
    "有没有解决",
    "解决了吗",
    "现在怎么样",
    "现在如何",
    "现在呢",
    "跑通了吗",
    "闭环",
    "情况",
    "progress",
    "status",
    "result",
    "solved",
    "working",
    "complete",
    "completed",
)

FOLLOW_UP_ACTION_PATTERNS = (
    "继续",
    "继续推进",
    "接着",
    "下一步",
    "后续",
    "剩下",
    "把这",
    "把剩下",
    "补到",
    "补齐",
    "提审",
    "提交审核",
    "排到",
    "排到前",
    "搞定",
    "完成剩余",
    "不要停止",
    "直到",
    "做完",
    "finish",
    "remaining",
    "follow-up",
    "followup",
    "continue",
)

TERMINAL_TASK_STATUSES = {"completed", "failed"}


def _is_internal_runtime_request_text(text: str) -> bool:
    """
    中文注解：
    - 功能：实现 `_is_internal_runtime_request_text` 对应的处理逻辑。
    - 角色：属于本模块中的内部辅助逻辑；私有函数通常服务同文件主流程，公共函数通常作为跨模块入口或能力接口。
    - 调用关系：建议结合本文件的模块说明、调用方以及同名相关辅助函数一起阅读。
    """
    normalized = text.strip()
    return (
        "[Autonomy runtime execution request]" in normalized
        and "task_id:" in normalized
        and "stage:" in normalized
        and "user_goal:" in normalized
    )


def _write_json(path: Path, payload: object) -> str:
    """
    中文注解：
    - 功能：实现 `_write_json` 对应的处理逻辑。
    - 角色：属于本模块中的内部辅助逻辑；私有函数通常服务同文件主流程，公共函数通常作为跨模块入口或能力接口。
    - 调用关系：建议结合本文件的模块说明、调用方以及同名相关辅助函数一起阅读。
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return str(path)


def _strip_transport_wrapper(text: str) -> str:
    """
    中文注解：
    - 功能：实现 `_strip_transport_wrapper` 对应的处理逻辑。
    - 角色：属于本模块中的内部辅助逻辑；私有函数通常服务同文件主流程，公共函数通常作为跨模块入口或能力接口。
    - 调用关系：建议结合本文件的模块说明、调用方以及同名相关辅助函数一起阅读。
    """
    cleaned = text
    cleaned = re.sub(r"Conversation info \(untrusted metadata\):\s*```[\s\S]*?```", "", cleaned, flags=re.MULTILINE)
    cleaned = re.sub(r"Sender \(untrusted metadata\):\s*```[\s\S]*?```", "", cleaned, flags=re.MULTILINE)
    cleaned = re.sub(r"Replied message \(untrusted, for context\):\s*```[\s\S]*?```", "", cleaned, flags=re.MULTILINE)
    cleaned = re.sub(r"^\[[^\]]+\]\s*", "", cleaned).strip()
    runtime_match = re.search(
        r"\[Autonomy runtime execution request\][\s\S]*?user_goal:\s*(.+?)\n(?:done_definition:|stage_goal:|selected_plan:)",
        cleaned,
        flags=re.MULTILINE,
    )
    if runtime_match:
        extracted_goal = runtime_match.group(1).strip()
        if extracted_goal:
            cleaned = extracted_goal
    lines = [line.strip() for line in cleaned.splitlines() if line.strip()]
    if lines:
        return "\n".join(lines)
    return text.strip()


def _looks_actionable(text: str, intent: Dict[str, object]) -> bool:
    """
    中文注解：
    - 功能：实现 `_looks_actionable` 对应的处理逻辑。
    - 角色：属于本模块中的内部辅助逻辑；私有函数通常服务同文件主流程，公共函数通常作为跨模块入口或能力接口。
    - 调用关系：建议结合本文件的模块说明、调用方以及同名相关辅助函数一起阅读。
    """
    normalized = text.strip()
    lowered = normalized.lower()
    if not normalized:
        return False
    if len(normalized) >= 24:
        return True
    if any(token in lowered for token in ACTION_PATTERNS):
        return True
    if any(intent.get(key) for key in ("requires_external_information", "needs_browser", "may_download_artifacts", "may_execute_external_code")):
        return True
    if intent.get("task_types", ["general"]) != ["general"]:
        return True
    return False


def _looks_like_status_query(text: str) -> bool:
    """
    中文注解：
    - 功能：实现 `_looks_like_status_query` 对应的处理逻辑。
    - 角色：属于本模块中的内部辅助逻辑；私有函数通常服务同文件主流程，公共函数通常作为跨模块入口或能力接口。
    - 调用关系：建议结合本文件的模块说明、调用方以及同名相关辅助函数一起阅读。
    """
    lowered = text.strip().lower()
    if not lowered:
        return False
    if len(lowered) > 80:
        return False
    normalized = re.sub(r"\s+", "", lowered)
    return any(token in normalized for token in STATUS_QUERY_PATTERNS)


def _looks_like_followup_goal(text: str, intent: Dict[str, object]) -> bool:
    """
    中文注解：
    - 功能：实现 `_looks_like_followup_goal` 对应的处理逻辑。
    - 角色：属于本模块中的内部辅助逻辑；私有函数通常服务同文件主流程，公共函数通常作为跨模块入口或能力接口。
    - 调用关系：建议结合本文件的模块说明、调用方以及同名相关辅助函数一起阅读。
    """
    lowered = text.strip().lower()
    if not lowered:
        return False
    normalized = re.sub(r"\s+", "", lowered)
    if any(token in normalized for token in FOLLOW_UP_ACTION_PATTERNS):
        return True
    if any(intent.get(key) for key in ("needs_browser", "needs_verification", "requires_external_information")):
        return True
    return intent.get("task_types", ["general"]) != ["general"]


def _safe_load_contract(task_id: str):
    """
    中文注解：
    - 功能：实现 `_safe_load_contract` 对应的处理逻辑。
    - 角色：属于本模块中的内部辅助逻辑；私有函数通常服务同文件主流程，公共函数通常作为跨模块入口或能力接口。
    - 调用关系：建议结合本文件的模块说明、调用方以及同名相关辅助函数一起阅读。
    """
    if not task_id or not contract_path(task_id).exists():
        return None
    return load_contract(task_id)


def _safe_load_state(task_id: str):
    """
    中文注解：
    - 功能：实现 `_safe_load_state` 对应的处理逻辑。
    - 角色：属于本模块中的内部辅助逻辑；私有函数通常服务同文件主流程，公共函数通常作为跨模块入口或能力接口。
    - 调用关系：建议结合本文件的模块说明、调用方以及同名相关辅助函数一起阅读。
    """
    path = state_path(task_id)
    if not task_id or not path.exists():
        return None
    return load_state(task_id)


def _snapshot_governance_attention(snapshot: Dict[str, object]) -> Dict[str, object]:
    governance = (snapshot.get("governance", {}) or {}) if isinstance(snapshot, dict) else {}
    permission = (governance.get("permission_decision", {}) or {}) if isinstance(governance, dict) else {}
    project_control = (governance.get("project_control", {}) or {}) if isinstance(governance, dict) else {}
    crawler_project = (governance.get("crawler_project", {}) or {}) if isinstance(governance, dict) else {}
    return {
        "permission_overall_status": str(permission.get("overall_status", "")).strip() or "unknown",
        "permission_primary_reason": str(permission.get("primary_reason", "")).strip() or "unknown",
        "crawler_health_status": str(crawler_project.get("health_status", "")).strip() or "unknown",
        "project_feedback_status": str(((project_control.get("summary", {}) or {}).get("crawler_feedback_coverage_status", ""))).strip() or "unknown",
        "scheduler_modes": dict(project_control.get("scheduler_modes", {}) or {}),
    }


def _is_lightweight_followup_prompt(text: str, intent: Dict[str, object]) -> bool:
    normalized = re.sub(r"\s+", "", text.strip().lower())
    if not normalized:
        return False
    lightweight_tokens = {
        "继续",
        "继续吧",
        "接着",
        "开始吧",
        "开始",
        "可以",
        "好的",
        "同意",
        "继续推进",
        "继续。",
        "continue",
        "goon",
        "start",
    }
    if normalized in lightweight_tokens:
        return True
    if len(normalized) <= 12 and _looks_like_followup_goal(text, intent):
        return True
    return False


def _should_prefer_governance_status_reply(text: str, intent: Dict[str, object], snapshot: Dict[str, object]) -> bool:
    if not _is_lightweight_followup_prompt(text, intent):
        return False
    if str(snapshot.get("status", "")).strip() != "blocked":
        return False
    next_action = str(snapshot.get("next_action", "")).strip()
    if next_action == "await_project_crawler_remediation":
        return True
    governance_attention = _snapshot_governance_attention(snapshot)
    permission_status = str(governance_attention.get("permission_overall_status", "")).strip().lower()
    crawler_health_status = str(governance_attention.get("crawler_health_status", "")).strip().lower()
    if permission_status == "blocked":
        return True
    if crawler_health_status == "critical" and next_action in {
        "request_authorized_session",
        "await_human_verification_checkpoint",
        "await_approval_or_contract_fix",
    }:
        return True
    return False


def _task_predecessor(task_id: str) -> str:
    """
    中文注解：
    - 功能：实现 `_task_predecessor` 对应的处理逻辑。
    - 角色：属于本模块中的内部辅助逻辑；私有函数通常服务同文件主流程，公共函数通常作为跨模块入口或能力接口。
    - 调用关系：建议结合本文件的模块说明、调用方以及同名相关辅助函数一起阅读。
    """
    contract = _safe_load_contract(task_id)
    if not contract:
        return ""
    return str(contract.metadata.get("predecessor_task_id", "")).strip()


def _lineage_root_task_id(task_id: str) -> str:
    """
    中文注解：
    - 功能：实现 `_lineage_root_task_id` 对应的处理逻辑。
    - 角色：属于本模块中的内部辅助逻辑；私有函数通常服务同文件主流程，公共函数通常作为跨模块入口或能力接口。
    - 调用关系：建议结合本文件的模块说明、调用方以及同名相关辅助函数一起阅读。
    """
    current = task_id
    seen = set()
    while current and current not in seen:
        seen.add(current)
        predecessor = _task_predecessor(current)
        if not predecessor:
            return current
        current = predecessor
    return task_id


def _task_created_at(task_id: str) -> str:
    """
    中文注解：
    - 功能：实现 `_task_created_at` 对应的处理逻辑。
    - 角色：属于本模块中的内部辅助逻辑；私有函数通常服务同文件主流程，公共函数通常作为跨模块入口或能力接口。
    - 调用关系：建议结合本文件的模块说明、调用方以及同名相关辅助函数一起阅读。
    """
    contract = _safe_load_contract(task_id)
    if not contract:
        return ""
    return str(contract.metadata.get("created_at", "")).strip()


def _lineage_task_ids(root_task_id: str) -> List[str]:
    """
    中文注解：
    - 功能：实现 `_lineage_task_ids` 对应的处理逻辑。
    - 角色：属于本模块中的内部辅助逻辑；私有函数通常服务同文件主流程，公共函数通常作为跨模块入口或能力接口。
    - 调用关系：建议结合本文件的模块说明、调用方以及同名相关辅助函数一起阅读。
    """
    task_ids: List[str] = []
    if contract_path(root_task_id).exists():
        task_ids.append(root_task_id)
    if not TASKS_ROOT.exists():
        return task_ids
    for candidate in sorted(path.name for path in TASKS_ROOT.iterdir() if path.is_dir()):
        if candidate == root_task_id:
            continue
        if _lineage_root_task_id(candidate) == root_task_id:
            task_ids.append(candidate)
    return sorted(task_ids, key=lambda task_id: (_task_created_at(task_id), task_id))


def _find_active_lineage_task(root_task_id: str, *, preferred_task_id: str = "") -> str:
    """
    中文注解：
    - 功能：实现 `_find_active_lineage_task` 对应的处理逻辑。
    - 角色：属于本模块中的内部辅助逻辑；私有函数通常服务同文件主流程，公共函数通常作为跨模块入口或能力接口。
    - 调用关系：建议结合本文件的模块说明、调用方以及同名相关辅助函数一起阅读。
    """
    active_candidates: List[str] = []
    for task_id in _lineage_task_ids(root_task_id):
        state = _safe_load_state(task_id)
        if not state:
            continue
        if state.metadata.get("superseded_by_task_id"):
            continue
        if state.status in TERMINAL_TASK_STATUSES:
            continue
        active_candidates.append(task_id)
    if not active_candidates:
        return ""
    return active_candidates[-1]


def _next_successor_task_id(parent_task_id: str) -> str:
    """
    中文注解：
    - 功能：实现 `_next_successor_task_id` 对应的处理逻辑。
    - 角色：属于本模块中的内部辅助逻辑；私有函数通常服务同文件主流程，公共函数通常作为跨模块入口或能力接口。
    - 调用关系：建议结合本文件的模块说明、调用方以及同名相关辅助函数一起阅读。
    """
    root_task_id = _lineage_root_task_id(parent_task_id)
    base = f"{root_task_id}-followup"
    candidate = base
    counter = 2
    while contract_path(candidate).exists():
        candidate = f"{base}-{counter}"
        counter += 1
    return candidate


def _mark_task_superseded(task_id: str, replacement_task_id: str, reason: str) -> None:
    """
    中文注解：
    - 功能：实现 `_mark_task_superseded` 对应的处理逻辑。
    - 角色：属于本模块中的内部辅助逻辑；私有函数通常服务同文件主流程，公共函数通常作为跨模块入口或能力接口。
    - 调用关系：建议结合本文件的模块说明、调用方以及同名相关辅助函数一起阅读。
    """
    state = _safe_load_state(task_id)
    if not state:
        return
    if state.metadata.get("superseded_by_task_id") == replacement_task_id:
        return
    state.status = "blocked"
    state.next_action = f"superseded_by:{replacement_task_id}"
    state.blockers = [reason]
    state.last_update_at = utc_now_iso()
    state.metadata["superseded_by_task_id"] = replacement_task_id
    save_state(state)
    log_event(task_id, "task_superseded", replacement_task_id=replacement_task_id, reason=reason)


def _clear_task_superseded(task_id: str) -> None:
    """
    中文注解：
    - 功能：实现 `_clear_task_superseded` 对应的处理逻辑。
    - 角色：属于本模块中的内部辅助逻辑；私有函数通常服务同文件主流程，公共函数通常作为跨模块入口或能力接口。
    - 调用关系：建议结合本文件的模块说明、调用方以及同名相关辅助函数一起阅读。
    """
    state = _safe_load_state(task_id)
    if not state:
        return
    if not state.metadata.get("superseded_by_task_id"):
        return
    state.metadata.pop("superseded_by_task_id", None)
    if str(state.next_action).startswith("superseded_by:"):
        state.next_action = f"start_stage:{state.current_stage}" if state.current_stage else "initialize"
    if state.status == "blocked" and state.blockers:
        state.blockers = [item for item in state.blockers if "superseded" not in str(item).lower()]
        if not state.blockers:
            state.status = "planning"
    state.last_update_at = utc_now_iso()
    save_state(state)
    log_event(task_id, "task_superseded_cleared")


def _resolve_linked_active_task_id(existing_task_id: str) -> str:
    """
    中文注解：
    - 功能：实现 `_resolve_linked_active_task_id` 对应的处理逻辑。
    - 角色：属于本模块中的内部辅助逻辑；私有函数通常服务同文件主流程，公共函数通常作为跨模块入口或能力接口。
    - 调用关系：建议结合本文件的模块说明、调用方以及同名相关辅助函数一起阅读。
    """
    if not existing_task_id:
        return ""
    root_task_id = _lineage_root_task_id(existing_task_id)
    active_task_id = _find_active_lineage_task(root_task_id, preferred_task_id=existing_task_id)
    if active_task_id:
        return active_task_id
    lineage_candidates = _lineage_task_ids(root_task_id)
    if lineage_candidates:
        return lineage_candidates[-1]
    return existing_task_id


def _normalize_goal_text(text: str) -> str:
    """
    中文注解：
    - 功能：实现 `_normalize_goal_text` 对应的处理逻辑。
    - 角色：属于本模块中的内部辅助逻辑；私有函数通常服务同文件主流程，公共函数通常作为跨模块入口或能力接口。
    - 调用关系：建议结合本文件的模块说明、调用方以及同名相关辅助函数一起阅读。
    """
    return re.sub(r"\s+", "", text.strip().lower())


def _should_branch_from_active_task(existing_task_id: str, goal: str, intent: Dict[str, object]) -> bool:
    """
    中文注解：
    - 功能：实现 `_should_branch_from_active_task` 对应的处理逻辑。
    - 角色：属于本模块中的内部辅助逻辑；私有函数通常服务同文件主流程，公共函数通常作为跨模块入口或能力接口。
    - 调用关系：建议结合本文件的模块说明、调用方以及同名相关辅助函数一起阅读。
    """
    contract = _safe_load_contract(existing_task_id)
    state = _safe_load_state(existing_task_id)
    if not contract or not state:
        return False
    if state.status in TERMINAL_TASK_STATUSES:
        return False
    raw_current_goal = str(contract.user_goal)
    current_goal = _normalize_goal_text(_strip_transport_wrapper(raw_current_goal))
    new_goal = _normalize_goal_text(goal)
    if _is_internal_runtime_request_text(raw_current_goal) and not _is_internal_runtime_request_text(goal):
        return True
    if not current_goal or not new_goal or current_goal == new_goal:
        return False
    if not _looks_like_followup_goal(goal, intent):
        return False
    numbered_scope = bool(re.search(r"(1[\.\u3001:：]|2[\.\u3001:：]|3[\.\u3001:：]|4[\.\u3001:：])", goal))
    materially_longer = len(new_goal) >= len(current_goal) + 18
    explicit_remaining_scope = any(token in new_goal for token in ("剩下", "环节", "补到", "补齐", "提交审核", "提审", "闭环"))
    return numbered_scope or materially_longer or explicit_remaining_scope


def _build_task(
    task_id: str,
    goal: str,
    source: str,
    metadata_extra: Dict[str, object] | None = None,
    inherited_intent: Dict[str, object] | None = None,
) -> Dict[str, object]:
    """
    中文注解：
    - 功能：把已经确定好的目标正式建成任务。
    - 输入：task_id、goal、source，以及可选的继承 intent 和额外 metadata。
    - 输出：返回 control center 生成的 package，同时在 runtime/tasks 下写出 contract/state。
    - 调用关系：这是 brain_router 真正“落任务”的工厂封装，内部先调 orchestrator 产出任务包，再调 manager.create_task 完成实际落盘。
    """
    # 先把自然语言目标翻译成结构化任务包；这个包会被写进 contract metadata，
    # 也是后续 runtime / doctor / context_builder 继续工作的基础输入。
    package = build_control_center_package(task_id, goal, source=source, inherited_intent=inherited_intent)
    if metadata_extra:
        package["metadata"] = {
            **package["metadata"],
            **metadata_extra,
        }
    create_task(
        build_args(
            task_id=task_id,
            goal=goal,
            done_definition=package["done_definition"],
            stage=[],
            stage_json=json.dumps(package["stages"], ensure_ascii=False),
            hard_constraint=package["hard_constraints"],
            soft_preference=[],
            allowed_tool=package["allowed_tools"],
            forbidden_action=[],
            metadata_json=json.dumps(package["metadata"], ensure_ascii=False),
        )
    )
    return package


def _task_matches_root_mission_profile(task_id: str, mission_profile: Dict[str, object]) -> bool:
    """
    中文注解：
    - 功能：实现 `_task_matches_root_mission_profile` 对应的处理逻辑。
    - 角色：属于本模块中的内部辅助逻辑；私有函数通常服务同文件主流程，公共函数通常作为跨模块入口或能力接口。
    - 调用关系：建议结合本文件的模块说明、调用方以及同名相关辅助函数一起阅读。
    """
    if not task_id or not mission_profile.get("matched"):
        return False
    if task_id == str(mission_profile.get("root_task_id", "")).strip():
        return True
    contract = _safe_load_contract(task_id)
    if not contract:
        return False
    control_center = contract.metadata.get("control_center", {}) or {}
    return str(control_center.get("mission_profile_id", "")).strip() == str(mission_profile.get("profile_id", "")).strip()


def route_instruction(
    *,
    provider: str,
    conversation_id: str,
    conversation_type: str,
    text: str,
    source: str,
    sender_id: str = "",
    sender_name: str = "",
    message_id: str = "",
    session_key: str = "",
) -> Dict[str, object]:
    """
    中文注解：
    - 功能：本模块的总入口，负责对一条聊天指令做最终路由。
    - 典型输出模式：
      - `authoritative_task_status`：只回当前任务真实状态，不创建新任务。
      - `append_to_existing_task`：继续挂到当前活跃任务。
      - `create_new_root_task`：当前话题已经切根，需要新的 root mission。
      - `create_successor_task` / `branch_from_active_task`：沿现有 lineage 开新分支或后续任务。
    - 调用关系：Telegram / 主会话入口先调用这里，后续 receipt engine、runtime、doctor 都依赖这里写回的 task_id 和 link。
    """
    goal = _strip_transport_wrapper(text)
    intent = analyze_intent(goal, source=source)
    mission_profile = detect_root_mission_profile(goal, intent=intent)
    existing = read_link(provider, conversation_id)
    route: Dict[str, object] = {
        "routed_at": utc_now_iso(),
        "provider": provider,
        "conversation_id": conversation_id,
        "conversation_type": conversation_type,
        "sender_id": sender_id,
        "sender_name": sender_name,
        "message_id": message_id,
        "source": source,
        "goal": goal,
        "intent": intent,
        "mode": "instant_reply_only",
        "task_id": existing.get("task_id"),
        "created_task": False,
        "attached_existing": bool(existing),
        "brain_required": True,
        "mission_profile": mission_profile,
    }

    if existing:
        # 如果当前会话已经绑过任务，先把它解析到真正活跃的 canonical task。
        # 这一步的目标是避免用户还盯着一个已经 superseded 的旧 follow-up。
        resolved_task_id = _resolve_linked_active_task_id(str(existing.get("task_id", "")))
        if resolved_task_id and resolved_task_id != existing.get("task_id"):
            stale_task_id = str(existing.get("task_id", "")).strip()
            stale_state = _safe_load_state(stale_task_id)
            if stale_state and stale_state.status not in TERMINAL_TASK_STATUSES:
                _mark_task_superseded(
                    stale_task_id,
                    resolved_task_id,
                    reason=f"superseded by newer active lineage task {resolved_task_id}",
                )
            existing["superseded_task_id"] = existing.get("task_id")
            existing["task_id"] = resolved_task_id
        if str(existing.get("task_id", "")).strip():
            _clear_task_superseded(str(existing.get("task_id", "")).strip())
        existing["updated_at"] = utc_now_iso()
        existing["last_message_id"] = message_id
        existing["last_sender_id"] = sender_id
        existing["last_sender_name"] = sender_name
        existing["last_goal"] = goal
        actionable = _looks_actionable(goal, intent)
        status_query = _looks_like_status_query(goal) and not actionable
        if status_query:
            # 状态问询不应该把系统再次推入任务创建链。
            # 这里直接读取权威状态快照，确保回复和真实 state / control plane 对齐。
            snapshot = build_task_status_snapshot(str(existing.get("task_id", "")))
            route["mode"] = "authoritative_task_status"
            route["authoritative_task_status"] = snapshot
            route["governance_attention"] = _snapshot_governance_attention(snapshot)
            response_constraints = dict(snapshot.get("reply_contract", {}) or {})
            response_constraints["governance_attention"] = route["governance_attention"]
            route["response_constraints"] = response_constraints
            route["link_path"] = write_link(provider, conversation_id, existing)
        elif actionable:
            # 动作型消息会继续分流：
            # 1. 是否应该切成新的 root mission
            # 2. 是否只是继续当前 root mission
            # 3. 是否应当沿 lineage 开 successor
            existing_task_id = str(existing.get("task_id", ""))
            governance_snapshot = build_task_status_snapshot(existing_task_id) if existing_task_id else {}
            if governance_snapshot and _should_prefer_governance_status_reply(goal, intent, governance_snapshot):
                route["mode"] = "authoritative_task_status"
                route["authoritative_task_status"] = governance_snapshot
                route["governance_attention"] = _snapshot_governance_attention(governance_snapshot)
                response_constraints = dict(governance_snapshot.get("reply_contract", {}) or {})
                response_constraints["governance_attention"] = route["governance_attention"]
                response_constraints["brain_router_reason"] = "lightweight_followup_while_governance_blocked"
                route["response_constraints"] = response_constraints
                route["task_id"] = existing_task_id
                route["link_path"] = write_link(provider, conversation_id, existing)
            elif mission_profile.get("matched") and not _task_matches_root_mission_profile(existing_task_id, mission_profile):
                # 主题已经明显切根，并且新目标命中了 mission profile；
                # 这里优先创建稳定的 root mission，而不是继续在旧 follow-up 上堆叠。
                task_id = str(mission_profile.get("root_task_id", "")).strip() or slugify(goal)
                canonical_goal = str(mission_profile.get("canonical_goal", "")).strip() or goal
                if not contract_path(task_id).exists():
                    _build_task(
                        task_id,
                        canonical_goal,
                        source=f"{source}:root_mission",
                        metadata_extra={
                            "root_mission": True,
                            "root_task_id": task_id,
                            "ideal_plan_path": mission_profile.get("ideal_plan_path", ""),
                        },
                    )
                    route["created_task"] = True
                payload = {
                    "provider": provider,
                    "conversation_id": conversation_id,
                    "conversation_type": conversation_type,
                    "task_id": task_id,
                    "goal": canonical_goal,
                    "updated_at": utc_now_iso(),
                    "last_message_id": message_id,
                    "last_sender_id": sender_id,
                    "last_sender_name": sender_name,
                    "brain_source": source,
                    "mission_profile_id": mission_profile.get("profile_id", ""),
                }
                if session_key:
                    payload["session_key"] = session_key
                elif str(existing.get("session_key", "")).strip():
                    payload["session_key"] = str(existing.get("session_key", "")).strip()
                route["mode"] = "create_new_root_task"
                route["attached_existing"] = False
                route["task_id"] = task_id
                route["link_path"] = write_link(provider, conversation_id, payload)
            elif mission_profile.get("matched") and _task_matches_root_mission_profile(existing_task_id, mission_profile):
                # 已经处在正确 root mission 上，就不要再长新的 task，
                # 直接把会话继续挂回这个 root/canonical task。
                route["mode"] = "append_to_existing_task"
                route["task_id"] = existing_task_id
                route["link_path"] = write_link(provider, conversation_id, existing)
            else:
                existing_state = load_state(existing_task_id) if existing_task_id else None
                should_branch_from_active = bool(existing_task_id) and _should_branch_from_active_task(existing_task_id, goal, intent)
                if (existing_state and existing_state.status == "completed" and _looks_like_followup_goal(goal, intent)) or should_branch_from_active:
                    # 当前任务已经完成，或者用户明显在继续推进剩余环节；
                    # 这里才允许沿 lineage 开 successor，而不是让所有短消息都无限套娃。
                    root_task_id = _lineage_root_task_id(existing_task_id)
                    active_task_id = _find_active_lineage_task(root_task_id, preferred_task_id=existing_task_id)
                    if existing_state and existing_state.status == "completed" and active_task_id and active_task_id != existing_task_id:
                        existing["task_id"] = active_task_id
                        existing["goal"] = goal
                        route["mode"] = "append_to_active_successor_task"
                        route["task_id"] = active_task_id
                        route["lineage_root_task_id"] = root_task_id
                        route["link_path"] = write_link(provider, conversation_id, existing)
                    else:
                        task_id = _next_successor_task_id(existing_task_id)
                        predecessor_task_id = existing_task_id
                        predecessor_contract = load_contract(predecessor_task_id)
                        predecessor_snapshot = build_task_status_snapshot(predecessor_task_id)
                        if _is_internal_runtime_request_text(str(predecessor_contract.user_goal)):
                            inherited_intent = {}
                        else:
                            inherited_intent = predecessor_contract.metadata.get("control_center", {}).get("inherited_intent", {})
                            if not inherited_intent:
                                inherited_intent = predecessor_contract.metadata.get("control_center", {}).get("intent", {})
                        # successor 会继承 predecessor 的意图和上下文，但必须重新获得自己的 contract/state；
                        # 这样旧任务的完成证明、等待状态和失败痕迹不会直接污染新任务。
                        _build_task(
                            task_id,
                            goal,
                            source=f"{source}:successor",
                            metadata_extra={
                                "predecessor_task_id": predecessor_task_id,
                                "predecessor_status": existing_state.status,
                                "predecessor_authoritative_summary": predecessor_snapshot.get("authoritative_summary", ""),
                                "lineage_root_task_id": root_task_id,
                                "require_fresh_successor_business_outcome": True,
                            },
                            inherited_intent=inherited_intent,
                        )
                        payload = {
                            "provider": provider,
                            "conversation_id": conversation_id,
                            "conversation_type": conversation_type,
                            "task_id": task_id,
                            "goal": goal,
                            "updated_at": utc_now_iso(),
                            "last_message_id": message_id,
                            "last_sender_id": sender_id,
                            "last_sender_name": sender_name,
                            "brain_source": source,
                            "predecessor_task_id": predecessor_task_id,
                            "lineage_root_task_id": root_task_id,
                        }
                        if session_key:
                            payload["session_key"] = session_key
                        for stale_task_id in _lineage_task_ids(root_task_id):
                            if stale_task_id in {task_id, root_task_id}:
                                continue
                            stale_state = _safe_load_state(stale_task_id)
                            if stale_state and stale_state.status not in TERMINAL_TASK_STATUSES:
                                _mark_task_superseded(
                                    stale_task_id,
                                    task_id,
                                    reason=f"superseded by active successor {task_id}",
                                )
                        route["mode"] = "create_successor_task"
                        route["created_task"] = True
                        route["attached_existing"] = False
                        route["task_id"] = task_id
                        route["predecessor_task_id"] = predecessor_task_id
                        route["lineage_root_task_id"] = root_task_id
                        if should_branch_from_active:
                            route["mode"] = "branch_from_active_task"
                        route["link_path"] = write_link(provider, conversation_id, payload)
                else:
                    route["mode"] = "append_to_existing_task"
                    route["task_id"] = existing_task_id
                    route["link_path"] = write_link(provider, conversation_id, existing)
        else:
            # 非动作型、也不是状态问询的消息，目前保守地继续挂在当前任务上，
            # 让上层回复器自行决定是闲聊说明还是更轻量的解释型回执。
            route["mode"] = "append_to_existing_task"
            route["task_id"] = existing.get("task_id")
            route["link_path"] = write_link(provider, conversation_id, existing)
    elif _looks_actionable(goal, intent):
        if mission_profile.get("matched"):
            task_id = str(mission_profile.get("root_task_id", "")).strip() or slugify(goal)
            goal = str(mission_profile.get("canonical_goal", "")).strip() or goal
            route["mode"] = "create_new_root_task"
        else:
            task_id = slugify(goal)
        if not contract_path(task_id).exists():
            _build_task(task_id, goal, source=source)
            route["created_task"] = True
        payload = {
            "provider": provider,
            "conversation_id": conversation_id,
            "conversation_type": conversation_type,
            "task_id": task_id,
            "goal": goal,
            "updated_at": utc_now_iso(),
            "last_message_id": message_id,
            "last_sender_id": sender_id,
            "last_sender_name": sender_name,
            "brain_source": source,
        }
        if session_key:
            payload["session_key"] = session_key
        if route["mode"] != "create_new_root_task":
            route["mode"] = "create_or_attach"
        route["task_id"] = task_id
        route["link_path"] = write_link(provider, conversation_id, payload)

    route["route_path"] = _write_json(BRAIN_ROUTES_ROOT / provider / f"{conversation_id}.json", route)
    return route


def main() -> int:
    """
    中文注解：
    - 功能：实现 `main` 对应的处理逻辑。
    - 角色：属于本模块中的对外可见逻辑；私有函数通常服务同文件主流程，公共函数通常作为跨模块入口或能力接口。
    - 调用关系：建议结合本文件的模块说明、调用方以及同名相关辅助函数一起阅读。
    """
    import argparse

    parser = argparse.ArgumentParser(description="Route an incoming instruction through the control-center brain first")
    parser.add_argument("--provider", required=True)
    parser.add_argument("--conversation-id", required=True)
    parser.add_argument("--conversation-type", default="direct")
    parser.add_argument("--text", required=True)
    parser.add_argument("--source", default="manual")
    parser.add_argument("--sender-id", default="")
    parser.add_argument("--sender-name", default="")
    parser.add_argument("--message-id", default="")
    args = parser.parse_args()
    print(
        json.dumps(
            route_instruction(
                provider=args.provider,
                conversation_id=args.conversation_id,
                conversation_type=args.conversation_type,
                text=args.text,
                source=args.source,
                sender_id=args.sender_id,
                sender_name=args.sender_name,
                message_id=args.message_id,
                session_key="",
            ),
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
