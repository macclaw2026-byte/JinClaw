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
- 文件路径：`tools/openmoss/autonomy/capability_gap_engine.py`
- 文件作用：把阻塞态里的“能力缺口”统一翻译成可解释、自愈优先的结构化合同。
- 顶层函数：utc_now_iso、build_capability_gap_report。
- 顶层类：无顶层类。
- 阅读建议：先看 schema 输出，再看 local-reuse / research / build 的梯子推导逻辑。
"""
from __future__ import annotations

import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

from recovery_engine import classify_failure

CONTROL_CENTER_DIR = Path("/Users/mac_claw/.openclaw/workspace/tools/openmoss/control_center")
if str(CONTROL_CENTER_DIR) not in sys.path:
    sys.path.insert(0, str(CONTROL_CENTER_DIR))

from capability_registry import build_capability_registry
from control_center_schemas import build_capability_gap_schema


def utc_now_iso() -> str:
    """
    中文注解：
    - 功能：生成 UTC ISO 时间戳。
    - 设计意图：让 capability-gap 合同的检查时间可审计。
    """
    return datetime.now(timezone.utc).isoformat()


def _extract_missing_command(error_text: str) -> str:
    """
    中文注解：
    - 功能：从 blocker/error 中提取缺失命令或依赖名。
    - 设计意图：优先抓住“缺什么”这个最可操作的信号，而不是只知道任务被卡住。
    """
    match = re.search(r"command not found:\s*([A-Za-z0-9._/-]+)", str(error_text or ""), re.IGNORECASE)
    if match:
        return match.group(1).strip()
    match = re.search(r"No module named ['\"]?([A-Za-z0-9._-]+)['\"]?", str(error_text or ""), re.IGNORECASE)
    if match:
        return match.group(1).strip()
    match = re.search(r"missing[_ ]dependency[:= ]+([A-Za-z0-9._/-]+)", str(error_text or ""), re.IGNORECASE)
    if match:
        return match.group(1).strip()
    return ""


def _tokenize(*values: object) -> List[str]:
    """
    中文注解：
    - 功能：把 goal / blocker / next_action 统一切成检索 token。
    - 设计意图：保持规则可解释，不引入黑箱 embedding。
    """
    tokens: List[str] = []
    for value in values:
        for token in re.split(r"[^a-zA-Z0-9_\u4e00-\u9fff]+", str(value or "").lower()):
            normalized = token.strip()
            if len(normalized) >= 2:
                tokens.append(normalized)
    return list(dict.fromkeys(tokens))


def _tool_score(candidate: Dict[str, Any], *, target: str, allowed_tools: set[str], tokens: List[str]) -> int:
    """
    中文注解：
    - 功能：给本地 tool 候选做可解释评分。
    - 设计意图：优先 exact-match，再看 allowed-tools / provides / token overlap。
    """
    name = str(candidate.get("name", "")).strip().lower()
    provides = {str(item).strip().lower() for item in (candidate.get("provides", []) or []) if str(item).strip()}
    score = 0
    if name and target and name == target:
        score += 12
    if target and target in provides:
        score += 8
    if name in allowed_tools:
        score += 5
    if provides & allowed_tools:
        score += 4
    if any(token and token in {name, *provides} for token in tokens):
        score += 2
    if candidate.get("exists"):
        score += 1
    return score


def _skill_score(candidate: Dict[str, Any], *, tokens: List[str]) -> int:
    """
    中文注解：
    - 功能：给本地 skill 候选做可解释评分。
    - 设计意图：skill 不直接等于工具，但常常代表已有方法论与桥接能力。
    """
    name = str(candidate.get("name", "")).strip().lower()
    tags = {str(item).strip().lower() for item in (candidate.get("tags", []) or []) if str(item).strip()}
    score = 0
    if any(token and token in name for token in tokens):
        score += 6
    if tags & set(tokens):
        score += 4
    return score


def _top_tool_candidates(registry: Dict[str, Any], *, target: str, allowed_tools: set[str], tokens: List[str]) -> List[Dict[str, Any]]:
    """
    中文注解：
    - 功能：筛出最相关的本地 tool 候选。
    - 设计意图：阻塞时先看现有工具能不能接住，不要直接跳外部搜索。
    """
    rows: List[Dict[str, Any]] = []
    for candidate in registry.get("tools", []) or []:
        score = _tool_score(candidate, target=target, allowed_tools=allowed_tools, tokens=tokens)
        if score <= 0 or not candidate.get("exists"):
            continue
        rows.append(
            {
                "name": str(candidate.get("name", "")).strip(),
                "path": str(candidate.get("path", "")).strip(),
                "provides": list(candidate.get("provides", []) or []),
                "runtime_channels": list(candidate.get("runtime_channels", []) or []),
                "score": score,
            }
        )
    rows.sort(key=lambda item: (-int(item.get("score", 0) or 0), str(item.get("name", ""))))
    return rows[:5]


def _top_skill_candidates(registry: Dict[str, Any], *, tokens: List[str]) -> List[Dict[str, Any]]:
    """
    中文注解：
    - 功能：筛出最相关的本地 skill 候选。
    - 设计意图：当工具层不够时，优先复用现有 skill/workflow，而不是立刻造新轮子。
    """
    rows: List[Dict[str, Any]] = []
    for candidate in registry.get("skills", []) or []:
        score = _skill_score(candidate, tokens=tokens)
        if score <= 0:
            continue
        rows.append(
            {
                "name": str(candidate.get("name", "")).strip(),
                "path": str(candidate.get("path", "")).strip(),
                "tags": list(candidate.get("tags", []) or []),
                "score": score,
            }
        )
    rows.sort(key=lambda item: (-int(item.get("score", 0) or 0), str(item.get("name", ""))))
    return rows[:5]


def _top_generated_candidates(registry: Dict[str, Any], *, tokens: List[str]) -> List[Dict[str, Any]]:
    """
    中文注解：
    - 功能：筛出可复用的 generated/promoted capability 候选。
    - 设计意图：已有生成能力或被推广的能力应先被复用，再谈新建。
    """
    candidates: List[Dict[str, Any]] = []
    for collection_name in ("generated_capabilities", "promoted_capabilities"):
        for candidate in registry.get(collection_name, []) or []:
            haystack = " ".join(
                [
                    str(candidate.get("name", "")).lower(),
                    str(candidate.get("purpose", "")).lower(),
                    str(candidate.get("status", "")).lower(),
                    str(candidate.get("rebuild_root", "")).lower(),
                ]
            )
            score = sum(2 for token in tokens if token and token in haystack)
            if score <= 0:
                continue
            candidates.append(
                {
                    "name": str(candidate.get("name", "")).strip(),
                    "path": str(candidate.get("path", "") or candidate.get("rebuild_root", "")).strip(),
                    "source": collection_name,
                    "score": score,
                }
            )
    candidates.sort(key=lambda item: (-int(item.get("score", 0) or 0), str(item.get("name", ""))))
    return candidates[:5]


def build_capability_gap_report(
    *,
    task_id: str,
    goal: str,
    next_action: str,
    blockers: List[str] | None = None,
    allowed_tools: List[str] | None = None,
    target_stage: str = "",
    previous_gap: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    """
    中文注解：
    - 功能：构造 capability-gap 合同。
    - 输入角色：消费任务 goal、阻塞文本、当前 next_action 和本地 capability registry。
    - 输出角色：供 runtime/doctor/snapshot 统一决定下一层自愈梯子，而不是把“卡住了”停留在口头描述。
    """
    blockers = [str(item).strip() for item in (blockers or []) if str(item).strip()]
    blocker_text = "; ".join(blockers)
    previous_gap = previous_gap or {}
    attempted_steps = [str(item).strip() for item in (previous_gap.get("attempted_steps", []) or []) if str(item).strip()]
    classification = classify_failure(blocker_text) if blocker_text else "general_failure"
    missing_dependency = _extract_missing_command(blocker_text)
    tokens = _tokenize(goal, blocker_text, next_action, missing_dependency)
    allowed_tool_set = {str(item).strip().lower() for item in (allowed_tools or []) if str(item).strip()}
    registry = build_capability_registry()
    local_tool_candidates = _top_tool_candidates(registry, target=missing_dependency.lower(), allowed_tools=allowed_tool_set, tokens=tokens)
    skill_candidates = _top_skill_candidates(registry, tokens=tokens)
    generated_candidates = _top_generated_candidates(registry, tokens=tokens)
    exact_local_tool = bool(missing_dependency and any(str(item.get("name", "")).strip().lower() == missing_dependency.lower() for item in local_tool_candidates))
    research_allowed = bool(allowed_tool_set & {"search", "web", "browser", "agent-browser", "curl", "httpx", "curl_cffi"})
    build_feasible = bool(allowed_tool_set & {"python", "node", "bash", "sh"}) or any(
        str(item.get("name", "")).strip().lower() == "python" and item.get("exists")
        for item in registry.get("tools", []) or []
    )
    gap_detected = bool(
        blocker_text
        or next_action in {"inspect_runtime_contract_or_environment", "research_capability_gap", "build_missing_capability"}
    )
    selected_path = "observe_only"
    next_step = "continue_current_plan"
    auto_continue = False
    requires_human_decision = False
    rationale: List[str] = []
    if gap_detected:
        if exact_local_tool and "local_reuse" not in attempted_steps:
            selected_path = "reuse_local_capability"
            next_step = "retry_current_stage_with_local_capability"
            auto_continue = True
            rationale.append("Missing dependency already exists locally, so the safest next step is to reuse it and retry once.")
        elif research_allowed and "research_existing_tooling" not in attempted_steps:
            selected_path = "research_existing_tooling"
            next_step = "record_existing_tooling_options"
            rationale.append("No exact local reuse path is ready, so the loop should study existing allowed tooling before building a new one.")
        elif build_feasible and "build_local_capability" not in attempted_steps:
            selected_path = "build_local_capability"
            next_step = "prepare_in_house_capability_build"
            rationale.append("Existing local reuse is insufficient, but the runtime has enough local build capability to prepare an in-house replacement.")
        else:
            selected_path = "ask_user_or_doctor_boundary"
            next_step = "escalate_with_structured_gap_report"
            requires_human_decision = True
            rationale.append("The self-heal ladder is exhausted or gated by boundary conditions, so escalation must carry a structured gap report.")
    ladder_steps = [
        {
            "step": "local_reuse",
            "status": "completed" if "local_reuse" in attempted_steps else ("selected" if selected_path == "reuse_local_capability" else "pending"),
        },
        {
            "step": "research_existing_tooling",
            "status": "completed" if "research_existing_tooling" in attempted_steps else ("selected" if selected_path == "research_existing_tooling" else "pending"),
        },
        {
            "step": "build_local_capability",
            "status": "completed" if "build_local_capability" in attempted_steps else ("selected" if selected_path == "build_local_capability" else "pending"),
        },
        {
            "step": "ask_user_or_doctor_boundary",
            "status": "selected" if selected_path == "ask_user_or_doctor_boundary" else "pending",
        },
    ]
    tool_evolution_plan = {
        "enabled": bool(gap_detected),
        "selected_path": selected_path,
        "target_dependency": missing_dependency,
        "research_candidates": [dict(item) for item in local_tool_candidates[:3]],
        "skill_fallbacks": [dict(item) for item in skill_candidates[:3]],
        "generated_fallbacks": [dict(item) for item in generated_candidates[:3]],
        "planned_actions": [],
    }
    if selected_path == "reuse_local_capability":
        tool_evolution_plan["planned_actions"] = [
            "reuse_local_capability",
            "retry_current_stage_with_local_capability",
        ]
    elif selected_path == "research_existing_tooling":
        tool_evolution_plan["planned_actions"] = [
            "inspect_local_capability_registry",
            "record_existing_tooling_options",
            "only_then_consider_external_research",
        ]
    elif selected_path == "build_local_capability":
        tool_evolution_plan["planned_actions"] = [
            "inspect_existing_generated_capabilities",
            "prepare_in_house_capability_build",
            "wire_new_capability_back_into_runtime",
        ]
    else:
        tool_evolution_plan["planned_actions"] = [
            "escalate_with_structured_gap_report",
        ]
    return build_capability_gap_schema(
        enabled=gap_detected,
        gap_detected=gap_detected,
        task_id=task_id,
        target_stage=target_stage,
        current_action=next_action,
        classification=classification,
        blocker=blocker_text,
        missing_dependency=missing_dependency,
        selected_path=selected_path,
        next_step=next_step,
        auto_continue=auto_continue,
        requires_external_research=research_allowed,
        build_feasible=build_feasible,
        requires_human_decision=requires_human_decision,
        local_tool_candidates=local_tool_candidates,
        skill_candidates=skill_candidates,
        generated_capability_candidates=generated_candidates,
        attempted_steps=attempted_steps,
        ladder_steps=ladder_steps,
        tool_evolution_plan=tool_evolution_plan,
        rationale=rationale,
        contract_source="capability_gap_engine",
        checked_at=utc_now_iso(),
    )
