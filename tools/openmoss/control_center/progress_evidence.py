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
- 文件路径：`tools/openmoss/control_center/progress_evidence.py`
- 文件作用：负责判断任务是否存在真实进展证据。
- 顶层函数：_read_json、_seconds_since、_progress_age_seconds、_recent_events、build_progress_evidence。
- 顶层类：无顶层类。
- 阅读建议：先看模块说明，再按函数/类 docstring 顺着主流程理解调用关系。
"""
from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

from goal_sanitizer import sanitize_goal_text
from intent_analyzer import analyze_intent
from paths import OPENMOSS_ROOT
from run_liveness_verifier import build_run_liveness


AUTONOMY_TASKS_ROOT = OPENMOSS_ROOT / "runtime/autonomy/tasks"
LINKS_ROOT = OPENMOSS_ROOT / "runtime/autonomy/links"
SESSIONS_ROOT = Path("/Users/mac_claw/.openclaw/agents/main/sessions")
SESSIONS_INDEX_PATH = SESSIONS_ROOT / "sessions.json"
TASK_SUMMARIES_ROOT = OPENMOSS_ROOT / "runtime/control_center/tasks"
GOVERNANCE_PIPELINES_ROOT = OPENMOSS_ROOT / "runtime/control_center/governance/memory/pipelines"
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
_CONVERSATION_LINK_INDEX_CACHE: Dict[str, Any] = {
    "root_mtime_ns": None,
    "index": {},
}
_RECENT_EVENT_TAIL_BYTES = 256 * 1024


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


def _task_summary(task_id: str) -> Dict[str, Any]:
    """
    中文注解：
    - 功能：读取 control-center task summary，补充“长期任务记忆”视角。
    - 设计意图：有些 ghost / reanimated task 会重新生成 runtime state，但 summary 仍明确标记为 completed。
      这类矛盾需要在 progress evidence 层被识别出来，避免医生和 supervisor 一直把它当作新鲜运行态。
    """
    return _read_json(TASK_SUMMARIES_ROOT / task_id / "summary.json", {})


def _governance_task_summary(task_id: str) -> Dict[str, Any]:
    """
    中文注解：
    - 功能：从 governance pipeline memory 中提取 task_summary。
    - 设计意图：某些任务的 canonical completion 状态只保存在 governance memory 里，而不是 runtime/control_center/tasks。
      对 ghost / reanimated task 的判定，必须优先读到真正持久化的那份摘要。
    """
    payload = _read_json(GOVERNANCE_PIPELINES_ROOT / f"{task_id}.json", {})
    layers = payload.get("layers", {}) or {}
    task_layer = layers.get("task", {}) or {}
    return task_layer.get("task_summary", {}) or {}


def _seconds_since(iso_text: str) -> float:
    """
    中文注解：
    - 功能：实现 `_seconds_since` 对应的处理逻辑。
    - 角色：属于本模块中的内部辅助逻辑；私有函数通常服务同文件主流程，公共函数通常作为跨模块入口或能力接口。
    - 调用关系：建议结合本文件的模块说明、调用方以及同名相关辅助函数一起阅读。
    """
    if not iso_text:
        return 10**9
    try:
        dt = datetime.fromisoformat(str(iso_text).replace("Z", "+00:00"))
    except ValueError:
        return 10**9
    return max(0.0, (datetime.now(timezone.utc) - dt).total_seconds())


def _progress_age_seconds(*, status: str, next_action: str, last_progress_at: str, last_update_at: str) -> float:
    """
    中文注解：
    - 功能：实现 `_progress_age_seconds` 对应的处理逻辑。
    - 角色：属于本模块中的内部辅助逻辑；私有函数通常服务同文件主流程，公共函数通常作为跨模块入口或能力接口。
    - 调用关系：建议结合本文件的模块说明、调用方以及同名相关辅助函数一起阅读。
    """
    progress_age = _seconds_since(last_progress_at)
    update_age = _seconds_since(last_update_at)
    # For poll loops, last_update_at mostly reflects bookkeeping churn rather than
    # real forward motion. We should treat "time since last meaningful progress"
    # as authoritative so the supervisor/doctor can detect stale poll_run tasks.
    if status == "waiting_external" and next_action.startswith("poll_run:"):
        return progress_age
    # In normal states, any real stage progress or state update can count as
    # recent movement, so use the fresher of the two timestamps.
    return min(progress_age, update_age)


def _recent_events(task_id: str, limit: int = 12) -> List[Dict[str, Any]]:
    """
    中文注解：
    - 功能：实现 `_recent_events` 对应的处理逻辑。
    - 角色：属于本模块中的内部辅助逻辑；私有函数通常服务同文件主流程，公共函数通常作为跨模块入口或能力接口。
    - 调用关系：建议结合本文件的模块说明、调用方以及同名相关辅助函数一起阅读。
    """
    events_path = AUTONOMY_TASKS_ROOT / task_id / "events.jsonl"
    if not events_path.exists():
        return []
    rows: List[Dict[str, Any]] = []

    def _tail_lines(path: Path, *, wanted: int) -> List[str]:
        if wanted <= 0:
            return []
        try:
            with path.open("rb") as fh:
                fh.seek(0, 2)
                position = fh.tell()
                buffer = b""
                while position > 0 and buffer.count(b"\n") <= wanted and len(buffer) < _RECENT_EVENT_TAIL_BYTES:
                    read_size = min(8192, position, _RECENT_EVENT_TAIL_BYTES - len(buffer))
                    position -= read_size
                    fh.seek(position)
                    buffer = fh.read(read_size) + buffer
        except OSError:
            return []
        return buffer.decode("utf-8", errors="ignore").splitlines()[-wanted:]

    for line in _tail_lines(events_path, wanted=limit):
        try:
            rows.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return rows


def _normalize_set(values: Any) -> set[str]:
    """
    中文注解：
    - 功能：把意图分析里的 keywords/task_types/domains 统一规整成小写集合，方便后续做“是否明显变题”的判断。
    """
    return {str(item).strip().lower() for item in (values or []) if str(item).strip()}


def _normalize_goal(text: str) -> str:
    """
    中文注解：
    - 功能：把 goal 压平做轻量文本比对；这里只用于辅助判断，不直接替代真正的意图分析。
    """
    return re.sub(r"\s+", "", str(text or "").strip().lower())


def _goal_conformance_analysis_text(text: str, *, max_chars: int = 1200) -> str:
    """
    中文注解：
    - 功能：把超长 contract/user goal 压缩成更适合做 conformance 判断的短文本。
    - 设计意图：很多 runtime task 会把系统纪律、阶段说明、verification guidance 一并塞进 goal；
      这些内容对“用户方向有没有变”几乎没帮助，却会显著放大意图分析成本。
      这里优先提取显式 `Goal:` / `目标:` 行，提取不到时再回退到裁剪后的正文。
    """
    normalized = sanitize_goal_text(str(text or ""))
    if len(normalized) <= max_chars:
        return normalized
    lines = [line.strip() for line in normalized.splitlines() if line.strip()]
    goal_lines = [
        line
        for line in lines
        if re.match(r"^(goal|目标|user_goal)\s*[:：]", line, flags=re.IGNORECASE)
    ]
    compact = "\n".join(dict.fromkeys(goal_lines))
    if compact:
        return compact[:max_chars]
    return normalized[:max_chars]


def _goal_word_tokens(text: str) -> set[str]:
    """
    中文注解：
    - 功能：从原始 goal 中提取更“语义性”的英文/平台词，用来弥补中文长句在轻量意图分析里容易丢平台特征的问题。
    """
    return {token.lower() for token in re.findall(r"[A-Za-z][A-Za-z0-9_-]{1,}", str(text or ""))}


def _looks_like_status_query(text: str) -> bool:
    """
    中文注解：
    - 功能：识别“这更像一句状态追问”而不是新任务目标，避免医生把普通追问误判成目标漂移。
    """
    lowered = _normalize_goal(text)
    if not lowered or len(lowered) > 80:
        return False
    return any(token in lowered for token in STATUS_QUERY_PATTERNS)


def _looks_actionable(text: str, intent: Dict[str, object]) -> bool:
    """
    中文注解：
    - 功能：判断一段最新用户文本是不是足以构成新的动作型目标。
    - 设计意图：只有当“确实像一个可执行新目标”时，才把它和当前 task 做 conformance 检查。
    """
    normalized = str(text or "").strip()
    lowered = normalized.lower()
    if not normalized:
        return False
    if len(normalized) >= 24:
        return True
    if any(token in lowered for token in ACTION_PATTERNS):
        return True
    if any(intent.get(key) for key in ("requires_external_information", "needs_browser", "may_download_artifacts", "may_execute_external_code")):
        return True
    return intent.get("task_types", ["general"]) != ["general"]


def _topic_diverged(current_intent: Dict[str, object], new_intent: Dict[str, object], current_goal: str, new_goal: str) -> bool:
    """
    中文注解：
    - 功能：判断“最新用户目标”和“当前 task 目标”是否已经明显分叉。
    - 设计意图：这里只复用了 route guardrail 的同类思路，让医生判断和路由判断尽量一致，而不是各说各话。
    """
    current_types = _normalize_set(current_intent.get("task_types", []))
    new_types = _normalize_set(new_intent.get("task_types", []))
    current_domains = _normalize_set(current_intent.get("domains", [])) | _normalize_set(current_intent.get("likely_platforms", []))
    new_domains = _normalize_set(new_intent.get("domains", [])) | _normalize_set(new_intent.get("likely_platforms", []))
    current_keywords = _normalize_set(current_intent.get("keywords", []))
    new_keywords = _normalize_set(new_intent.get("keywords", []))

    type_disjoint = bool(current_types and new_types and current_types.isdisjoint(new_types))
    domain_disjoint = bool(current_domains and new_domains and current_domains.isdisjoint(new_domains))
    keyword_disjoint = bool(current_keywords and new_keywords and current_keywords.isdisjoint(new_keywords))
    browser_shift = bool(current_intent.get("needs_browser")) != bool(new_intent.get("needs_browser"))
    external_shift = bool(current_intent.get("requires_external_information")) != bool(new_intent.get("requires_external_information"))
    risk_shift = str(current_intent.get("risk_level", "")).strip() != str(new_intent.get("risk_level", "")).strip()

    current_norm = _normalize_goal(current_goal)
    new_norm = _normalize_goal(new_goal)
    textual_overlap = bool(current_norm and new_norm and (current_norm in new_norm or new_norm in current_norm))
    current_goal_tokens = _goal_word_tokens(current_goal)
    new_goal_tokens = _goal_word_tokens(new_goal)
    goal_token_disjoint = bool(new_goal_tokens and current_goal_tokens.isdisjoint(new_goal_tokens))

    if textual_overlap:
        return False
    if goal_token_disjoint:
        return True
    if new_goal_tokens and not current_goal_tokens:
        return True
    if type_disjoint and (domain_disjoint or browser_shift or external_shift):
        return True
    if type_disjoint and keyword_disjoint and risk_shift:
        return True
    if browser_shift and domain_disjoint and keyword_disjoint:
        return True
    return False


def _extract_text_from_content(content: Any) -> str:
    """
    中文注解：
    - 功能：从 transcript 里的 OpenClaw content 结构提取用户可读文本。
    """
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: List[str] = []
        for item in content:
            if not isinstance(item, dict):
                continue
            if item.get("type") == "text":
                parts.append(str(item.get("text", "")))
        return "\n".join(part for part in parts if part)
    return ""


def _extract_reply_context_goal(text: str) -> Dict[str, str]:
    """
    中文注解：
    - 功能：从 OpenClaw 包装消息里的 `Replied message` 上下文提取被引用的原始目标文本。
    - 设计意图：有些“为什么停了/怎么还没出结果”类追问，本体只是状态追问；
      真正的业务目标却只存在于 reply context 里。这里把那段目标重新抽出来，
      让医生对比的是“真正被追问的目标”，而不是追问句本身。
    """
    raw = str(text or "")
    match = re.search(
        r"Replied message \(untrusted, for context\):\s*```json\s*(\{[\s\S]*?\})\s*```",
        raw,
        flags=re.DOTALL,
    )
    if not match:
        return {}
    try:
        payload = json.loads(match.group(1))
    except json.JSONDecodeError:
        return {}
    body = sanitize_goal_text(str(payload.get("body", "") or ""))
    if not body:
        return {}
    return {
        "text": body,
        "sender_label": str(payload.get("sender_label", "")).strip(),
    }


def _session_file_for_key(session_key: str, *, session_registry: Dict[str, Any] | None = None) -> Path | None:
    """
    中文注解：
    - 功能：根据 session_key 找到 transcript 文件，供医生读取“这条会话最近到底来了什么用户消息”。
    """
    registry = session_registry if isinstance(session_registry, dict) else _read_json(SESSIONS_INDEX_PATH, {})
    session_info = registry.get(session_key, {}) if isinstance(registry, dict) else {}
    session_file = str(session_info.get("sessionFile") or "").strip()
    if not session_file:
        session_id = str(session_info.get("sessionId") or "").strip()
        if session_id:
            session_file = str(SESSIONS_ROOT / f"{session_id}.jsonl")
    if not session_file:
        return None
    path = Path(session_file)
    return path if path.exists() else None


def _is_internal_runtime_request(text: str) -> bool:
    """
    中文注解：
    - 功能：过滤掉 runtime 自己写回 transcript 的内部执行请求，避免把系统内部 prompt 当成用户真实目标。
    """
    normalized = str(text or "").strip()
    return (
        "[Autonomy runtime execution request]" in normalized
        and "task_id:" in normalized
        and "stage:" in normalized
        and "user_goal:" in normalized
    )


def _is_internal_heartbeat_prompt(text: str) -> bool:
    """
    中文注解：
    - 功能：过滤掉 brain/selfheal 注入的 heartbeat 提示，避免它们被医生误当成最新用户目标。
    """
    normalized = str(text or "").strip()
    lowered = normalized.lower()
    return (
        "read heartbeat.md if it exists" in lowered
        and "reply heartbeat_ok" in lowered
    ) or ("current time:" in lowered and "heartbeat.md" in lowered)


def _latest_external_user_message(
    session_key: str,
    *,
    limit: int = 80,
    session_registry: Dict[str, Any] | None = None,
) -> Dict[str, str]:
    """
    中文注解：
    - 功能：读取某条会话最新的外部用户消息，并做 goal 清洗。
    """
    session_file = _session_file_for_key(session_key, session_registry=session_registry)
    if not session_file:
        return {}
    try:
        lines = session_file.read_text(encoding="utf-8", errors="replace").splitlines()[-limit:]
    except OSError:
        return {}
    for raw in reversed(lines):
        try:
            obj = json.loads(raw)
        except json.JSONDecodeError:
            continue
        if obj.get("type") != "message":
            continue
        message = obj.get("message") or {}
        if message.get("role") != "user":
            continue
        text = _extract_text_from_content(message.get("content"))
        cleaned = sanitize_goal_text(text)
        if cleaned and not _is_internal_runtime_request(cleaned) and not _is_internal_heartbeat_prompt(cleaned):
            reply_context = _extract_reply_context_goal(text)
            result = {
                "message_id": str(obj.get("id", "")).strip(),
                "timestamp": str(obj.get("timestamp", "")).strip(),
                "text": cleaned,
            }
            if reply_context:
                result["reply_context_goal"] = str(reply_context.get("text", "")).strip()
                result["reply_context_sender_label"] = str(reply_context.get("sender_label", "")).strip()
            return result
    return {}


def _conversation_links_for_task(task_id: str) -> List[Dict[str, Any]]:
    """
    中文注解：
    - 功能：找到当前 task 绑定过的会话 link。
    - 设计意图：医生需要知道“哪条会话把这个 task 当成当前任务”，才能把最新用户目标和当前执行对象做一致性比对。
    """
    cache_root_mtime_ns: int | None = None
    if LINKS_ROOT.exists():
        try:
            cache_root_mtime_ns = LINKS_ROOT.stat().st_mtime_ns
        except OSError:
            cache_root_mtime_ns = None
    if _CONVERSATION_LINK_INDEX_CACHE.get("root_mtime_ns") != cache_root_mtime_ns:
        rows_by_task: Dict[str, List[Dict[str, Any]]] = {}
        if LINKS_ROOT.exists():
            for path in sorted(LINKS_ROOT.glob("*.json")):
                payload = _read_json(path, {})
                if not payload:
                    continue
                row = dict(payload)
                refs = {
                    str(payload.get("task_id", "")).strip(),
                    str(payload.get("lineage_root_task_id", "")).strip(),
                    str(payload.get("predecessor_task_id", "")).strip(),
                }
                for ref in {item for item in refs if item}:
                    rows_by_task.setdefault(ref, []).append(row)
        _CONVERSATION_LINK_INDEX_CACHE["root_mtime_ns"] = cache_root_mtime_ns
        _CONVERSATION_LINK_INDEX_CACHE["index"] = rows_by_task

    rows: List[Dict[str, Any]] = []
    contract = _read_json(AUTONOMY_TASKS_ROOT / task_id / "contract.json", {})
    metadata = contract.get("metadata", {}) or {}
    related_ids = {
        task_id,
        str(metadata.get("lineage_root_task_id", "")).strip(),
        str(metadata.get("predecessor_task_id", "")).strip(),
    }
    related_ids = {item for item in related_ids if item}
    if not LINKS_ROOT.exists():
        return rows
    seen_rows: set[tuple[str, str, str]] = set()
    index = _CONVERSATION_LINK_INDEX_CACHE.get("index", {}) if isinstance(_CONVERSATION_LINK_INDEX_CACHE.get("index", {}), dict) else {}
    for related_id in related_ids:
        for payload in (index.get(related_id, []) or []):
            signature = (
                str(payload.get("provider", "")).strip(),
                str(payload.get("conversation_id", "")).strip(),
                str(payload.get("task_id", "")).strip(),
            )
            if signature in seen_rows:
                continue
            seen_rows.add(signature)
            rows.append(dict(payload))
    return rows


def _goal_conformance_signal(task_id: str, contract: Dict[str, Any]) -> Dict[str, Any]:
    """
    中文注解：
    - 功能：检查“最新用户目标”是否仍然和当前 task 对得上。
    - 判定来源：
      - link.last_goal / last_message_id
      - 绑定 session 的最新外部用户消息
      - 当前 contract.user_goal
    """
    contract_goal = sanitize_goal_text(str(contract.get("user_goal", "") or ""))
    if not contract_goal:
        return {"ok": True, "reason": "contract_goal_missing"}
    contract_goal_for_analysis = _goal_conformance_analysis_text(contract_goal)
    current_intent = analyze_intent(contract_goal_for_analysis, source="progress_evidence:contract_goal")
    links = _conversation_links_for_task(task_id)
    best_mismatch: Dict[str, Any] = {}
    session_latest_cache: Dict[str, Dict[str, str]] = {}
    candidate_analysis_cache: Dict[str, Dict[str, Any]] = {}
    session_registry = _read_json(SESSIONS_INDEX_PATH, {})
    for link in links:
        conversation_type = str(link.get("conversation_type", "")).strip().lower()
        if conversation_type == "service" or str(link.get("link_kind", "")).strip() == "root_mission_autonomy":
            continue
        session_key = str(link.get("session_key", "")).strip()
        if session_key:
            if session_key not in session_latest_cache:
                session_latest_cache[session_key] = _latest_external_user_message(session_key, session_registry=session_registry)
            latest_from_session = session_latest_cache.get(session_key, {})
        else:
            latest_from_session = {}
        candidates: List[Dict[str, Any]] = []
        last_goal = sanitize_goal_text(str(link.get("last_goal", "") or ""))
        if last_goal:
            candidates.append(
                {
                    "source": "link_last_goal",
                    "text": last_goal,
                    "message_id": str(link.get("last_message_id", "")).strip(),
                    "timestamp": str(link.get("updated_at", "")).strip(),
                }
            )
        if latest_from_session:
            reply_context_goal = sanitize_goal_text(str(latest_from_session.get("reply_context_goal", "") or ""))
            if reply_context_goal:
                candidates.append(
                    {
                        "source": "session_reply_context",
                        "text": reply_context_goal,
                        "message_id": str(latest_from_session.get("message_id", "")).strip(),
                        "timestamp": str(latest_from_session.get("timestamp", "")).strip(),
                    }
                )
            candidates.append(
                {
                    "source": "session_latest_user",
                    "text": sanitize_goal_text(str(latest_from_session.get("text", "") or "")),
                    "message_id": str(latest_from_session.get("message_id", "")).strip(),
                    "timestamp": str(latest_from_session.get("timestamp", "")).strip(),
                }
            )
        for candidate in candidates:
            text = str(candidate.get("text", "")).strip()
            if not text:
                continue
            analysis_text = _goal_conformance_analysis_text(text)
            if not analysis_text:
                continue
            cached_analysis = candidate_analysis_cache.get(analysis_text)
            if cached_analysis is None:
                intent = analyze_intent(analysis_text, source=f"progress_evidence:{candidate.get('source', 'candidate')}")
                actionable = _looks_actionable(text, intent)
                diverged = actionable and _topic_diverged(current_intent, intent, contract_goal_for_analysis, analysis_text)
                cached_analysis = {
                    "intent": intent,
                    "actionable": actionable,
                    "diverged": diverged,
                }
                candidate_analysis_cache[analysis_text] = cached_analysis
            if not cached_analysis.get("actionable"):
                continue
            if not cached_analysis.get("diverged"):
                continue
            mismatch = {
                "ok": False,
                "reason": "latest_user_goal_mismatch_with_bound_task",
                "task_goal": contract_goal,
                "latest_user_goal": text,
                "latest_user_message_id": str(candidate.get("message_id", "")).strip(),
                "latest_user_at": str(candidate.get("timestamp", "")).strip(),
                "provider": str(link.get("provider", "")).strip(),
                "conversation_id": str(link.get("conversation_id", "")).strip(),
                "conversation_type": conversation_type or "direct",
                "session_key": session_key,
                "source": str(candidate.get("source", "")).strip(),
            }
            if not best_mismatch or mismatch.get("latest_user_at", "") >= best_mismatch.get("latest_user_at", ""):
                best_mismatch = mismatch
    return best_mismatch or {"ok": True, "reason": "aligned_with_latest_user_goal"}


def build_progress_evidence(task_id: str, *, stale_after_seconds: int = 300) -> Dict[str, Any]:
    """
    中文注解：
    - 功能：实现 `build_progress_evidence` 对应的处理逻辑。
    - 角色：属于本模块中的对外可见逻辑；私有函数通常服务同文件主流程，公共函数通常作为跨模块入口或能力接口。
    - 调用关系：建议结合本文件的模块说明、调用方以及同名相关辅助函数一起阅读。
    """
    state = _read_json(AUTONOMY_TASKS_ROOT / task_id / "state.json", {})
    contract = _read_json(AUTONOMY_TASKS_ROOT / task_id / "contract.json", {})
    status = str(state.get("status", "unknown"))
    current_stage = str(state.get("current_stage", ""))
    next_action = str(state.get("next_action", ""))
    metadata = state.get("metadata", {}) or {}
    active_execution = metadata.get("active_execution", {}) or {}
    has_active_execution = bool(active_execution.get("run_id"))
    last_progress_at = str(state.get("last_progress_at", ""))
    last_update_at = str(state.get("last_update_at", ""))
    idle_seconds = _progress_age_seconds(
        status=status,
        next_action=next_action,
        last_progress_at=last_progress_at,
        last_update_at=last_update_at,
    )
    business_outcome = metadata.get("business_outcome", {}) or {}
    milestone_stats = metadata.get("milestone_stats", {}) or {}
    business_goal_satisfied = business_outcome.get("goal_satisfied") is True
    user_visible_result_confirmed = business_outcome.get("user_visible_result_confirmed") is True
    if status in {"completed", "failed"}:
        return {
            "task_id": task_id,
            "goal": contract.get("user_goal", ""),
            "status": status,
            "current_stage": current_stage,
            "next_action": next_action,
            "has_active_execution": has_active_execution,
            "active_execution_run_id": str(active_execution.get("run_id", "")),
            "idle_seconds": idle_seconds,
            "stale_after_seconds": stale_after_seconds,
            "recent_event_types": [],
            "business_goal_satisfied": business_goal_satisfied,
            "user_visible_result_confirmed": user_visible_result_confirmed,
            "milestone_stats": milestone_stats,
            "run_liveness": {},
            "task_summary": {},
            "goal_conformance": {"ok": True, "reason": "terminal_state"},
            "progress_state": "terminal",
            "needs_intervention": False,
            "reason": status,
        }
    events = _recent_events(task_id)
    event_types = [str(item.get("type", "")) for item in events if str(item.get("type", "")).strip()]
    run_liveness = build_run_liveness(task_id)
    goal_conformance = _goal_conformance_signal(task_id, contract)
    task_summary = _task_summary(task_id)
    governance_task_summary = _governance_task_summary(task_id)
    if not task_summary and governance_task_summary:
        task_summary = governance_task_summary
    summary_status = str(task_summary.get("status", "")).strip()
    summary_completed_stages = list(task_summary.get("completed_stages", []) or [])
    summary_verification_ok = task_summary.get("verification_ok") is True
    summary_says_completed = (
        summary_status == "completed"
        or (
            summary_verification_ok
            and all(stage in summary_completed_stages for stage in ["understand", "plan", "execute", "verify", "learn"])
        )
    )
    completion_guards = run_liveness.get("completion_guards", {}) or {}
    reanimated_completed = bool(
        summary_says_completed
        and int(completion_guards.get("present_count", 0) or 0) > 0
        and status in {"planning", "running", "recovering", "waiting_external", "verifying"}
    )
    dormant_satisfied = bool(
        int(completion_guards.get("present_count", 0) or 0) > 0
        and business_goal_satisfied
        and user_visible_result_confirmed
        and not has_active_execution
        and status in {"planning", "running", "recovering", "waiting_external", "verifying"}
    )
    satisfied_redundant_dispatch = bool(
        int(completion_guards.get("present_count", 0) or 0) > 0
        and business_goal_satisfied
        and user_visible_result_confirmed
        and bool(milestone_stats.get("all_required_completed"))
        and status in {"planning", "running", "recovering", "waiting_external", "verifying"}
        and current_stage == "plan"
        and (
            next_action.startswith("poll_run:")
            or next_action.startswith("start_stage:plan")
            or status == "waiting_external"
        )
    )

    evidence = {
        "task_id": task_id,
        "goal": contract.get("user_goal", ""),
        "status": status,
        "current_stage": current_stage,
        "next_action": next_action,
        "has_active_execution": has_active_execution,
        "active_execution_run_id": str(active_execution.get("run_id", "")),
        "idle_seconds": idle_seconds,
        "stale_after_seconds": stale_after_seconds,
        "recent_event_types": event_types,
        "business_goal_satisfied": business_goal_satisfied,
        "user_visible_result_confirmed": user_visible_result_confirmed,
        "milestone_stats": milestone_stats,
        "run_liveness": run_liveness,
        "task_summary": {
            "status": summary_status,
            "completed_stages": summary_completed_stages,
            "verification_ok": summary_verification_ok,
        },
        "goal_conformance": goal_conformance,
        "progress_state": "healthy",
        "needs_intervention": False,
        "reason": "healthy",
    }

    if run_liveness.get("orphaned_completed") is True:
        evidence["progress_state"] = "orphaned_completed_task"
        evidence["needs_intervention"] = False
        evidence["reason"] = str(
            run_liveness.get("orphaned_completed_reason")
            or "completed_workspace_guards_with_missing_runtime_state"
        )
        return evidence

    if run_liveness.get("satisfied_waiting_residue") is True:
        evidence["progress_state"] = "satisfied_waiting_residue"
        evidence["needs_intervention"] = True
        evidence["reason"] = str(
            run_liveness.get("satisfied_waiting_residue_reason")
            or "waiting_external_residue_with_satisfied_business_outcome"
        )
        return evidence

    if reanimated_completed:
        evidence["progress_state"] = "reanimated_completed_task"
        evidence["needs_intervention"] = True
        evidence["reason"] = "completed_summary_and_workspace_guards_conflict_with_live_runtime_state"
        return evidence

    if dormant_satisfied:
        evidence["progress_state"] = "satisfied_without_live_execution"
        evidence["needs_intervention"] = True
        evidence["reason"] = "business_outcome_satisfied_and_confirmed_without_live_runtime_execution"
        return evidence

    if satisfied_redundant_dispatch:
        evidence["progress_state"] = "satisfied_redundant_dispatch"
        evidence["needs_intervention"] = True
        evidence["reason"] = "business_outcome_already_satisfied_but_plan_stage_re_dispatched"
        return evidence

    if goal_conformance.get("ok") is False:
        evidence["progress_state"] = "goal_execution_mismatch"
        evidence["needs_intervention"] = True
        evidence["reason"] = str(goal_conformance.get("reason", "latest_user_goal_mismatch_with_bound_task"))
        return evidence

    if status == "waiting_external" and not has_active_execution:
        evidence["progress_state"] = "waiting_external_without_execution"
        evidence["needs_intervention"] = True
        evidence["reason"] = "waiting_external_without_active_execution"
        return evidence

    if status == "waiting_external" and next_action.startswith("poll_run:") and idle_seconds >= stale_after_seconds:
        evidence["progress_state"] = "stalled_waiting_external"
        evidence["needs_intervention"] = True
        evidence["reason"] = "stale_poll_run_without_recent_progress"
        return evidence

    if status in {"planning", "running", "recovering"} and not has_active_execution and idle_seconds >= stale_after_seconds:
        evidence["progress_state"] = "idle_without_execution"
        evidence["needs_intervention"] = True
        evidence["reason"] = "no_active_execution_and_no_recent_progress"
        return evidence

    if status == "blocked":
        evidence["progress_state"] = "blocked"
        evidence["needs_intervention"] = True
        evidence["reason"] = f"blocked:{next_action or 'unknown'}"
        return evidence

    if status == "verifying" and idle_seconds >= stale_after_seconds:
        evidence["progress_state"] = "stalled_verification"
        evidence["needs_intervention"] = True
        evidence["reason"] = "verification_not_advancing"
        return evidence

    return evidence
